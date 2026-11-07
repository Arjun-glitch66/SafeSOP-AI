"""
Provider interface for structured LLM output: generate(prompt, schema) -> parsed pydantic object.

Selected by environment variables:
  LLM_PROVIDER           gemini (default) | ollama
  LLM_FALLBACK_PROVIDER  empty (default: no fallback) | gemini | ollama
  GEMINI_API_KEY, GEMINI_MODEL           for gemini
  OLLAMA_URL (default http://localhost:11434), OLLAMA_MODEL   for ollama (a local model)

The primary provider retries on its own (the Gemini SDK retries 429/5xx with backoff). Output
that fails `validate` with OutputValidationError (cut off, blocked, empty) is asked for again,
up to LLM_OUTPUT_RETRIES more times (default 1). If the primary still fails, the fallback runs. A fallback is never
silent: the result says fallback_used=True with the reason, the caller stores both on the
version, and a warning is logged.
"""
import json
import logging
import os
import urllib.error
import urllib.request

from google import genai
from google.genai import types

logger = logging.getLogger("safesop.llm")

RETRY_STATUS_CODES = [429, 500, 502, 503, 504]


class OutputValidationError(RuntimeError):
    """The provider answered, but the output is unusable (truncated, blocked, empty). Worth one more try."""


def output_retries():
    try:
        return max(0, int(os.getenv("LLM_OUTPUT_RETRIES", "1")))
    except ValueError:
        return 1


class GeminiProvider:
    name = "gemini"

    def __init__(self, model=None):
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.model = model or os.getenv("GEMINI_MODEL")

    def generate(self, prompt, schema, system_instruction=None, temperature=None):
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured. Add it to the project's .env file.")
        if not self.model:
            raise RuntimeError("GEMINI_MODEL is not configured. Add a model ID available to your API key "
                               "to the project's .env file.")
        client = genai.Client(
            api_key=self.api_key,
            http_options=types.HttpOptions(
                timeout=120_000,  # milliseconds
                # The SDK retries rate limits (429) and server errors with exponential backoff.
                retry_options=types.HttpRetryOptions(attempts=4, http_status_codes=RETRY_STATUS_CODES),
            ),
        )
        response = client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=temperature,
                response_mime_type="application/json",
                response_schema=schema,
            ),
        )
        candidates = getattr(response, "candidates", None) or []
        reason = getattr(candidates[0], "finish_reason", None) if candidates else None
        usage = getattr(response, "usage_metadata", None)
        return {
            "parsed": response.parsed if isinstance(response.parsed, schema) else None,
            "finish_reason": getattr(reason, "name", reason),
            "provider": self.name, "model": self.model,
            "input_tokens": getattr(usage, "prompt_token_count", None),
            "output_tokens": getattr(usage, "candidates_token_count", None),
        }


class OllamaProvider:
    """A local model served by Ollama. Structured output via its `format` JSON schema."""
    name = "ollama"

    def __init__(self, model=None):
        self.url = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
        self.model = model or os.getenv("OLLAMA_MODEL")

    def generate(self, prompt, schema, system_instruction=None, temperature=None):
        if not self.model:
            raise RuntimeError("OLLAMA_MODEL is not configured.")
        messages = ([{"role": "system", "content": system_instruction}] if system_instruction else []) + [
            {"role": "user", "content": prompt}]
        body = {"model": self.model, "messages": messages, "stream": False,
                "format": schema.model_json_schema(), "options": {"temperature": temperature}}
        request = urllib.request.Request(f"{self.url}/api/chat", data=json.dumps(body).encode("utf-8"),
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Ollama at {self.url} is not reachable: {exc.reason}") from None
        try:
            parsed = schema.model_validate_json(payload["message"]["content"])
        except (KeyError, ValueError):
            parsed = None
        return {
            "parsed": parsed, "finish_reason": payload.get("done_reason"),
            "provider": self.name, "model": self.model,
            "input_tokens": payload.get("prompt_eval_count"), "output_tokens": payload.get("eval_count"),
        }


PROVIDERS = {"gemini": GeminiProvider, "ollama": OllamaProvider}


def make_provider(name, model=None):
    if name not in PROVIDERS:
        raise RuntimeError(f"Unknown LLM provider '{name}'. Use one of: {', '.join(PROVIDERS)}.")
    return PROVIDERS[name](model)


def generate(prompt, schema, system_instruction=None, temperature=None, model=None, validate=None):
    """Structured generation with an optional, always-recorded fallback.

    `validate(result)` raises if the output is unusable (e.g. a truncated draft); that counts
    as a failure of the provider. `model` overrides the primary provider's model only.
    Returns the provider result plus fallback_used and fallback_reason.
    """
    primary = os.getenv("LLM_PROVIDER", "gemini").strip().lower()
    fallback = os.getenv("LLM_FALLBACK_PROVIDER", "").strip().lower()

    def attempt(provider):
        """Call the provider; ask again (a fresh sample) while the output fails validation."""
        for tries in range(1, output_retries() + 2):
            result = provider.generate(prompt, schema, system_instruction=system_instruction, temperature=temperature)
            try:
                if validate:
                    validate(result)
                return {**result, "attempts": tries}
            except OutputValidationError as exc:
                if tries > output_retries():
                    raise
                logger.warning("%s returned unusable output (%s); asking again.", provider.name, exc)
        raise AssertionError("unreachable")

    try:
        return {**attempt(make_provider(primary, model)), "fallback_used": False, "fallback_reason": None}
    except Exception as exc:
        if not fallback or fallback == primary:
            raise
        reason = f"{primary} failed: {type(exc).__name__}: {exc}"[:500]
        logger.warning("LLM primary provider failed; using fallback %s. %s", fallback, reason)
        try:
            result = attempt(make_provider(fallback))
        except Exception as fallback_exc:
            raise RuntimeError(f"{reason}. Fallback {fallback} also failed: "
                               f"{type(fallback_exc).__name__}: {fallback_exc}") from fallback_exc
        return {**result, "fallback_used": True, "fallback_reason": reason}
