#!/usr/bin/env python3
"""
providers.py — LLM provider abstraction for ttypal chat and memory extraction.

Supported providers:
  - gemini:  Google Gemini (also used for view generation)
  - openai:  OpenAI API (GPT-4o, GPT-4o-mini, etc.)
  - anthropic: Anthropic Claude
  - ollama:  Local models via Ollama (OpenAI-compatible)
  - openai-compatible: Any OpenAI-compatible endpoint
"""

import os
from abc import ABC, abstractmethod


class ChatProvider(ABC):
    """Abstract LLM provider for chat and text generation."""

    @abstractmethod
    def stream_chat(self, messages, system_prompt, max_tokens=2048):
        """Yield text chunks for streaming chat.

        Args:
            messages: [{"role": "user"|"assistant", "content": str}, ...]
            system_prompt: System prompt string.
            max_tokens: Maximum tokens to generate.
        Yields:
            str: Text chunks as they arrive.
        """
        ...

    @abstractmethod
    def generate(self, prompt, max_tokens=4096, temperature=0.1, json_mode=False):
        """Generate a complete text response (non-streaming).

        Args:
            prompt: User prompt string.
            max_tokens: Maximum tokens.
            temperature: Sampling temperature.
            json_mode: If True, request JSON output.
        Returns:
            str: Complete response text.
        """
        ...


# ─── Gemini ──────────────────────────────────────────────


class GeminiProvider(ChatProvider):
    def __init__(self, api_key, chat_model='gemini-3-flash-preview',
                 extract_model='gemini-3.1-flash-lite-preview'):
        try:
            from google import genai
            from google.genai import types as gtypes
        except ImportError:
            raise ImportError(
                "Gemini provider requires google-genai. "
                "Install with: pip install ttypal[gemini]"
            )
        self._gtypes = gtypes
        self.client = genai.Client(api_key=api_key)
        self.chat_model = chat_model
        self.extract_model = extract_model

    def stream_chat(self, messages, system_prompt, max_tokens=2048):
        contents = []
        for m in messages:
            role = 'model' if m['role'] == 'assistant' else 'user'
            contents.append({"role": role, "parts": [{"text": m['content']}]})

        config = self._gtypes.GenerateContentConfig(
            system_instruction=system_prompt,
            max_output_tokens=max_tokens,
        )
        stream = self.client.models.generate_content_stream(
            model=self.chat_model,
            contents=contents,
            config=config,
        )
        for chunk in stream:
            if chunk.text:
                yield chunk.text

    def generate(self, prompt, max_tokens=4096, temperature=0.1, json_mode=False):
        config = self._gtypes.GenerateContentConfig(
            max_output_tokens=max_tokens,
            temperature=temperature,
        )
        if json_mode:
            config.response_mime_type = 'application/json'

        resp = self.client.models.generate_content(
            model=self.extract_model,
            contents=[{"role": "user", "parts": [{"text": prompt}]}],
            config=config,
        )
        return resp.text.strip()


# ─── OpenAI (also covers Ollama & compatible endpoints) ──


class OpenAIProvider(ChatProvider):
    def __init__(self, api_key=None, base_url=None,
                 chat_model='gpt-4o-mini', extract_model=None):
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError(
                "OpenAI provider requires the openai package. "
                "Install with: pip install ttypal[openai]"
            )
        kwargs = {}
        if api_key:
            kwargs['api_key'] = api_key
        if base_url:
            kwargs['base_url'] = base_url
        self.client = OpenAI(**kwargs)
        self.chat_model = chat_model
        self.extract_model = extract_model or chat_model

    def stream_chat(self, messages, system_prompt, max_tokens=2048):
        msgs = [{"role": "system", "content": system_prompt}] + [
            {"role": m["role"], "content": m["content"]} for m in messages
        ]
        stream = self.client.chat.completions.create(
            model=self.chat_model,
            messages=msgs,
            max_tokens=max_tokens,
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content

    def generate(self, prompt, max_tokens=4096, temperature=0.1, json_mode=False):
        kwargs = {
            'model': self.extract_model,
            'messages': [{"role": "user", "content": prompt}],
            'max_tokens': max_tokens,
            'temperature': temperature,
        }
        if json_mode:
            kwargs['response_format'] = {"type": "json_object"}
        resp = self.client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content.strip()


# ─── Anthropic ───────────────────────────────────────────


class AnthropicProvider(ChatProvider):
    def __init__(self, api_key=None,
                 chat_model='claude-sonnet-4-20250514', extract_model=None):
        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "Anthropic provider requires the anthropic package. "
                "Install with: pip install ttypal[anthropic]"
            )
        kwargs = {}
        if api_key:
            kwargs['api_key'] = api_key
        self.client = anthropic.Anthropic(**kwargs)
        self.chat_model = chat_model
        self.extract_model = extract_model or chat_model

    def stream_chat(self, messages, system_prompt, max_tokens=2048):
        msgs = [{"role": m["role"], "content": m["content"]} for m in messages]
        with self.client.messages.stream(
            model=self.chat_model,
            system=system_prompt,
            messages=msgs,
            max_tokens=max_tokens,
        ) as stream:
            for text in stream.text_stream:
                yield text

    def generate(self, prompt, max_tokens=4096, temperature=0.1, json_mode=False):
        resp = self.client.messages.create(
            model=self.extract_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return resp.content[0].text.strip()


# ─── OpenClaw (OpenAI-compatible gateway) ────────────────


class OpenClawProvider(ChatProvider):
    """Chat via OpenClaw Gateway. Memory and personality managed by OpenClaw.

    OpenClaw exposes /v1/chat/completions (OpenAI-compatible).
    Session persistence via `user` field; agent via `x-openclaw-agent-id`.
    System prompt is handled by OpenClaw's SOUL.md — not passed from ttypal.
    """

    # Flag for live.py to skip ttypal's built-in memory management
    manages_memory = True

    def __init__(self, base_url='http://localhost:18789/v1',
                 token=None, agent_id='main', user_id=None):
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError(
                "OpenClaw provider requires the openai package. "
                "Install with: pip install ttypal[openai]"
            )
        self.client = OpenAI(
            api_key=token or 'openclaw',
            base_url=base_url,
            default_headers={
                'x-openclaw-agent-id': agent_id,
                'x-openclaw-thinking': 'off',
            },
        )
        self.user_id = user_id

    def init_session(self, character_name):
        """Set user_id for session persistence in OpenClaw."""
        self.user_id = f'ttypal-{character_name}'

    def stream_chat(self, messages, system_prompt, max_tokens=2048):
        # Don't prepend system prompt — OpenClaw uses SOUL.md
        msgs = [{"role": m["role"], "content": m["content"]} for m in messages]
        kwargs = {
            'model': 'openclaw',
            'messages': msgs,
            'max_tokens': max_tokens,
            'stream': True,
        }
        if self.user_id:
            kwargs['user'] = self.user_id

        stream = self.client.chat.completions.create(**kwargs)
        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content

    def generate(self, prompt, max_tokens=4096, temperature=0.1, json_mode=False):
        kwargs = {
            'model': 'openclaw',
            'messages': [{"role": "user", "content": prompt}],
            'max_tokens': max_tokens,
            'temperature': temperature,
        }
        if self.user_id:
            kwargs['user'] = self.user_id
        if json_mode:
            kwargs['response_format'] = {"type": "json_object"}
        resp = self.client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content.strip()


# ─── CLI (claude -p, etc.) ───────────────────────────────


class CLIProvider(ChatProvider):
    """Chat via `claude -p` with session persistence via `-r`.

    Session flow:
      1st message: claude -p --session-id <uuid> --system-prompt <soul+memory> "msg"
      Nth message: claude -p -r <uuid> "msg"

    Claude Code manages conversation history — no need to pack history into prompts.
    Memory extraction uses separate one-shot calls.
    """

    def __init__(self, command='claude', model=None, session_id=None):
        import shutil
        self.command = command
        self.model = model
        self._session_id = session_id  # set per-character in init_session()
        self._session_started = False
        if not shutil.which(command):
            raise FileNotFoundError(
                f"'{command}' not found in PATH. "
                f"Install it or choose a different provider."
            )

    def init_session(self, character_name):
        """Generate a deterministic session ID for this character."""
        import uuid
        self._session_id = str(uuid.uuid5(
            uuid.NAMESPACE_DNS, f'ttypal.{character_name}'
        ))
        self._session_started = False

    def stream_chat(self, messages, system_prompt, max_tokens=2048):
        import subprocess

        # Only send the latest user message — Claude Code session has the rest
        last_msg = messages[-1]['content'] if messages else ''

        cmd = [self.command, '-p']

        if not self._session_started and self._session_id:
            # First message: create session with system prompt
            cmd += ['--session-id', self._session_id]
            cmd += ['--system-prompt', system_prompt]
            self._session_started = True
        elif self._session_id:
            # Resume existing session
            cmd += ['-r', self._session_id]

        if self.model:
            cmd += ['--model', self.model]

        cmd.append(last_msg)

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        while True:
            chunk = proc.stdout.read(1)
            if not chunk:
                break
            yield chunk

        proc.wait()
        if proc.returncode != 0:
            err = proc.stderr.read()[:200]
            self._session_started = False  # retry session creation next time
            yield f' (error: {err})'

    def generate(self, prompt, max_tokens=4096, temperature=0.1, json_mode=False):
        """One-shot generation (for memory extraction). No session."""
        import subprocess
        cmd = [self.command, '-p']
        if self.model:
            cmd += ['--model', self.model]
        cmd.append(prompt)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(f"{self.command} failed: {result.stderr[:200]}")
        return result.stdout.strip()


# ─── Factory ─────────────────────────────────────────────


def create_provider(cfg):
    """Create a ChatProvider from config dict. Returns None if unconfigured."""
    provider_name = cfg.get('chat_provider', 'gemini')

    if provider_name == 'gemini':
        api_key = (cfg.get('gemini_api_key', '')
                   or os.environ.get('GEMINI_API_KEY', ''))
        if not api_key:
            return None
        return GeminiProvider(
            api_key,
            chat_model=cfg.get('chat_model', 'gemini-3-flash-preview'),
            extract_model=cfg.get('extract_model', 'gemini-3.1-flash-lite-preview'),
        )

    elif provider_name == 'openai':
        api_key = (cfg.get('openai_api_key', '')
                   or os.environ.get('OPENAI_API_KEY', ''))
        if not api_key:
            return None
        return OpenAIProvider(
            api_key=api_key,
            chat_model=cfg.get('chat_model', 'gpt-4o-mini'),
        )

    elif provider_name == 'anthropic':
        api_key = (cfg.get('anthropic_api_key', '')
                   or os.environ.get('ANTHROPIC_API_KEY', ''))
        if not api_key:
            return None
        return AnthropicProvider(
            api_key=api_key,
            chat_model=cfg.get('chat_model', 'claude-sonnet-4-20250514'),
        )

    elif provider_name == 'ollama':
        base_url = cfg.get('ollama_base_url', 'http://localhost:11434/v1')
        return OpenAIProvider(
            api_key='ollama',
            base_url=base_url,
            chat_model=cfg.get('chat_model', 'llama3.2'),
        )

    elif provider_name == 'openai-compatible':
        api_key = (cfg.get('chat_api_key', '')
                   or os.environ.get('CHAT_API_KEY', ''))
        base_url = cfg.get('chat_base_url', '')
        if not base_url:
            return None
        return OpenAIProvider(
            api_key=api_key or 'none',
            base_url=base_url,
            chat_model=cfg.get('chat_model', ''),
        )

    elif provider_name == 'claude-cli':
        command = cfg.get('cli_command', 'claude')
        model = cfg.get('chat_model')
        return CLIProvider(command=command, model=model)

    elif provider_name == 'openclaw':
        base_url = cfg.get('openclaw_url', 'http://localhost:18789/v1')
        token = cfg.get('openclaw_token', '')
        agent_id = cfg.get('openclaw_agent_id', 'main')
        return OpenClawProvider(
            base_url=base_url,
            token=token or None,
            agent_id=agent_id,
        )

    return None
