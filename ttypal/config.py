#!/usr/bin/env python3
"""
config.py — Config management and first-run setup wizard for ttypal.

Config is stored at ~/.ttypal/config.json:
  {
    "gemini_api_key": "...",
    "character": "clawra"
  }

Environment variables override config file values.
"""

import os
import json
import sys

_CONFIG_DIR = os.path.join(os.path.expanduser('~'), '.ttypal')
_CONFIG_PATH = os.path.join(_CONFIG_DIR, 'config.json')

_PRESET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           'characters', 'preset')


def load_config():
    """Load config from ~/.ttypal/config.json. Returns dict."""
    if not os.path.exists(_CONFIG_PATH):
        return {}
    try:
        with open(_CONFIG_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg):
    """Save config dict to ~/.ttypal/config.json."""
    os.makedirs(_CONFIG_DIR, exist_ok=True)
    with open(_CONFIG_PATH, 'w') as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def get_api_key(cfg=None):
    """Get Gemini API key: env var > config file."""
    env = os.environ.get('GEMINI_API_KEY', '')
    if env:
        return env
    if cfg is None:
        cfg = load_config()
    return cfg.get('gemini_api_key', '')


def get_character(cfg=None):
    """Get character name: --character flag > config file > 'clawra'."""
    if cfg is None:
        cfg = load_config()
    return cfg.get('character', 'clawra')


def list_presets():
    """List available preset character names."""
    if not os.path.isdir(_PRESET_DIR):
        return []
    return sorted(d for d in os.listdir(_PRESET_DIR)
                  if os.path.isdir(os.path.join(_PRESET_DIR, d)))


def _read_soul_summary(name):
    """Read first descriptive line of a preset's soul.md (skip 'You are X')."""
    soul_path = os.path.join(_PRESET_DIR, name, 'soul.md')
    if not os.path.exists(soul_path):
        return ''
    with open(soul_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or line.startswith('You are '):
                continue
            # Truncate long lines
            return line[:80] + ('...' if len(line) > 80 else '')
    return ''


def needs_setup():
    """True if first run (no config file exists)."""
    return not os.path.exists(_CONFIG_PATH)


def run_setup(force=False):
    """Interactive first-run setup wizard. Returns config dict."""
    cfg = load_config()

    if not force and not needs_setup():
        return cfg

    print()
    print("  \033[1m\033[38;2;255;100;160m╭─────────────────────────────╮\033[0m")
    print("  \033[1m\033[38;2;255;100;160m│      ttypal  setup          │\033[0m")
    print("  \033[1m\033[38;2;255;100;160m╰─────────────────────────────╯\033[0m")
    print()

    # ── Step 1: API key ──
    print("  \033[1m[1/2] Gemini API Key\033[0m")
    print("  \033[2mChat requires a Gemini API key (free).\033[0m")
    print("  \033[2mGet one at: https://aistudio.google.com/apikey\033[0m")
    print()

    existing_key = get_api_key(cfg)
    if existing_key:
        masked = existing_key[:4] + '···' + existing_key[-4:]
        print(f"  Current: {masked}")
        key_input = input("  New key (enter to keep): ").strip()
        if key_input:
            cfg['gemini_api_key'] = key_input
    else:
        key_input = input("  API key (enter to skip): ").strip()
        if key_input:
            cfg['gemini_api_key'] = key_input
        else:
            print("  \033[2mSkipped — chat will be disabled.\033[0m")

    print()

    # ── Step 2: Character selection ──
    print("  \033[1m[2/2] Choose Character\033[0m")
    print()

    presets = list_presets()
    for i, name in enumerate(presets, 1):
        summary = _read_soul_summary(name)
        print(f"  \033[1m[{i}]\033[0m {name}")
        if summary:
            print(f"      \033[2m{summary}\033[0m")

    custom_idx = len(presets) + 1
    print(f"  \033[1m[{custom_idx}]\033[0m Create custom character")
    print(f"      \033[2mBring your own reference images\033[0m")
    print()

    current = cfg.get('character', 'clawra')
    choice = input(f"  Select [default: {current}]: ").strip()

    if choice.isdigit():
        idx = int(choice)
        if 1 <= idx <= len(presets):
            cfg['character'] = presets[idx - 1]
        elif idx == custom_idx:
            _setup_custom(cfg)
    elif choice and choice in presets:
        cfg['character'] = choice
    # else: keep current

    # ── Save ──
    save_config(cfg)
    print()
    print(f"  \033[32m✓\033[0m Saved to {_CONFIG_PATH}")
    print(f"  \033[2mCharacter: {cfg.get('character', 'clawra')}\033[0m")
    print(f"  \033[2mAPI key: {'set' if cfg.get('gemini_api_key') else 'not set'}\033[0m")
    print(f"  \033[2mRun 'ttypal --setup' to change later.\033[0m")
    print()

    return cfg


def _setup_custom(cfg):
    """Guide user through custom character creation."""
    print()
    name = input("  Character name: ").strip().lower()
    if not name:
        print("  \033[2mCancelled.\033[0m")
        return

    # Validate name
    if not name.replace('_', '').replace('-', '').isalnum():
        print("  \033[31mName must be alphanumeric (a-z, 0-9, _, -)\033[0m")
        return

    custom_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              'characters', 'custom', name)

    if os.path.isdir(custom_dir):
        print(f"  '{name}' already exists.")
        cfg['character'] = name
        return

    # Create directory structure
    os.makedirs(os.path.join(custom_dir, 'views'), exist_ok=True)
    os.makedirs(os.path.join(custom_dir, 'refs'), exist_ok=True)

    # Build soul.md
    soul_path = os.path.join(custom_dir, 'soul.md')
    cap_name = name.capitalize()

    print()
    print(f"  \033[1mDefine {cap_name}'s personality\033[0m")
    print(f"  \033[2mThis becomes soul.md — the character's system prompt.\033[0m")
    print()

    api_key = get_api_key(cfg)
    soul_text = None

    # Option A: Auto-generate from existing character
    if api_key:
        based_on = input("  Based on an existing character/person? (name or enter to skip):\n  ").strip()
        if based_on:
            soul_text = _generate_soul(api_key, cap_name, based_on)

    # Option B: Manual input
    if soul_text is None:
        soul_text = _build_soul_manual(cap_name)

    with open(soul_path, 'w') as f:
        f.write(soul_text)

    cfg['character'] = name

    print()
    print(f"  \033[32m✓\033[0m Created characters/custom/{name}/")
    print(f"  \033[32m✓\033[0m soul.md written — edit anytime at:")
    print(f"      {os.path.relpath(soul_path)}")
    # Offer to launch view generation UI
    refs_dir = os.path.join(custom_dir, 'refs')
    refs_exist = any(f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))
                     for f in os.listdir(refs_dir)) if os.path.isdir(refs_dir) else False

    if refs_exist:
        print()
        launch = input("  Reference images found. Launch view generator? (Y/n): ").strip().lower()
        if launch != 'n':
            _launch_view_setup(name)
    else:
        print()
        print(f"  \033[1mNext:\033[0m Add reference images to characters/custom/{name}/refs/")
        print(f"  Then run: \033[1mttypal-setup --character {name}\033[0m")
        print(f"  \033[2mOpens a browser UI to generate & review views.\033[0m")


def _launch_view_setup(character_name):
    """Launch ttypal-setup browser UI for a character."""
    from .setup_views import main as setup_main
    print()
    print(f"  \033[2mLaunching view generator for {character_name}...\033[0m")
    sys.argv = ['ttypal-setup', '--character', character_name]
    setup_main()


def _build_soul_manual(cap_name):
    """Build soul.md from interactive prompts."""
    print(f"  \033[2mPress enter to skip any step.\033[0m")
    print()

    backstory = input("  Backstory (who are they, age, origin):\n  ").strip()
    print()
    conflict = input("  Inner conflict (what drives them vs. what they fear):\n  ").strip()
    print()
    voice = input("  Voice (how do they talk — tone, habits, quirks):\n  ").strip()
    print()
    rules = input("  Behavior rules (do/don't for the AI):\n  ").strip()

    parts = [f"You are {cap_name}.\n"]
    if backstory:
        parts.append(backstory + '\n')
    if conflict:
        parts.append(conflict + '\n')
    if voice:
        parts.append(voice + '\n')
    if rules:
        parts.append(rules + '\n')

    return '\n'.join(parts)


def _generate_soul(api_key, char_name, based_on):
    """Generate soul.md via Gemini based on an existing character/person.

    Returns generated text, or None if generation fails (falls back to manual).
    """
    try:
        from google import genai
    except ImportError:
        print("  \033[31mgoogle-genai not installed. pip install ttypal[chat]\033[0m")
        print()
        return None

    prompt = f"""\
Write a soul.md personality file for a chatbot character named "{char_name}", \
based on "{based_on}".

Follow this structure exactly:
1. First line: "You are {char_name}."
2. Backstory paragraph (2-3 sentences — age, origin, what shaped them. \
Adapt from the source material but make it feel personal, not encyclopedic.)
3. Inner conflict paragraph (what drives them vs. what scares them)
4. Voice direction paragraph (HOW they talk — tone, habits, verbal quirks. \
"Show don't tell": describe behaviors, not adjectives.)
5. Behavior rules paragraph (concrete do/don't instructions for the AI)

Rules:
- Write in THIRD PERSON ("She is...", "She speaks..."), not first or second person
- Under 200 words total
- No markdown headers, no bullet points — just plain paragraphs
- Capture the essence, not a biography
- Give contradictions (confident but insecure, tough but caring)
- Voice matters more than lore"""

    print(f"  \033[2mGenerating from \"{based_on}\"...\033[0m")

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model='gemini-3-flash-preview',
            contents=prompt,
        )
        text = response.text.strip()
    except Exception as e:
        print(f"  \033[31mGeneration failed: {e}\033[0m")
        print()
        return None

    # Preview
    print()
    print("  \033[2m┌─── soul.md preview ───\033[0m")
    for line in text.split('\n'):
        print(f"  \033[2m│\033[0m {line}")
    print("  \033[2m└───────────────────────\033[0m")
    print()

    confirm = input("  Use this? (Y/n/retry): ").strip().lower()
    if confirm == 'n':
        print()
        return None  # fall back to manual
    if confirm == 'retry':
        return _generate_soul(api_key, char_name, based_on)

    return text + '\n'
