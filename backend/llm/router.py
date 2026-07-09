"""Multi-provider LLM router with local fallback."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import httpx

# Load project .env if present (does not override already-exported env)
try:
    from dotenv import load_dotenv

    _root = Path(__file__).resolve().parents[2]
    load_dotenv(_root / ".env", override=False)
except Exception:
    pass


@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str
    ok: bool = True
    error: Optional[str] = None


class LLMRouter:
    def __init__(self) -> None:
        self.mode = os.getenv("SIMECONOMY_LLM_MODE", "auto").lower()
        self.providers = self._build_provider_list()

    def _build_provider_list(self) -> list[dict[str, str]]:
        providers: list[dict[str, str]] = []
        if os.getenv("DEEPSEEK_API_KEY"):
            providers.append(
                {
                    "name": "deepseek",
                    "api_style": "openai",
                    "base_url": os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
                    "api_key": os.getenv("DEEPSEEK_API_KEY", ""),
                    "model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
                }
            )
        # Kimi / Moonshot
        kimi_key = os.getenv("MOONSHOT_API_KEY") or os.getenv("KIMI_API_KEY")
        if kimi_key:
            providers.append(
                {
                    "name": "kimi",
                    "api_style": "openai",
                    "base_url": os.getenv("MOONSHOT_BASE_URL", "https://api.moonshot.cn/v1"),
                    "api_key": kimi_key,
                    "model": os.getenv("KIMI_MODEL", "moonshot-v1-8k"),
                }
            )
        if os.getenv("MINIMAX_API_KEY"):
            # Hermes uses Anthropic-compatible MiniMax endpoint by default
            providers.append(
                {
                    "name": "minimax",
                    "api_style": os.getenv("MINIMAX_API_STYLE", "anthropic"),
                    "base_url": os.getenv(
                        "MINIMAX_BASE_URL", "https://api.minimax.io/anthropic"
                    ),
                    "api_key": os.getenv("MINIMAX_API_KEY", ""),
                    "model": os.getenv("MINIMAX_MODEL", "MiniMax-M3"),
                }
            )
        if os.getenv("OPENAI_API_KEY"):
            providers.append(
                {
                    "name": "openai",
                    "api_style": "openai",
                    "base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
                    "api_key": os.getenv("OPENAI_API_KEY", ""),
                    "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                }
            )
        local_base = os.getenv("LOCAL_LLM_BASE_URL")
        if local_base:
            providers.append(
                {
                    "name": "local",
                    "api_style": "openai",
                    "base_url": local_base.rstrip("/"),
                    "api_key": os.getenv("LOCAL_LLM_API_KEY", "ollama"),
                    "model": os.getenv("LOCAL_LLM_MODEL", "qwen2.5:7b"),
                }
            )
        return providers

    def available(self) -> bool:
        if self.mode == "off":
            return False
        if self.mode == "local":
            return any(p["name"] == "local" for p in self.providers)
        return len(self.providers) > 0

    def complete(
        self,
        system: str,
        user: str,
        temperature: float = 0.2,
        max_tokens: int = 800,
    ) -> LLMResponse:
        if self.mode == "off":
            return LLMResponse("", "none", "none", ok=False, error="LLM mode off")

        chain = self.providers
        if self.mode == "local":
            chain = [p for p in self.providers if p["name"] == "local"]
        elif self.mode == "cloud":
            chain = [p for p in self.providers if p["name"] != "local"]

        last_err = "no providers configured"
        for p in chain:
            try:
                if p.get("api_style") == "anthropic":
                    text = self._chat_anthropic_compatible(
                        p, system, user, temperature, max_tokens
                    )
                else:
                    text = self._chat_openai_compatible(
                        p, system, user, temperature, max_tokens
                    )
                return LLMResponse(text=text, provider=p["name"], model=p["model"], ok=True)
            except Exception as e:
                last_err = f"{p['name']}: {e}"
                continue
        return LLMResponse("", "none", "none", ok=False, error=last_err)

    def _chat_openai_compatible(
        self,
        provider: dict[str, str],
        system: str,
        user: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        url = f"{provider['base_url'].rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {provider['api_key']}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": provider["model"],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        with httpx.Client(timeout=60.0) as client:
            r = client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
        return data["choices"][0]["message"]["content"]

    def _chat_anthropic_compatible(
        self,
        provider: dict[str, str],
        system: str,
        user: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """MiniMax (and similar) Anthropic Messages API."""
        base = provider["base_url"].rstrip("/")
        # accept either .../anthropic or .../anthropic/v1
        if base.endswith("/v1"):
            url = f"{base}/messages"
        else:
            url = f"{base}/v1/messages"
        headers = {
            "x-api-key": provider["api_key"],
            "Authorization": f"Bearer {provider['api_key']}",
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        payload = {
            "model": provider["model"],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        with httpx.Client(timeout=90.0) as client:
            r = client.post(url, headers=headers, json=payload)
            if r.status_code >= 400:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:400]}")
            data = r.json()
        # Anthropic content blocks
        content = data.get("content")
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    parts.append(block)
            text = "".join(parts)
            if text:
                return text
        if isinstance(content, str):
            return content
        # fallback shapes
        if "choices" in data:
            return data["choices"][0]["message"]["content"]
        raise RuntimeError(f"unexpected minimax response keys: {list(data)[:12]}")

    @staticmethod
    def parse_json_actions(text: str) -> list[dict[str, Any]]:
        """Extract a JSON list of actions from model output."""
        text = text.strip()
        if not text:
            return []
        if "```" in text:
            parts = text.split("```")
            for part in parts:
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                if part.startswith("[") or part.startswith("{"):
                    text = part
                    break
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            start = text.find("[")
            end = text.rfind("]")
            if start >= 0 and end > start:
                try:
                    data = json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    return []
            else:
                return []
        if isinstance(data, dict):
            if "actions" in data:
                data = data["actions"]
            else:
                data = [data]
        if not isinstance(data, list):
            return []
        return [x for x in data if isinstance(x, dict) and "tool" in x]
