#!/usr/bin/env python3
"""
clawra_art.py - Draw Clawra in your terminal

Usage:
    python clawra_art.py              # Full display (banner + character + info)
    python clawra_art.py --banner     # Logo banner only
    python clawra_art.py --character  # ASCII character art only
    python clawra_art.py --image      # High-quality image conversion (requires Pillow)
    python clawra_art.py --image -w 60  # Custom width for image mode
    python clawra_art.py --pixel      # Pixel art version using half-blocks
    python clawra_art.py --all        # Show everything

Requires: Python 3.6+
Optional: Pillow (pip install Pillow) for --image mode
"""

import sys
import os
import shutil
import argparse
import tempfile
import urllib.request

# ─── ANSI Helpers ────────────────────────────────────────────

RST  = "\033[0m"
BOLD = "\033[1m"
DIM  = "\033[2m"

def fg(r, g, b):
    return f"\033[38;2;{r};{g};{b}m"

def bg(r, g, b):
    return f"\033[48;2;{r};{g};{b}m"

# ─── Color Palette ───────────────────────────────────────────

PINK    = fg(255, 100, 150)
LPINK   = fg(255, 180, 200)
BLUE    = fg(130, 190, 255)
HAIR    = fg(45, 35, 28)
SKIN    = fg(255, 218, 185)
WHITE   = fg(255, 255, 255)
GRAY    = fg(130, 130, 130)
DGRAY   = fg(80, 80, 80)
RED     = fg(255, 80, 100)
CREAM   = fg(250, 245, 238)
EYE_D   = fg(50, 38, 30)
BLUSH   = fg(255, 180, 175)

# ─── Logo Banner ─────────────────────────────────────────────

def banner():
    a = PINK
    return f"""
{a}{BOLD}   ██████╗ ██╗       █████╗  ██╗    ██╗ ██████╗   █████╗
  ██╔════╝ ██║      ██╔══██╗ ██║    ██║ ██╔══██╗ ██╔══██╗
  ██║      ██║      ███████║ ██║ █╗ ██║ ██████╔╝ ███████║
  ██║      ██║      ██╔══██║ ██║███╗██║ ██╔══██╗ ██╔══██║
  ╚██████╗ ███████╗ ██║  ██║ ╚███╔███╔╝ ██║  ██║ ██║  ██║
   ╚═════╝ ╚══════╝ ╚═╝  ╚═╝  ╚══╝╚══╝ ╚═╝  ╚═╝ ╚═╝  ╚═╝{RST}
"""

# ─── ASCII Character Art ────────────────────────────────────

def character_art():
    h  = HAIR
    s  = SKIN
    p  = LPINK
    w  = WHITE
    e  = EYE_D
    b  = BLUSH
    r  = RED
    c  = CREAM
    d  = DGRAY
    g  = GRAY

    lines = [
        f"",
        f"  {h}               /\\          /\\",
        f"  {h}              / {p}·{h} \\        / {p}·{h} \\",
        f"  {h}             / {p}· ·{h} \\      / {p}· ·{h} \\",
        f"  {h}            / {p}· · ·{h} \\    / {p}· · ·{h} \\",
        f"  {h}           / {p}· · · ·{h} \\  / {p}· · · ·{h} \\",
        f"  {h}          /━━━━━━━━━━━━━━━━━━━━━\\",
        f"  {h}         ┃ {g}░░░░░░░░░░░░░░░░░░░{h} ┃",
        f"  {h}        ┃{s} ╭───────────────────╮ {h}┃",
        f"  {h}        ┃{s} │ {h}▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒{s} │ {h}┃",
        f"  {h}        ┃{s} │                     │ {h}┃",
        f"  {h}        ┃{s} │   {w}◕ {e}‿{s}        {w}◕ {e}‿{s}   │ {h}┃",
        f"  {h}        ┃{s} │                     │ {h}┃",
        f"  {h}        ┃{s} │  {b}◜{s}      ▿      {b}◝{s}  │ {h}┃",
        f"  {h}        ┃{s} │                     │ {h}┃",
        f"  {h}        ┃{s} │       {r}╰ ‿ ╯{s}        │ {h}┃",
        f"  {h}        ┃{s} ╰───────────────────╯ {h}┃",
        f"  {h}         ┃{s}                       {h}┃",
        f"  {h}          ┃{s}    ╭──────────╮    {h}┃",
        f"  {h}           ┃{c}   │ {d}◇{c}  ┃┃  {d}◇{c} │   {h}┃",
        f"  {h}            ╲{c}  │    ┃┃    │  {h}╱",
        f"  {h}             ╲{c} └────┸┸────┘ {h}╱",
        f"  {h}              ╲               ╱",
        f"  {h}               ╰─────────────╯",
        f"",
    ]
    return "\n".join(l + RST for l in lines)

# ─── Pixel Art (half-block rendering) ───────────────────────

# Palette for pixel art: char → (R, G, B)
PIXEL_PALETTE = {
    '.': None,                     # transparent
    'H': (40, 32, 25),            # hair dark
    'h': (70, 55, 45),            # hair highlight
    'S': (255, 215, 180),         # skin
    's': (240, 198, 165),         # skin shadow
    'E': (45, 33, 26),            # eye dark
    'W': (255, 255, 255),         # white (eye)
    'w': (220, 230, 255),         # eye highlight
    'B': (255, 178, 172),         # blush
    'M': (235, 108, 128),         # mouth
    'L': (220, 85, 105),          # lip dark
    'C': (248, 244, 240),         # clothing
    'D': (75, 75, 80),            # clothing dark
    'P': (255, 175, 195),         # ear pink
    'N': (245, 200, 175),         # nose
    'K': (255, 255, 255),         # teeth
}

# 26 wide × 34 tall pixel grid  →  26 chars × 17 terminal lines
# Cute chibi girl with cat ears and long dark hair
PIXEL_ROWS = [
    #0         1         2
    #0123456789012345678901234 5
    "......H............H......",  # 0   ear tips
    ".....HH............HH.....",  # 1
    "....HPH............HPH....",  # 2
    "...HPPH............HPPH...",  # 3
    "..HPPHHHHHHHHHHHHHHHPPH...",  # 4   ears meet head
    ".HHHHHHHHHHHHHHHHHHHHHHHH..",  # 5   hair dome
    ".HHHHhHHHHHHHHHHhHHHHHH..",  # 6   highlights
    ".HHHHHHHHHHHHHHHHHHHHHHHH..",  # 7
    ".HHSSSSSSSSSSSSSSSSSSSSHH..",  # 8   forehead
    ".HHsHHhHHHHHHHHHHhHHsHH..",  # 9   bangs
    ".HHsHhHHhHHHHhHHhHHsHH...",  # 10  bangs detail
    ".HHSSSSSSSSSSSSSSSSSSSSHH..",  # 11  face
    ".HHSS.WWEEE..WWEEE.SSSHH..",  # 12  eyes
    ".HHSS.WWEEE..WWEEE.SSSHH..",  # 13  eyes
    ".HHSS.WwEEE..WwEEE.SSSHH..",  # 14  eye highlight
    ".HHSSS.EEE....EEE.SSSSHH..",  # 15  below eyes
    "..HSSB...........BSSSHH...",  # 16  blush
    "..HSSSSS...N...SSSSHH.....",  # 17  nose
    "..HHSSSS.MMMM.SSSSHH.....",  # 18  mouth
    "..HHSSSS.MKKM.SSSHH......",  # 19  teeth
    "...HHSSSSSSSSSSSSHH.......",  # 20  chin
    "...HHHHSSSSSSSSHHHH.......",  # 21
    "....HHH...SS...HHH........",  # 22  neck
    "....HH..SSSSSS..HH........",  # 23
    "...HHH..CCCCCC..HHH.......",  # 24  clothing top
    "..HHHH..CDCDCD..HHHH......",  # 25  clothing pattern
    ".HHHHH.CCCCCCCC.HHHHH.....",  # 26
    "HHHHHH.CCCCCCCC.HHHHHH....",  # 27
    "HHHHH...........HHHHHHH...",  # 28  hair flowing
    "HHHH.............HHHHHH...",  # 29
    "HHH...............HHHHH...",  # 30
    "HH.................HHHH...",  # 31
]

def render_pixel_art(pixel_rows=None, palette=None, indent=4):
    """Render pixel data using half-block characters with true color"""
    if pixel_rows is None:
        pixel_rows = list(PIXEL_ROWS)
    if palette is None:
        palette = PIXEL_PALETTE

    # Normalize all rows to same width
    max_width = max(len(row) for row in pixel_rows)
    pixel_rows = [row.ljust(max_width, '.') for row in pixel_rows]

    # Pad to even number of rows
    if len(pixel_rows) % 2:
        pixel_rows.append('.' * max_width)

    lines = []
    for i in range(0, len(pixel_rows), 2):
        top_row = pixel_rows[i]
        bot_row = pixel_rows[i + 1]

        line = " " * indent
        prev_had_color = False

        for j in range(max_width):
            top_ch = top_row[j] if j < len(top_row) else '.'
            bot_ch = bot_row[j] if j < len(bot_row) else '.'

            top_c = palette.get(top_ch)
            bot_c = palette.get(bot_ch)

            if top_c and bot_c:
                line += fg(*top_c) + bg(*bot_c) + "▀"
                prev_had_color = True
            elif top_c:
                if prev_had_color:
                    line += RST
                line += fg(*top_c) + "▀"
                prev_had_color = True
            elif bot_c:
                if prev_had_color:
                    line += RST
                line += fg(*bot_c) + "▄"
                prev_had_color = True
            else:
                if prev_had_color:
                    line += RST
                    prev_had_color = False
                line += " "

        lines.append(line + RST)

    return "\n".join(lines)

# ─── Image-to-Terminal Converter ─────────────────────────────

CLAWRA_IMG_URL = "https://cdn.jsdelivr.net/gh/SumeLabs/clawra@main/assets/clawra.png"

def download_reference_image():
    """Download the Clawra reference image"""
    path = os.path.join(tempfile.gettempdir(), "clawra_ref.png")
    if not os.path.exists(path):
        try:
            print(f"{GRAY}Downloading reference image...{RST}")
            urllib.request.urlretrieve(CLAWRA_IMG_URL, path)
        except Exception as e:
            print(f"{RED}Download failed: {e}{RST}")
            return None
    return path

def image_to_terminal(img_path, width=50):
    """Convert an image to terminal art using half-block characters with true color"""
    try:
        from PIL import Image
    except ImportError:
        return None

    img = Image.open(img_path).convert('RGBA')

    # Calculate target pixel dimensions
    aspect_ratio = img.height / img.width
    target_w = width
    target_h = int(target_w * aspect_ratio)
    if target_h % 2:
        target_h += 1

    img_resized = img.resize((target_w, target_h), Image.LANCZOS)
    pixels = list(img_resized.getdata())  # returns flat list of (R,G,B,A) tuples

    lines = []
    for y in range(0, target_h, 2):
        line = ""
        for x in range(target_w):
            top_idx = y * target_w + x
            bot_idx = (y + 1) * target_w + x if y + 1 < target_h else None

            tr, tg, tb, ta = pixels[top_idx]
            if bot_idx is not None and bot_idx < len(pixels):
                br, bg_r, bb, ba = pixels[bot_idx]
            else:
                br, bg_r, bb, ba = 0, 0, 0, 0

            top_vis = ta > 128
            bot_vis = ba > 128

            if top_vis and bot_vis:
                line += fg(tr, tg, tb) + bg(br, bg_r, bb) + "▀"
            elif top_vis:
                line += fg(tr, tg, tb) + "▀"
            elif bot_vis:
                line += fg(br, bg_r, bb) + "▄"
            else:
                line += " "

        lines.append(line + RST)

    return "\n".join(lines)

# ─── Braille Art Converter ───────────────────────────────────

def image_to_braille(img_path, width=60):
    """Convert image to braille characters with true color (higher detail)"""
    try:
        from PIL import Image
    except ImportError:
        return None

    img = Image.open(img_path).convert('RGBA')

    # Braille character = 2 wide × 4 tall dots
    pixel_w = width * 2
    aspect_ratio = img.height / img.width
    pixel_h = int(pixel_w * aspect_ratio)
    pixel_h = (pixel_h // 4) * 4  # round to multiple of 4

    img_resized = img.resize((pixel_w, pixel_h), Image.LANCZOS)
    img_rgb = img_resized.convert('RGB')
    img_gray = img_resized.convert('L')

    rgb_data = list(img_rgb.getdata())
    gray_data = list(img_gray.getdata())

    # Braille dot positions:  [0] [3]
    #                         [1] [4]
    #                         [2] [5]
    #                         [6] [7]
    dot_map = [
        (0, 0, 0x01), (1, 0, 0x08),
        (0, 1, 0x02), (1, 1, 0x10),
        (0, 2, 0x04), (1, 2, 0x20),
        (0, 3, 0x40), (1, 3, 0x80),
    ]

    threshold = 160
    lines = []

    for by in range(0, pixel_h, 4):
        line = ""
        for bx in range(0, pixel_w, 2):
            code = 0x2800
            r_sum, g_sum, b_sum, count = 0, 0, 0, 0

            for dx, dy, bit in dot_map:
                px, py = bx + dx, by + dy
                if px < pixel_w and py < pixel_h:
                    idx = py * pixel_w + px
                    if gray_data[idx] < threshold:
                        code |= bit
                    r, g, b = rgb_data[idx]
                    r_sum += r
                    g_sum += g
                    b_sum += b
                    count += 1

            if count > 0:
                ar = r_sum // count
                ag = g_sum // count
                ab = b_sum // count
                line += fg(ar, ag, ab) + chr(code)
            else:
                line += " "

        lines.append(line + RST)

    return "\n".join(lines)

# ─── Classic ASCII Art (character density shading) ───────────

# Character ramps: light → dark (for dark terminal backgrounds where text is bright)
ASCII_RAMPS = {
    'simple':  ' .:-=+*#%@',
    'detailed': ' .\'`^",:;Il!i><~+_-?][}{1)(|/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$',
    'blocks':  ' ░▒▓█',
    'minimal': ' .:░▒▓█',
}

def image_to_ascii(img_path, width=80, color=True, ramp='detailed', invert=False):
    """Convert image to classic ASCII art using character density shading.

    Characters with more visual 'weight' represent darker pixels.
    Optionally colorize each character with the pixel's original color.
    """
    try:
        from PIL import Image, ImageStat
    except ImportError:
        return None

    img = Image.open(img_path).convert('RGB')

    # Terminal chars are ~2x taller than wide, so adjust aspect ratio
    aspect_ratio = img.height / img.width
    char_aspect = 0.45  # approximate width/height of a monospace char
    target_w = width
    target_h = int(target_w * aspect_ratio * char_aspect)

    img_resized = img.resize((target_w, target_h), Image.LANCZOS)
    img_gray = img_resized.convert('L')

    rgb_data = list(img_resized.getdata())
    gray_data = list(img_gray.getdata())

    chars = ASCII_RAMPS.get(ramp, ASCII_RAMPS['detailed'])
    num_chars = len(chars)

    lines = []
    for y in range(target_h):
        line = ""
        for x in range(target_w):
            idx = y * target_w + x
            brightness = gray_data[idx]  # 0=black, 255=white

            if invert:
                # For light terminal backgrounds
                char_idx = int(brightness / 256 * num_chars)
            else:
                # For dark terminal backgrounds (bright text = dark pixel)
                char_idx = int((255 - brightness) / 256 * num_chars)

            char_idx = min(char_idx, num_chars - 1)
            ch = chars[char_idx]

            if color and ch != ' ':
                r, g, b = rgb_data[idx]
                line += fg(r, g, b) + ch
            else:
                line += ch

        if color:
            line += RST
        lines.append(line)

    return "\n".join(lines)

# ─── Info Section ────────────────────────────────────────────

def info_text():
    return f"""
  {BLUE}{BOLD}Your AI Companion{RST}  {RED}❤{RST}  {PINK}clawra.love{RST}

  {GRAY}Discord · Telegram · WhatsApp{RST}
  {GRAY}AI Selfies · 24/7 Online · Customizable{RST}
"""

# ─── Main ────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Clawra Terminal Art - Draw Clawra in your terminal',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
modes:
  (default)        Logo banner + ASCII character art + info
  --banner         Logo banner only
  --character      ASCII character art only
  --pixel          Pixel art using colored half-blocks
  --image          Photo-quality from reference image (needs Pillow)
  --braille        Braille character art (highest detail, needs Pillow)
  --ascii          Classic ASCII art with character density shading (needs Pillow)
  --all            Show all art styles

examples:
  python clawra_art.py
  python clawra_art.py --ascii -w 80           Classic ASCII portrait
  python clawra_art.py --ascii -w 100 --ramp blocks  Block shading
  python clawra_art.py --ascii --no-color      Monochrome ASCII
  python clawra_art.py --image -w 60
  python clawra_art.py --all
        """
    )
    parser.add_argument('--banner', action='store_true', help='Show logo banner only')
    parser.add_argument('--character', action='store_true', help='Show ASCII character art')
    parser.add_argument('--pixel', action='store_true', help='Show pixel art version')
    parser.add_argument('--image', action='store_true', help='Half-block image (needs Pillow)')
    parser.add_argument('--braille', action='store_true', help='Braille art (needs Pillow)')
    parser.add_argument('--ascii', action='store_true', help='Classic ASCII density art (needs Pillow)')
    parser.add_argument('-w', '--width', type=int, default=80, help='Width for image modes (default: 80)')
    parser.add_argument('--ramp', choices=['simple', 'detailed', 'blocks', 'minimal'], default='detailed',
                        help='ASCII character ramp style (default: detailed)')
    parser.add_argument('--no-color', action='store_true', help='Monochrome output (no ANSI colors)')
    parser.add_argument('--invert', action='store_true', help='Invert for light backgrounds')
    parser.add_argument('--all', action='store_true', help='Show all art styles')
    args = parser.parse_args()

    any_mode = any([args.banner, args.character, args.pixel, args.image, args.braille, args.ascii, args.all])

    # Default: show banner + character + info
    if not any_mode:
        print(banner())
        print(character_art())
        print(info_text())
        return

    if args.all:
        print(banner())
        print()
        print(f"  {PINK}{BOLD}━━ ASCII Art ━━{RST}")
        print(character_art())
        print()
        print(f"  {PINK}{BOLD}━━ Pixel Art ━━{RST}")
        print(render_pixel_art())
        print()

        img_path = download_reference_image()
        if img_path:
            result = image_to_terminal(img_path, args.width)
            if result:
                print(f"\n  {PINK}{BOLD}━━ Half-Block Photo ({args.width}w) ━━{RST}")
                print(result)

            braille = image_to_braille(img_path, args.width)
            if braille:
                print(f"\n  {PINK}{BOLD}━━ Braille Art ({args.width}w) ━━{RST}")
                print(braille)

            ascii_art = image_to_ascii(img_path, args.width, color=not args.no_color,
                                        ramp=args.ramp, invert=args.invert)
            if ascii_art:
                print(f"\n  {PINK}{BOLD}━━ Classic ASCII Art ({args.width}w, {args.ramp}) ━━{RST}")
                print(ascii_art)

            if not result and not braille and not ascii_art:
                print(f"  {GRAY}(Install Pillow for photo modes: pip install Pillow){RST}")

        print(info_text())
        return

    if args.banner:
        print(banner())

    if args.character:
        print(character_art())

    if args.pixel:
        print(render_pixel_art())

    if args.image or args.braille or args.ascii:
        img_path = download_reference_image()
        if not img_path:
            print(f"{RED}Could not download reference image.{RST}")
            return

        if args.image:
            result = image_to_terminal(img_path, args.width)
            if result:
                print(result)
            else:
                print(f"{RED}Pillow not installed. Run: pip install Pillow{RST}")

        if args.braille:
            result = image_to_braille(img_path, args.width)
            if result:
                print(result)
            else:
                print(f"{RED}Pillow not installed. Run: pip install Pillow{RST}")

        if args.ascii:
            result = image_to_ascii(img_path, args.width, color=not args.no_color,
                                    ramp=args.ramp, invert=args.invert)
            if result:
                print(result)
            else:
                print(f"{RED}Pillow not installed. Run: pip install Pillow{RST}")


if __name__ == '__main__':
    main()
