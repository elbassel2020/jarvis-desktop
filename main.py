"""Jarvis Desktop — Phase 2 entry point."""
from loguru import logger
from core.pipeline import JarvisPipeline
from dotenv import load_dotenv
import os

load_dotenv('config/.env')

logger.add('logs/jarvis_{time}.log', rotation='1 day', retention='7 days')


def main():
    logger.info("=" * 60)
    logger.info("JARVIS DESKTOP v0.2.0 — Phase 2 Voice + Intent")
    logger.info("=" * 60)

    pipeline = JarvisPipeline(
        capture_duration=int(os.getenv('CAPTURE_DURATION', '5')),
        whisper_model=os.getenv('WHISPER_MODEL', 'small'),
        wake_word=os.getenv('WAKE_WORD', 'hey_jarvis'),
        wake_threshold=float(os.getenv('WAKE_THRESHOLD', '0.35')),
    )
    pipeline.run()


if __name__ == '__main__':
    main()
