"""Phase 6 tests — BrainRouter multi-LLM + ElevenLabs TTS."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', '.env'))


# ------------------------------------------------------------------ #
#  BrainRouter unit tests                                             #
# ------------------------------------------------------------------ #

def test_router_import():
    from core.brain_router import BrainRouter
    assert BrainRouter is not None


def test_classify_complexity():
    from core.brain_router import classify_complexity
    assert classify_complexity('what time') == 'simple'
    assert classify_complexity('open calculator please') == 'simple'
    assert classify_complexity('search for Schneider contactors in Jubail market') == 'medium'
    long = 'can you please help me find the best electrical contractor software for managing contracts in Saudi Arabia specifically for small businesses'
    assert classify_complexity(long) == 'complex'


def test_router_init():
    from core.brain_router import BrainRouter
    r = BrainRouter()
    # At least Qwen fallback always available
    assert r._fallback_model is not None


def test_router_time_en():
    from core.brain_router import BrainRouter
    r = BrainRouter()
    result = r.think('time')
    assert result['action'] == 'time', f"Expected 'time', got {result['action']} via {result['backend']}"
    assert result['confidence'] > 0


def test_router_screenshot_ar():
    from core.brain_router import BrainRouter
    r = BrainRouter()
    result = r.think('خد لقطة شاشة')
    assert result['action'] == 'screenshot', f"Got {result['action']} via {result['backend']}"


def test_router_search():
    from core.brain_router import BrainRouter
    r = BrainRouter()
    result = r.think('search for Schneider contactors')
    # v0.13.0: product searches may route to 'shop' or 'search' — both valid
    assert result['action'] in ('search', 'shop'), f"Got {result['action']} via {result['backend']}"


def test_router_open_app():
    from core.brain_router import BrainRouter
    r = BrainRouter()
    result = r.think('open calculator')
    assert result['action'] == 'open_app', f"Got {result['action']} via {result['backend']}"


def test_router_empty():
    from core.brain_router import BrainRouter
    r = BrainRouter()
    result = r.think('')
    assert result['action'] == 'cancel'


def test_router_chat():
    from core.brain_router import BrainRouter
    r = BrainRouter()
    result = r.think('how are you doing today')
    assert result['action'] == 'chat'
    assert len(result['response']) > 0


def test_router_arabic_open():
    from core.brain_router import BrainRouter
    r = BrainRouter()
    result = r.think('افتح كروم')
    assert result['action'] == 'open_app', f"Got {result['action']} via {result['backend']}"


# ------------------------------------------------------------------ #
#  LLMBrain wrapper still works                                       #
# ------------------------------------------------------------------ #

def test_llmbrain_delegates_to_router():
    from core.llm_brain import LLMBrain
    b = LLMBrain()
    from core.brain_router import BrainRouter
    assert isinstance(b._router, BrainRouter)


def test_llmbrain_think_time():
    from core.llm_brain import LLMBrain
    b = LLMBrain()
    result = b.think('time')
    assert result['action'] == 'time'


# ------------------------------------------------------------------ #
#  ElevenLabs TTS smoke test (requires ELEVENLABS_API_KEY)           #
# ------------------------------------------------------------------ #

def test_elevenlabs_key_present():
    assert os.getenv('ELEVENLABS_API_KEY'), "ELEVENLABS_API_KEY not set"


def test_elevenlabs_tts_smoke():
    """Generates a short audio file — requires real key and internet."""
    eleven_key = os.getenv('ELEVENLABS_API_KEY')
    if not eleven_key:
        import pytest
        pytest.skip("No ELEVENLABS_API_KEY")
    from elevenlabs.client import ElevenLabs
    client = ElevenLabs(api_key=eleven_key)
    audio = client.text_to_speech.convert(
        voice_id='pNInz6obpgDQGcFmaJgB',  # Adam — free-tier compatible
        text='Jarvis ready',
        model_id='eleven_multilingual_v2',
    )
    data = b''.join(audio)
    assert len(data) > 1000, "ElevenLabs returned suspiciously small audio"
