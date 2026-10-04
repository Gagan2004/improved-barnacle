from __future__ import annotations

import json
import threading
from typing import Any, Literal

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from apps.config import GEMINI_API_KEY, GEMINI_MODEL

_CLIENT: genai.Client | None = None
_LOCK = threading.Lock()


class GoalSpec(BaseModel):
    restated_goal: str
    success_criteria: list[str]
    notes: list[str] = Field(default_factory=list)


class AgentDecision(BaseModel):
    think: str
    action: Literal["tool", "ask_user", "finish"]
    tool_name: str | None = None
    tool_args_json: str = "{}"
    question: str | None = None
    summary: str | None = None


class VerifyReport(BaseModel):
    passed: bool
    reason: str
    unmatched: list[str] = Field(default_factory=list)


def client() -> genai.Client:
    global _CLIENT
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set. Copy .env.example to .env.")
    if _CLIENT is None:
        _CLIENT = genai.Client(api_key=GEMINI_API_KEY)
    return _CLIENT


def _parse_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text[:-3]
    return json.loads(text)


def json_config(temperature: float = 0.2) -> types.GenerateContentConfig:
    # Clerk implements its own tool loop; disable Gemini AFC so generate_content
    # does not warn or try to auto-call Python functions.
    return types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=temperature,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )


def generate_json(prompt: str, schema_name: str) -> dict[str, Any]:
    with _LOCK:
        response = client().models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=json_config(),
        )
    raw = response.text
    if not raw:
        raise RuntimeError("Gemini returned an empty response")
    data = _parse_json(raw)
    if schema_name == "goal":
        return GoalSpec.model_validate(data).model_dump()
    if schema_name == "decision":
        return AgentDecision.model_validate(data).model_dump()
    if schema_name == "verify":
        return VerifyReport.model_validate(data).model_dump()
    return data
