"""Groq LLM that retries once on a second model when the first is rate limited (each model has its own free quota)."""

from loguru import logger
from openai import RateLimitError
from pipecat.services.groq.llm import GroqLLMService


class FallbackGroqLLMService(GroqLLMService):
    def __init__(self, *, fallback_model: str, **kwargs):
        super().__init__(**kwargs)
        self._fallback_model = fallback_model
        self._use_fallback = False

    def build_chat_completion_params(self, params_from_context) -> dict:
        params = super().build_chat_completion_params(params_from_context)
        if self._use_fallback:
            params["model"] = self._fallback_model
        return params

    async def get_chat_completions(self, context):
        try:
            return await super().get_chat_completions(context)
        except RateLimitError:
            logger.warning(
                f"{self._settings.model} rate limited, retrying on {self._fallback_model}"
            )
            self._use_fallback = True
            try:
                return await super().get_chat_completions(context)
            finally:
                self._use_fallback = False
