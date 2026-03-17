#!/usr/bin/env python3
"""
ttypal — Interactive braille art chatbot companion for your terminal.
Renders anime characters as braille art that follows the mouse.
Uses optical flow warping for smooth transitions between views.
"""

import sys
import os
import time
import random
import signal
import locale
import math
import re
import unicodedata
import argparse
import shutil
import threading
import json
import hashlib

import numpy as np
import cv2

locale.setlocale(locale.LC_ALL, '')

try:
    from PIL import Image, ImageFilter, ImageEnhance
except ImportError:
    print("pip install Pillow"); sys.exit(1)

try:
    from Quartz.CoreGraphics import CGEventGetLocation, CGEventCreate
    HAS_QUARTZ = True
except ImportError:
    HAS_QUARTZ = False

from .config import load_config, needs_setup, run_setup
from .providers import create_provider
from .memory import MemoryManager

_DIR = os.path.dirname(os.path.abspath(__file__))

# ─── ANSI escape sequences ──────────────────────────────

ESC = '\033'
CSI = f'{ESC}['


def mv(x, y):
    return f'{CSI}{y+1};{x+1}H'


def _fg(r, g, b):
    return f'{CSI}38;2;{r};{g};{b}m'


RST = f'{CSI}0m'
BOLD = f'{CSI}1m'
DIM = f'{CSI}2m'
HIDE = f'{CSI}?25l'
SHOW = f'{CSI}?25h'
CLR = f'{CSI}2J'
HOME = f'{CSI}H'
ERASE_LINE = f'{CSI}K'
MOUSE_ON = f'{CSI}?1003h{CSI}?1006h'
MOUSE_OFF = f'{CSI}?1003l{CSI}?1006l'

_ANSI_RE = re.compile(r'\033\[[^m]*m')

# ─── Text utilities ─────────────────────────────────────


def _cw(c):
    """Display width: CJK=2, others=1."""
    return 2 if unicodedata.east_asian_width(c) in ('W', 'F') else 1


def _vis_trunc(s, width):
    """Truncate to `width` visible columns, preserving ANSI codes."""
    vis = 0; i = 0
    while i < len(s) and vis < width:
        m = _ANSI_RE.match(s, i)
        if m:
            i = m.end()
        else:
            cw = _cw(s[i])
            if vis + cw > width:
                break
            vis += cw; i += 1
    return s[:i] + RST


def _wrap(s, width):
    """Wrap string into lines of at most `width` visible columns."""
    result = []
    for paragraph in s.split('\n'):
        cur = ''; vis = 0; i = 0
        while i < len(paragraph):
            m = _ANSI_RE.match(paragraph, i)
            if m:
                cur += m.group(); i = m.end()
            else:
                cw = _cw(paragraph[i])
                if vis + cw > width:
                    result.append(cur + RST)
                    cur = ''; vis = 0
                cur += paragraph[i]; vis += cw; i += 1
        result.append(cur + RST)
    return result or ['']


# ─── Braille conversion ─────────────────────────────────

BRAILLE_BITS = {
    (0, 0): 0, (1, 0): 1, (2, 0): 2, (3, 0): 6,
    (0, 1): 3, (1, 1): 4, (2, 1): 5, (3, 1): 7,
}


def otsu(gray_img):
    hist = gray_img.histogram()
    total = sum(hist)
    if total == 0:
        return 128
    sum_all = sum(i * hist[i] for i in range(256))
    sb = 0; wb = 0; best_v = 0; thr = 128
    for t in range(256):
        wb += hist[t]
        if wb == 0:
            continue
        wf = total - wb
        if wf == 0:
            break
        sb += t * hist[t]
        v = wb * wf * ((sb / wb) - ((sum_all - sb) / wf)) ** 2
        if v > best_v:
            best_v = v; thr = t
    return thr


def to_braille(gray_img, target_w):
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
    for y in range(0, new_h - new_h % 4, 4):
        line = ""
        for x in range(0, tw - tw % 2, 2):
            code = 0
            for row in range(4):
                for col in range(2):
                    if px[x + col, y + row] < thr:
                        code |= (1 << BRAILLE_BITS[(row, col)])
            line += chr(0x2800 + code)
        lines.append(line)
    return lines, tw // 2, new_h // 4


# ─── View position constants ────────────────────────────

_VIEW_POS = {
    'center': (0.0, 0.0),
    'left': (-1.0, 0.0), 'right': (1.0, 0.0),
    'up': (0.0, -1.0), 'down': (0.0, 1.0),
    'left_up': (-1.0, -1.0), 'right_up': (1.0, -1.0),
    'left_down': (-1.0, 1.0), 'right_down': (1.0, 1.0),
    'left_mup': (-1.0, -0.5), 'up_mleft': (-0.5, -1.0),
    'up_mright': (0.5, -1.0), 'right_mup': (1.0, -0.5),
    'right_mdown': (1.0, 0.5), 'down_mright': (0.5, 1.0),
    'down_mleft': (-0.5, 1.0), 'left_mdown': (-1.0, 0.5),
    'center_mleft': (-0.5, 0.0), 'center_mright': (0.5, 0.0),
    'center_mup': (0.0, -0.5), 'center_mdown': (0.0, 0.5),
    'center_mleft_up': (-0.5, -0.5), 'center_mright_up': (0.5, -0.5),
    'center_mleft_down': (-0.5, 0.5), 'center_mright_down': (0.5, 0.5),
}

_GRID_NAMES = [
    ['left_up',    'up',    'right_up'],
    ['left',    'center',      'right'],
    ['left_down',  'down', 'right_down'],
]

_GRID5 = [
    ['left_up',    'up_mleft',          'up',          'up_mright',          'right_up'],
    ['left_mup',   'center_mleft_up',   'center_mup',  'center_mright_up',  'right_mup'],
    ['left',       'center_mleft',      'center',      'center_mright',     'right'],
    ['left_mdown', 'center_mleft_down', 'center_mdown', 'center_mright_down', 'right_mdown'],
    ['left_down',  'down_mleft',        'down',        'down_mright',       'right_down'],
]

_INNER_SYNTH_MAP = {
    'center_mleft_up':   'left_up',
    'center_mup':        'up',
    'center_mright_up':  'right_up',
    'center_mleft':      'left',
    'center_mright':     'right',
    'center_mleft_down': 'left_down',
    'center_mdown':      'down',
    'center_mright_down': 'right_down',
}

# ─── Optical flow (pure functions) ──────────────────────


def _compute_flow(src, dst):
    """Compute dense optical flow from src to dst."""
    s = src.astype(np.uint8)
    d = dst.astype(np.uint8)
    return cv2.calcOpticalFlowFarneback(
        s, d, None,
        pyr_scale=0.5, levels=4, winsize=21,
        iterations=5, poly_n=7, poly_sigma=1.5,
        flags=cv2.OPTFLOW_FARNEBACK_GAUSSIAN,
    )


def _build_grid_edges(views):
    """Build list of adjacent (name_a, name_b) pairs present in views."""
    edges = []
    for r in range(3):
        for c in range(3):
            name = _GRID_NAMES[r][c]
            if name not in views:
                continue
            for dr, dc in [(0, 1), (1, 0), (1, 1), (1, -1)]:
                nr, nc = r + dr, c + dc
                if 0 <= nr < 3 and 0 <= nc < 3:
                    nb = _GRID_NAMES[nr][nc]
                    if nb in views:
                        edges.append((name, nb))
    return edges


# ─── Quartz helper ───────────────────────────────────────


def _quartz_pos():
    pos = CGEventGetLocation(CGEventCreate(None))
    return pos.x, pos.y


# ─── Terminal I/O ────────────────────────────────────────


def _setup_terminal():
    import tty, termios
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    tty.setraw(fd)
    sys.stdout.write(HIDE + CLR + MOUSE_ON)
    sys.stdout.flush()
    return old


def _teardown_terminal(old):
    import termios
    termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old)
    sys.stdout.write(MOUSE_OFF + SHOW + CLR + mv(0, 0) + RST)
    sys.stdout.flush()


_SPINNER = '⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'


def _render_md(text, color_code):
    """Basic markdown: **bold**, `code`, preserve newlines."""
    result = ''
    i = 0
    while i < len(text):
        if text[i:i+2] == '**':
            end = text.find('**', i + 2)
            if end != -1:
                result += BOLD + text[i+2:end] + RST + color_code
                i = end + 2
                continue
        if text[i] == '`' and text[i:i+3] != '```':
            end = text.find('`', i + 1)
            if end != -1:
                result += f'{_fg(180, 200, 160)}{text[i+1:end]}{RST}{color_code}'
                i = end + 1
                continue
        result += text[i]
        i += 1
    return result


def _poll(timeout=0.03):
    import select
    events = []
    fd = sys.stdin.fileno()
    while True:
        r, _, _ = select.select([fd], [], [], timeout)
        if not r:
            break
        timeout = 0
        data = os.read(fd, 4096).decode('utf-8', errors='ignore')
        i = 0
        while i < len(data):
            if data[i] == '\x1b' and i + 1 < len(data) and data[i + 1] == '[':
                if i + 2 < len(data) and data[i + 2] == '<':
                    # SGR mouse event
                    j = i + 3
                    while j < len(data) and data[j] not in ('M', 'm'):
                        j += 1
                    if j < len(data):
                        parts = data[i + 3:j].split(';')
                        if len(parts) == 3:
                            try:
                                events.append(('mouse', int(parts[1]) - 1, int(parts[2]) - 1))
                            except ValueError:
                                pass
                        i = j + 1
                        continue
                # CSI sequences: arrows, page up/down, home/end
                j = i + 2
                seq = ''
                while j < len(data) and not data[j].isalpha() and data[j] != '~':
                    seq += data[j]
                    j += 1
                if j < len(data):
                    ch = data[j]
                    if ch == 'A':
                        events.append(('arrow_up',))
                    elif ch == 'B':
                        events.append(('arrow_down',))
                    elif ch == 'C':
                        events.append(('arrow_right',))
                    elif ch == 'D':
                        events.append(('arrow_left',))
                    elif ch == 'H':
                        events.append(('home',))
                    elif ch == 'F':
                        events.append(('end',))
                    elif ch == '~':
                        if seq == '5':
                            events.append(('page_up',))
                        elif seq == '6':
                            events.append(('page_down',))
                i = j + 1
            elif data[i] == '\x01':  # Ctrl+A
                events.append(('home',)); i += 1
            elif data[i] == '\x05':  # Ctrl+E
                events.append(('end',)); i += 1
            elif data[i] == '\x15':  # Ctrl+U
                events.append(('clear_line',)); i += 1
            elif data[i] == '\x17':  # Ctrl+W
                events.append(('delete_word',)); i += 1
            elif data[i] == '\x03':
                events.append(('quit',)); i += 1
            elif data[i] == '\x1b':
                events.append(('esc',)); i += 1
            elif data[i] in ('\r', '\n'):
                events.append(('enter',)); i += 1
            elif data[i] == '\x7f':
                events.append(('backspace',)); i += 1
            elif data[i] == ' ':
                events.append(('key', ' ')); i += 1
            else:
                events.append(('key', data[i])); i += 1
    return events


# ─── App ─────────────────────────────────────────────────


class App:
    DEAD_ZONE = 0.04
    BLEND_ZONE = 0.06
    MAX_CHAT = 20
    MAX_HISTORY = 20
    CAL_EXPIRE = 0.3
    EMA_ALPHA = 0.3

    def __init__(self, character=None, no_chat=False, views_dir=None, force_setup=False):
        self.character_name = character
        self.character_dir = None
        self.no_chat = no_chat
        self.views_dir_override = views_dir
        self.force_setup = force_setup

        # Views
        self.V = {}
        self.BV = {}
        self.mouth = None
        self.flows = {}
        self.synth = {}
        self.has_blink = False

        # Gaze
        self.gaze_origin_x = 0.5
        self.gaze_origin_y = 0.37
        self.gaze_screen_x = None
        self.gaze_screen_y = None

        # Pane calibration
        self.char_w = 8.0
        self.char_h = 16.0
        self.pane_x0 = None
        self.pane_y0 = None
        self._prev_cal = None
        self._last_term_size = (0, 0)

        # Chat
        self.chat_lock = threading.Lock()
        self.chat_lines = []
        self.chat_speaking = False
        self.chat_streaming = False
        self.chat_history = []
        self.provider = None
        self.memory = None
        self._history_path = None

        # Render cache
        self._braille_cache_key = None
        self._braille_cache = None
        self._mgrid_cache = {}

        # Paths
        self._views_dir = None
        self._cache_path = None

    # ── Bootstrap ────────────────────────────────────────

    def bootstrap(self):
        cfg = self._load_config()
        self._resolve_character(cfg)
        self._load_gaze()
        self._load_views()
        self._init_flows()
        self._init_chat(cfg)
        self._print_status()

    def _print_status(self):
        provider_name = type(self.provider).__name__.replace('Provider', '') if self.provider else 'none'
        mem_mode = 'OpenClaw' if self._provider_manages_memory else 'built-in'
        print(f"  Chat: {provider_name} | Memory: {mem_mode} | Character: {self.character_name}")
        time.sleep(1.5)

    def _load_config(self):
        if self.force_setup:
            return run_setup(force=True)
        elif needs_setup():
            return run_setup()
        else:
            return load_config()

    def _find_character_dir(self, name):
        custom = os.path.join(_DIR, 'characters', 'custom', name)
        if os.path.isdir(custom):
            return custom
        preset = os.path.join(_DIR, 'characters', 'preset', name)
        if os.path.isdir(preset):
            print(f"First use of '{name}' — copying preset to custom...")
            shutil.copytree(preset, custom)
            return custom
        return None

    def _resolve_character(self, cfg):
        if self.views_dir_override:
            self._views_dir = self.views_dir_override
            self.character_dir = os.path.dirname(self._views_dir)
            self.character_name = self.character_name or os.path.basename(self.character_dir)
            return

        if not self.character_name:
            self.character_name = cfg.get('character', 'clawra')

        self.character_dir = self._find_character_dir(self.character_name)
        if not self.character_dir:
            if self.character_name != 'clawra':
                print(f"Character '{self.character_name}' not found, falling back to clawra")
                self.character_name = 'clawra'
                self.character_dir = self._find_character_dir('clawra')
            if not self.character_dir:
                print("No characters found")
                sys.exit(1)

        self._views_dir = os.path.join(self.character_dir, 'views')

    def _load_gaze(self):
        gaze_path = os.path.join(self.character_dir, 'gaze.json')
        if os.path.exists(gaze_path):
            with open(gaze_path) as f:
                gd = json.load(f)
                self.gaze_origin_x = gd.get('gaze_x', self.gaze_origin_x)
                self.gaze_origin_y = gd.get('gaze_y', self.gaze_origin_y)

    def _load_views(self):
        npz_path = os.path.join(self._views_dir, 'views.npz')

        if os.path.exists(npz_path):
            print("Loading views from views.npz...")
            npz = np.load(npz_path)
            for key in npz.files:
                arr = npz[key].astype(np.float32)
                if key.startswith('view_'):
                    self.V[key[5:]] = arr
                elif key.startswith('blink_'):
                    self.BV[key[6:]] = arr
                elif key == 'mouth_center':
                    self.mouth = arr
            npz.close()
            print(f"  {len(self.V)} views, {len(self.BV)} blinks, "
                  f"mouth={'yes' if self.mouth is not None else 'no'}")
        else:
            print("Loading views from PNGs...")
            for name in _VIEW_POS:
                path = os.path.join(self._views_dir, f'view_{name}.png')
                if os.path.exists(path):
                    self.V[name] = np.array(Image.open(path).convert('L'), dtype=np.float32)
            for name in _VIEW_POS:
                path = os.path.join(self._views_dir, f'blink_{name}.png')
                if os.path.exists(path):
                    self.BV[name] = np.array(Image.open(path).convert('L'), dtype=np.float32)
            mouth_path = os.path.join(self._views_dir, 'mouth_center.png')
            if os.path.exists(mouth_path):
                self.mouth = np.array(Image.open(mouth_path).convert('L'), dtype=np.float32)
            print(f"  {len(self.V)} views, {len(self.BV)} blinks")

        assert 'center' in self.V, f"Missing view_center in {self._views_dir}"
        self.has_blink = len(self.BV) > 0
        self._cache_path = os.path.join(self._views_dir, '.flow_cache.npz')

    # ── Optical flow ─────────────────────────────────────

    def _view_fingerprint(self):
        h = hashlib.md5()
        npz_path = os.path.join(self._views_dir, 'views.npz')
        if os.path.exists(npz_path):
            h.update(f"npz:{os.path.getmtime(npz_path):.6f}".encode())
        else:
            for name in sorted(self.V.keys()):
                path = os.path.join(self._views_dir, f'view_{name}.png')
                if os.path.exists(path):
                    h.update(f"{name}:{os.path.getmtime(path):.6f}".encode())
        return h.hexdigest()

    def _load_flow_cache(self):
        """Load flows + synth views from cache (no allow_pickle)."""
        if not os.path.exists(self._cache_path):
            return None
        try:
            data = np.load(self._cache_path)
            fp = str(data['fingerprint'])
            if fp != self._view_fingerprint():
                data.close()
                return None
            # Detect old pickle-based cache format — invalidate it
            if 'flows' in data.files or 'synth' in data.files:
                data.close()
                return None
            flows = {}
            synth = {}
            for key in data.files:
                if key.startswith('flow__'):
                    parts = key[6:].split('__')
                    if len(parts) == 2:
                        flows[(parts[0], parts[1])] = data[key].astype(np.float32)
                elif key.startswith('synth__'):
                    synth[key[7:]] = data[key].astype(np.float32)
            data.close()
            return flows, synth
        except Exception:
            return None

    def _save_flow_cache(self):
        """Save flows + synth views without pickle."""
        arrays = {'fingerprint': np.array(self._view_fingerprint())}
        for (a, b), flow in self.flows.items():
            arrays[f'flow__{a}__{b}'] = flow
        for name, arr in self.synth.items():
            arrays[f'synth__{name}'] = arr
        np.savez_compressed(self._cache_path, **arrays)

    def _init_flows(self):
        cached = self._load_flow_cache()
        if cached:
            print("Loaded optical flows from cache")
            self.flows, self.synth = cached
            return

        # Check if any inner views need synthesis via optical flow
        needs_synth = any(
            inner_name not in self.V and extreme in self.V
            for inner_name, extreme in _INNER_SYNTH_MAP.items()
        )

        if not needs_synth:
            # All views present — no flows needed
            print("All views present, skipping flow computation")
            self._save_flow_cache()
            return

        print("Precomputing optical flows...")
        edges = _build_grid_edges(self.V)
        for a, b in edges:
            self.flows[(a, b)] = _compute_flow(self.V[a], self.V[b])
            self.flows[(b, a)] = _compute_flow(self.V[b], self.V[a])
        print(f"  {len(self.flows)} flow fields computed")

        print("Synthesizing inner views...")
        for inner_name, extreme in _INNER_SYNTH_MAP.items():
            if (inner_name not in self.V
                    and extreme in self.V
                    and ('center', extreme) in self.flows):
                self.synth[inner_name] = self._warp_with_flow(
                    self.V['center'], self.flows[('center', extreme)], 0.5
                )
        print(f"  {len(self.synth)} inner views synthesized")
        self._save_flow_cache()
        print("  Saved to cache")

    def _warp_with_flow(self, img, flow, t):
        """Warp img by flow scaled by t, with cached coordinate grids."""
        h, w = img.shape[:2]
        key = (h, w)
        if key not in self._mgrid_cache:
            gy, gx = np.mgrid[0:h, 0:w].astype(np.float32)
            self._mgrid_cache[key] = (gy, gx)
        gy, gx = self._mgrid_cache[key]
        map_x = gx + flow[:, :, 0] * t
        map_y = gy + flow[:, :, 1] * t
        return cv2.remap(img.astype(np.float32), map_x, map_y,
                         cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)

    # ── View blending ────────────────────────────────────

    def _get5(self, row, col):
        name = _GRID5[row][col]
        if name in self.V:
            return self.V[name]
        if name in self.synth:
            return self.synth[name]
        return self.V['center']

    def _bget5(self, row, col):
        name = _GRID5[row][col]
        if name in self.BV:
            return self.BV[name]
        if name in self.V:
            return self.V[name]
        if name in self.synth:
            return self.synth[name]
        return self.V['center']

    def _grid_blend(self, dx, dy):
        """Bilinear interpolation on 5x5 grid with smoothstep easing."""
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

        v00 = self._get5(cy, cx)
        v10 = self._get5(cy, cx + 1)
        v01 = self._get5(cy + 1, cx)
        v11 = self._get5(cy + 1, cx + 1)

        top = cv2.addWeighted(v00, 1.0 - fx, v10, fx, 0)
        bot = cv2.addWeighted(v01, 1.0 - fx, v11, fx, 0)
        return cv2.addWeighted(top, 1.0 - fy, bot, fy, 0)

    def _blink_blend(self, dx, dy):
        """Blend blink views using 5x5 grid bilinear."""
        if not self.BV:
            return self.V['center']
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

        v00 = self._bget5(cy, cx)
        v10 = self._bget5(cy, cx + 1)
        v01 = self._bget5(cy + 1, cx)
        v11 = self._bget5(cy + 1, cx + 1)

        top = cv2.addWeighted(v00, 1.0 - fx, v10, fx, 0)
        bot = cv2.addWeighted(v01, 1.0 - fx, v11, fx, 0)
        return cv2.addWeighted(top, 1.0 - fy, bot, fy, 0)

    def blend_views(self, dx, dy):
        """Center dead zone + 5x5 grid bilinear outside."""
        dx = max(-1.0, min(1.0, dx))
        dy = max(-1.0, min(1.0, dy))

        dist = math.sqrt(dx * dx + dy * dy)

        if dist < self.DEAD_ZONE:
            return self.V['center']

        grid = self._grid_blend(dx, dy)

        if dist < self.DEAD_ZONE + self.BLEND_ZONE:
            t = (dist - self.DEAD_ZONE) / self.BLEND_ZONE
            t = t * t * (3.0 - 2.0 * t)
            return cv2.addWeighted(self.V['center'], 1.0 - t, grid, t, 0)

        return grid

    def draw_frame(self, dx, dy, blink_t, mouth_t):
        """Generate a frame. blink_t=0..1, mouth_t=0..1."""
        if mouth_t > 0.0 and self.mouth is not None:
            normal = self.blend_views(dx, dy)
            result = cv2.addWeighted(normal, 1.0 - mouth_t, self.mouth, mouth_t, 0)
        else:
            result = self.blend_views(dx, dy)

        if blink_t > 0.0 and self.has_blink:
            blink = self._blink_blend(dx, dy)
            result = cv2.addWeighted(result, 1.0 - blink_t, blink, blink_t, 0)

        return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))

    # ── Mouse tracking ───────────────────────────────────

    def _calibrate(self, col, row, tw, th):
        """Refine pane pixel bounds from terminal mouse events."""
        if not HAS_QUARTZ:
            return
        if (tw, th) != self._last_term_size:
            self._prev_cal = None
            self._last_term_size = (tw, th)
        px, py = _quartz_pos()
        now = time.time()

        if self._prev_cal is not None and (now - self._prev_cal[4]) < self.CAL_EXPIRE:
            dc = col - self._prev_cal[0]
            dr = row - self._prev_cal[1]
            dpx = px - self._prev_cal[2]
            dpy = py - self._prev_cal[3]
            if abs(dc) >= 5:
                new_cw = abs(dpx / dc)
                if 4.0 <= new_cw <= 20.0:
                    self.char_w += self.EMA_ALPHA * (new_cw - self.char_w)
            if abs(dr) >= 5:
                new_ch = abs(dpy / dr)
                if 8.0 <= new_ch <= 40.0:
                    self.char_h += self.EMA_ALPHA * (new_ch - self.char_h)

        new_x0 = px - col * self.char_w
        new_y0 = py - row * self.char_h
        if self.pane_x0 is not None:
            if abs(new_x0 - self.pane_x0) > 50 or abs(new_y0 - self.pane_y0) > 50:
                self.pane_x0 += 0.1 * (new_x0 - self.pane_x0)
                self.pane_y0 += 0.1 * (new_y0 - self.pane_y0)
            else:
                self.pane_x0 += 0.3 * (new_x0 - self.pane_x0)
                self.pane_y0 += 0.3 * (new_y0 - self.pane_y0)
        else:
            self.pane_x0 = new_x0
            self.pane_y0 = new_y0
        self._prev_cal = (col, row, px, py, now)

    def _global_mouse(self, tw, th):
        """Map Quartz global mouse to [-1,1] relative to character's glabella."""
        if self.pane_x0 is None:
            return 0.0, 0.0
        px, py = _quartz_pos()
        if self.gaze_screen_x is not None:
            cx = self.gaze_screen_x
            cy = self.gaze_screen_y
        else:
            cx = self.pane_x0 + tw * self.char_w / 2
            cy = self.pane_y0 + th * self.char_h / 2
        hw = tw * self.char_w / 2
        hh = th * self.char_h / 2
        dx = (px - cx) / hw if hw > 0 else 0.0
        dy = (py - cy) / hh if hh > 0 else 0.0
        return dx, dy

    # ── Chat ─────────────────────────────────────────────

    def _init_chat(self, cfg):
        self.provider = create_provider(cfg)

        # Initialize session for providers that support it (CLI, OpenClaw)
        if self.provider and hasattr(self.provider, 'init_session'):
            self.provider.init_session(self.character_name or 'clawra')

        # If provider manages memory (OpenClaw), skip ttypal's memory system
        self._provider_manages_memory = getattr(
            self.provider, 'manages_memory', False)

        char_dir = self.character_dir or os.path.join(_DIR, 'characters', 'preset', 'clawra')
        if not self._provider_manages_memory:
            self.memory = MemoryManager(
                char_dir,
                provider=self.provider,
                character_name=self.character_name or 'clawra',
            )
            self._history_path = self.memory.history_path
            self._load_history()
        else:
            self.memory = None
            self._history_path = os.path.join(char_dir, '.memory', 'history.json')
            os.makedirs(os.path.dirname(self._history_path), exist_ok=True)
            self._load_history()

    def _load_history(self):
        if not os.path.exists(self._history_path):
            return
        try:
            with open(self._history_path) as f:
                data = json.load(f)
            with self.chat_lock:
                self.chat_history = []
                for d in data:
                    role = d.get("role", "user")
                    if role == "model":
                        role = "assistant"
                    content = d.get("content") or d.get("text", "")
                    self.chat_history.append({"role": role, "content": content})
                if len(self.chat_history) > self.MAX_HISTORY:
                    self.chat_history = self.chat_history[-self.MAX_HISTORY:]
                self.chat_lines = [
                    ("you" if h["role"] == "user" else self.character_name,
                     h["content"], '')
                    for h in self.chat_history
                ]
                if len(self.chat_lines) > self.MAX_CHAT:
                    self.chat_lines = self.chat_lines[-self.MAX_CHAT:]
        except Exception:
            pass

    def _save_history(self):
        try:
            with self.chat_lock:
                data = [
                    {"role": h["role"], "content": h["content"]}
                    for h in self.chat_history
                ]
            with open(self._history_path, 'w') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    @staticmethod
    def _timestamp():
        from datetime import datetime
        return datetime.now().strftime('%H:%M')

    def _send_chat(self, text):
        """Send message via provider with streaming, update chat in real time."""
        ts = self._timestamp()
        with self.chat_lock:
            self.chat_lines.append(('you', text, ts))
            if len(self.chat_lines) > self.MAX_CHAT:
                self.chat_lines.pop(0)
            self.chat_speaking = True
            self.chat_lines.append((self.character_name, '', ts))
            self.chat_history.append({"role": "user", "content": text})

        response_text = ''
        try:
            sys_prompt = self.memory.build_system_prompt() if self.memory else ''
            for chunk in self.provider.stream_chat(
                    self.chat_history, sys_prompt):
                if not self.chat_streaming:
                    with self.chat_lock:
                        self.chat_streaming = True
                response_text += chunk
                with self.chat_lock:
                    self.chat_lines[-1] = (self.character_name, response_text, ts)
        except Exception as e:
            response_text += f' (error: {e})'
            with self.chat_lock:
                self.chat_lines[-1] = (self.character_name, response_text, ts)

        with self.chat_lock:
            self.chat_history.append({"role": "assistant", "content": response_text})
            if len(self.chat_history) > self.MAX_HISTORY:
                dropped = self.chat_history[:-self.MAX_HISTORY]
                self.chat_history[:] = self.chat_history[-self.MAX_HISTORY:]
                if self.memory:
                    threading.Thread(
                        target=self.memory.on_history_compact,
                        args=(dropped,),
                        daemon=True,
                    ).start()

        self._save_history()
        if self.memory:
            self.memory.on_turn_complete(list(self.chat_history))

        with self.chat_lock:
            self.chat_streaming = False
            self.chat_speaking = False

    # ── Main loop ────────────────────────────────────────

    def run(self):
        old = _setup_terminal()
        signal.signal(signal.SIGWINCH, lambda *_: None)
        try:
            self._loop()
        finally:
            if self.memory and self.chat_history and not self._provider_manages_memory:
                with self.chat_lock:
                    history_copy = list(self.chat_history)
                self.memory.on_session_end(history_copy)
            _teardown_terminal(old)

    def _loop(self):
        tw, th = os.get_terminal_size()
        mx, my = tw // 2, th // 2
        head_x = 0.0
        head_y = 0.0

        # Initialize layout vars to avoid NameError on first frame
        ox = tw // 2
        oy = th // 2
        bw = 1
        bh = 1

        # Snap-to-nearest-view when mouse is idle
        last_tgt = (0.0, 0.0)
        idle_since = time.time()
        IDLE_THRESH = 0.3
        SNAP_SPEED = 0.12

        # Blink state
        next_blink = time.time() + random.uniform(2.0, 5.0)
        blink_start = 0.0
        blink_dur = 0.25
        blink_t = 0.0

        # Mouth state
        mouth_t = 0.0
        mouth_cycle = 0.5

        # Chat input
        input_buf = ''
        cursor_pos = 0
        chat_mode = False
        has_chat = self.provider is not None
        scroll_offset = 0  # 0 = bottom (newest), >0 = scrolled up

        color = (210, 210, 220)

        while True:
            for ev in _poll(0.04):
                if ev[0] == 'quit':
                    return
                elif ev[0] == 'esc':
                    if chat_mode:
                        chat_mode = False
                        input_buf = ''
                        cursor_pos = 0
                    else:
                        return
                elif ev[0] == 'key' and ev[1] in 'qQ' and not chat_mode:
                    return
                elif ev[0] == 'mouse':
                    mx, my = ev[1], ev[2]
                    if HAS_QUARTZ:
                        self._calibrate(mx, my, tw, th)
                elif ev[0] == 'enter':
                    if chat_mode and input_buf.strip() and not self.chat_speaking:
                        msg = input_buf.strip()
                        input_buf = ''
                        cursor_pos = 0
                        scroll_offset = 0
                        if has_chat:
                            threading.Thread(
                                target=self._send_chat, args=(msg,), daemon=True
                            ).start()
                        else:
                            with self.chat_lock:
                                self.chat_lines.append(('you', msg, self._timestamp()))
                                self.chat_lines.append(
                                    (self.character_name, '(chat not configured)', self._timestamp()))
                    elif not chat_mode and not self.no_chat:
                        chat_mode = True
                elif ev[0] == 'backspace':
                    if chat_mode and input_buf and cursor_pos > 0:
                        input_buf = input_buf[:cursor_pos-1] + input_buf[cursor_pos:]
                        cursor_pos -= 1
                elif ev[0] == 'arrow_left':
                    if chat_mode and cursor_pos > 0:
                        cursor_pos -= 1
                elif ev[0] == 'arrow_right':
                    if chat_mode and cursor_pos < len(input_buf):
                        cursor_pos += 1
                elif ev[0] == 'home':
                    if chat_mode:
                        cursor_pos = 0
                elif ev[0] == 'end':
                    if chat_mode:
                        cursor_pos = len(input_buf)
                elif ev[0] == 'clear_line':
                    if chat_mode:
                        input_buf = ''
                        cursor_pos = 0
                elif ev[0] == 'delete_word':
                    if chat_mode and cursor_pos > 0:
                        j = cursor_pos - 1
                        while j > 0 and input_buf[j-1] == ' ':
                            j -= 1
                        while j > 0 and input_buf[j-1] != ' ':
                            j -= 1
                        input_buf = input_buf[:j] + input_buf[cursor_pos:]
                        cursor_pos = j
                elif ev[0] == 'arrow_up':
                    if chat_mode and not input_buf:
                        scroll_offset += 1
                elif ev[0] == 'arrow_down':
                    if chat_mode and not input_buf and scroll_offset > 0:
                        scroll_offset -= 1
                elif ev[0] == 'page_up':
                    scroll_offset += 5
                elif ev[0] == 'page_down':
                    scroll_offset = max(0, scroll_offset - 5)
                elif ev[0] == 'key':
                    if chat_mode:
                        input_buf = input_buf[:cursor_pos] + ev[1] + input_buf[cursor_pos:]
                        cursor_pos += 1
                        scroll_offset = 0  # snap to bottom on new input

            tw, th = os.get_terminal_size()
            now = time.time()

            # Mouse tracking
            if HAS_QUARTZ and self.pane_x0 is not None:
                tgt_x, tgt_y = self._global_mouse(tw, th)
            else:
                gcx = ox + bw * self.gaze_origin_x
                gcy = oy + bh * self.gaze_origin_y
                tgt_x = (mx - gcx) / (tw / 2)
                tgt_y = (my - gcy) / (th / 2)
            tgt_x = max(-1.0, min(1.0, tgt_x))
            tgt_y = max(-1.0, min(1.0, tgt_y))

            # Lock head to center while speaking
            if self.chat_speaking:
                tgt_x = 0.0
                tgt_y = 0.0

            # Detect mouse idle → snap to nearest view
            if abs(tgt_x - last_tgt[0]) > 0.02 or abs(tgt_y - last_tgt[1]) > 0.02:
                idle_since = now
                last_tgt = (tgt_x, tgt_y)

            if now - idle_since > IDLE_THRESH:
                best_name = 'center'
                best_dist = tgt_x ** 2 + tgt_y ** 2
                for vname, (vx, vy) in _VIEW_POS.items():
                    if vname not in self.V and vname not in self.synth:
                        continue
                    d = (tgt_x - vx) ** 2 + (tgt_y - vy) ** 2
                    if d < best_dist:
                        best_dist = d
                        best_name = vname
                snap_x, snap_y = _VIEW_POS[best_name]
                head_x += (snap_x - head_x) * SNAP_SPEED
                head_y += (snap_y - head_y) * SNAP_SPEED
            else:
                head_x += (tgt_x - head_x) * 0.18
                head_y += (tgt_y - head_y) * 0.18

            # Layout
            chat_rows = 0 if self.no_chat else max(8, th // 3)
            avail_h = th - 4 - chat_rows
            tw_fit = tw * 2
            th_fit = int(avail_h * 4 / 0.75)
            target_w = min(tw_fit, th_fit)
            target_w = max(40, (target_w // 2) * 2)

            # Blink timing
            if self.has_blink and now >= next_blink and blink_start == 0.0:
                blink_start = now
            if blink_start > 0.0:
                elapsed = now - blink_start
                if elapsed < blink_dur:
                    half = blink_dur / 2
                    blink_t = elapsed / half if elapsed < half else (blink_dur - elapsed) / half
                else:
                    blink_t = 0.0
                    blink_start = 0.0
                    next_blink = now + random.uniform(2.0, 5.0)

            # Mouth animation (triangle wave while streaming only)
            if self.chat_streaming and self.mouth is not None:
                phase = (now % mouth_cycle) / mouth_cycle
                mouth_t = phase * 2 if phase < 0.5 else (1.0 - phase) * 2
            else:
                mouth_t *= 0.7
                if mouth_t < 0.01:
                    mouth_t = 0.0

            # Braille rendering (cached when unchanged)
            cache_key = (round(head_x, 2), round(head_y, 2),
                         round(blink_t, 1), round(mouth_t, 1), target_w)
            if cache_key == self._braille_cache_key and self._braille_cache is not None:
                lines, bw, bh = self._braille_cache
            else:
                frame = self.draw_frame(head_x, head_y, blink_t, mouth_t)
                lines, bw, bh = to_braille(frame, target_w)
                self._braille_cache_key = cache_key
                self._braille_cache = (lines, bw, bh)

            ox = max(0, (tw - bw) // 2)
            oy = max(1, (th - bh - chat_rows) // 2)

            # Update gaze origin to character's glabella position on screen
            if self.pane_x0 is not None:
                self.gaze_screen_x = (
                    self.pane_x0 + (ox + bw * self.gaze_origin_x) * self.char_w)
                self.gaze_screen_y = (
                    self.pane_y0 + (oy + bh * self.gaze_origin_y) * self.char_h)

            # ── Build frame buffer (HOME + per-line erase, no full CLR) ──
            buf = [HOME]

            # Clear rows above title
            for y in range(max(0, oy - 1)):
                buf.append(mv(0, y) + ERASE_LINE)

            # Title
            title_text = ' '.join(self.character_name.upper())
            title_len = len(title_text) + 4
            title = f"{_fg(255, 100, 160)}{BOLD}  {title_text}  {RST}"
            title_y = max(0, oy - 1)
            buf.append(mv(max(0, (tw - title_len) // 2), title_y) + title + ERASE_LINE)

            # Art
            fc = _fg(*color)
            art_end = oy + len(lines)
            for ri, line in enumerate(lines):
                y = oy + ri
                if 0 <= y < th:
                    buf.append(mv(0, y) + ERASE_LINE + mv(ox, y) + fc + line)
            buf.append(RST)

            if not self.no_chat:
                # Clear gap between art and chat
                chat_y = th - chat_rows
                for y in range(art_end, chat_y):
                    buf.append(mv(0, y) + ERASE_LINE)

                # Chat separator with provider label
                chat_label = (type(self.provider).__name__.replace('Provider', '').lower()
                              if self.provider else '')
                sep_left = f"─── Chat "
                sep_right = f" [{chat_label}] ───" if chat_label else " ───"
                sep_fill = '─' * max(0, tw - len(sep_left) - len(sep_right))
                buf.append(mv(0, chat_y)
                           + f"{_fg(80, 80, 90)}{sep_left}{sep_fill}{sep_right}{RST}")

                # Chat messages with improved formatting
                with self.chat_lock:
                    snapshot = list(self.chat_lines)
                cw = tw - 4  # margins
                disp = []

                for idx, (speaker, text, *rest) in enumerate(snapshot):
                    ts = rest[0] if rest else ''
                    is_char = speaker != 'you'

                    # Speaker header with timestamp
                    if is_char:
                        name_str = (f" {_fg(255, 100, 160)}{BOLD}"
                                    f"{self.character_name.capitalize()}{RST}")
                        clr = _fg(255, 100, 160)
                    else:
                        name_str = f" {_fg(120, 180, 235)}{BOLD}You{RST}"
                        clr = _fg(120, 180, 235)

                    if ts:
                        pad = max(0, cw - len(speaker) - len(ts) - 2)
                        header = f"{clr}┌{RST}{name_str}{' ' * pad}{_fg(60, 60, 70)}{ts}{RST}"
                    else:
                        header = f"{clr}┌{RST}{name_str}"
                    disp.append(header)

                    # Message body with markdown
                    body_color = clr
                    rendered = _render_md(text, body_color)
                    body_lines = _wrap(f"{body_color}{rendered}{RST}", cw)
                    for bl in body_lines:
                        disp.append(f" {_fg(50, 50, 60)}│{RST} {bl}")

                    # Spacing between messages
                    if idx < len(snapshot) - 1:
                        disp.append('')

                # Typing indicator
                if self.chat_speaking and not self.chat_streaming:
                    spin_ch = _SPINNER[int(now * 8) % len(_SPINNER)]
                    disp.append(
                        f" {_fg(255, 100, 160)}┌{RST} "
                        f"{_fg(255, 100, 160)}{BOLD}{self.character_name.capitalize()}{RST} "
                        f"{_fg(100, 100, 110)}is thinking {spin_ch}{RST}")

                # Scroll handling
                max_lines = chat_rows - 2
                total = len(disp)
                scroll_offset = min(scroll_offset, max(0, total - max_lines))
                if scroll_offset > 0:
                    end_idx = total - scroll_offset
                    start_idx = max(0, end_idx - max_lines)
                    vis_lines = disp[start_idx:end_idx]
                else:
                    vis_lines = disp[-max_lines:] if total > max_lines else disp

                for ci in range(max_lines):
                    y = chat_y + 1 + ci
                    if y >= th - 1:
                        break
                    if ci < len(vis_lines):
                        buf.append(mv(1, y) + vis_lines[ci] + ERASE_LINE)
                    else:
                        buf.append(mv(0, y) + ERASE_LINE)

                # Scroll indicator
                if scroll_offset > 0:
                    scroll_hint = f" {_fg(80, 80, 90)}[↑{scroll_offset}]{RST}"
                    buf.append(mv(tw - 6, chat_y) + scroll_hint)

                # Input line with cursor positioning
                input_y = th - 1
                if chat_mode:
                    before = input_buf[:cursor_pos]
                    after = input_buf[cursor_pos:]
                    cursor_ch = "█" if int(now * 3) % 2 == 0 else "▏"
                    prompt_str = (f"{_fg(120, 180, 235)}> {RST}"
                                  f"{before}"
                                  f"{_fg(120, 180, 235)}{cursor_ch}{RST}"
                                  f"{after}")
                    buf.append(mv(0, input_y) + prompt_str + ERASE_LINE)
                else:
                    hint = ("enter:chat  q:quit"
                            + (f"  [{chat_label}]" if has_chat
                               else f"  [{len(self.V)}v+{len(self.BV)}b]"))
                    buf.append(mv(0, input_y)
                               + f"{_fg(80, 80, 90)}{DIM}{hint}{RST}" + ERASE_LINE)
            else:
                # No-chat mode: clear below art, show minimal status
                for y in range(art_end, th - 1):
                    buf.append(mv(0, y) + ERASE_LINE)
                hint = f"q:quit  [{len(self.V)}v+{len(self.BV)}b]"
                buf.append(mv(0, th - 1)
                           + f"{_fg(80, 80, 90)}{DIM}{hint}{RST}" + ERASE_LINE)

            sys.stdout.write(''.join(buf))
            sys.stdout.flush()


# ─── Entry point ─────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description='ttypal — Interactive braille art chatbot companion',
    )
    parser.add_argument('--character', '-c', type=str, default=None,
                        help='Character name (preset or custom)')
    parser.add_argument('--views-dir', type=str, default=None,
                        help='Direct path to views directory')
    parser.add_argument('--setup', action='store_true',
                        help='Re-run the setup wizard')
    parser.add_argument('--no-chat', action='store_true',
                        help='Disable chat panel (art-only mode)')
    args = parser.parse_args()

    app = App(
        character=args.character,
        no_chat=args.no_chat,
        views_dir=args.views_dir,
        force_setup=args.setup,
    )
    app.bootstrap()
    app.run()


if __name__ == '__main__':
    main()
