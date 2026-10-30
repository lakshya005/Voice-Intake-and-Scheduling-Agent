"""Per-turn timing observer: logs how long each stage of a voice turn took.

Timestamps are pipeline-clock nanoseconds. A turn starts when the caller stops speaking and ends
when the bot stops speaking or the caller interrupts it. Voice-to-voice latency is
t_tts_first_byte - t_user_stop. The greeting has no user turn, so it is not measured.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from loguru import logger
from pipecat.frames.frames import (
    BotStoppedSpeakingFrame,
    InterruptionFrame,
    LLMTextFrame,
    TranscriptionFrame,
    TTSAudioRawFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.observers.base_observer import BaseObserver, FramePushed


@dataclass
class TurnTimes:
    t_user_stop: int | None = None
    t_stt_final: int | None = None
    t_llm_first_token: int | None = None
    t_tts_first_byte: int | None = None
    interrupted: bool = False


def _ms(t: int | None, start: int) -> str:
    return "-" if t is None else f"{(t - start) / 1e6:.0f}ms"


class TimingObserver(BaseObserver):
    def __init__(
        self,
        on_turn: Callable[["TimingObserver", TurnTimes], Awaitable[None]] | None = None,
    ):
        # Each processor re-pushes a frame; observing only the first push counts every frame once.
        super().__init__(observe_every_push=False)
        self._current = TurnTimes()
        self.completed: list[TurnTimes] = []
        self._on_turn = on_turn
        self._tasks: set[asyncio.Task] = set()
        self._anchor: tuple[int, int] | None = (
            None  # (pipeline ns, wall-clock ns) at the first frame seen
        )

    def wall_clock(self, t: int | None) -> datetime | None:
        """Pipeline-clock ns to wall-clock time. Absolute error is the anchor's; differences stay exact."""
        if t is None or self._anchor is None:
            return None
        return datetime.fromtimestamp(
            (self._anchor[1] + t - self._anchor[0]) / 1e9, tz=UTC
        )

    async def on_push_frame(self, data: FramePushed):
        frame, t, cur = data.frame, data.timestamp, self._current
        if self._anchor is None:
            self._anchor = (t, time.time_ns())
        if isinstance(frame, UserStoppedSpeakingFrame):
            if cur.t_user_stop is not None and cur.t_llm_first_token is None:
                return  # Flux emits a second stop frame per turn; it must not reset the turn or wipe stt_final
            if (
                cur.t_user_stop is not None
            ):  # a new turn began while the previous one was still being answered
                self._current = cur = TurnTimes()
            cur.t_user_stop = t
        elif isinstance(frame, TranscriptionFrame):
            # With Flux the final transcript can arrive before the user-stop frame, so this is
            # recorded as pending on the current turn. The last transcript before the LLM answers wins.
            if cur.t_llm_first_token is None:
                cur.t_stt_final = t
        elif isinstance(frame, LLMTextFrame):
            if cur.t_user_stop is not None and cur.t_llm_first_token is None:
                cur.t_llm_first_token = t
        elif isinstance(frame, TTSAudioRawFrame):
            if cur.t_llm_first_token is not None and cur.t_tts_first_byte is None:
                cur.t_tts_first_byte = t
        elif isinstance(frame, InterruptionFrame):
            if cur.t_user_stop is not None:
                cur.interrupted = True
                self._finish()
        elif isinstance(frame, BotStoppedSpeakingFrame):
            if cur.t_user_stop is not None:
                self._finish()

    def _finish(self):
        cur = self._current
        self._current = TurnTimes()
        self.completed.append(cur)
        if self._on_turn:  # fire and forget: uploading must not delay the pipeline
            task = asyncio.create_task(self._on_turn(self, cur))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        s = cur.t_user_stop
        logger.info(
            f"TURN TIMING stt_final={_ms(cur.t_stt_final, s)} llm_first_token={_ms(cur.t_llm_first_token, s)} "
            f"voice_to_voice={_ms(cur.t_tts_first_byte, s)} interrupted={cur.interrupted} (all relative to user stop)"
        )
