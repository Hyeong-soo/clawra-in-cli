#!/usr/bin/env python3
"""
setup_views.py — Browser-based interactive view setup tool for ttypal.

Usage:
    python3 setup_views.py [ref1.png ref2.png ...] [--output-dir views_v2] [--port 5111]

Opens a browser UI showing a 5x5 grid of character views.
Generate, review, and regenerate views interactively.
"""

import argparse
import os
import sys
import threading
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed

from flask import Flask, jsonify, request, send_from_directory
from PIL import Image

from .generate_multiview import (
    ALL_VIEW_NAMES,
    INNER_MIDPOINT_VIEWS,
    MIDPOINT_VIEWS,
    VIEW_DEPS,
    VIEW_GEN_INFO,
    VIEWS_9,
    _save_result,
    generate_center,
    generate_mouth_open,
    generate_view,
    get_api_key,
)

try:
    from google import genai
except ImportError:
    print("pip install google-genai")
    sys.exit(1)

# ─── Config ───────────────────────────────────────────────

DEFAULT_MODEL = "gemini-3-pro-image-preview"

# 5x5 grid layout (row-major)
GRID_5x5 = [
    ["left_up",    "up_mleft",          "up",         "up_mright",          "right_up"],
    ["left_mup",   "center_mleft_up",   "center_mup", "center_mright_up",  "right_mup"],
    ["left",       "center_mleft",      "center",     "center_mright",     "right"],
    ["left_mdown", "center_mleft_down", "center_mdown","center_mright_down","right_mdown"],
    ["left_down",  "down_mleft",        "down",       "down_mright",       "right_down"],
]

# ─── App State ────────────────────────────────────────────

app = Flask(__name__)

output_dir = ""
ref_image_paths = []
style_ref_image = None
model_name = DEFAULT_MODEL
client = None

# Per-view status: "missing" | "generating" | "done" | "error"
# Extra slots: blink_* for each view + mouth_center
ALL_SLOTS = ALL_VIEW_NAMES + [f"blink_{n}" for n in ALL_VIEW_NAMES] + ["mouth_center"]
view_status = {name: "missing" for name in ALL_SLOTS}
view_errors = {}

_executor = ThreadPoolExecutor(max_workers=10)


def _update_status_from_disk():
    """Check which views/blinks/mouth exist on disk."""
    for name in ALL_VIEW_NAMES:
        if view_status[name] == "generating":
            continue
        path = os.path.join(output_dir, f"view_{name}.png")
        view_status[name] = "done" if os.path.exists(path) else "missing"
    for name in ALL_VIEW_NAMES:
        bk = f"blink_{name}"
        if view_status[bk] == "generating":
            continue
        path = os.path.join(output_dir, f"blink_{name}.png")
        view_status[bk] = "done" if os.path.exists(path) else "missing"
    if view_status["mouth_center"] != "generating":
        path = os.path.join(output_dir, "mouth_center.png")
        view_status["mouth_center"] = "done" if os.path.exists(path) else "missing"


def _deps_met(view_name):
    """Check if all dependencies for a view are met (exist on disk)."""
    for dep in VIEW_DEPS.get(view_name, []):
        if not os.path.exists(os.path.join(output_dir, f"view_{dep}.png")):
            return False
    return True


def _generate_one(slot_name):
    """Generate a single view/blink/mouth. Called in thread pool."""
    from .generate_multiview import generate_blink_view
    try:
        view_status[slot_name] = "generating"
        view_errors.pop(slot_name, None)

        if slot_name == "center":
            refs = [Image.open(p) for p in ref_image_paths]
            if not refs:
                raise ValueError("No reference images uploaded")
            result = generate_center(client, refs, output_dir, model_name, style_ref=style_ref_image)
        elif slot_name == "mouth_center":
            center_path = os.path.join(output_dir, "view_center.png")
            ref = Image.open(center_path)
            result = generate_mouth_open(client, ref, output_dir, model_name)
        elif slot_name.startswith("blink_"):
            base = slot_name[6:]  # strip "blink_"
            base_path = os.path.join(output_dir, f"view_{base}.png")
            ref = Image.open(base_path)
            result = generate_blink_view(client, ref, base, output_dir, model_name)
        elif slot_name in VIEW_GEN_INFO:
            info = VIEW_GEN_INFO[slot_name]
            center_path = os.path.join(output_dir, "view_center.png")
            ref = Image.open(center_path)
            result = generate_view(client, ref, slot_name, info[1], output_dir, model_name)
        else:
            raise ValueError(f"Unknown slot: {slot_name}")

        if result:
            view_status[slot_name] = "done"
        else:
            view_status[slot_name] = "error"
            view_errors[slot_name] = "Generation failed after retries"
    except Exception as e:
        view_status[slot_name] = "error"
        view_errors[slot_name] = str(e)
        print(f"  [{slot_name}] error: {e}")


# ─── Routes ───────────────────────────────────────────────

@app.route("/")
def index():
    return HTML_PAGE


@app.route("/api/status")
def api_status():
    _update_status_from_disk()
    result = {}
    for name in ALL_VIEW_NAMES:
        result[name] = {
            "status": view_status[name],
            "deps_met": _deps_met(name),
            "deps": VIEW_DEPS.get(name, []),
            "error": view_errors.get(name),
        }
    # Blink + mouth status
    for name in ALL_VIEW_NAMES:
        bk = f"blink_{name}"
        result[bk] = {
            "status": view_status[bk],
            "deps_met": view_status[name] == "done",
            "error": view_errors.get(bk),
        }
    result["mouth_center"] = {
        "status": view_status["mouth_center"],
        "deps_met": view_status["center"] == "done",
        "error": view_errors.get("mouth_center"),
    }
    result["_refs"] = [os.path.basename(p) for p in ref_image_paths]
    return jsonify(result)


@app.route("/api/generate", methods=["POST"])
def api_generate():
    data = request.json
    views = data.get("views", [])
    if not views:
        return jsonify({"error": "No views specified"}), 400

    submitted = []
    for name in views:
        if name not in ALL_SLOTS:
            continue
        if view_status[name] == "generating":
            continue
        # Delete existing file for regeneration
        if name == "mouth_center":
            path = os.path.join(output_dir, "mouth_center.png")
        elif name.startswith("blink_"):
            path = os.path.join(output_dir, f"{name}.png")
        else:
            path = os.path.join(output_dir, f"view_{name}.png")
        if os.path.exists(path):
            os.remove(path)
        _executor.submit(_generate_one, name)
        submitted.append(name)

    return jsonify({"submitted": submitted})


@app.route("/api/generate-all", methods=["POST"])
def api_generate_all():
    """Generate all missing views/blinks/mouth in dependency order, parallel within each phase."""
    _update_status_from_disk()

    # Phase 0: center
    phase0 = ["center"] if view_status["center"] == "missing" else []
    # Phase 1: all other views (all depend only on center)
    phase1 = [n for n in ALL_VIEW_NAMES if n != "center" and view_status[n] == "missing"]
    # Phase 2: mouth + all blinks (depend on their base view)
    phase2 = []
    if view_status["mouth_center"] == "missing":
        phase2.append("mouth_center")
    for n in ALL_VIEW_NAMES:
        bk = f"blink_{n}"
        if view_status[bk] == "missing":
            phase2.append(bk)

    def run_batch(names):
        futures = {_executor.submit(_generate_one, n): n for n in names}
        for f in as_completed(futures):
            try:
                f.result()
            except Exception as e:
                print(f"  batch error: {e}")

    def run_all():
        if phase0:
            run_batch(phase0)
        if phase1:
            run_batch(phase1)
        if phase2:
            run_batch(phase2)

    threading.Thread(target=run_all, daemon=True).start()

    return jsonify({
        "phase0": phase0,
        "phase1": phase1,
        "phase2": phase2,
        "total": len(phase0) + len(phase1) + len(phase2),
    })


@app.route("/api/upload-refs", methods=["POST"])
def api_upload_refs():
    files = request.files.getlist("refs")
    if not files:
        return jsonify({"error": "No files uploaded"}), 400

    refs_dir = os.path.join(output_dir, "_refs")
    os.makedirs(refs_dir, exist_ok=True)

    ref_image_paths.clear()
    for f in files:
        path = os.path.join(refs_dir, f.filename)
        f.save(path)
        ref_image_paths.append(path)

    return jsonify({"refs": [os.path.basename(p) for p in ref_image_paths]})


@app.route("/api/finish", methods=["POST"])
def api_finish():
    """Save gaze origin, pack NPZ, and shut down server."""
    # Save gaze origin
    data = request.get_json(silent=True) or {}
    gaze_x = data.get('gaze_x', 0.5)
    gaze_y = data.get('gaze_y', 0.37)
    char_dir = os.path.dirname(output_dir)  # output_dir is <char>/views
    gaze_path = os.path.join(char_dir, 'gaze.json')
    import json as _j
    with open(gaze_path, 'w') as f:
        _j.dump({'gaze_x': round(gaze_x, 4), 'gaze_y': round(gaze_y, 4)}, f)

    _pack_npz()

    # Schedule shutdown after response is sent
    import signal
    def _shutdown():
        os.kill(os.getpid(), signal.SIGINT)
    threading.Timer(0.5, _shutdown).start()

    npz_path = os.path.join(output_dir, 'views.npz')
    msg = f"✓ Gaze origin saved ({gaze_x:.0%}, {gaze_y:.0%})"
    if os.path.exists(npz_path):
        size_mb = os.path.getsize(npz_path) / (1024 * 1024)
        msg += f" · views.npz ({size_mb:.1f} MB)"
    msg += " · Server stopped. You can close this tab."
    return jsonify({"message": msg})


@app.route("/views/<path:filename>")
def serve_view(filename):
    return send_from_directory(output_dir, filename)


@app.route("/refs/<path:filename>")
def serve_ref(filename):
    refs_dir = os.path.join(output_dir, "_refs")
    return send_from_directory(refs_dir, filename)


# ─── HTML ─────────────────────────────────────────────────

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>ttypal View Setup</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #1a1a2e; color: #e0e0e0; padding: 20px; }
h1 { text-align: center; margin-bottom: 8px; font-size: 24px; color: #fff; }
.subtitle { text-align: center; color: #888; margin-bottom: 20px; font-size: 13px; }

.top-bar { display: flex; justify-content: center; gap: 12px; margin-bottom: 24px; flex-wrap: wrap; }
.top-bar button { padding: 10px 24px; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 600; transition: all 0.2s; }
.btn-generate-all { background: #4361ee; color: #fff; }
.btn-generate-all:hover { background: #3a56d4; }
.btn-generate-all:disabled { background: #555; cursor: not-allowed; }
.btn-finish { background: #2d6a4f; color: #fff; }
.btn-finish:hover { background: #245a42; }

.refs-area { text-align: center; margin-bottom: 20px; }
.refs-area label { display: inline-block; padding: 8px 20px; background: #2d2d44; border: 2px dashed #555; border-radius: 8px; cursor: pointer; font-size: 13px; transition: all 0.2s; }
.refs-area label:hover { border-color: #4361ee; background: #33335a; }
.refs-area input[type=file] { display: none; }
.ref-thumbs { display: flex; justify-content: center; gap: 8px; margin-top: 8px; }
.ref-thumbs img { width: 60px; height: 75px; object-fit: cover; border-radius: 4px; border: 1px solid #444; }

.grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; max-width: 900px; margin: 0 auto; }

.cell { background: #16213e; border-radius: 10px; padding: 8px; text-align: center; position: relative; border: 2px solid transparent; transition: all 0.2s; }
.cell:hover { border-color: #4361ee; }
.cell.status-done { border-color: #2d6a4f; }
.cell.status-generating { border-color: #f4a261; animation: pulse 1.5s infinite; }
.cell.status-error { border-color: #e63946; }
.cell.center-cell { border-color: #4361ee; }

@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.6; } }

.cell-name { font-size: 11px; font-weight: 600; color: #aaa; margin-bottom: 4px; letter-spacing: 0.5px; }
.cell-img-wrap { width: 100%; aspect-ratio: 4/5; background: #0f0f23; border-radius: 6px; overflow: hidden; margin-bottom: 6px; display: flex; align-items: center; justify-content: center; }
.cell-img-wrap img { width: 100%; height: 100%; object-fit: cover; }
.cell-img-wrap .placeholder { color: #444; font-size: 28px; }

.cell-status { font-size: 10px; margin-bottom: 4px; }
.cell-status.s-done { color: #2d6a4f; }
.cell-status.s-generating { color: #f4a261; }
.cell-status.s-error { color: #e63946; }
.cell-status.s-missing { color: #666; }

.cell-btn { padding: 4px 10px; border: none; border-radius: 4px; cursor: pointer; font-size: 11px; font-weight: 600; transition: all 0.15s; }
.cell-btn.gen { background: #4361ee; color: #fff; }
.cell-btn.gen:hover { background: #3a56d4; }
.cell-btn.regen { background: #e76f51; color: #fff; }
.cell-btn.regen:hover { background: #d65a3a; }
.cell-btn:disabled { background: #444; color: #777; cursor: not-allowed; }

.log { max-width: 900px; margin: 24px auto 0; background: #0f0f23; border-radius: 8px; padding: 12px; font-family: 'SF Mono', monospace; font-size: 12px; color: #888; max-height: 150px; overflow-y: auto; }
</style>
</head>
<body>

<h1>ttypal View Setup</h1>
<p class="subtitle">5x5 Multi-View Grid &mdash; Generate, Review, Regenerate</p>

<div class="refs-area">
  <label>
    Upload Reference Images (1-N)
    <input type="file" id="ref-input" multiple accept="image/*">
  </label>
  <div class="ref-thumbs" id="ref-thumbs"></div>
</div>

<div class="top-bar">
  <button class="btn-generate-all" id="btn-gen-all" onclick="generateAll()">Generate All Missing</button>
  <button class="btn-finish" onclick="finish()">Finish &amp; Pack NPZ</button>
</div>

<div class="grid" id="grid"></div>

<div class="extras" id="extras-section" style="max-width:900px;margin:20px auto 0;">
  <h3 style="color:#aaa;font-size:14px;margin-bottom:8px;">Blinks &amp; Mouth</h3>
  <div style="display:flex;flex-wrap:wrap;gap:6px;align-items:center;" id="extras-bar"></div>
</div>

<div class="log" id="log"></div>

<script>
const GRID = GRID_DATA;
const ALL_VIEWS = ALL_VIEWS_DATA;
let statusCache = {};

function log(msg) {
  const el = document.getElementById('log');
  const t = new Date().toLocaleTimeString();
  el.textContent = `[${t}] ${msg}\n` + el.textContent;
}

// Build grid
function buildGrid() {
  const grid = document.getElementById('grid');
  grid.innerHTML = '';
  for (const row of GRID) {
    for (const name of row) {
      const cell = document.createElement('div');
      cell.className = 'cell';
      cell.id = `cell-${name}`;
      if (name === 'center') cell.classList.add('center-cell');
      cell.innerHTML = `
        <div class="cell-name">${name}</div>
        <div class="cell-img-wrap" id="img-${name}">
          <span class="placeholder">?</span>
        </div>
        <div class="cell-status s-missing" id="status-${name}">missing</div>
        <button class="cell-btn gen" id="btn-${name}" onclick="genView('${name}')">Generate</button>
      `;
      grid.appendChild(cell);
    }
  }
}

function updateUI(data) {
  statusCache = data;
  // Update ref thumbs
  const thumbs = document.getElementById('ref-thumbs');
  if (data._refs && data._refs.length > 0) {
    thumbs.innerHTML = data._refs.map(f => `<img src="/refs/${f}" title="${f}">`).join('');
  }

  for (const name of ALL_VIEWS) {
    const info = data[name];
    if (!info) continue;
    const cell = document.getElementById(`cell-${name}`);
    const imgWrap = document.getElementById(`img-${name}`);
    const statusEl = document.getElementById(`status-${name}`);
    const btn = document.getElementById(`btn-${name}`);

    // Status class on cell
    cell.className = 'cell';
    if (name === 'center') cell.classList.add('center-cell');
    cell.classList.add(`status-${info.status}`);

    // Image
    if (info.status === 'done') {
      imgWrap.innerHTML = `<img src="/views/view_${name}.png?t=${Date.now()}" loading="lazy">`;
    } else if (info.status === 'generating') {
      imgWrap.innerHTML = '<span class="placeholder" style="animation:pulse 1s infinite">...</span>';
    } else {
      imgWrap.innerHTML = '<span class="placeholder">?</span>';
    }

    // Status text
    statusEl.className = `cell-status s-${info.status}`;
    let statusText = info.status;
    if (info.error) statusText += `: ${info.error}`;
    if (!info.deps_met && info.status !== 'done') statusText = 'deps not met';
    statusEl.textContent = statusText;

    // Button
    if (info.status === 'done') {
      btn.textContent = 'Regenerate';
      btn.className = 'cell-btn regen';
      btn.disabled = false;
    } else if (info.status === 'generating') {
      btn.textContent = 'Generating...';
      btn.className = 'cell-btn gen';
      btn.disabled = true;
    } else {
      btn.textContent = 'Generate';
      btn.className = 'cell-btn gen';
      btn.disabled = !info.deps_met;
      if (name === 'center') btn.disabled = false; // center can always be generated
    }
  }
  updateExtras(data);
}

async function poll() {
  try {
    const res = await fetch('/api/status');
    const data = await res.json();
    updateUI(data);
  } catch (e) { /* ignore */ }
}

async function genView(name) {
  log(`Generating ${name}...`);
  try {
    const res = await fetch('/api/generate', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({views: [name]})
    });
    const data = await res.json();
    if (data.submitted) log(`Submitted: ${data.submitted.join(', ')}`);
  } catch(e) { log(`Error: ${e}`); }
}

async function generateAll() {
  log('Generating all missing views...');
  document.getElementById('btn-gen-all').disabled = true;
  try {
    const res = await fetch('/api/generate-all', {method: 'POST'});
    const data = await res.json();
    log(`Queued: ${data.total} (views:${data.phase0.length}+${data.phase1.length} blinks+mouth:${data.phase2.length})`);
  } catch(e) { log(`Error: ${e}`); }
  setTimeout(() => { document.getElementById('btn-gen-all').disabled = false; }, 3000);
}

// File upload
document.getElementById('ref-input').addEventListener('change', async (e) => {
  const files = e.target.files;
  if (!files.length) return;
  const fd = new FormData();
  for (const f of files) fd.append('refs', f);
  log(`Uploading ${files.length} reference(s)...`);
  try {
    const res = await fetch('/api/upload-refs', {method: 'POST', body: fd});
    const data = await res.json();
    log(`Uploaded: ${data.refs.join(', ')}`);
    poll();
  } catch(e) { log(`Error: ${e}`); }
});

const EXTRA_SLOTS = ALL_VIEWS.map(n => `blink_${n}`).concat(['mouth_center']);

function buildExtras() {
  const bar = document.getElementById('extras-bar');
  bar.innerHTML = '';
  for (const slot of EXTRA_SLOTS) {
    const chip = document.createElement('span');
    chip.id = `extra-${slot}`;
    chip.style.cssText = 'display:inline-flex;align-items:center;gap:4px;padding:3px 8px;border-radius:4px;font-size:11px;cursor:pointer;background:#16213e;border:1px solid #333;';
    chip.textContent = slot;
    chip.onclick = () => genView(slot);
    bar.appendChild(chip);
  }
}

function updateExtras(data) {
  for (const slot of EXTRA_SLOTS) {
    const chip = document.getElementById(`extra-${slot}`);
    if (!chip) continue;
    const info = data[slot];
    if (!info) continue;
    const colors = {done:'#2d6a4f', generating:'#f4a261', error:'#e63946', missing:'#333'};
    chip.style.borderColor = colors[info.status] || '#333';
    chip.style.color = info.status === 'done' ? '#6abf7b' : info.status === 'generating' ? '#f4a261' : info.status === 'error' ? '#e63946' : '#666';
    chip.title = info.error || info.status;
  }
}

async function finish() {
  // Show gaze origin picker overlay
  const centerImg = `/views/view_center.png?t=${Date.now()}`;
  const overlay = document.createElement('div');
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.9);display:flex;flex-direction:column;align-items:center;justify-content:center;z-index:9999;';
  overlay.innerHTML = `
    <p style="color:#ccc;font-size:18px;margin-bottom:12px">Click between the character's eyes (glabella)</p>
    <div style="position:relative;display:inline-block;cursor:crosshair" id="gaze-wrap">
      <img src="${centerImg}" style="max-height:80vh;border:1px solid #444" id="gaze-img">
      <div id="gaze-marker" style="display:none;position:absolute;width:12px;height:12px;border-radius:50%;border:2px solid #f44;background:rgba(255,68,68,0.4);transform:translate(-50%,-50%);pointer-events:none"></div>
    </div>
    <div style="margin-top:16px;display:flex;gap:12px">
      <button id="gaze-confirm" style="padding:10px 24px;background:#2d6a4f;color:#fff;border:none;border-radius:8px;cursor:pointer;font-size:14px;display:none">Confirm & Finish</button>
      <button onclick="this.closest('div[style*=fixed]').remove()" style="padding:10px 24px;background:#555;color:#fff;border:none;border-radius:8px;cursor:pointer;font-size:14px">Cancel</button>
    </div>`;
  document.body.appendChild(overlay);

  let gazeX = 0.5, gazeY = 0.37;
  const img = document.getElementById('gaze-img');
  const marker = document.getElementById('gaze-marker');
  const confirmBtn = document.getElementById('gaze-confirm');

  img.addEventListener('click', (e) => {
    const rect = img.getBoundingClientRect();
    gazeX = (e.clientX - rect.left) / rect.width;
    gazeY = (e.clientY - rect.top) / rect.height;
    marker.style.left = (gazeX * 100) + '%';
    marker.style.top = (gazeY * 100) + '%';
    marker.style.display = 'block';
    confirmBtn.style.display = 'inline-block';
  });

  confirmBtn.addEventListener('click', async () => {
    overlay.innerHTML = '<p style="color:#6abf7b;font-size:20px">Packing NPZ and shutting down...</p>';
    try {
      const res = await fetch('/api/finish', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({gaze_x: gazeX, gaze_y: gazeY})
      });
      const data = await res.json();
      document.body.innerHTML = `<div style="display:flex;justify-content:center;align-items:center;height:100vh;color:#6abf7b;font-size:24px;font-family:monospace">${data.message}</div>`;
    } catch(e) {}
  });
}

// Init
buildGrid();
buildExtras();
poll();
setInterval(poll, 2000);
</script>
</body>
</html>"""

# Inject grid data into HTML
import json as _json
HTML_PAGE = HTML_PAGE.replace(
    "GRID_DATA",
    _json.dumps(GRID_5x5),
).replace(
    "ALL_VIEWS_DATA",
    _json.dumps(ALL_VIEW_NAMES),
)


# ─── Main ─────────────────────────────────────────────────

def main():
    global output_dir, ref_image_paths, model_name, client, style_ref_image

    _base_dir = os.path.dirname(os.path.abspath(__file__))

    parser = argparse.ArgumentParser(description="Interactive view setup for ttypal")
    parser.add_argument("references", nargs="*", help="Reference image(s) for center generation")
    parser.add_argument("--character", default=None, help="Character name (searches preset/ then custom/)")
    parser.add_argument("--preset", action="store_true", help="Force preset directory (with --character)")
    parser.add_argument("--output-dir", default=None, help="Output directory (overrides --character)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Gemini model (default: {DEFAULT_MODEL})")
    parser.add_argument("--port", type=int, default=5111, help="Server port (default: 5111)")
    parser.add_argument("--style-ref", default=None, help="Style reference image for tonal guidance")
    args = parser.parse_args()

    # Determine character directory and output paths
    char_dir = None
    if args.character:
        subdir = "preset" if args.preset else "custom"
        # Search existing first
        for sd in ("preset", "custom"):
            candidate = os.path.join(_base_dir, "characters", sd, args.character)
            if os.path.isdir(candidate):
                char_dir = candidate
                break
        # Create new if not found
        if not char_dir:
            char_dir = os.path.join(_base_dir, "characters", subdir, args.character)
            os.makedirs(char_dir, exist_ok=True)
            # Create default soul.md
            soul_path = os.path.join(char_dir, "soul.md")
            if not os.path.exists(soul_path):
                default_soul = os.path.join(_base_dir, "characters", "preset", "clawra", "soul.md")
                import shutil as _sh
                if os.path.exists(default_soul):
                    _sh.copy2(default_soul, soul_path)
                else:
                    with open(soul_path, "w") as f:
                        f.write(f"You are {args.character}.\n")

    if args.output_dir:
        output_dir = os.path.abspath(args.output_dir)
    elif char_dir:
        output_dir = os.path.join(char_dir, "views")
    else:
        output_dir = os.path.join(_base_dir, "characters", "preset", "clawra", "views")
    os.makedirs(output_dir, exist_ok=True)
    model_name = args.model

    # Determine refs directory
    if char_dir:
        refs_dir = os.path.join(char_dir, "refs")
    else:
        refs_dir = os.path.join(output_dir, "_refs")
    os.makedirs(refs_dir, exist_ok=True)

    # Reference images from CLI → copy to refs/
    import shutil
    for p in args.references:
        if os.path.exists(p):
            src = os.path.abspath(p)
            dest = os.path.join(refs_dir, os.path.basename(p))
            if src != os.path.abspath(dest):
                shutil.copy2(src, dest)
            ref_image_paths.append(dest)
        else:
            print(f"Warning: {p} not found, skipping")

    # Auto-load existing refs if none provided via CLI
    if not ref_image_paths:
        for f in sorted(os.listdir(refs_dir)):
            if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                ref_image_paths.append(os.path.join(refs_dir, f))
        if ref_image_paths:
            print(f"Loaded {len(ref_image_paths)} existing reference(s) from {refs_dir}")

    # Load style reference if provided
    if args.style_ref and os.path.exists(args.style_ref):
        style_ref_image = Image.open(args.style_ref)
        print(f"Style ref: {args.style_ref}")
    else:
        style_ref_image = None

    # Init Gemini client
    api_key = get_api_key()
    client = genai.Client(api_key=api_key)

    _update_status_from_disk()

    print(f"\n  Output: {output_dir}")
    print(f"  Model:  {model_name}")
    print(f"  Refs:   {len(ref_image_paths)} image(s)")
    views_done = sum(1 for n in ALL_VIEW_NAMES if view_status[n] == 'done')
    blinks_done = sum(1 for n in ALL_VIEW_NAMES if view_status[f'blink_{n}'] == 'done')
    mouth_done = 1 if view_status['mouth_center'] == 'done' else 0
    print(f"  Views:  {views_done}/{len(ALL_VIEW_NAMES)}, Blinks: {blinks_done}/{len(ALL_VIEW_NAMES)}, Mouth: {mouth_done}/1\n")

    # Open browser after short delay
    url = f"http://127.0.0.1:{args.port}"
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    print(f"  Server: {url}")
    print(f"  Press Ctrl+C to stop\n")

    try:
        app.run(host="127.0.0.1", port=args.port, debug=False)
    except KeyboardInterrupt:
        pass
    finally:
        _pack_npz()


_npz_packed = False

def _pack_npz():
    """Pack all generated PNGs into views.npz for fast loading."""
    global _npz_packed
    if _npz_packed:
        return
    _npz_packed = True

    from PIL import Image as _PILImage
    import numpy as _np

    arrays = {}
    count = 0
    for name in ALL_VIEW_NAMES:
        for prefix in ('view_', 'blink_'):
            path = os.path.join(output_dir, f'{prefix}{name}.png')
            if os.path.exists(path):
                arrays[f'{prefix}{name}'] = _np.array(
                    _PILImage.open(path).convert('L'), dtype=_np.uint8)
                count += 1
    mouth_path = os.path.join(output_dir, 'mouth_center.png')
    if os.path.exists(mouth_path):
        arrays['mouth_center'] = _np.array(
            _PILImage.open(mouth_path).convert('L'), dtype=_np.uint8)
        count += 1

    if not arrays:
        print("\n  No views to pack.")
        return

    npz_path = os.path.join(output_dir, 'views.npz')
    _np.savez_compressed(npz_path, **arrays)
    size_mb = os.path.getsize(npz_path) / (1024 * 1024)
    print(f"\n  \033[32m✓\033[0m Packed {count} images → views.npz ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
