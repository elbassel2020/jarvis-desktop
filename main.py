"""Jarvis Desktop v0.8.0 — Daily Driver."""
import sys
from loguru import logger
from core.pipeline import JarvisPipeline
from dotenv import load_dotenv
import os

load_dotenv('config/.env')

# Always log to file; add stderr only in interactive terminal
logger.add('logs/jarvis_{time}.log', rotation='1 day', retention='7 days')
if not sys.stdout.isatty():
    # Running headless (VBS auto-start) — stderr goes nowhere, silence it
    logger.remove(0)


def main():
    logger.info("=" * 60)
    logger.info("JARVIS DESKTOP v0.8.0 — Daily Driver")
    logger.info("=" * 60)

    pipeline = JarvisPipeline(
        capture_duration=int(os.getenv('CAPTURE_DURATION', '5')),
        whisper_model=os.getenv('WHISPER_MODEL', 'whisper-large-v3-turbo'),
        wake_word=os.getenv('WAKE_WORD', 'hey_jarvis_v0.1'),
        wake_threshold=float(os.getenv('WAKE_THRESHOLD', '0.45')),
        llm_model=os.getenv('LLM_MODEL', 'qwen2.5:7b'),
    )
    pipeline.run()


if __name__ == '__main__':
    main()
