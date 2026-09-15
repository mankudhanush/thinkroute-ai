from __future__ import annotations

import json
import logging
import re
from collections import OrderedDict

import httpx

from app.services.classification import (
    VALID_COMPLEXITIES,
    VALID_INTENTS,
    ClassificationResult,
    enrich,
)

logger = logging.getLogger(__name__)

# String confidence levels some models emit instead of a float.
CONFIDENCE_WORDS = {"low": 0.4, "medium": 0.7, "high": 0.9}

# The intent model only needs to produce THREE fields — the rest of the
# metadata is derived deterministically in classification.enrich(). Keeping
# the schema tiny lets us cap max_tokens low so the LLM path stays fast.
CLASSIFICATION_SYSTEM_PROMPT = """You are a strict intent classification engine. You do NOT answer the user's question. You ONLY return a single minified JSON object.

Return exactly:
{"intent": <one of: coding, debugging, reasoning, education, mathematics, summarization, translation, creative_writing, document_analysis, research, conversation, general_chat>, "complexity": <low|medium|high>, "confidence": <number 0.0-1.0>}

complexity = the EFFORT and SCOPE the task requires, NOT the prompt length.
- low: trivial, single-step, tiny output (a greeting, a one-line fix, translate a sentence).
- medium: one focused artifact (a single function/script/API, explain one concept).
- high: large multi-component work (build an app/website/system, design an architecture, summarize a whole paper).
Example: "Build a website" is short but complexity is high.

Return ONLY the JSON. No markdown, no code fences, no explanation."""


class IntentClassifier:
    """qwen3:4b used strictly as a classifier — it NEVER answers the prompt.

    Called via Ollama's native /api/chat with format="json" (keeps the model's
    <think> trace out of the returned content) and a tiny token budget. Results
    are memoised per-prompt so repeated prompts are instant.
    """

    def __init__(
        self,
        model: str = "qwen3:4b",
        api_base: str = "http://localhost:11434",
        cache_size: int = 512,
    ) -> None:
        self.model = model.removeprefix("ollama/")
        self.api_base = api_base.rstrip("/")
        self.timeout_seconds = 90.0
        self._cache: OrderedDict[str, ClassificationResult] = OrderedDict()
        self._cache_size = cache_size

    async def classify(self, prompt: str) -> ClassificationResult:
        key = prompt.strip().lower()
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            logger.info("[IntentClassifier] cache hit → %s/%s", cached.intent, cached.complexity)
            return cached

        logger.info("[IntentClassifier] Classifying via qwen3:4b (len=%d): %.80s...", len(prompt), prompt)

        result = ClassificationResult.fallback()
        for attempt in range(2):
            try:
                raw = await self._call_model(prompt)
                parsed = self._parse(raw)
                if parsed is not None:
                    result = parsed
                    logger.info(
                        "[IntentClassifier] ✓ %s/%s conf=%.2f",
                        result.intent, result.complexity, result.confidence,
                    )
                    break
                logger.warning("[IntentClassifier] Parse failed on attempt %d, retrying...", attempt + 1)
            except Exception as exc:
                logger.warning("[IntentClassifier] Model call failed on attempt %d: %s", attempt + 1, exc)
        else:
            logger.warning("[IntentClassifier] All attempts failed, using fallback")

        self._remember(key, result)
        return result

    def _remember(self, key: str, result: ClassificationResult) -> None:
        self._cache[key] = result
        self._cache.move_to_end(key)
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)

    async def _call_model(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": CLASSIFICATION_SYSTEM_PROMPT},
                # /no_think asks qwen3 to skip its reasoning trace for speed.
                {"role": "user", "content": f"/no_think\nClassify this prompt:\n\n{prompt}"},
            ],
            "stream": False,
            "format": "json",
            "think": False,
            "options": {
                "temperature": 0,
                "top_p": 0,
                "num_predict": 60,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(f"{self.api_base}/api/chat", json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            logger.warning("[IntentClassifier] Ollama request failed: %s", exc)
            return ""

        message = data.get("message") or {}
        return message.get("content") or ""

    def _parse(self, raw: str) -> ClassificationResult | None:
        if not raw:
            return None

        text = raw.strip()
        # Defensive cleanup in case thinking tags / fences leak into content.
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        text = re.sub(r"<think>.*", "", text, flags=re.DOTALL).strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        text = text.strip()

        start, end = text.find("{"), text.rfind("}") + 1
        if start == -1 or end == 0:
            logger.warning("[IntentClassifier] No JSON braces found (len=%d)", len(text))
            return None

        try:
            data = json.loads(text[start:end])
        except json.JSONDecodeError as exc:
            logger.debug("[IntentClassifier] JSON parse error: %s — raw: %.200s", exc, text)
            return None
        if not isinstance(data, dict):
            return None

        intent = str(data.get("intent", "general_chat")).lower().strip()
        complexity = str(data.get("complexity", "medium")).lower().strip()
        confidence = self._coerce_confidence(data.get("confidence", 0.7))

        if intent not in VALID_INTENTS:
            intent = "general_chat"
        if complexity not in VALID_COMPLEXITIES:
            complexity = "medium"

        # Derive the full metadata contract from the three core fields.
        return enrich(intent, complexity, confidence, source="model")

    @staticmethod
    def _coerce_confidence(value: object) -> float:
        if isinstance(value, bool):
            return 0.7
        if isinstance(value, (int, float)):
            return max(0.0, min(1.0, float(value)))
        if isinstance(value, str):
            norm = value.strip().lower()
            if norm in CONFIDENCE_WORDS:
                return CONFIDENCE_WORDS[norm]
            try:
                return max(0.0, min(1.0, float(norm)))
            except ValueError:
                return 0.7
        return 0.7
