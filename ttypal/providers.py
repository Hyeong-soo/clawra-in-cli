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


# ─── CLI (claude -p, etc.) ───────────────────────────────


class CLIProvider(ChatProvider):
    """Chat via CLI tools like `claude -p`. No API key needed."""

    def __init__(self, command='claude', args=None):
        import shutil
        self.command = command
        self.args = args if args is not None else ['-p']
        if not shutil.which(command):
            raise FileNotFoundError(
                f"'{command}' not found in PATH. "
                f"Install it or choose a different provider."
            )

    def _build_prompt(self, messages, system_prompt=None):
        parts = []
        if system_prompt:
            parts.append(f"<system>\n{system_prompt}\n</system>\n")
        for m in messages:
            tag = "user" if m["role"] == "user" else "assistant"
            parts.append(f"<{tag}>\n{m['content']}\n</{tag}>\n")
        return '\n'.join(parts)

    def stream_chat(self, messages, system_prompt, max_tokens=2048):
        import subprocess
        prompt = self._build_prompt(messages, system_prompt)
        proc = subprocess.Popen(
            [self.command] + self.args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        proc.stdin.write(prompt)
        proc.stdin.close()

        while True:
            chunk = proc.stdout.read(1)
            if not chunk:
                break
            yield chunk

        proc.wait()
        if proc.returncode != 0:
            err = proc.stderr.read()[:200]
            yield f' (error: {err})'

    def generate(self, prompt, max_tokens=4096, temperature=0.1, json_mode=False):
        import subprocess
        result = subprocess.run(
            [self.command] + self.args,
            input=prompt,
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
        return CLIProvider(command=command)

    return None
