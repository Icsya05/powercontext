"""MiniMax client - the code modifier of the SDD context module.

MiniMax is reached through its OpenAI-compatible endpoint.  The module sends
the development context that seekdb produced and asks for a unified diff.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .config import MiniMaxConfig

#: MiniMax emits a reasoning block before the answer.
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
#: The model is asked for a fenced block; accept any language tag.
_DIFF_FENCE_RE = re.compile(r"```[a-zA-Z0-9_+.-]*[ \t]*\r?\n(?P<body>.*?)```", re.DOTALL)


class MiniMaxError(RuntimeError):
    """Raised when MiniMax cannot be reached or answers unexpectedly."""


@dataclass
class MiniMaxResult:
    content: str
    usage: dict[str, Any]
    request_id: str
    model: str
    patch: str


class MiniMaxClient:
    """Call the MiniMax OpenAI-compatible chat completions endpoint."""

    def __init__(self, config: MiniMaxConfig, recorder=None) -> None:
        self.config = config
        self.recorder = recorder

    def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 32768,
        temperature: float = 0.2,
    ) -> MiniMaxResult:
        """One chat completion.

        ``max_tokens`` has to be generous: MiniMax-M3 is a reasoning model and
        spends a large part of the budget on its ``<think>`` block before it
        starts writing the answer.
        """
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        request = urllib.request.Request(
            f"{self.config.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=600) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            if self.recorder is not None:
                self.recorder.record("minimax.error", status=exc.code, detail=detail[:800])
            raise MiniMaxError(f"MiniMax HTTP {exc.code}: {detail[:800]}") from exc
        except Exception as exc:  # noqa: BLE001
            if self.recorder is not None:
                self.recorder.record("minimax.error", detail=str(exc)[:400])
            raise MiniMaxError(f"cannot reach MiniMax at {self.config.base_url}: {exc}") from exc

        choice = (body.get("choices") or [{}])[0]
        content = (choice.get("message") or {}).get("content") or ""
        usage = body.get("usage") or {}

        if self.recorder is not None:
            self.recorder.record(
                "minimax.call",
                model=self.config.model,
                endpoint=f"{self.config.base_url}/chat/completions",
                request_id=body.get("id"),
                usage=usage,
                system_chars=len(system),
                user_chars=len(user),
                answer_chars=len(content),
                answer=content,
            )

        return MiniMaxResult(
            content=content,
            usage=usage,
            request_id=str(body.get("id") or ""),
            model=self.config.model,
            patch=self.extract_patch(content),
        )

    @staticmethod
    def strip_thinking(content: str) -> str:
        """Remove MiniMax's ``<think>`` reasoning block."""
        return _THINK_RE.sub("", content).strip()

    @classmethod
    def extract_patch(cls, content: str) -> str:
        """Pull the unified diff out of the model answer.

        The model is asked for one fenced block containing a unified diff.
        When the fence is missing the raw answer is returned so the caller
        can still try to apply it.
        """
        cleaned = cls.strip_thinking(content)
        matches = _DIFF_FENCE_RE.findall(cleaned)
        if matches:
            return matches[0].strip() + "\n"
        return cleaned.strip() + "\n"

    @classmethod
    def extract_file(cls, content: str) -> str:
        """Pull the body of one fenced code block out of the model answer."""
        cleaned = cls.strip_thinking(content)
        matches = _DIFF_FENCE_RE.findall(cleaned)
        if matches:
            return matches[0].strip() + "\n"
        return cleaned.strip() + "\n"
