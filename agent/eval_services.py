"""LLM factories for the eval harness: the judge and the simulated caller run on Groq, like the bot."""

import os

from dotenv import load_dotenv
from pipecat.services.groq.llm import GroqLLMService

load_dotenv()


def groq(config: dict) -> GroqLLMService:
    return GroqLLMService(
        api_key=os.environ["GROQ_API_KEY"],
        settings=GroqLLMService.Settings(
            model=config.get("model", "openai/gpt-oss-120b")
        ),
    )
