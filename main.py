"""Jarvis Desktop — Entry point (Phase 1: wake word only)."""
from loguru import logger
from core.wake_listener import WakeListener
from dotenv import load_dotenv
import os

load_dotenv('config/.env')

logger.add('logs/jarvis_{time}.log', rotation='1 day', retention='7 days')


def main():
    logger.info("=" * 60)
    logger.info("JARVIS DESKTOP v0.1.0 — Phase 1 Foundation")
    logger.info("=" * 60)

    listener = WakeListener(
        wake_word=os.getenv('WAKE_WORD', 'hey_jarvis'),
        threshold=float(os.getenv('WAKE_THRESHOLD', '0.5')),
    )

    listener.listen_forever()


if __name__ == '__main__':
    main()
