#!/usr/bin/env python3
"""
memory.py - Tiered memory system for clawra characters.

Architecture based on Simon Kim's memory article:
  - soul.md:     Identity/persona (always injected)
  - user.md:     User information accumulated over conversations
  - memory.md:   M0 (permanent) / M30 / M90 / M365 tiered memories with expiry
  - lessons.md:  Patterns and lessons learned
  - diary/:      Daily session logs (YYYY-MM-DD.md)

Boot sequence:
  SOUL + USER + MEMORY + LESSONS + yesterday diary + today diary -> system prompt

Runtime:
  - Every N turns, background extraction via Gemini (facts -> user.md/memory.md)
  - On history compaction, summarize dropped messages -> diary
  - On session end, final extraction + diary entry

Distillation:
  - On boot: expire old M30/M90/M365 items past their date
  - During extraction: promote recurring M30 items to M90, etc.
"""

import os
import re
import json
import threading
from datetime import date, timedelta, datetime


_TIER_HEADERS = {
    'M0':   '## M0 : Core Memory (Permanent)',
    'M365': '## M365 : 1-year Memory',
    'M90':  '## M90 : 90-day Memory',
    'M30':  '## M30 : 30-day Memory',
}

_TIER_DAYS = {'M30': 30, 'M90': 90, 'M365': 365}

_EXTRACT_MODEL = 'gemini-3.1-flash-lite-preview'


class MemoryManager:
    EXTRACT_INTERVAL = 5  # extract after every N user-model exchanges

    def __init__(self, character_dir, gemini_client=None, character_name=None):
        self.char_dir = character_dir
        self.client = gemini_client
        self.char_name = character_name or os.path.basename(character_dir)
        self._lock = threading.Lock()
        self._turns_since_extract = 0
        self._extracting = False

        # User data directory: <character_dir>/.memory/
        # Keeps personal data out of version control (gitignored)
        self.data_dir = os.path.join(character_dir, '.memory')
        os.makedirs(self.data_dir, exist_ok=True)

        # Character definition (in repo, public)
        self.soul_path = os.path.join(character_dir, 'soul.md')

        # User data (in ~/.clawra/, private)
        self.user_path = os.path.join(self.data_dir, 'user.md')
        self.memory_path = os.path.join(self.data_dir, 'memory.md')
        self.lessons_path = os.path.join(self.data_dir, 'lessons.md')
        self.history_path = os.path.join(self.data_dir, 'history.json')
        self.diary_dir = os.path.join(self.data_dir, 'diary')

        os.makedirs(self.diary_dir, exist_ok=True)
        self._init_files()
        self._distill_on_boot()

    # ── File helpers ─────────────────────────────────────────

    def _init_files(self):
        """Create default memory files if absent."""
        if not os.path.exists(self.user_path):
            with open(self.user_path, 'w') as f:
                f.write("# User Profile\n")

        if not os.path.exists(self.memory_path):
            with open(self.memory_path, 'w') as f:
                f.write(
                    "## M0 : Core Memory (Permanent)\n\n"
                    "## M365 : 1-year Memory\n\n"
                    "## M90 : 90-day Memory\n\n"
                    "## M30 : 30-day Memory\n"
                )

        if not os.path.exists(self.lessons_path):
            with open(self.lessons_path, 'w') as f:
                f.write("# Lessons Learned\n")

    def _read(self, path):
        try:
            with open(path) as f:
                return f.read().strip()
        except FileNotFoundError:
            return ''

    def _diary_path(self, d=None):
        if d is None:
            d = date.today()
        return os.path.join(self.diary_dir, f"{d.isoformat()}.md")

    def _has_content(self, text, skip_header=None):
        """Check if text has real content lines (- items or ## subsections)."""
        for line in text.split('\n'):
            s = line.strip()
            if skip_header and s == skip_header:
                continue
            if s.startswith('- ') or s.startswith('## ['):
                return True
        return False

    # ── Boot: distillation (expiry + promotion) ──────────────

    def _distill_on_boot(self):
        """Remove expired memories and promote recurring ones."""
        content = self._read(self.memory_path)
        if not content:
            return

        today_str = date.today().isoformat()
        lines = content.split('\n')
        new_lines = []
        expired_count = 0

        for line in lines:
            m = re.search(r'<!--\s*expires:\s*(\d{4}-\d{2}-\d{2})\s*-->', line)
            if m and m.group(1) < today_str:
                expired_count += 1
                continue
            new_lines.append(line)

        if expired_count > 0:
            with open(self.memory_path, 'w') as f:
                f.write('\n'.join(new_lines))

    # ── System prompt (boot ritual) ──────────────────────────

    def build_system_prompt(self):
        """Build full system prompt with all memory layers injected.

        This is the 'boot ritual': reconstructing identity and context
        from persistent memory files every session.
        """
        parts = []

        # SOUL — who am I
        soul = self._read(self.soul_path)
        if soul:
            parts.append(soul)

        # USER — who am I talking to
        user = self._read(self.user_path)
        if user and self._has_content(user, '# User Profile'):
            parts.append(user)

        # MEMORY — what do I remember
        memory = self._read(self.memory_path)
        if memory and self._has_content(memory):
            parts.append(memory)

        # LESSONS — what have I learned
        lessons = self._read(self.lessons_path)
        if lessons and self._has_content(lessons, '# Lessons Learned'):
            parts.append(lessons)

        # DIARY — yesterday + today (two-day context window)
        yesterday = self._read(self._diary_path(date.today() - timedelta(days=1)))
        if yesterday:
            parts.append(f"## Yesterday's session\n{yesterday}")

        today_diary = self._read(self._diary_path())
        if today_diary:
            parts.append(f"## Today so far\n{today_diary}")

        # Behavioral instructions (TIER 1 — always injected, minimal)
        parts.append(
            "\n## Instructions\n"
            "- 터미널 채팅창에서 대화 중. 답변은 짧고 자연스럽게, 보통 1-3문장.\n"
            "- 기억하고 있는 유저 정보나 이전 맥락이 있으면 자연스럽게 활용해.\n"
            "- 모르는 건 모른다고 해. 지어내지 마."
        )

        return '\n\n'.join(parts)

    # ── Post-response hook ───────────────────────────────────

    def on_turn_complete(self, chat_history):
        """Called after each model response. Triggers extraction if due."""
        self._turns_since_extract += 1
        if (self._turns_since_extract >= self.EXTRACT_INTERVAL
                and self.client and not self._extracting):
            self._turns_since_extract = 0
            threading.Thread(
                target=self._extract_bg,
                args=(list(chat_history),),
                daemon=True,
            ).start()

    def _extract_bg(self, messages):
        if self._extracting:
            return
        self._extracting = True
        try:
            self._extract(messages)
        finally:
            self._extracting = False

    # ── Fact extraction via Gemini ────────────────────────────

    def _extract(self, messages):
        """Use Gemini to extract facts, memories, diary, lessons from conversation."""
        if not messages or not self.client:
            return

        recent = messages[-10:]
        conv_text = '\n'.join(
            f"{'user' if m['role'] == 'user' else self.char_name}: "
            f"{m['parts'][0]['text']}"
            for m in recent
        )

        current_user = self._read(self.user_path)
        current_memory = self._read(self.memory_path)
        today_str = date.today().isoformat()

        prompt = (
            "You are a memory extraction system. Analyze this conversation "
            "between a user and a character, and extract structured information.\n\n"
            f"CHARACTER NAME: {self.char_name}\n\n"
            f"CONVERSATION:\n{conv_text}\n\n"
            f"CURRENT USER PROFILE:\n{current_user}\n\n"
            f"CURRENT MEMORY STATE:\n{current_memory}\n\n"
            "Return a JSON object with exactly these keys:\n\n"
            '"user_facts": Array of strings — NEW facts about the user not already '
            "in the profile. Include: name, location, job, relationships, preferences, "
            "habits, important life events, communication style. "
            "Empty array [] if nothing new.\n\n"
            '"memory_items": Array of objects {{"tier": string, "text": string}} — '
            "notable events, decisions, emotional moments, or context NOT already in memory.\n"
            "  - M0: Permanent core facts (user's name, fundamental relationship dynamics)\n"
            "  - M365: Year-level important events\n"
            "  - M90: Quarter-level project/context\n"
            "  - M30: Recent events and short-term context (default for most items)\n"
            "Empty array [] if nothing notable.\n\n"
            '"promotions": Array of objects {{"text_match": string, "from": string, "to": string}} — '
            "if a fact already in M30 keeps coming up or has proven important enough "
            "to be promoted to M90/M365/M0. text_match should be a substring of the existing "
            "memory item. Empty array [] if no promotions.\n\n"
            '"diary": String — 1-2 sentence summary of this conversation segment. '
            'Empty string "" if just trivial greetings.\n\n'
            '"lesson": String or null — if the character responded poorly, made an error, '
            "or there's a behavioral pattern to remember for next time. null if nothing.\n\n"
            "RULES:\n"
            "- Do NOT duplicate facts already present\n"
            "- Be highly selective — only genuinely important information\n"
            "- Each item under 20 words\n"
            "- Most new items should be M30 unless clearly permanent\n"
            "- Respond with ONLY the JSON object, no markdown fences"
        )

        try:
            from google.genai import types as gtypes
            resp = self.client.models.generate_content(
                model=_EXTRACT_MODEL,
                contents=[{"role": "user", "parts": [{"text": prompt}]}],
                config=gtypes.GenerateContentConfig(
                    max_output_tokens=4096,
                    temperature=0.1,
                    response_mime_type='application/json',
                ),
            )

            text = resp.text.strip()
            data = json.loads(text)
            with self._lock:
                self._apply(data, today_str)
        except Exception:
            pass

    def _apply(self, data, today_str):
        """Apply extracted data to memory files."""
        self._apply_user_facts(data.get('user_facts', []))
        self._apply_memory_items(data.get('memory_items', []), today_str)
        self._apply_promotions(data.get('promotions', []), today_str)
        self._apply_diary(data.get('diary', ''), today_str)
        self._apply_lesson(data.get('lesson'), today_str)

    def _apply_user_facts(self, facts):
        if not facts:
            return
        content = self._read(self.user_path)
        changed = False
        for fact in facts:
            fact = fact.strip()
            if fact and fact not in content:
                content += f"\n- {fact}"
                changed = True
        if changed:
            with open(self.user_path, 'w') as f:
                f.write(content)

    def _apply_memory_items(self, items, today_str):
        if not items:
            return
        content = self._read(self.memory_path)
        changed = False

        for item in items:
            tier = item.get('tier', 'M30')
            text = item.get('text', '').strip()
            if not text or text in content:
                continue

            # Build entry with expiry
            days = _TIER_DAYS.get(tier)
            expiry = ''
            if days:
                exp = (date.today() + timedelta(days=days)).isoformat()
                expiry = f' <!-- expires: {exp} -->'

            entry = f"- [{today_str}] {text}{expiry}"
            content = self._insert_into_tier(content, tier, entry)
            changed = True

        if changed:
            with open(self.memory_path, 'w') as f:
                f.write(content)

    def _apply_promotions(self, promotions, today_str):
        """Promote memory items between tiers."""
        if not promotions:
            return
        content = self._read(self.memory_path)
        changed = False

        for promo in promotions:
            text_match = promo.get('text_match', '').strip()
            from_tier = promo.get('from', '')
            to_tier = promo.get('to', '')
            if not text_match or not from_tier or not to_tier:
                continue
            if from_tier == to_tier:
                continue

            # Find the line containing text_match
            lines = content.split('\n')
            found_idx = None
            found_line = None
            for i, line in enumerate(lines):
                if text_match in line and line.strip().startswith('- '):
                    found_idx = i
                    found_line = line
                    break

            if found_idx is None:
                continue

            # Extract the core text (remove date prefix, expiry comment)
            core = re.sub(r'<!--.*?-->', '', found_line).strip()
            core = re.sub(r'^-\s*\[\d{4}-\d{2}-\d{2}\]\s*', '', core).strip()

            # Remove from old location
            lines.pop(found_idx)
            content = '\n'.join(lines)

            # Build new entry in target tier
            days = _TIER_DAYS.get(to_tier)
            expiry = ''
            if days:
                exp = (date.today() + timedelta(days=days)).isoformat()
                expiry = f' <!-- expires: {exp} -->'

            entry = f"- [{today_str}] {core}{expiry}"
            content = self._insert_into_tier(content, to_tier, entry)
            changed = True

        if changed:
            with open(self.memory_path, 'w') as f:
                f.write(content)

    def _insert_into_tier(self, content, tier, entry):
        """Insert an entry line into the correct tier section of memory.md."""
        header = _TIER_HEADERS.get(tier, _TIER_HEADERS['M30'])

        if header not in content:
            content += f'\n{header}\n{entry}\n'
            return content

        idx = content.index(header) + len(header)
        # Find next section boundary
        next_sec = content.find('\n## ', idx)

        if next_sec == -1:
            # Last section — append at end
            content = content.rstrip() + '\n' + entry + '\n'
        else:
            # Insert before next section
            before = content[:next_sec].rstrip()
            after = content[next_sec:]
            content = before + '\n' + entry + after

        return content

    def _apply_diary(self, diary, today_str):
        if not diary or not diary.strip():
            return
        path = self._diary_path()
        existing = self._read(path)
        now_str = datetime.now().strftime('%H:%M')
        if not existing:
            existing = f"# {today_str}"
        existing += f"\n\n## {now_str}\n- {diary}"
        with open(path, 'w') as f:
            f.write(existing)

    def _apply_lesson(self, lesson, today_str):
        if not lesson or not lesson.strip():
            return
        content = self._read(self.lessons_path)
        if lesson in content:
            return
        content += f"\n\n## [{today_str}]\n- {lesson}"
        with open(self.lessons_path, 'w') as f:
            f.write(content)

    # ── History compaction ───────────────────────────────────

    def on_history_compact(self, old_messages):
        """Summarize messages being dropped from sliding window -> diary."""
        if not self.client or not old_messages:
            return

        conv_text = '\n'.join(
            f"{'user' if m['role'] == 'user' else self.char_name}: "
            f"{m['parts'][0]['text']}"
            for m in old_messages
        )

        prompt = (
            "Summarize this conversation in 1-2 sentences. "
            "Focus on: topics discussed, decisions made, user information revealed.\n\n"
            f"CONVERSATION:\n{conv_text}\n\n"
            "Respond with ONLY the summary text."
        )

        try:
            from google.genai import types as gtypes
            resp = self.client.models.generate_content(
                model=_EXTRACT_MODEL,
                contents=[{"role": "user", "parts": [{"text": prompt}]}],
                config=gtypes.GenerateContentConfig(
                    max_output_tokens=256,
                    temperature=0.1,
                ),
            )
            summary = resp.text.strip()
            if not summary:
                return

            with self._lock:
                today_str = date.today().isoformat()
                path = self._diary_path()
                existing = self._read(path)
                now_str = datetime.now().strftime('%H:%M')
                if not existing:
                    existing = f"# {today_str}"
                existing += f"\n\n## Compacted ({now_str})\n- {summary}"
                with open(path, 'w') as f:
                    f.write(existing)
        except Exception:
            pass

    # ── Session end ──────────────────────────────────────────

    def on_session_end(self, chat_history):
        """Final extraction when the user exits. Runs synchronously."""
        if self.client and chat_history:
            self._extract(chat_history)
