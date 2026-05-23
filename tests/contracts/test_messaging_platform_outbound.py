"""Contract: concrete messaging platforms expose the outbound queue protocol."""

from __future__ import annotations

import pytest


def test_telegram_platform_satisfies_platform_outbound() -> None:
    from messaging.platforms.outbound import PlatformOutbound
    from messaging.platforms.telegram import TelegramPlatform

    assert isinstance(TelegramPlatform(bot_token="t"), PlatformOutbound)


def test_discord_platform_satisfies_platform_outbound_when_available() -> None:
    pytest.importorskip("discord")

    from messaging.platforms.discord import DISCORD_AVAILABLE, DiscordPlatform
    from messaging.platforms.outbound import PlatformOutbound

    if not DISCORD_AVAILABLE:
        pytest.skip("Discord optional stack unavailable in this environment")

    assert isinstance(DiscordPlatform(bot_token="t"), PlatformOutbound)
