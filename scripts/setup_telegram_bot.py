"""Telegram bot token setup."""
import getpass
from jarvis.security.credential_broker import broker

if __name__ == "__main__":
    print("Telegram Bot Setup")
    print("Get your token: Telegram → @BotFather → /mybots → @MSMA_Walid_bot → API Token\n")
    token = getpass.getpass("Bot token: ")
    # Note: account uses hyphen (valid in HANDLE_RE: [a-z0-9_-]+)
    broker.store("telegram", "msma-walid-bot", token)
    print("Stored: cred://telegram/msma-walid-bot")
    print(f"Bot will only respond to chat_id=1032010360 (Walid)")
