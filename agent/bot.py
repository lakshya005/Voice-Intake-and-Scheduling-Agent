"""Minimal voice loop: browser WebRTC -> VAD -> STT -> LLM -> TTS.

Run from agent/:  uv run bot.py   then open http://localhost:7860/client
TURN_MODE=smart_turn (default): Silero VAD + Smart Turn v3, Deepgram Nova STT
TURN_MODE=flux: Deepgram Flux decides end of turn itself
"""

import os
import re

from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.deepgram.flux.stt import DeepgramFluxSTTService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.groq.llm import GroqLLMService
from pipecat.services.kokoro.tts import KokoroTTSService
from pipecat.transports.base_transport import TransportParams
from pipecat.turns.user_start import (
    TranscriptionUserTurnStartStrategy,
    VADUserTurnStartStrategy,
)
from pipecat.turns.user_stop import TurnAnalyzerUserTurnStopStrategy
from pipecat.turns.user_turn_strategies import (
    ExternalUserTurnStrategies,
    UserTurnStrategies,
)
from pipecat.utils.text.transforms import expand_phone_numbers
from pipecat.workers.runner import WorkerRunner

from backend_client import BackendClient
from metrics.timing_observer import TimingObserver, TurnTimes

load_dotenv(override=True)

TURN_MODE = os.getenv("TURN_MODE", "smart_turn")
SYSTEM_PROMPT = (
    "You are a friendly receptionist for a medical office. Keep every reply to one or two short sentences: "
    "your words are spoken aloud. Do not give medical advice."
)


async def speak_naturally(text: str, text_type: str) -> str:
    # The LLM often emits U+2011 (non-breaking hyphen), which Pipecat's phone regex doesn't match.
    text = re.sub("[‐-―−]", "-", text)
    # Kokoro pauses at every period in "p.m."; "PM" is spoken as one unit.
    text = re.sub(r"\b([AaPp])\.\s?[Mm]\.", lambda m: m.group(1).upper() + "M", text)
    return await expand_phone_numbers(text, text_type)


transport_params = {
    "webrtc": lambda: TransportParams(audio_in_enabled=True, audio_out_enabled=True),
}


async def bot(runner_args: RunnerArguments):
    transport = await create_transport(runner_args, transport_params)

    llm = GroqLLMService(
        api_key=os.environ["GROQ_API_KEY"],
        settings=GroqLLMService.Settings(system_instruction=SYSTEM_PROMPT),
    )
    tts = KokoroTTSService(
        settings=KokoroTTSService.Settings(voice="af_heart"),
        text_transforms=[("*", speak_naturally)],
    )
    context = LLMContext()

    if TURN_MODE == "flux":
        stt = DeepgramFluxSTTService(api_key=os.environ["DEEPGRAM_API_KEY"])
        user_params = LLMUserAggregatorParams(
            user_turn_strategies=ExternalUserTurnStrategies()
        )
    else:
        stt = DeepgramSTTService(api_key=os.environ["DEEPGRAM_API_KEY"])
        user_params = LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(),
            user_turn_strategies=UserTurnStrategies(
                start=[
                    VADUserTurnStartStrategy(),
                    TranscriptionUserTurnStartStrategy(),
                ],
                stop=[
                    TurnAnalyzerUserTurnStopStrategy(
                        turn_analyzer=LocalSmartTurnAnalyzerV3()
                    )
                ],
            ),
        )
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context, user_params=user_params
    )

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_aggregator,
            llm,
            tts,
            transport.output(),
            assistant_aggregator,
        ]
    )
    backend = BackendClient()
    call = {"id": None, "idx": 0}  # set when the client connects

    async def upload_turn(observer: TimingObserver, turn: TurnTimes):
        # Timings describe the assistant's answer to the caller's turn, so one row per exchange, role=assistant.
        idx, call["idx"] = call["idx"], call["idx"] + 1
        await backend.add_turn(
            call["id"],
            {
                "idx": idx,
                "role": "assistant",
                "interrupted": turn.interrupted,
                **{
                    f: (
                        w.isoformat()
                        if (w := observer.wall_clock(getattr(turn, f)))
                        else None
                    )
                    for f in (
                        "t_user_stop",
                        "t_stt_final",
                        "t_llm_first_token",
                        "t_tts_first_byte",
                    )
                },
            },
        )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
        observers=[TimingObserver(on_turn=upload_turn)],
    )

    @assistant_aggregator.event_handler("on_assistant_turn_stopped")
    async def log_assistant_turn(aggregator, message):
        # What the context stores for this turn; when interrupted it should be only what was spoken.
        logger.info(
            f"ASSISTANT TURN interrupted={message.interrupted} content={message.content!r}"
        )

    @transport.event_handler("on_client_connected")
    async def on_connected(transport, client):
        call["id"] = await backend.start_call()
        context.add_message(
            {
                "role": "developer",
                "content": "Greet the caller and ask how you can help.",
            }
        )
        await worker.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_disconnected(transport, client):
        await backend.end_call(call["id"])
        await worker.cancel()

    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
    await runner.add_workers(worker)
    await runner.run()


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
