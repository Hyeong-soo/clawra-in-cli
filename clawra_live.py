#!/usr/bin/env python3
"""
clawra_live.py - Interactive anime Clawra with multi-view interpolation.
Renders braille art that follows the mouse using pre-generated view images.
Uses optical flow warping for smooth transitions between views.
"""

import sys, os, time, random, signal, locale, math
import numpy as np
import cv2
locale.setlocale(locale.LC_ALL, '')

try:
    from PIL import Image
except ImportError:
    print("pip install Pillow"); sys.exit(1)

try:
    from Quartz.CoreGraphics import CGEventGetLocation, CGEventCreate
    HAS_QUARTZ = True
except ImportError:
    HAS_QUARTZ = False

# ─── Pane calibration: maps terminal char coords ↔ screen pixels ──

_char_w = 8.0    # estimated char width in pixels
_char_h = 16.0   # estimated char height in pixels
_pane_x0 = None  # pixel x of terminal pane (0,0) corner
_pane_y0 = None
_prev_cal = None  # (col, row, px, py, time) for two-point calibration
_last_term_size = (0, 0)
_CAL_EXPIRE = 0.3   # discard stale reference after this many seconds
_EMA_ALPHA = 0.3

def _quartz_pos():
    pos = CGEventGetLocation(CGEventCreate(None))
    return pos.x, pos.y

def _calibrate(col, row, tw, th):
    """Called on every terminal mouse event to refine pane pixel bounds."""
    global _char_w, _char_h, _pane_x0, _pane_y0, _prev_cal, _last_term_size
    if not HAS_QUARTZ:
        return
    if (tw, th) != _last_term_size:
        _prev_cal = None
        _last_term_size = (tw, th)
    px, py = _quartz_pos()
    now = time.time()
    if _prev_cal is not None and (now - _prev_cal[4]) < _CAL_EXPIRE:
        dc = col - _prev_cal[0]
        dr = row - _prev_cal[1]
        dpx = px - _prev_cal[2]
        dpy = py - _prev_cal[3]
        if abs(dc) >= 5:
            new_cw = abs(dpx / dc)
            if 4.0 <= new_cw <= 20.0:
                _char_w += _EMA_ALPHA * (new_cw - _char_w)
        if abs(dr) >= 5:
            new_ch = abs(dpy / dr)
            if 8.0 <= new_ch <= 40.0:
                _char_h += _EMA_ALPHA * (new_ch - _char_h)
    new_x0 = px - col * _char_w
    new_y0 = py - row * _char_h
    # Reject jumps > 50px from established origin (likely stale/bad data)
    if _pane_x0 is not None:
        if abs(new_x0 - _pane_x0) > 50 or abs(new_y0 - _pane_y0) > 50:
            # Big jump — EMA toward it slowly instead of snapping
            _pane_x0 += 0.1 * (new_x0 - _pane_x0)
            _pane_y0 += 0.1 * (new_y0 - _pane_y0)
        else:
            _pane_x0 += 0.3 * (new_x0 - _pane_x0)
            _pane_y0 += 0.3 * (new_y0 - _pane_y0)
    else:
        _pane_x0 = new_x0
        _pane_y0 = new_y0
    _prev_cal = (col, row, px, py, now)

def _global_mouse(tw, th):
    """Map Quartz global mouse to [-1,1] relative to calibrated pane."""
    if _pane_x0 is None:
        return 0.0, 0.0
    px, py = _quartz_pos()
    cx = _pane_x0 + tw * _char_w / 2
    cy = _pane_y0 + th * _char_h / 2
    hw = tw * _char_w / 2
    hh = th * _char_h / 2
    dx = (px - cx) / hw if hw > 0 else 0.0
    dy = (py - cy) / hh if hh > 0 else 0.0
    return dx, dy

ESC = '\033'; CSI = f'{ESC}['
def mv(x, y): return f'{CSI}{y+1};{x+1}H'
def _fg(r,g,b): return f'{CSI}38;2;{r};{g};{b}m'
RST = f'{CSI}0m'; BOLD = f'{CSI}1m'; DIM = f'{CSI}2m'
HIDE = f'{CSI}?25l'; SHOW = f'{CSI}?25h'; CLR = f'{CSI}2J'
MOUSE_ON = f'{CSI}?1003h{CSI}?1006h'
MOUSE_OFF = f'{CSI}?1003l{CSI}?1006l'

# ─── Multi-view image loading ─────────────────────────────

_DIR = os.path.dirname(os.path.abspath(__file__))
_VIEWS_DIR = os.path.join(_DIR, 'views')

def _load_view(name):
    """Load a view image as numpy float32 array."""
    path = os.path.join(_VIEWS_DIR, f'view_{name}.png')
    if os.path.exists(path):
        return np.array(Image.open(path).convert('L'), dtype=np.float32)
    return None

# View positions in (dx, dy) space: dx=-1(left)..+1(right), dy=-1(up)..+1(down)
_VIEW_POS = {
    # 9 extreme views (3x3 grid corners + center)
    'center': (0.0, 0.0),
    'left': (-1.0, 0.0), 'right': (1.0, 0.0),
    'up': (0.0, -1.0), 'down': (0.0, 1.0),
    'left_up': (-1.0, -1.0), 'right_up': (1.0, -1.0),
    'left_down': (-1.0, 1.0), 'right_down': (1.0, 1.0),
    # 8 outer-ring midpoints (between adjacent extremes)
    'left_mup':    (-1.0, -0.5),   # between left and left_up
    'up_mleft':    (-0.5, -1.0),   # between up and left_up
    'up_mright':   (0.5, -1.0),    # between up and right_up
    'right_mup':   (1.0, -0.5),    # between right and right_up
    'right_mdown': (1.0, 0.5),     # between right and right_down
    'down_mright': (0.5, 1.0),     # between down and right_down
    'down_mleft':  (-0.5, 1.0),    # between down and left_down
    'left_mdown':  (-1.0, 0.5),    # between left and left_down
}

# 3x3 grid for bilinear fallback (when < 17 views)
_GRID_NAMES = [
    [  'left_up',    'up',    'right_up'],
    [  'left',    'center',      'right'],
    ['left_down',  'down', 'right_down'],
]

# Set of 3x3 grid view names
_GRID_POS_SET = {_GRID_NAMES[r][c] for r in range(3) for c in range(3)}

# Load all available views
_V = {}
for name in _VIEW_POS:
    arr = _load_view(name)
    if arr is not None:
        _V[name] = arr

assert 'center' in _V, f"Missing view_center.png in {_VIEWS_DIR}"

# Load blink (eyes-closed) views for all 17 views
_BV = {}
for name in _VIEW_POS:
    path = os.path.join(_VIEWS_DIR, f'blink_{name}.png')
    if os.path.exists(path):
        _BV[name] = np.array(Image.open(path).convert('L'), dtype=np.float32)

_HAS_BLINK = len(_BV) > 0

# ─── Optical flow precomputation ──────────────────────────

def _compute_flow(src, dst):
    """Compute dense optical flow from src to dst (both float32 arrays)."""
    s = src.astype(np.uint8)
    d = dst.astype(np.uint8)
    flow = cv2.calcOpticalFlowFarneback(
        s, d, None,
        pyr_scale=0.5, levels=4, winsize=21,
        iterations=5, poly_n=7, poly_sigma=1.5,
        flags=cv2.OPTFLOW_FARNEBACK_GAUSSIAN,
    )
    return flow  # shape (H, W, 2)


def _warp_with_flow(img, flow, t):
    """Warp img by flow scaled by t using remap."""
    h, w = img.shape[:2]
    # Create coordinate grids
    gy, gx = np.mgrid[0:h, 0:w].astype(np.float32)
    map_x = gx + flow[:, :, 0] * t
    map_y = gy + flow[:, :, 1] * t
    return cv2.remap(img.astype(np.float32), map_x, map_y,
                     cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


# ─── Optical flow cache ───────────────────────────────────

_CACHE_PATH = os.path.join(_VIEWS_DIR, '.flow_cache.npz')

def _view_fingerprint():
    """Hash of view file mtimes to detect changes."""
    import hashlib
    h = hashlib.md5()
    for name in sorted(_V.keys()):
        path = os.path.join(_VIEWS_DIR, f'view_{name}.png')
        h.update(f"{name}:{os.path.getmtime(path):.6f}".encode())
    return h.hexdigest()

def _load_cache():
    """Try loading flows + synth views from cache. Returns (flows, synth) or None."""
    if not os.path.exists(_CACHE_PATH):
        return None
    try:
        data = np.load(_CACHE_PATH, allow_pickle=True)
        if data['fingerprint'].item() != _view_fingerprint():
            return None
        flows = data['flows'].item()
        synth = data['synth'].item()
        return flows, synth
    except Exception:
        return None

def _save_cache(flows, synth):
    np.savez_compressed(
        _CACHE_PATH,
        fingerprint=np.array(_view_fingerprint()),
        flows=np.array(flows),
        synth=np.array(synth),
    )

# Precompute flows between adjacent grid cells
_GRID_EDGES = []
for r in range(3):
    for c in range(3):
        name = _GRID_NAMES[r][c]
        if name not in _V:
            continue
        if c + 1 < 3:
            nb = _GRID_NAMES[r][c + 1]
            if nb in _V:
                _GRID_EDGES.append((name, nb))
        if r + 1 < 3:
            nb = _GRID_NAMES[r + 1][c]
            if nb in _V:
                _GRID_EDGES.append((name, nb))
        if c + 1 < 3 and r + 1 < 3:
            nb = _GRID_NAMES[r + 1][c + 1]
            if nb in _V:
                _GRID_EDGES.append((name, nb))
        if c - 1 >= 0 and r + 1 < 3:
            nb = _GRID_NAMES[r + 1][c - 1]
            if nb in _V:
                _GRID_EDGES.append((name, nb))

_INNER_SYNTH = {
    (1, 1): 'left_up',    (1, 2): 'up',       (1, 3): 'right_up',
    (2, 1): 'left',                            (2, 3): 'right',
    (3, 1): 'left_down',  (3, 2): 'down',      (3, 3): 'right_down',
}

_cached = _load_cache()
if _cached:
    print("Loaded optical flows from cache")
    _FLOWS, _SYNTH = _cached
else:
    print("Precomputing optical flows...")
    _FLOWS = {}
    for a, b in _GRID_EDGES:
        _FLOWS[(a, b)] = _compute_flow(_V[a], _V[b])
        _FLOWS[(b, a)] = _compute_flow(_V[b], _V[a])
    print(f"  {len(_FLOWS)} flow fields computed")

    print("Synthesizing inner views...")
    _SYNTH = {}
    for (sr, sc), extreme in _INNER_SYNTH.items():
        if extreme in _V and ('center', extreme) in _FLOWS:
            _SYNTH[(sr, sc)] = _warp_with_flow(
                _V['center'], _FLOWS[('center', extreme)], 0.5
            )
    print(f"  {len(_SYNTH)} inner views synthesized")
    _save_cache(_FLOWS, _SYNTH)
    print("  Saved to cache")

# 5x5 grid layout
_GRID5 = [
    ['left_up',    'up_mleft',    'up',     'up_mright',    'right_up'],
    ['left_mup',   (1,1),         (1,2),    (1,3),          'right_mup'],
    ['left',       (2,1),         'center', (2,3),          'right'],
    ['left_mdown', (3,1),         (3,2),    (3,3),          'right_mdown'],
    ['left_down',  'down_mleft',  'down',   'down_mright',  'right_down'],
]


def _get5(row, col):
    """Get view for 5x5 grid position."""
    entry = _GRID5[row][col]
    if isinstance(entry, str):
        if entry in _V:
            return _V[entry]
        return _V['center']
    # Tuple = synthesized inner view
    if entry in _SYNTH:
        return _SYNTH[entry]
    return _V['center']


_DEAD_ZONE = 0.4   # show pure center within this radius
_BLEND_ZONE = 0.15  # crossfade from center to grid over this width


def _grid_blend(dx, dy):
    """Bilinear interpolation on 5x5 grid with smoothstep easing."""
    # Map [-1,1] to [0,4] grid coords
    gx = (dx + 1.0) * 2.0
    gy = (dy + 1.0) * 2.0
    gx = max(0.0, min(4.0, gx))
    gy = max(0.0, min(4.0, gy))

    cx = min(int(gx), 3)
    cy = min(int(gy), 3)

    fx = gx - cx
    fy = gy - cy
    fx = fx * fx * (3.0 - 2.0 * fx)
    fy = fy * fy * (3.0 - 2.0 * fy)

    v00 = _get5(cy, cx)
    v10 = _get5(cy, cx + 1)
    v01 = _get5(cy + 1, cx)
    v11 = _get5(cy + 1, cx + 1)

    top = v00 * (1.0 - fx) + v10 * fx
    bot = v01 * (1.0 - fx) + v11 * fx
    return top * (1.0 - fy) + bot * fy


def blend_views(dx, dy):
    """Center dead zone + 5x5 grid bilinear outside."""
    dx = max(-1.0, min(1.0, dx))
    dy = max(-1.0, min(1.0, dy))

    dist = math.sqrt(dx * dx + dy * dy)

    if dist < _DEAD_ZONE:
        return _V['center']

    grid = _grid_blend(dx, dy)

    if dist < _DEAD_ZONE + _BLEND_ZONE:
        t = (dist - _DEAD_ZONE) / _BLEND_ZONE
        t = t * t * (3.0 - 2.0 * t)
        return _V['center'] * (1.0 - t) + grid * t

    return grid


def _bget5(row, col):
    """Get blink view for 5x5 grid position, falling back to normal view."""
    entry = _GRID5[row][col]
    if isinstance(entry, str):
        return _BV.get(entry, _V.get(entry, _V['center']))
    # Tuple = synthesized inner — use normal synth as fallback
    return _SYNTH.get(entry, _V['center'])


def _blink_blend(dx, dy):
    """Blend blink views using 5x5 grid bilinear (mirrors _grid_blend)."""
    if not _BV:
        return _V['center']
    dx = max(-1.0, min(1.0, dx))
    dy = max(-1.0, min(1.0, dy))

    gx = (dx + 1.0) * 2.0
    gy = (dy + 1.0) * 2.0
    gx = max(0.0, min(4.0, gx))
    gy = max(0.0, min(4.0, gy))

    cx = min(int(gx), 3)
    cy = min(int(gy), 3)

    fx = gx - cx
    fy = gy - cy
    fx = fx * fx * (3.0 - 2.0 * fx)
    fy = fy * fy * (3.0 - 2.0 * fy)

    v00 = _bget5(cy, cx)
    v10 = _bget5(cy, cx + 1)
    v01 = _bget5(cy + 1, cx)
    v11 = _bget5(cy + 1, cx + 1)

    top = v00 * (1.0 - fx) + v10 * fx
    bot = v01 * (1.0 - fx) + v11 * fx
    return top * (1.0 - fy) + bot * fy


def draw_frame(dx=0.0, dy=0.0, blink_t=0.0):
    """Generate a frame. blink_t=0 normal, blink_t=1 fully closed."""
    result = blend_views(dx, dy)
    if blink_t > 0.0 and _HAS_BLINK:
        blink = _blink_blend(dx, dy)
        result = result * (1.0 - blink_t) + blink * blink_t
    return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))


# ─── Braille conversion (bobibo style) ───────────────────

BRAILLE_BITS = {(0,0):0,(1,0):1,(2,0):2,(3,0):6,(0,1):3,(1,1):4,(2,1):5,(3,1):7}

def otsu(gray_img):
    hist = gray_img.histogram()
    total = sum(hist)
    if total == 0: return 128
    sum_all = sum(i * hist[i] for i in range(256))
    sb = 0; wb = 0; mv = 0; thr = 128
    for t in range(256):
        wb += hist[t]
        if wb == 0: continue
        wf = total - wb
        if wf == 0: break
        sb += t * hist[t]
        v = wb * wf * ((sb/wb) - ((sum_all-sb)/wf))**2
        if v > mv: mv = v; thr = t
    return thr

def to_braille(gray_img, target_w):
    from PIL import ImageFilter, ImageEnhance
    w, h = gray_img.size
    ratio = target_w / w
    new_h = int(h * ratio * 0.75)
    new_h = max(4, (new_h // 4) * 4)
    tw = (target_w // 2) * 2

    small = gray_img.resize((tw, new_h), Image.LANCZOS)
    small = small.filter(ImageFilter.SHARPEN)
    small = ImageEnhance.Contrast(small).enhance(1.6)
    thr = otsu(small)
    px = small.load()

    lines = []
    for y in range(0, new_h - new_h%4, 4):
        line = ""
        for x in range(0, tw - tw%2, 2):
            code = 0
            for row in range(4):
                for col in range(2):
                    if px[x+col, y+row] < thr:
                        code |= (1 << BRAILLE_BITS[(row, col)])
            line += chr(0x2800 + code)
        lines.append(line)
    return lines, tw // 2, new_h // 4

# ─── Terminal I/O ─────────────────────────────────────────

def setup():
    import tty, termios
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    tty.setraw(fd)
    sys.stdout.write(HIDE + CLR + MOUSE_ON)
    sys.stdout.flush()
    return old

def teardown(old):
    import termios
    termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old)
    sys.stdout.write(MOUSE_OFF + SHOW + CLR + mv(0,0) + RST)
    sys.stdout.flush()

def poll(timeout=0.03):
    import select
    events = []
    fd = sys.stdin.fileno()
    while True:
        r, _, _ = select.select([fd], [], [], timeout)
        if not r: break
        timeout = 0
        data = os.read(fd, 4096).decode('utf-8', errors='ignore')
        i = 0
        while i < len(data):
            if data[i] == '\x1b' and i+1 < len(data) and data[i+1] == '[':
                if i+2 < len(data) and data[i+2] == '<':
                    j = i + 3
                    while j < len(data) and data[j] not in ('M','m'): j += 1
                    if j < len(data):
                        parts = data[i+3:j].split(';')
                        if len(parts) == 3:
                            try: events.append(('mouse', int(parts[1])-1, int(parts[2])-1))
                            except ValueError: pass
                        i = j + 1; continue
                j = i + 2
                while j < len(data) and not data[j].isalpha() and data[j] != '~': j += 1
                i = j + 1
            elif data[i] == '\x03': events.append(('quit',)); i += 1
            elif data[i] == '\x1b': events.append(('quit',)); i += 1
            elif data[i] == ' ': events.append(('space',)); i += 1
            else: events.append(('key', data[i])); i += 1
    return events

# ─── Main ─────────────────────────────────────────────────

def main():
    old = setup()
    signal.signal(signal.SIGWINCH, lambda *_: None)
    try:
        loop()
    finally:
        teardown(old)

def loop():
    tw, th = os.get_terminal_size()
    mx, my = tw//2, th//2
    head_x = 0.0; head_y = 0.0

    # Blink state
    next_blink = time.time() + random.uniform(2.0, 5.0)
    blink_start = 0.0
    blink_dur = 0.25  # seconds for full blink cycle
    blink_t = 0.0

    color = (210, 210, 220)

    while True:
        for ev in poll(0.04):
            if ev[0] == 'quit' or (ev[0] == 'key' and ev[1] in 'qQ'): return
            elif ev[0] == 'mouse':
                mx, my = ev[1], ev[2]
                if HAS_QUARTZ:
                    _calibrate(mx, my, tw, th)

        tw, th = os.get_terminal_size()

        if HAS_QUARTZ and _pane_x0 is not None:
            tgt_x, tgt_y = _global_mouse(tw, th)
        else:
            tcx, tcy = tw / 2, th / 2
            tgt_x = (mx - tcx) / (tw / 2)
            tgt_y = (my - tcy) / (th / 2)
        tgt_x = max(-1.0, min(1.0, tgt_x))
        tgt_y = max(-1.0, min(1.0, tgt_y))
        head_x += (tgt_x - head_x) * 0.18
        head_y += (tgt_y - head_y) * 0.18

        # Fit to terminal: braille char = 2px wide, 4px tall
        # Each braille char occupies 1 terminal column, 1 terminal row
        # So max braille cols = tw, max braille rows = th - 4 (title+footer)
        # Pixel width = braille_cols * 2, pixel height = braille_rows * 4
        avail_h = th - 4
        # Pick target_w that fits both width and height (keeping aspect 0.75)
        tw_fit = tw * 2  # pixel width from terminal width
        th_fit = int(avail_h * 4 / 0.75)  # pixel width that would fill height
        target_w = min(tw_fit, th_fit)
        target_w = max(40, (target_w // 2) * 2)

        # Blink timing
        now = time.time()
        if _HAS_BLINK and now >= next_blink and blink_start == 0.0:
            blink_start = now
        if blink_start > 0.0:
            elapsed = now - blink_start
            if elapsed < blink_dur:
                # Triangle wave: 0→1→0 over blink_dur
                half = blink_dur / 2
                blink_t = elapsed / half if elapsed < half else (blink_dur - elapsed) / half
            else:
                blink_t = 0.0
                blink_start = 0.0
                next_blink = now + random.uniform(2.0, 5.0)

        # Draw frame via flow-warped multi-view blending
        frame = draw_frame(head_x, head_y, blink_t)

        # Convert to braille
        lines, bw, bh = to_braille(frame, target_w)

        ox = max(0, (tw - bw) // 2)
        oy = max(2, (th - bh) // 2)

        buf = [CLR]

        # Title
        title = f"{_fg(255,100,160)}{BOLD}  C L A W R A  {RST}"
        buf.append(mv(max(0,(tw-17)//2), max(0, oy-2)) + title)

        # Art
        fc = _fg(*color)
        for ri, line in enumerate(lines):
            y = oy + ri
            if 0 <= y < th:
                buf.append(mv(ox, y) + fc + line)
        buf.append(RST)

        # Footer
        views_str = f"{len(_V)}v+{len(_BV)}b"
        info = f"{_fg(120,180,235)}{DIM}q:quit  mouse:look  [{views_str}]{RST}"
        buf.append(mv(max(0,(tw-40)//2), min(th-1, oy+bh+1)) + info)

        sys.stdout.write(''.join(buf))
        sys.stdout.flush()

if __name__ == '__main__':
    main()
