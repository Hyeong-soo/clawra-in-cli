#!/usr/bin/env python3
"""
clawra_live.py - Interactive anime Clawra with multi-view interpolation.
Renders braille art that follows the mouse using pre-generated view images.
Uses optical flow warping for smooth transitions between views.
"""

import sys, os, time, random, signal, locale, math, re, unicodedata
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

# Gaze origin: character's glabella (between eyes) in normalized image coords
_GAZE_ORIGIN_X = 0.5   # center horizontally
_GAZE_ORIGIN_Y = 0.37  # ~37% from top (between eyebrows)

# Updated per frame by main loop
_gaze_screen_x = None  # pixel x of glabella on screen
_gaze_screen_y = None  # pixel y of glabella on screen

def _global_mouse(tw, th):
    """Map Quartz global mouse to [-1,1] relative to character's glabella."""
    if _pane_x0 is None:
        return 0.0, 0.0
    px, py = _quartz_pos()
    # Use glabella as origin if available, else fall back to pane center
    if _gaze_screen_x is not None:
        cx = _gaze_screen_x
        cy = _gaze_screen_y
    else:
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

_ANSI_RE = re.compile(r'\033\[[^m]*m')

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
    # Split on newlines first, then wrap each segment
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

# ─── Multi-view image loading ─────────────────────────────

_DIR = os.path.dirname(os.path.abspath(__file__))

# --character <name> to select a character (searches preset/ then custom/)
# --views-dir <path> still works as direct override
_CHARACTER_NAME = None
_CHARACTER_DIR = None

import shutil

def _find_character_dir(name):
    """Find character directory: custom/<name> first, then copy from preset/<name>.

    Preset = read-only template (public on GitHub).
    Custom = user's working copy (created on first use by copying preset).
    """
    custom = os.path.join(_DIR, 'characters', 'custom', name)
    if os.path.isdir(custom):
        return custom

    preset = os.path.join(_DIR, 'characters', 'preset', name)
    if os.path.isdir(preset):
        print(f"First use of '{name}' — copying preset to custom...")
        shutil.copytree(preset, custom)
        return custom

    return None

if '--character' in sys.argv:
    _idx = sys.argv.index('--character')
    if _idx + 1 < len(sys.argv):
        _CHARACTER_NAME = sys.argv[_idx + 1]
        _CHARACTER_DIR = _find_character_dir(_CHARACTER_NAME)
        if not _CHARACTER_DIR:
            print(f"Character '{_CHARACTER_NAME}' not found in characters/preset/ or characters/custom/")
            sys.exit(1)

if _CHARACTER_DIR:
    _VIEWS_DIR = os.path.join(_CHARACTER_DIR, 'views')
elif '--views-dir' in sys.argv:
    _idx = sys.argv.index('--views-dir')
    if _idx + 1 < len(sys.argv):
        _VIEWS_DIR = os.path.abspath(sys.argv[_idx + 1])
else:
    # Default: use clawra (copy from preset if needed)
    _CHARACTER_NAME = 'clawra'
    _CHARACTER_DIR = _find_character_dir('clawra')
    _VIEWS_DIR = os.path.join(_CHARACTER_DIR, 'views')

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
    # 8 inner-ring midpoints (between center and extremes)
    'center_mleft':      (-0.5,  0.0),
    'center_mright':     ( 0.5,  0.0),
    'center_mup':        ( 0.0, -0.5),
    'center_mdown':      ( 0.0,  0.5),
    'center_mleft_up':   (-0.5, -0.5),
    'center_mright_up':  ( 0.5, -0.5),
    'center_mleft_down': (-0.5,  0.5),
    'center_mright_down':( 0.5,  0.5),
}

# 3x3 grid for bilinear fallback (when < 17 views)
_GRID_NAMES = [
    [  'left_up',    'up',    'right_up'],
    [  'left',    'center',      'right'],
    ['left_down',  'down', 'right_down'],
]

# Set of 3x3 grid view names
_GRID_POS_SET = {_GRID_NAMES[r][c] for r in range(3) for c in range(3)}

# ─── View loading: views.npz (cache) or individual PNGs ──

_NPZ_PATH = os.path.join(_VIEWS_DIR, 'views.npz')
_V = {}
_BV = {}
_MOUTH = None

if os.path.exists(_NPZ_PATH):
    print("Loading views from views.npz...")
    _npz = np.load(_NPZ_PATH)
    for key in _npz.files:
        arr = _npz[key].astype(np.float32)
        if key.startswith('view_'):
            _V[key[5:]] = arr
        elif key.startswith('blink_'):
            _BV[key[6:]] = arr
        elif key == 'mouth_center':
            _MOUTH = arr
    _npz.close()
    print(f"  {len(_V)} views, {len(_BV)} blinks, mouth={'yes' if _MOUTH is not None else 'no'}")
else:
    print("Loading views from PNGs...")
    for name in _VIEW_POS:
        path = os.path.join(_VIEWS_DIR, f'view_{name}.png')
        if os.path.exists(path):
            _V[name] = np.array(Image.open(path).convert('L'), dtype=np.float32)
    for name in _VIEW_POS:
        path = os.path.join(_VIEWS_DIR, f'blink_{name}.png')
        if os.path.exists(path):
            _BV[name] = np.array(Image.open(path).convert('L'), dtype=np.float32)
    mouth_path = os.path.join(_VIEWS_DIR, 'mouth_center.png')
    if os.path.exists(mouth_path):
        _MOUTH = np.array(Image.open(mouth_path).convert('L'), dtype=np.float32)
    print(f"  {len(_V)} views, {len(_BV)} blinks")

assert 'center' in _V, f"Missing view_center in {_VIEWS_DIR}"
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
    """Hash of view data to detect changes."""
    import hashlib
    h = hashlib.md5()
    # Use npz mtime if available, else individual PNGs
    if os.path.exists(_NPZ_PATH):
        h.update(f"npz:{os.path.getmtime(_NPZ_PATH):.6f}".encode())
    else:
        for name in sorted(_V.keys()):
            path = os.path.join(_VIEWS_DIR, f'view_{name}.png')
            if os.path.exists(path):
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

# Fallback: synthesize inner views via optical flow if real images don't exist
_INNER_SYNTH_MAP = {
    'center_mleft_up':   'left_up',
    'center_mup':        'up',
    'center_mright_up':  'right_up',
    'center_mleft':      'left',
    'center_mright':     'right',
    'center_mleft_down': 'left_down',
    'center_mdown':      'down',
    'center_mright_down':'right_down',
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

    print("Synthesizing inner views (fallback for missing)...")
    _SYNTH = {}
    for inner_name, extreme in _INNER_SYNTH_MAP.items():
        if inner_name not in _V and extreme in _V and ('center', extreme) in _FLOWS:
            _SYNTH[inner_name] = _warp_with_flow(
                _V['center'], _FLOWS[('center', extreme)], 0.5
            )
    print(f"  {len(_SYNTH)} inner views synthesized")
    _save_cache(_FLOWS, _SYNTH)
    print("  Saved to cache")

# 5x5 grid layout — all named views
_GRID5 = [
    ['left_up',    'up_mleft',          'up',          'up_mright',          'right_up'],
    ['left_mup',   'center_mleft_up',   'center_mup',  'center_mright_up',  'right_mup'],
    ['left',       'center_mleft',      'center',      'center_mright',     'right'],
    ['left_mdown', 'center_mleft_down', 'center_mdown','center_mright_down','right_mdown'],
    ['left_down',  'down_mleft',        'down',        'down_mright',       'right_down'],
]


def _get5(row, col):
    """Get view for 5x5 grid position."""
    name = _GRID5[row][col]
    if name in _V:
        return _V[name]
    # Fallback to synthesized inner view
    if name in _SYNTH:
        return _SYNTH[name]
    return _V['center']


_DEAD_ZONE = 0.12   # show pure center within this radius
_BLEND_ZONE = 0.08  # crossfade from center to grid over this width


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
    name = _GRID5[row][col]
    if name in _BV:
        return _BV[name]
    if name in _V:
        return _V[name]
    if name in _SYNTH:
        return _SYNTH[name]
    return _V['center']


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


def draw_frame(dx=0.0, dy=0.0, blink_t=0.0, mouth_t=0.0):
    """Generate a frame. blink_t=0..1 eye close, mouth_t=0..1 mouth open."""
    if mouth_t > 0.0 and _MOUTH is not None:
        # Speaking: blend toward center + mouth open
        normal = blend_views(dx, dy)
        result = normal * (1.0 - mouth_t) + _MOUTH * mouth_t
    else:
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
            elif data[i] == '\x1b': events.append(('esc',)); i += 1
            elif data[i] == '\r' or data[i] == '\n':
                events.append(('enter',)); i += 1
            elif data[i] == '\x7f':
                events.append(('backspace',)); i += 1
            elif data[i] == ' ': events.append(('key', ' ')); i += 1
            else: events.append(('key', data[i])); i += 1
    return events

# ─── Gemini chat (background thread) ─────────────────────

import threading, json as _json

try:
    from google import genai
    from google.genai import types as _gtypes
    _HAS_GENAI = True
except ImportError:
    _HAS_GENAI = False

_chat_lock = threading.Lock()
_chat_lines = []       # [(speaker, text), ...]
_chat_speaking = False  # True during entire response cycle
_chat_streaming = False # True only while tokens are arriving
_MAX_CHAT = 20

# API key: env var first, then 1Password
_GEMINI_KEY = os.environ.get('GEMINI_API_KEY', '')

# Gemini client
_gemini_client = None
if _HAS_GENAI and _GEMINI_KEY:
    _gemini_client = genai.Client(api_key=_GEMINI_KEY)

# Memory manager (tiered memory system)
from memory import MemoryManager

_char_dir_for_memory = _CHARACTER_DIR or os.path.join(_DIR, 'characters', 'preset', 'clawra')
_memory = MemoryManager(
    _char_dir_for_memory,
    gemini_client=_gemini_client,
    character_name=_CHARACTER_NAME or 'clawra',
)

# Conversation history for Gemini (role: user/model)
_chat_history = []

# Persistent history — stored in <character_dir>/.memory/ alongside memory files
_HISTORY_PATH = _memory.history_path

def _load_history():
    global _chat_history, _chat_lines
    if not os.path.exists(_HISTORY_PATH):
        return
    try:
        with open(_HISTORY_PATH) as f:
            data = _json.load(f)
        _chat_history = [{"role": d["role"], "parts": [{"text": d["text"]}]} for d in data]
        if len(_chat_history) > 20:
            _chat_history = _chat_history[-20:]
        _chat_lines = [("you" if d["role"] == "user" else _CHARACTER_NAME, d["text"]) for d in data]
        if len(_chat_lines) > _MAX_CHAT:
            _chat_lines = _chat_lines[-_MAX_CHAT:]
    except Exception:
        pass

def _save_history():
    try:
        data = [{"role": h["role"], "text": h["parts"][0]["text"]} for h in _chat_history]
        with open(_HISTORY_PATH, 'w') as f:
            _json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

_load_history()

def _send_to_gemini(text):
    """Send message to Gemini with streaming, update chat in real time."""
    global _chat_speaking, _chat_streaming
    with _chat_lock:
        _chat_lines.append(('you', text))
        if len(_chat_lines) > _MAX_CHAT:
            _chat_lines.pop(0)
        _chat_speaking = True
        _chat_lines.append((_CHARACTER_NAME, '...'))
    _chat_history.append({"role": "user", "parts": [{"text": text}]})

    response_text = ''
    try:
        sys_instr = _memory.build_system_prompt()
        config = _gtypes.GenerateContentConfig(
            system_instruction=sys_instr,
            max_output_tokens=2048,
        )
        stream = _gemini_client.models.generate_content_stream(
            model='gemini-3-flash-preview',
            contents=_chat_history,
            config=config,
        )
        for chunk in stream:
            if chunk.text:
                if not _chat_streaming:
                    with _chat_lock:
                        _chat_streaming = True
                # Drip-feed character by character for typing effect
                for ch in chunk.text:
                    response_text += ch
                    with _chat_lock:
                        _chat_lines[-1] = (_CHARACTER_NAME, response_text)
                    time.sleep(0.03)
            # Check if generation was cut short
            if hasattr(chunk, 'candidates') and chunk.candidates:
                fr = getattr(chunk.candidates[0], 'finish_reason', None)
                if fr and str(fr) not in ('STOP', 'FinishReason.STOP', 'None', '0'):
                    response_text += f' [!{fr}]'
                    with _chat_lock:
                        _chat_lines[-1] = (_CHARACTER_NAME, response_text)
    except Exception as e:
        response_text += f' (error: {e})'
        with _chat_lock:
            _chat_lines[-1] = (_CHARACTER_NAME, response_text)

    _chat_history.append({"role": "model", "parts": [{"text": response_text}]})
    # Keep history bounded — summarize dropped messages before discarding
    _MAX_HISTORY = 20  # 10 turns (user + model pairs)
    if len(_chat_history) > _MAX_HISTORY:
        dropped = _chat_history[:-_MAX_HISTORY]
        _chat_history[:] = _chat_history[-_MAX_HISTORY:]
        # Background: summarize compacted messages into diary
        threading.Thread(
            target=_memory.on_history_compact,
            args=(dropped,),
            daemon=True,
        ).start()
    _save_history()
    # Background: extract facts/memories from conversation
    _memory.on_turn_complete(_chat_history)
    with _chat_lock:
        _chat_streaming = False
        _chat_speaking = False

# ─── Main ─────────────────────────────────────────────────

def main():
    old = setup()
    signal.signal(signal.SIGWINCH, lambda *_: None)
    try:
        loop()
    finally:
        # Final memory extraction before exit (synchronous)
        if _memory and _chat_history:
            _memory.on_session_end(_chat_history)
        teardown(old)

def loop():
    global _chat_speaking
    tw, th = os.get_terminal_size()
    mx, my = tw//2, th//2
    head_x = 0.0; head_y = 0.0

    # Snap-to-nearest-view when mouse is idle
    _last_tgt = (0.0, 0.0)
    _idle_since = time.time()
    _IDLE_THRESH = 0.3    # seconds before snapping
    _SNAP_SPEED = 0.12    # easing speed toward snap target

    # Blink state
    next_blink = time.time() + random.uniform(2.0, 5.0)
    blink_start = 0.0
    blink_dur = 0.25
    blink_t = 0.0

    # Mouth state
    mouth_t = 0.0
    mouth_cycle = 0.5  # seconds per open/close cycle

    # Chat input
    input_buf = ''
    chat_mode = False
    has_gemini = _gemini_client is not None

    color = (210, 210, 220)

    while True:
        for ev in poll(0.04):
            if ev[0] == 'quit':
                return
            elif ev[0] == 'esc':
                if chat_mode:
                    chat_mode = False
                    input_buf = ''
                else:
                    return
            elif ev[0] == 'key' and ev[1] in 'qQ' and not chat_mode:
                return
            elif ev[0] == 'mouse':
                mx, my = ev[1], ev[2]
                if HAS_QUARTZ:
                    _calibrate(mx, my, tw, th)
            elif ev[0] == 'enter':
                if chat_mode and input_buf.strip() and not _chat_speaking:
                    msg = input_buf.strip()
                    input_buf = ''
                    if has_gemini:
                        threading.Thread(target=_send_to_gemini, args=(msg,), daemon=True).start()
                    else:
                        with _chat_lock:
                            _chat_lines.append(('you', msg))
                            _chat_lines.append((_CHARACTER_NAME, '(gemini not configured)'))
                elif not chat_mode:
                    chat_mode = True
            elif ev[0] == 'backspace':
                if chat_mode and input_buf:
                    input_buf = input_buf[:-1]
            elif ev[0] == 'key':
                if chat_mode:
                    input_buf += ev[1]

        tw, th = os.get_terminal_size()
        now = time.time()

        # Mouse tracking
        if HAS_QUARTZ and _pane_x0 is not None:
            tgt_x, tgt_y = _global_mouse(tw, th)
        else:
            # Use glabella position in terminal char coords as origin
            try:
                gcx = ox + bw * _GAZE_ORIGIN_X
                gcy = oy + bh * _GAZE_ORIGIN_Y
            except NameError:
                gcx, gcy = tw / 2, th / 2
            tgt_x = (mx - gcx) / (tw / 2)
            tgt_y = (my - gcy) / (th / 2)
        tgt_x = max(-1.0, min(1.0, tgt_x))
        tgt_y = max(-1.0, min(1.0, tgt_y))

        # When speaking, lock head to center (no mouse tracking)
        if _chat_speaking:
            tgt_x = 0.0
            tgt_y = 0.0

        # Detect mouse idle → snap to nearest view
        if abs(tgt_x - _last_tgt[0]) > 0.02 or abs(tgt_y - _last_tgt[1]) > 0.02:
            _idle_since = now
            _last_tgt = (tgt_x, tgt_y)

        if now - _idle_since > _IDLE_THRESH:
            # Find nearest 5x5 grid view position
            best_name = 'center'
            best_dist = tgt_x ** 2 + tgt_y ** 2
            for vname, (vx, vy) in _VIEW_POS.items():
                if vname not in _V and vname not in _SYNTH:
                    continue
                d = (tgt_x - vx) ** 2 + (tgt_y - vy) ** 2
                if d < best_dist:
                    best_dist = d
                    best_name = vname
            snap_x, snap_y = _VIEW_POS[best_name]
            head_x += (snap_x - head_x) * _SNAP_SPEED
            head_y += (snap_y - head_y) * _SNAP_SPEED
        else:
            head_x += (tgt_x - head_x) * 0.18
            head_y += (tgt_y - head_y) * 0.18

        # Fit to terminal (chat area = ~1/3 of terminal height)
        chat_rows = max(8, th // 3)
        avail_h = th - 4 - chat_rows
        tw_fit = tw * 2
        th_fit = int(avail_h * 4 / 0.75)
        target_w = min(tw_fit, th_fit)
        target_w = max(40, (target_w // 2) * 2)

        # Blink timing
        if _HAS_BLINK and now >= next_blink and blink_start == 0.0:
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
        if _chat_streaming and _MOUTH is not None:
            phase = (now % mouth_cycle) / mouth_cycle
            mouth_t = phase * 2 if phase < 0.5 else (1.0 - phase) * 2
        else:
            mouth_t *= 0.7  # fade out

        # Draw frame
        frame = draw_frame(head_x, head_y, blink_t, mouth_t)
        lines, bw, bh = to_braille(frame, target_w)

        ox = max(0, (tw - bw) // 2)
        oy = max(1, (th - bh - chat_rows) // 2)

        # Update gaze origin to character's glabella position on screen
        if _pane_x0 is not None:
            global _gaze_screen_x, _gaze_screen_y
            _gaze_screen_x = _pane_x0 + (ox + bw * _GAZE_ORIGIN_X) * _char_w
            _gaze_screen_y = _pane_y0 + (oy + bh * _GAZE_ORIGIN_Y) * _char_h

        buf = [CLR]

        # Title
        _title_text = ' '.join(_CHARACTER_NAME.upper())
        _title_len = len(_title_text) + 4  # 2 spaces padding each side
        title = f"{_fg(255,100,160)}{BOLD}  {_title_text}  {RST}"
        buf.append(mv(max(0,(tw-_title_len)//2), max(0, oy-1)) + title)

        # Art
        fc = _fg(*color)
        for ri, line in enumerate(lines):
            y = oy + ri
            if 0 <= y < th:
                buf.append(mv(ox, y) + fc + line)
        buf.append(RST)

        # Chat area (bottom of terminal)
        chat_y = th - chat_rows
        buf.append(mv(0, chat_y) + f"{_fg(80,80,90)}{'─' * tw}{RST}")

        with _chat_lock:
            snapshot = list(_chat_lines)
        # Wrap messages into display lines
        cw = tw - 2
        disp = []
        for speaker, text in snapshot:
            if speaker != 'you':
                prefix = f"{_fg(255,100,160)}{BOLD}{_CHARACTER_NAME.capitalize()}:{RST} "
            else:
                prefix = f"{_fg(120,180,235)}You:{RST} "
            wrapped = _wrap(prefix + text, cw)
            disp.extend(wrapped)
        # Show last N lines that fit
        max_lines = chat_rows - 2
        vis_lines = disp[-max_lines:]
        pad = ' ' * cw
        for ci in range(max_lines):
            y = chat_y + 1 + ci
            if y >= th - 1:
                break
            if ci < len(vis_lines):
                buf.append(mv(1, y) + vis_lines[ci])
            else:
                buf.append(mv(1, y) + pad)

        # Input line
        input_y = th - 1
        if chat_mode:
            prompt_str = f"{_fg(120,180,235)}> {RST}{input_buf}"
            cursor = "█" if int(now * 3) % 2 == 0 else " "
            buf.append(mv(0, input_y) + prompt_str + f"{_fg(120,180,235)}{cursor}{RST}")
        else:
            hint = "enter:chat  q:quit" + (f"  [gemini]" if has_gemini else f"  [{len(_V)}v+{len(_BV)}b]")
            buf.append(mv(0, input_y) + f"{_fg(80,80,90)}{DIM}{hint}{RST}")

        sys.stdout.write(''.join(buf))
        sys.stdout.flush()

if __name__ == '__main__':
    main()
