#!/usr/bin/env python3
"""
generate_multiview.py — Generate multi-view character images using Gemini API.

Usage:
    python3 generate_multiview.py <reference_image> [--output-dir <dir>] [--angles 5|9|17]

Two-phase generation:
  Phase 1 (9 views): Generate from single reference + text prompt
  Phase 2 (8 more → 17): Generate midpoints using TWO reference images
    e.g. slight_left = midpoint between center and left

Output files: view_<name>.png (800x1000, grayscale)
"""

import argparse
import os
import subprocess
import sys
import time

from PIL import Image

try:
    from google import genai
except ImportError:
    print("pip install google-genai"); sys.exit(1)


# ─── Phase 1: Extreme views (9 views from single reference) ─────────

VIEWS_5 = [
    ("center",      "looking straight at the viewer (front view)"),

    ("left",
     "facing LEFT. Her whole head is rotated 30° to the LEFT. Her nose points LEFT. "
     "3/4 profile view: her RIGHT ear is fully visible and exposed. The LEFT side of her face is hidden behind the nose. "
     "Her pupils and irises are shifted to the LEFT — she is LOOKING LEFT with her eyes. "
     "The nose, chin, and gaze ALL point to the LEFT edge of the image"),

    ("right",
     "facing RIGHT. Her whole head is rotated 30° to the RIGHT. Her nose points RIGHT. "
     "3/4 profile view: her LEFT ear is fully visible and exposed. The RIGHT side of her face is hidden behind the nose. "
     "Her pupils and irises are shifted to the RIGHT — she is LOOKING RIGHT with her eyes. "
     "The nose, chin, and gaze ALL point to the RIGHT edge of the image"),

    ("up",
     "looking UP. Her chin is raised HIGH, tilting her whole head BACK by 25°. "
     "Camera angle is from BELOW her face: we can see the UNDERSIDE of her chin and jaw clearly. "
     "Her nostrils are slightly visible from below. "
     "Her pupils and irises are shifted to the TOP of her eyes — she is LOOKING UPWARD. "
     "Her neck is extended and more visible"),

    ("down",
     "looking DOWN with her head bowed forward. This is a HIGH-ANGLE shot looking DOWN at her from ABOVE. "
     "The TOP of her head and HAIR CROWN dominate the image — we see much more hair than face. "
     "Her face is foreshortened: forehead is large, chin is barely visible, almost hidden. "
     "Her eyes are HALF-CLOSED or cast deeply downward, irises at the very BOTTOM of the eye sockets. "
     "Her neck is hidden behind her chin. Think of someone reading a book in their lap"),
]

VIEWS_9 = VIEWS_5 + [
    ("left_up",
     "facing UPPER-LEFT. Her head is rotated 25° LEFT and tilted 20° UPWARD. Her nose points to the upper-left corner. "
     "3/4 profile from below-right: RIGHT ear visible, chin raised, neck extended. "
     "Her pupils and irises point UPPER-LEFT — both shifted left AND upward in the eye sockets. "
     "The nose, chin, and gaze ALL point toward the UPPER-LEFT corner of the image"),

    ("right_up",
     "facing UPPER-RIGHT. Her head is rotated 25° RIGHT and tilted 20° UPWARD. Her nose points to the upper-right corner. "
     "3/4 profile from below-left: LEFT ear visible, chin raised, neck extended. "
     "Her pupils and irises point UPPER-RIGHT — both shifted right AND upward in the eye sockets. "
     "The nose, chin, and gaze ALL point toward the UPPER-RIGHT corner of the image"),

    ("left_down",
     "facing LOWER-LEFT. This is a HIGH-ANGLE 3/4 view — camera is ABOVE and to the RIGHT of her. "
     "Her head is turned 25° LEFT and bowed FORWARD 20°. Her nose points to the LOWER-LEFT corner. "
     "We see the TOP of her head prominently — hair crown is large. Her face is foreshortened from above. "
     "RIGHT ear is visible. Her eyes are HALF-CLOSED or cast deeply downward-left. "
     "Irises sit at the LOWER-LEFT of each eye socket. She looks like she is sadly gazing at something on the floor to her left"),

    ("right_down",
     "facing LOWER-RIGHT. This is a HIGH-ANGLE 3/4 view — camera is ABOVE and to the LEFT of her. "
     "Her head is turned 25° RIGHT and bowed FORWARD 20°. Her nose points to the LOWER-RIGHT corner. "
     "We see the TOP of her head prominently — hair crown is large. Her face is foreshortened from above. "
     "LEFT ear is visible. Her eyes are HALF-CLOSED or cast deeply downward-right. "
     "Irises sit at the LOWER-RIGHT of each eye socket. She looks like she is sadly gazing at something on the floor to her right"),
]


# ─── Phase 2: Outer-ring midpoint views (8 views from TWO reference images) ──
#
# These fill the gaps between adjacent EXTREME views on the outer ring:
#
#   left_up ─ [up_mleft] ─ up ─ [up_mright] ─ right_up
#     │                                            │
#  [left_mup]                                 [right_mup]
#     │                                            │
#   left ──────────── center ──────────────── right
#     │                                            │
#  [left_mdown]                               [right_mdown]
#     │                                            │
#   left_down ─ [down_mleft] ─ down ─ [down_mright] ─ right_down
#
# Each entry: (name, view_a, view_b)
# Generated by showing view_a + view_b, asking for exact midpoint
MIDPOINT_VIEWS = [
    ("left_mup",     "left",      "left_up",
     "between LEFT-facing and UPPER-LEFT-facing. Result should face LEFT with a slight upward tilt. Nose points LEFT, eyes look LEFT and slightly UP"),
    ("up_mleft",     "up",        "left_up",
     "between UPWARD-facing and UPPER-LEFT-facing. Result should look UP with head turned slightly LEFT. Nose points slightly left of up, eyes look UP-LEFT"),
    ("up_mright",    "up",        "right_up",
     "between UPWARD-facing and UPPER-RIGHT-facing. Result should look UP with head turned slightly RIGHT. LEFT ear should be partially visible. Nose points slightly right of up, eyes look UP-RIGHT"),
    ("right_mup",    "right",     "right_up",
     "between RIGHT-facing and UPPER-RIGHT-facing. Result should face RIGHT with a slight upward tilt. Nose points RIGHT, eyes look RIGHT and slightly UP"),
    ("right_mdown",  "right",     "right_down",
     "between RIGHT-facing and LOWER-RIGHT-facing. Result should face RIGHT with a slight downward tilt. Nose points RIGHT, eyes look RIGHT and slightly DOWN"),
    ("down_mright",  "down",      "right_down",
     "between DOWNWARD-facing and LOWER-RIGHT-facing. Result should look DOWN with head turned slightly RIGHT. LEFT ear should be partially visible. Eyes look DOWN-RIGHT"),
    ("down_mleft",   "down",      "left_down",
     "between DOWNWARD-facing and LOWER-LEFT-facing. Result should look DOWN with head turned slightly LEFT. RIGHT ear should be partially visible. Eyes look DOWN-LEFT"),
    ("left_mdown",   "left",      "left_down",
     "between LEFT-facing and LOWER-LEFT-facing. Result should face LEFT with a slight downward tilt. Nose points LEFT, eyes look LEFT and slightly DOWN"),
]


def get_api_key():
    """Get Gemini API key from 1Password."""
    try:
        result = subprocess.run(
            ["op", "item", "get", "2rvmtgejubwvpe2xwi6vo6av2q",
             "--fields", "label=credential", "--reveal"],
            capture_output=True, text=True, timeout=10,
        )
        key = result.stdout.strip()
        if key:
            return key
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    key = os.environ.get("GEMINI_API_KEY", "")
    if key:
        return key

    print("Error: Could not get API key from 1Password or GEMINI_API_KEY env var")
    sys.exit(1)


def _save_result(response, output_path):
    """Extract image from Gemini response and save as 800x1000 grayscale."""
    for part in response.parts:
        if part.inline_data is not None:
            tmp_path = output_path + ".tmp.png"
            part.as_image().save(tmp_path)
            img = Image.open(tmp_path).convert("L").resize((800, 1000), Image.LANCZOS)
            img.save(output_path)
            os.remove(tmp_path)
            return True
    return False


def generate_view(client, ref_image, view_name, view_desc, output_dir, model):
    """Phase 1: Generate a view from single reference + text description."""
    output_path = os.path.join(output_dir, f"view_{view_name}.png")

    if os.path.exists(output_path):
        print(f"  [{view_name}] already exists, skipping")
        return output_path

    single = (
        f"Redraw this exact same anime character in the exact same art style, "
        f"same hair, same face, same expression, same clothing (or lack thereof), "
        f"same line weight and shading style — but {view_desc}. "
        f"CRITICAL: her EYES (irises/pupils) MUST look in the SAME direction as her head is facing. "
        f"Keep the character centered in the frame. "
        f"Keep the same head-to-body proportions and framing. "
        f"Grayscale only, white background."
    )
    prompt = f"{single} {single}"

    print(f"  [{view_name}] generating (single ref)...")
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=model,
                contents=[prompt, ref_image],
            )
            if _save_result(response, output_path):
                print(f"  [{view_name}] saved → {output_path}")
                return output_path
            print(f"  [{view_name}] no image in response, retrying...")
        except Exception as e:
            print(f"  [{view_name}] error: {e}")
            if attempt < 2:
                time.sleep(2 ** (attempt + 1))

    print(f"  [{view_name}] FAILED after 3 attempts")
    return None


def generate_midpoint_view(client, img_a, img_b, view_name, direction_desc, output_dir, model):
    """Phase 2: Generate midpoint view using TWO adjacent reference images."""
    output_path = os.path.join(output_dir, f"view_{view_name}.png")

    if os.path.exists(output_path):
        print(f"  [{view_name}] already exists, skipping")
        return output_path

    single = (
        f"I am showing you TWO images of the same anime character at two different head angles. "
        f"Image 1 and Image 2 show poses that are {direction_desc}. "
        f"Generate the EXACT MIDPOINT pose between these two images. "
        f"The head rotation, tilt, and eye gaze should be EXACTLY HALFWAY between Image 1 and Image 2. "
        f"Her eyes (irises/pupils) MUST look in the same direction as her head is facing. "
        f"Keep the exact same character, art style, line weight, shading, hair, face, and proportions. "
        f"Keep the character centered in frame. Grayscale only, white background."
    )
    prompt = f"{single} {single}"

    print(f"  [{view_name}] generating (midpoint: {direction_desc})...")
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=model,
                contents=[prompt, img_a, img_b],
            )
            if _save_result(response, output_path):
                print(f"  [{view_name}] saved → {output_path}")
                return output_path
            print(f"  [{view_name}] no image in response, retrying...")
        except Exception as e:
            print(f"  [{view_name}] error: {e}")
            if attempt < 2:
                time.sleep(2 ** (attempt + 1))

    print(f"  [{view_name}] FAILED after 3 attempts")
    return None


def generate_blink_view(client, ref_image, view_name, output_dir, model):
    """Generate eyes-closed version of an existing view."""
    output_path = os.path.join(output_dir, f"blink_{view_name}.png")

    if os.path.exists(output_path):
        print(f"  [blink_{view_name}] already exists, skipping")
        return output_path

    single = (
        f"Redraw this EXACT same anime character in the EXACT same pose, same head angle, "
        f"same art style, same hair, same line weight, same shading, same clothing, "
        f"same framing and proportions — but with her EYES GENTLY CLOSED. "
        f"Her eyelids are softly shut, relaxed, as if mid-blink. "
        f"Do NOT change the head direction, do NOT change the pose, do NOT change anything "
        f"except closing the eyes. Keep everything else pixel-perfect identical. "
        f"Grayscale only, white background."
    )
    prompt = f"{single} {single}"

    print(f"  [blink_{view_name}] generating...")
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=model,
                contents=[prompt, ref_image],
            )
            if _save_result(response, output_path):
                print(f"  [blink_{view_name}] saved → {output_path}")
                return output_path
            print(f"  [blink_{view_name}] no image in response, retrying...")
        except Exception as e:
            print(f"  [blink_{view_name}] error: {e}")
            if attempt < 2:
                time.sleep(2 ** (attempt + 1))

    print(f"  [blink_{view_name}] FAILED after 3 attempts")
    return None


# All 17 view names for blink generation
_BLINK_VIEWS = ['center', 'left', 'right', 'up', 'down',
                'left_up', 'right_up', 'left_down', 'right_down',
                'left_mup', 'up_mleft', 'up_mright', 'right_mup',
                'right_mdown', 'down_mright', 'down_mleft', 'left_mdown']


def main():
    parser = argparse.ArgumentParser(description="Generate multi-view character images")
    parser.add_argument("reference", help="Path to reference character image")
    parser.add_argument("--output-dir", default=None, help="Output directory (default: views/)")
    parser.add_argument("--angles", type=int, default=17, choices=[5, 9, 17],
                        help="Number of views: 5 (cardinal), 9 (+diagonal), 17 (+midpoints)")
    parser.add_argument("--model", default="gemini-2.5-flash-image", help="Gemini model name")
    parser.add_argument("--force", nargs="*", default=[],
                        help="Force regeneration of specific views (e.g. --force slight_left slight_right)")
    parser.add_argument("--blink", action="store_true",
                        help="Generate eyes-closed versions of the 9 extreme views")
    parser.add_argument("--blink-only", action="store_true",
                        help="Only generate blink views (skip normal view generation)")
    args = parser.parse_args()

    if not os.path.exists(args.reference):
        print(f"Error: {args.reference} not found")
        sys.exit(1)

    output_dir = args.output_dir or os.path.join(os.path.dirname(args.reference), "views")
    os.makedirs(output_dir, exist_ok=True)

    # Force-delete specified views
    for name in args.force:
        for prefix in ("view_", "blink_"):
            path = os.path.join(output_dir, f"{prefix}{name}.png")
            if os.path.exists(path):
                os.remove(path)
                print(f"  [{prefix}{name}] force-deleted for regeneration")

    # Init API
    api_key = get_api_key()
    client = genai.Client(api_key=api_key)

    results = {}

    if not args.blink_only:
        # Copy reference as center view
        ref_img = Image.open(args.reference).convert("L").resize((800, 1000), Image.LANCZOS)
        center_path = os.path.join(output_dir, "view_center.png")
        ref_img.save(center_path)
        print(f"  [center] copied reference → {center_path}")

        # Load reference for API calls
        ref_pil = Image.open(args.reference)

        # ── Phase 1: Generate extreme views (from single reference) ──
        views = VIEWS_9 if args.angles >= 9 else VIEWS_5
        results = {"center": center_path}

        for name, desc in views:
            if name == "center":
                continue
            time.sleep(1)
            path = generate_view(client, ref_pil, name, desc, output_dir, args.model)
            if path:
                results[name] = path

        print(f"\n  Phase 1 complete: {len(results)}/{len(views)} views")

        # ── Phase 2: Generate outer-ring midpoint views ──
        if args.angles >= 17:
            print("\n  Phase 2: Generating outer-ring midpoint views...")

            for name, view_a_name, view_b_name, direction_desc in MIDPOINT_VIEWS:
                path_a = os.path.join(output_dir, f"view_{view_a_name}.png")
                path_b = os.path.join(output_dir, f"view_{view_b_name}.png")
                if not os.path.exists(path_a) or not os.path.exists(path_b):
                    print(f"  [{name}] skipping — need {view_a_name} and {view_b_name}")
                    continue

                img_a = Image.open(path_a)
                img_b = Image.open(path_b)
                time.sleep(1)
                path = generate_midpoint_view(
                    client, img_a, img_b,
                    name, direction_desc, output_dir, args.model,
                )
                if path:
                    results[name] = path

        print(f"\nDone! Generated {len(results)}/{args.angles} views in {output_dir}/")
        print("Views:", ", ".join(sorted(results.keys())))

    # ── Phase 3: Generate blink views (eyes-closed versions) ──
    if args.blink or args.blink_only:
        print("\n  Phase 3: Generating blink (eyes-closed) views...")
        blink_results = {}

        for view_name in _BLINK_VIEWS:
            view_path = os.path.join(output_dir, f"view_{view_name}.png")
            if not os.path.exists(view_path):
                print(f"  [blink_{view_name}] skipping — view_{view_name}.png not found")
                continue
            ref = Image.open(view_path)
            time.sleep(1)
            path = generate_blink_view(client, ref, view_name, output_dir, args.model)
            if path:
                blink_results[view_name] = path

        print(f"\n  Blink phase complete: {len(blink_results)}/{len(_BLINK_VIEWS)} blink views")

    # Generate manifest
    manifest_path = os.path.join(output_dir, "manifest.txt")
    with open(manifest_path, "w") as f:
        for name in sorted(results.keys()):
            f.write(f"{name}=view_{name}.png\n")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
