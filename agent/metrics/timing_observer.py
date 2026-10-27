"""Per-turn timing observer. [I WRITE]: fill in every TODO; Claude reviews.

Goal: for each user->assistant exchange, record four timestamps (nanoseconds, pipeline clock):
    t_user_stop         the caller finished speaking
    t_stt_final         the final transcript is ready
    t_llm_first_token   the LLM produced its first token
    t_tts_first_byte    the first synthesized audio left the TTS stage
Voice-to-voice latency = t_tts_first_byte - t_user_stop. Later steps store these in the `turns` table.

Hints (verify names in docs.pipecat.ai and the installed pipecat/frames/frames.py):
  - An observer only watches frames; it must never change them.
  - Every processor re-pushes a frame it passes along, so one frame is seen many times.
    `data.first_push` and `observe_every_push=False` exist for that reason.
  - `data.timestamp` is nanoseconds on the pipeline clock; keep it as int, convert only when printing.
  - Candidate frames: UserStoppedSpeakingFrame, TranscriptionFrame, LLMTextFrame, TTSAudioRawFrame,
    InterruptionFrame, BotStartedSpeakingFrame. Which one best marks each moment? Decide and justify.
  - With Flux, the STT service signals end of turn; with Smart Turn, the aggregator does. Does
    the same frame mark "user stopped" in both modes? Check by printing.
"""

from dataclasses import dataclass

from loguru import logger
from pipecat.observers.base_observer import BaseObserver, FramePushed


@dataclass
class TurnTimes:
    t_user_stop: int | None = None
    t_stt_final: int | None = None
    t_llm_first_token: int | None = None
    t_tts_first_byte: int | None = None
    interrupted: bool = False


class TimingObserver(BaseObserver):
    def __init__(self):
        # TODO 1: call super().__init__(...). Decide whether observe_every_push should be False, and why.
        self._current = TurnTimes()

    async def on_push_frame(self, data: FramePushed):
        frame = data.frame
        # TODO 2: when the caller stops speaking, start a fresh TurnTimes and set t_user_stop.
        # TODO 3: set t_stt_final on the final transcript. Beware interim transcripts.
        # TODO 4: set t_llm_first_token only for the FIRST token of the turn (not every token).
        # TODO 5: set t_tts_first_byte only for the FIRST audio frame of the turn.
        # TODO 6: on an interruption, mark the turn interrupted and decide what to do with its timings.
        # TODO 7: when the turn is complete, log it (loguru) with the four deltas in milliseconds,
        #         including voice-to-voice latency. Print first; the DB write comes later.
        pass
