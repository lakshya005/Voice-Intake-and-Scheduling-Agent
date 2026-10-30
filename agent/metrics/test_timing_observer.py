import asyncio

from pipecat.frames.frames import (
    BotStoppedSpeakingFrame,
    InterruptionFrame,
    LLMTextFrame,
    TranscriptionFrame,
    TTSAudioRawFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.observers.base_observer import FramePushed
from pipecat.processors.frame_processor import FrameDirection

from metrics.timing_observer import TimingObserver


def run(events):
    obs = TimingObserver()

    async def go():
        for t, frame in events:
            await obs.on_push_frame(
                FramePushed(None, None, frame, FrameDirection.DOWNSTREAM, t)
            )

    asyncio.run(go())
    return obs.completed


def stt(t):
    return TranscriptionFrame("hi", "u", "now")


def audio():
    return TTSAudioRawFrame(b"\0\0", 16000, 1)


def test_normal_turn_measures_each_stage():
    (turn,) = run(
        [
            (100, UserStoppedSpeakingFrame()),
            (150, stt(0)),
            (400, LLMTextFrame("Hello")),
            (450, LLMTextFrame(" there")),  # later tokens must not overwrite the first
            (900, audio()),
            (950, audio()),
            (2000, BotStoppedSpeakingFrame()),
        ]
    )
    assert (
        turn.t_user_stop,
        turn.t_stt_final,
        turn.t_llm_first_token,
        turn.t_tts_first_byte,
    ) == (100, 150, 400, 900)
    assert not turn.interrupted


def test_stt_final_before_user_stop_is_kept():  # Flux can finalize before the stop frame
    (turn,) = run(
        [
            (50, stt(0)),
            (100, UserStoppedSpeakingFrame()),
            (300, LLMTextFrame("a")),
            (700, audio()),
            (900, BotStoppedSpeakingFrame()),
        ]
    )
    assert turn.t_stt_final == 50


def test_greeting_without_user_turn_is_ignored():
    assert (
        run(
            [
                (10, LLMTextFrame("Hello")),
                (50, audio()),
                (500, BotStoppedSpeakingFrame()),
            ]
        )
        == []
    )


def test_interruption_flags_turn_and_following_bot_stop_is_ignored():
    turns = run(
        [
            (100, UserStoppedSpeakingFrame()),
            (300, LLMTextFrame("a")),
            (700, audio()),
            (1200, InterruptionFrame()),
            (1210, BotStoppedSpeakingFrame()),
        ]
    )
    assert len(turns) == 1 and turns[0].interrupted


def test_on_turn_callback_gets_turn_and_wall_clock_keeps_differences():
    seen = []

    async def go():
        async def on_turn(obs, turn):
            seen.append(
                (
                    turn,
                    obs.wall_clock(turn.t_user_stop),
                    obs.wall_clock(turn.t_tts_first_byte),
                )
            )

        obs = TimingObserver(on_turn=on_turn)
        for t, frame in [
            (1_000_000_000, UserStoppedSpeakingFrame()),
            (1_300_000_000, LLMTextFrame("a")),
            (1_900_000_000, audio()),
            (3_000_000_000, BotStoppedSpeakingFrame()),
        ]:
            await obs.on_push_frame(
                FramePushed(None, None, frame, FrameDirection.DOWNSTREAM, t)
            )
        await asyncio.gather(*obs._tasks)

    asyncio.run(go())
    ((_turn, stop, first_byte),) = seen
    assert (first_byte - stop).total_seconds() == 0.9
