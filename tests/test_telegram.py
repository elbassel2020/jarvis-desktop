"""Telegram bot tests — Telegram API mocked."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from jarvis.integrations.telegram import bot


def test_walid_chat_id_constant():
    assert bot.WALID_CHAT_ID == 1032010360


@pytest.mark.asyncio
async def test_send_to_walid_success():
    with patch("jarvis.integrations.telegram.bot.broker.resolve", return_value="fake_token"):
        with patch("telegram.Bot") as MockBot:
            instance = MockBot.return_value
            instance.send_message = AsyncMock(return_value=MagicMock())
            result = await bot.send_to_walid("Task complete")
    assert result is True


@pytest.mark.asyncio
async def test_send_to_walid_broker_fail():
    with patch(
        "jarvis.integrations.telegram.bot.broker.resolve",
        side_effect=Exception("no credential"),
    ):
        result = await bot.send_to_walid("test")
    assert result is False


def test_send_to_walid_audit_on_error():
    """Ensure audit log captures error outcome (sync wrapper test)."""
    import asyncio
    with patch(
        "jarvis.integrations.telegram.bot.broker.resolve",
        side_effect=Exception("auth fail"),
    ):
        result = asyncio.run(bot.send_to_walid("hello"))
    assert result is False
    from jarvis.security.audit import query_audit
    rows = query_audit(actor="telegram", action="send_to_walid", limit=1)
    assert len(rows) >= 1
    assert rows[0]["outcome"] == "error"
