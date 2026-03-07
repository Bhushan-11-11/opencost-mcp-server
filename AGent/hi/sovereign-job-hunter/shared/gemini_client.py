from __future__ import annotations

import json
import time
from dataclasses import dataclass

from google import genai
from google.genai import types


@dataclass
class GeminiConfig:
    api_key: str
    model: str
    temperature: float
    timeout_seconds: int


class GeminiClient:
    def __init__(self, config: GeminiConfig | None = None) -> None:
        if config is None:
            raise RuntimeError("GeminiConfig is required; no hardcoded defaults are allowed.")
        self.config = config
        self.client = genai.Client(
            api_key=self.config.api_key,
            http_options=types.HttpOptions(timeout=self.config.timeout_seconds * 1000),
        )

    def healthcheck(self) -> bool:
        try:
            target = self.config.model.strip()
            target_short = target.split("/")[-1]
            for model in self.client.models.list():
                name = getattr(model, "name", "") or ""
                short = name.split("/")[-1]
                if target == name or target == short or target_short == short:
                    return True
            return False
        except Exception:
            return False

    def generate(self, prompt: str, json_mode: bool = False, max_output_tokens: int = 2048) -> str:
        cfg_kwargs: dict[str, object] = {
            "temperature": self.config.temperature,
            "max_output_tokens": max_output_tokens,
        }
        if json_mode:
            cfg_kwargs["response_mime_type"] = "application/json"
        response = self.client.models.generate_content(
            model=self.config.model,
            contents=prompt,
            config=types.GenerateContentConfig(**cfg_kwargs),
        )
        text = (response.text or "").strip()
        if not text:
            raise RuntimeError("Gemini response text is empty.")
        return text

    def generate_json(self, prompt: str) -> dict:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                text = self.generate(prompt=prompt, json_mode=True, max_output_tokens=2048)
                return self._parse_json_text(text)
            except Exception as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(1.0 * (attempt + 1))
        raise RuntimeError(f"Gemini JSON generation failed: {last_error}")

    @staticmethod
    def _parse_json_text(text: str) -> dict:
        raw = text.strip()
        if raw.startswith("```"):
            lines = raw.splitlines()
            if len(lines) >= 3 and lines[-1].strip().startswith("```"):
                raw = "\n".join(lines[1:-1]).strip()
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = raw[start : end + 1]
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        raise RuntimeError("Gemini JSON response is not a valid object.")

    def embed_text(self, text: str, embedding_model: str) -> list[float]:
        response = self.client.models.embed_content(
            model=embedding_model,
            contents=text,
        )
        if not response.embeddings:
            raise RuntimeError("Gemini embedding response missing embeddings.")
        values = response.embeddings[0].values
        if not values:
            raise RuntimeError("Gemini embedding vector is empty.")
        return [float(v) for v in values]
