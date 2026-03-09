#!/usr/bin/env python3
"""
generate_multiview.py — Generate multi-view character images using Gemini API.

Usage:
    python3 generate_multiview.py <reference_image> [--output-dir <dir>] [--angles 5|9|17]

Two-phase generation:
  Phase 1 (9 views): Generate from single reference + text prompt
  Phase 2 (8 more → 17): Generate midpoints using TWO reference images
    e.g. slight_left = midpoint between center and left

Output files: view_<name>.png (750x1000, grayscale)
"""

import argparse
import os
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
     "looking DOWN with her head tilted slightly forward (~15°). "
     "More of her hair and forehead are visible than in the center view. Her chin is slightly tucked. "
     "Her eyes look downward, irises at the BOTTOM of the eye sockets. "
     "KEEP the same neutral expression as the center view — NOT sad, NOT sleepy. "
     "Same framing size as the center view — do NOT zoom in"),
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
     "facing LOWER-LEFT. Her head is turned 25° LEFT and bowed forward ~25°. "
     "Her nose points clearly to the lower-left. RIGHT ear is visible. "
     "More of the TOP of her head and hair is visible than in the left view. "
     "Her eyes look strongly downward-left, irises at the very LOWER-LEFT of each eye socket. "
     "KEEP the same neutral expression — NOT sad. Same framing size as center view"),

    ("right_down",
     "facing LOWER-RIGHT. Her head is turned 25° RIGHT and bowed forward ~25°. "
     "Her nose points clearly to the lower-right. LEFT ear is visible. "
     "More of the TOP of her head and hair is visible than in the right view. "
     "Her eyes look strongly downward-right, irises at the very LOWER-RIGHT of each eye socket. "
     "KEEP the same neutral expression — NOT sad. Same framing size as center view"),
]


# ─── Phase 2: Outer-ring midpoint views ──────────────────────────────
#
# Each entry: (name, view_desc) — generated from center reference like Phase 1
# These are explicit pose descriptions, NOT "midpoint between two images"
MIDPOINT_VIEWS = [
    ("left_mup",
     "facing LEFT with a slight upward chin tilt. Head rotated 30° LEFT, chin raised ~10°. "
     "3/4 profile: RIGHT ear visible. Nose points LEFT and slightly UP. "
     "Her pupils/irises are shifted LEFT and slightly UPWARD"),

    ("up_mleft",
     "looking UP with head turned slightly LEFT. Chin raised 20°, head rotated ~15° LEFT. "
     "Camera from slightly below-right. RIGHT ear partially visible. "
     "Nose points UP and slightly LEFT. Her pupils/irises shifted UPWARD-LEFT"),

    ("up_mright",
     "looking UP with head turned slightly RIGHT. Chin raised 20°, head rotated ~15° RIGHT. "
     "Camera from slightly below-left. LEFT ear partially visible. "
     "Nose points UP and slightly RIGHT. Her pupils/irises shifted UPWARD-RIGHT"),

    ("right_mup",
     "facing RIGHT with a slight upward chin tilt. Head rotated 30° RIGHT, chin raised ~10°. "
     "3/4 profile: LEFT ear visible. Nose points RIGHT and slightly UP. "
     "Her pupils/irises are shifted RIGHT and slightly UPWARD"),

    ("right_mdown",
     "facing RIGHT with a slight downward tilt. Head rotated 30° RIGHT, bowed ~10°. "
     "3/4 profile from slightly above: LEFT ear visible, forehead a bit more prominent. "
     "Nose points RIGHT and slightly DOWN. Her pupils/irises shifted RIGHT and slightly DOWNWARD"),

    ("down_mright",
     "looking DOWN with head turned slightly RIGHT. Head tilted forward ~15°, rotated ~15° RIGHT. "
     "LEFT ear partially visible. Slightly more forehead visible. "
     "Nose points DOWN-RIGHT. Her pupils/irises shifted DOWNWARD-RIGHT. "
     "KEEP neutral expression — NOT sad. Same framing size as center"),

    ("down_mleft",
     "looking DOWN with head turned slightly LEFT. Head tilted forward ~15°, rotated ~15° LEFT. "
     "RIGHT ear partially visible. Slightly more forehead visible. "
     "Nose points DOWN-LEFT. Her pupils/irises shifted DOWNWARD-LEFT. "
     "KEEP neutral expression — NOT sad. Same framing size as center"),

    ("left_mdown",
     "facing LEFT with a slight downward tilt. Head rotated 30° LEFT, bowed ~10°. "
     "3/4 profile from slightly above: RIGHT ear visible, forehead a bit more prominent. "
     "Nose points LEFT and slightly DOWN. Her pupils/irises shifted LEFT and slightly DOWNWARD"),
]


# ─── Phase 2b: Inner-ring midpoint views (center ↔ extreme) ──────────
#
#   left_up ─── up_mleft ──── up ──── up_mright ──── right_up
#     │                                                  │
#   left_mup   [c_mlu]      [c_mu]   [c_mru]        right_mup
#     │                                                  │
#   left ───── [c_ml] ───── center ── [c_mr] ──────── right
#     │                                                  │
#   left_mdown [c_mld]      [c_md]   [c_mrd]        right_mdown
#     │                                                  │
#   left_down ─ down_mleft ─ down ── down_mright ── right_down

INNER_MIDPOINT_VIEWS = [
    ("center_mleft",
     "facing SLIGHTLY LEFT. Head turned just ~15° to the LEFT — a very subtle 3/4 view. "
     "Nose shifted slightly LEFT of center. RIGHT ear barely peeking out. "
     "Still mostly front-facing. Eyes look slightly LEFT. "
     "This is NOT a full left turn — just a gentle, subtle leftward rotation"),

    ("center_mright",
     "facing SLIGHTLY RIGHT. Head turned just ~15° to the RIGHT — a very subtle 3/4 view. "
     "Nose shifted slightly RIGHT of center. LEFT ear barely peeking out. "
     "Still mostly front-facing. Eyes look slightly RIGHT. "
     "This is NOT a full right turn — just a gentle, subtle rightward rotation"),

    ("center_mup",
     "looking SLIGHTLY UPWARD. Her chin is noticeably raised — we can see more of her NECK and the UNDERSIDE of her chin. "
     "Her face is tilted BACK. Her nostrils are just barely hinting from below. "
     "Her eyes gaze slightly UPWARD — irises shifted toward the top of the eye sockets. "
     "IMPORTANT: The head must be visibly tilted back compared to a front view. "
     "The neck must be clearly more exposed than in a straight-ahead pose"),

    ("center_mdown",
     "looking SLIGHTLY DOWNWARD. Her head is tilted forward just a little (~8°). "
     "Slightly more forehead/hair visible than center. Her chin is slightly tucked. "
     "Her eyes look DOWNWARD — irises shifted toward the BOTTOM of the eye sockets. "
     "KEEP the same neutral expression — NOT sad. Same framing size as center"),

    ("center_mleft_up",
     "facing SLIGHTLY UPPER-LEFT. Head turned slightly LEFT, chin raised slightly. "
     "Subtle 3/4 view with upward tilt — more NECK visible, RIGHT ear barely peeking. "
     "Nose shifted LEFT and UP. Eyes look UPPER-LEFT. "
     "The neck and underside of chin must be slightly more visible than a front view"),

    ("center_mright_up",
     "facing SLIGHTLY UPPER-RIGHT. Head turned slightly RIGHT, chin raised slightly. "
     "Subtle 3/4 view with upward tilt — more NECK visible, LEFT ear barely peeking. "
     "Nose shifted RIGHT and UP. Eyes look UPPER-RIGHT. "
     "The neck and underside of chin must be slightly more visible than a front view"),

    ("center_mleft_down",
     "facing SLIGHTLY LOWER-LEFT. Head turned slightly LEFT, bowed slightly forward. "
     "Subtle 3/4 view with downward tilt — more HAIR/FOREHEAD visible, RIGHT ear barely peeking. "
     "Nose shifted LEFT and DOWN. Eyes look LOWER-LEFT. "
     "The top of the head and hair must be slightly more prominent than a front view"),

    ("center_mright_down",
     "facing SLIGHTLY LOWER-RIGHT. Head turned slightly RIGHT, bowed slightly forward. "
     "Subtle 3/4 view with downward tilt — more HAIR/FOREHEAD visible, LEFT ear barely peeking. "
     "Nose shifted RIGHT and DOWN. Eyes look LOWER-RIGHT. "
     "The top of the head and hair must be slightly more prominent than a front view"),
]

# All 25 view names
ALL_VIEW_NAMES = [
    'center',
    'left', 'right', 'up', 'down',
    'left_up', 'right_up', 'left_down', 'right_down',
    'left_mup', 'up_mleft', 'up_mright', 'right_mup',
    'right_mdown', 'down_mright', 'down_mleft', 'left_mdown',
    'center_mleft', 'center_mright', 'center_mup', 'center_mdown',
    'center_mleft_up', 'center_mright_up', 'center_mleft_down', 'center_mright_down',
]

# View dependency graph: all non-center views depend only on center
VIEW_DEPS = {'center': []}
for name, desc in VIEWS_9:
    if name != 'center':
        VIEW_DEPS[name] = ['center']
for name, desc in MIDPOINT_VIEWS:
    VIEW_DEPS[name] = ['center']
for name, desc in INNER_MIDPOINT_VIEWS:
    VIEW_DEPS[name] = ['center']

# View generation info: all views use Phase 1 style (center ref + pose desc)
VIEW_GEN_INFO = {}
for name, desc in VIEWS_9:
    if name != 'center':
        VIEW_GEN_INFO[name] = ('phase1', desc)
for name, desc in MIDPOINT_VIEWS:
    VIEW_GEN_INFO[name] = ('phase1', desc)
for name, desc in INNER_MIDPOINT_VIEWS:
    VIEW_GEN_INFO[name] = ('phase1', desc)


def get_api_key():
    """Get Gemini API key from GEMINI_API_KEY environment variable."""
    key = os.environ.get("GEMINI_API_KEY", "")
    if key:
        return key

    print("Error: Set GEMINI_API_KEY environment variable")
    sys.exit(1)


def _save_result(response, output_path, target_w=750, target_h=1000):
    """Extract image from Gemini response, resize to target size."""
    for part in response.parts:
        if part.inline_data is not None:
            tmp_path = output_path + ".tmp.png"
            part.as_image().save(tmp_path)
            src = Image.open(tmp_path).convert("L")
            if src.size != (target_w, target_h):
                src = src.resize((target_w, target_h), Image.LANCZOS)
            src.save(output_path)
            os.remove(tmp_path)
            return True
    return False


# Image generation config: 3:4 aspect ratio (750x1000)
_IMAGE_CONFIG = None
try:
    from google.genai import types as _gtypes
    _IMAGE_CONFIG = _gtypes.GenerateContentConfig(
        response_modalities=["IMAGE"],
        image_config=_gtypes.ImageConfig(aspect_ratio="3:4"),
    )
except Exception:
    pass


import numpy as np

def _make_mask_image(w, h, y_center_pct, y_radius_pct):
    """Create a mask image: white = edit region, black = keep.
    Horizontal band with Gaussian feathering."""
    from PIL import ImageFilter
    mask = np.zeros((h, w), dtype=np.uint8)
    cy = int(y_center_pct * h)
    r = int(y_radius_pct * h)
    mask[max(0, cy - r):min(h, cy + r), :] = 255
    img = Image.fromarray(mask)
    img = img.filter(ImageFilter.GaussianBlur(radius=int(0.03 * h)))
    return img


def _save_edit_result(response, output_path):
    """Save result from edit_image API response.

    Inpaint results should already match the input dimensions, so only
    convert to grayscale. Resize/crop only if dimensions don't match.
    """
    if response.generated_images:
        response.generated_images[0].image.save(output_path)
        src = Image.open(output_path).convert("L")
        target_w, target_h = 750, 1000
        if src.size == (target_w, target_h):
            # Already correct size — just save grayscale
            src.save(output_path)
        else:
            # Different size — resize to match exactly (no crop)
            src.resize((target_w, target_h), Image.LANCZOS).save(output_path)
        return True
    return False


def generate_center(client, ref_images, output_dir, model, style_ref=None):
    """Phase 0: Generate center (front-facing) view from 1-N reference images."""
    output_path = os.path.join(output_dir, "view_center.png")

    if os.path.exists(output_path):
        print(f"  [center] already exists, skipping")
        return output_path

    if style_ref:
        prompt = (
            "I'm giving you TWO reference images. "
            "IMAGE 1 (STYLE REFERENCE): Copy ONLY the grayscale rendering style, tonal range, and shading technique from this image. "
            "IMAGE 2 (CHARACTER REFERENCE): Draw THIS character — same face and hair only. "
            "DO NOT copy the character from image 1. Draw the character from image 2 in the rendering style of image 1. "
            "The character should have bare shoulders with NO clothing — just like the style reference. "
            "Front-facing view, looking straight at the viewer. "
            "CRITICAL FRAMING: The ENTIRE head including ALL hair must be fully visible — "
            "do NOT crop or cut off any part of the head or hair. "
            "Show from the top of the hair down to mid-chest. Leave a small margin above the hair. "
            "Horizontally centered. White background."
        )
    else:
        prompt = (
            "Draw this exact same anime character looking straight at the viewer (front view). "
            "Same art style, same hair, same face, same line weight and shading. "
            "The character should be facing DIRECTLY FORWARD, eyes looking at the viewer. "
            "CRITICAL FRAMING: The ENTIRE head including ALL hair must be fully visible — "
            "do NOT crop or cut off any part of the head or hair. "
            "Show from the top of the hair down to mid-chest (head-and-shoulders portrait). "
            "Leave a small margin of white space above the hair. "
            "The character must be horizontally centered with equal space on left and right. "
            "STYLE: Grayscale anime illustration with soft tonal shading — not pure line art, not overly dark. "
            "Hair should have moderate gray tones with subtle highlights, skin with light soft shading. "
            "Clothing and accessories must have clear tonal contrast — seams, patterns, shadows, and structural details "
            "should be distinctly visible with varying gray values so different parts are easily distinguishable. "
            "White background."
        )

    print(f"  [center] generating from {len(ref_images)} reference(s){'+ style ref' if style_ref else ''}...")
    contents = [prompt] + ([style_ref] if style_ref else []) + ref_images
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=model, contents=contents, config=_IMAGE_CONFIG,
            )
            if _save_result(response, output_path):
                print(f"  [center] saved → {output_path}")
                return output_path
            print(f"  [center] no image in response, retrying...")
        except Exception as e:
            print(f"  [center] error: {e}")
            if attempt < 2:
                time.sleep(2 ** (attempt + 1))

    print(f"  [center] FAILED after 3 attempts")
    return None


def generate_view(client, ref_image, view_name, view_desc, output_dir, model, style_ref=None):
    """Phase 1: Generate a view from single reference + text description."""
    output_path = os.path.join(output_dir, f"view_{view_name}.png")

    if os.path.exists(output_path):
        print(f"  [{view_name}] already exists, skipping")
        return output_path

    style_part = (
        "Match the grayscale style and tonal range of the STYLE REFERENCE image. "
    ) if style_ref else (
        "STYLE: Grayscale anime illustration with soft tonal shading — not pure line art, not overly dark. "
        "Hair should have moderate gray tones with subtle highlights, skin with light soft shading. "
        "Clothing and accessories must have clear tonal contrast — seams, patterns, shadows, and structural details "
        "should be distinctly visible with varying gray values so different parts are easily distinguishable. "
    )
    single = (
        f"Redraw this exact same anime character in the exact same art style, "
        f"same hair, same face, same expression, same clothing (or lack thereof), "
        f"same line weight and shading style — but {view_desc}. "
        f"CRITICAL: her EYES (irises/pupils) MUST look in the SAME direction as her head is facing. "
        f"The shoulders and upper body should naturally follow the head rotation — "
        f"when the head turns left, the shoulders also angle slightly left. "
        f"CRITICAL FRAMING: head-and-shoulders framing — the ENTIRE head including hair must be fully visible. "
        f"Do NOT crop or cut off the top of the head. Keep the character centered with the same proportions as the reference. "
        f"{style_part}"
        f"White background."
    )
    prompt = f"{single} {single}"

    print(f"  [{view_name}] generating (single ref)...")
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=model,
                contents=[prompt] + ([style_ref] if style_ref else []) + [ref_image],
                config=_IMAGE_CONFIG,
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
        f"CRITICAL FRAMING: head-and-shoulders framing — the ENTIRE head including hair must be fully visible. "
        f"Do NOT crop or cut off the top of the head. Keep the character centered in frame. Grayscale only, white background."
    )
    prompt = f"{single} {single}"

    print(f"  [{view_name}] generating (midpoint: {direction_desc})...")
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=model,
                contents=[prompt, img_a, img_b],
                config=_IMAGE_CONFIG,
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


_INPAINT_MODEL = "imagen-3.0-capability-001"


def _inpaint(client, ref_path, mask_img, prompt, output_path, label):
    """Run edit_image inpainting. Returns True on success."""
    # Save mask to temp file
    mask_path = output_path + ".mask.png"
    mask_img.save(mask_path)

    raw_ref = _gtypes.RawReferenceImage(
        reference_id=1,
        reference_image=_gtypes.Image.from_file(location=ref_path),
    )
    mask_ref = _gtypes.MaskReferenceImage(
        reference_id=2,
        config=_gtypes.MaskReferenceConfig(
            mask_mode="MASK_MODE_USER_PROVIDED",
            mask_dilation=0.03,
        ),
        reference_image=_gtypes.Image.from_file(location=mask_path),
    )
    for attempt in range(3):
        try:
            response = client.models.edit_image(
                model=_INPAINT_MODEL,
                prompt=prompt,
                reference_images=[raw_ref, mask_ref],
                config=_gtypes.EditImageConfig(
                    edit_mode="EDIT_MODE_INPAINT_INSERTION",
                    number_of_images=1,
                ),
            )
            if _save_edit_result(response, output_path):
                print(f"  [{label}] saved (inpaint) → {output_path}")
                os.remove(mask_path)
                return True
            print(f"  [{label}] no image in response, retrying...")
        except Exception as e:
            print(f"  [{label}] inpaint error: {e}")
            if attempt < 2:
                time.sleep(2 ** (attempt + 1))
    if os.path.exists(mask_path):
        os.remove(mask_path)
    return False


def _fallback_edit(client, ref_image, prompt, output_path, label, model):
    """Fallback: use generate_content for editing.

    Uses direct resize (no crop) to preserve alignment with the original view.
    """
    target_w, target_h = 750, 1000
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=model,
                contents=[ref_image, prompt],
                config=_IMAGE_CONFIG,
            )
            for part in response.parts:
                if part.inline_data is not None:
                    tmp_path = output_path + ".tmp.png"
                    part.as_image().save(tmp_path)
                    src = Image.open(tmp_path).convert("L")
                    src.resize((target_w, target_h), Image.LANCZOS).save(output_path)
                    os.remove(tmp_path)
                    print(f"  [{label}] saved (fallback) → {output_path}")
                    return True
            print(f"  [{label}] no image in response, retrying...")
        except Exception as e:
            print(f"  [{label}] fallback error: {e}")
            if attempt < 2:
                time.sleep(2 ** (attempt + 1))
    return False


def generate_mouth_open(client, ref_image, output_dir, model):
    """Generate mouth-open version of the center view for speaking animation."""
    output_path = os.path.join(output_dir, "mouth_center.png")
    if os.path.exists(output_path):
        print(f"  [mouth_center] already exists, skipping")
        return output_path

    ref_path = os.path.join(output_dir, "view_center.png")
    prompt = "Open the character's mouth slightly, as if speaking. Small natural parted lips."

    print(f"  [mouth_center] generating...")
    # Try inpainting first (mouth region: ~50%-58% of image height)
    mask = _make_mask_image(750, 1000, y_center_pct=0.54, y_radius_pct=0.04)
    if _inpaint(client, ref_path, mask, prompt, output_path, "mouth_center"):
        return output_path

    # Fallback
    print(f"  [mouth_center] inpaint failed, trying fallback...")
    fb_prompt = (
        "Edit this image: open the character's mouth slightly, as if speaking. "
        "Only modify the mouth. Do NOT change anything else. Output the full edited image."
    )
    if _fallback_edit(client, ref_image, fb_prompt, output_path, "mouth_center", model):
        return output_path

    print(f"  [mouth_center] FAILED after all attempts")
    return None


def generate_blink_view(client, ref_image, view_name, output_dir, model):
    """Generate eyes-closed version of an existing view."""
    output_path = os.path.join(output_dir, f"blink_{view_name}.png")
    if os.path.exists(output_path):
        print(f"  [blink_{view_name}] already exists, skipping")
        return output_path

    ref_path = os.path.join(output_dir, f"view_{view_name}.png")
    prompt = "Close the character's eyes gently, as if mid-blink. Soft closed eyelids, relaxed."

    print(f"  [blink_{view_name}] generating...")
    # Try inpainting first (eye region: ~27%-43% of image height)
    mask = _make_mask_image(750, 1000, y_center_pct=0.35, y_radius_pct=0.08)
    if _inpaint(client, ref_path, mask, prompt, output_path, f"blink_{view_name}"):
        return output_path

    # Fallback
    print(f"  [blink_{view_name}] inpaint failed, trying fallback...")
    fb_prompt = (
        "Edit this image: close the character's eyes gently, as if mid-blink. "
        "Only modify the eyes. Do NOT change anything else. Output the full edited image."
    )
    if _fallback_edit(client, ref_image, fb_prompt, output_path, f"blink_{view_name}", model):
        return output_path

    print(f"  [blink_{view_name}] FAILED after all attempts")
    return None


# All 25 view names for blink generation
_BLINK_VIEWS = ALL_VIEW_NAMES


def main():
    parser = argparse.ArgumentParser(description="Generate multi-view character images")
    parser.add_argument("reference", help="Path to reference character image")
    parser.add_argument("--output-dir", default=None, help="Output directory (default: views/)")
    parser.add_argument("--angles", type=int, default=25, choices=[5, 9, 17, 25],
                        help="Number of views: 5 (cardinal), 9 (+diagonal), 17 (+outer midpoints), 25 (+inner)")
    parser.add_argument("--model", default="gemini-3-pro-image-preview", help="Gemini model name")
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
        ref_img = Image.open(args.reference).convert("L").resize((750, 1000), Image.LANCZOS)
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
            for name, desc in MIDPOINT_VIEWS:
                time.sleep(1)
                path = generate_view(client, ref_pil, name, desc, output_dir, args.model)
                if path:
                    results[name] = path

        # ── Phase 2b: Generate inner-ring midpoint views ──
        if args.angles >= 25:
            print("\n  Phase 2b: Generating inner-ring midpoint views...")
            for name, desc in INNER_MIDPOINT_VIEWS:
                time.sleep(1)
                path = generate_view(client, ref_pil, name, desc, output_dir, args.model)
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
