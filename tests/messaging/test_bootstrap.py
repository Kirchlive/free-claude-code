"""Tests for :mod:`messaging.bootstrap`."""

from pathlib import Path

from config.settings import Settings


class _DummyTranscriptionBackend:
    """Satisfies :class:`~messaging.voice_backend.TranscriptionBackend` for bootstrap tests."""

    __slots__ = ()

    def transcribe_audio_file(
        self,
        file_path: Path,
        nim_model_id: str,
        *,
        api_key: str,
    ) -> str:
        return ""


def test_create_optional_platform_none_when_disabled(monkeypatch) -> None:
    from messaging.bootstrap import create_optional_messaging_platform

    monkeypatch.setitem(Settings.model_config, "env_file", ())
    monkeypatch.setenv("MESSAGING_PLATFORM", "none")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    settings = Settings()
    tb = _DummyTranscriptionBackend()
    assert (
        create_optional_messaging_platform(
            settings,
            nim_transcription_backend=tb,
        )
        is None
    )


def test_build_options_reflects_hf_token(monkeypatch) -> None:
    from messaging.bootstrap import build_messaging_platform_options

    monkeypatch.setitem(Settings.model_config, "env_file", ())
    monkeypatch.setenv("HF_TOKEN", "hf-test-token")
    settings = Settings()
    tb = _DummyTranscriptionBackend()
    opts = build_messaging_platform_options(
        settings,
        nim_transcription_backend=tb,
    )
    assert opts.hf_token == "hf-test-token"
