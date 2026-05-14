"""Tests for Transcriber — Groq primary, faster-whisper fallback, all mocked."""
import sys
import os
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


@pytest.fixture
def transcriber(tmp_path):
    audio = tmp_path / 'test.wav'
    audio.write_bytes(b'RIFF\x00\x00\x00\x00WAVEfmt ')

    with patch.dict(os.environ, {'GROQ_API_KEY': 'test-key-123'}), \
         patch('groq.Groq') as mock_groq_cls:
        mock_client = MagicMock()
        mock_groq_cls.return_value = mock_client
        from core.transcriber import Transcriber
        t = Transcriber(model_name='whisper-large-v3-turbo')
        t._audio_path = audio
        t._mock_groq_client = mock_client
    return t


def _mock_groq_response(text='hello world', language='en'):
    resp = MagicMock()
    resp.text = text
    resp.language = language
    return resp


class TestTranscriberInit:
    def test_requires_groq_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(RuntimeError, match='GROQ_API_KEY'):
                from core.transcriber import Transcriber
                Transcriber()

    def test_model_name_stored(self, transcriber):
        assert transcriber.model_name == 'whisper-large-v3-turbo'

    def test_local_lazy_none(self, transcriber):
        assert transcriber._local is None

    def test_fallback_local_name_stored(self, transcriber):
        assert transcriber.fallback_local_name == 'medium'


class TestGroqTranscription:
    def test_groq_success_returns_dict(self, transcriber):
        mock_resp = _mock_groq_response('hello jarvis')
        transcriber.groq.audio.transcriptions.create.return_value = mock_resp
        result = transcriber._try_groq(transcriber._audio_path)
        assert isinstance(result, dict)

    def test_groq_text_extracted(self, transcriber):
        mock_resp = _mock_groq_response('open chrome please')
        transcriber.groq.audio.transcriptions.create.return_value = mock_resp
        result = transcriber._try_groq(transcriber._audio_path)
        assert result['text'] == 'open chrome please'

    def test_groq_language_extracted(self, transcriber):
        mock_resp = _mock_groq_response('كم الساعة', 'ar')
        transcriber.groq.audio.transcriptions.create.return_value = mock_resp
        result = transcriber._try_groq(transcriber._audio_path)
        assert result['language'] == 'ar'

    def test_groq_backend_key(self, transcriber):
        mock_resp = _mock_groq_response()
        transcriber.groq.audio.transcriptions.create.return_value = mock_resp
        result = transcriber._try_groq(transcriber._audio_path)
        assert 'groq' in result['backend']

    def test_groq_has_duration_s(self, transcriber):
        mock_resp = _mock_groq_response()
        transcriber.groq.audio.transcriptions.create.return_value = mock_resp
        result = transcriber._try_groq(transcriber._audio_path)
        assert 'duration_s' in result
        assert isinstance(result['duration_s'], float)

    def test_groq_has_audio_file(self, transcriber):
        mock_resp = _mock_groq_response()
        transcriber.groq.audio.transcriptions.create.return_value = mock_resp
        result = transcriber._try_groq(transcriber._audio_path)
        assert 'audio_file' in result


class TestFallbackChain:
    def test_transcribe_uses_groq_primary(self, transcriber):
        mock_resp = _mock_groq_response('test')
        transcriber.groq.audio.transcriptions.create.return_value = mock_resp
        result = transcriber.transcribe(transcriber._audio_path)
        assert result['backend'].startswith('groq')

    def test_transcribe_falls_back_on_groq_failure(self, transcriber, tmp_path):
        transcriber.groq.audio.transcriptions.create.side_effect = Exception('connection error')

        mock_local = MagicMock()
        mock_segment = MagicMock()
        mock_segment.text = ' hello from local'
        mock_info = MagicMock()
        mock_info.language = 'en'
        mock_local.transcribe.return_value = ([mock_segment], mock_info)
        transcriber._local = mock_local

        result = transcriber.transcribe(transcriber._audio_path)
        assert 'faster-whisper' in result['backend']

    def test_transcribe_fallback_text_concatenated(self, transcriber):
        transcriber.groq.audio.transcriptions.create.side_effect = Exception('fail')

        seg1 = MagicMock(); seg1.text = 'Hello '
        seg2 = MagicMock(); seg2.text = 'world'
        mock_info = MagicMock(); mock_info.language = 'en'

        mock_local = MagicMock()
        mock_local.transcribe.return_value = ([seg1, seg2], mock_info)
        transcriber._local = mock_local

        result = transcriber.transcribe(transcriber._audio_path)
        assert result['text'] == 'Hello world'

    def test_transcribe_passes_language_to_groq(self, transcriber):
        mock_resp = _mock_groq_response('ok')
        transcriber.groq.audio.transcriptions.create.return_value = mock_resp
        transcriber.transcribe(transcriber._audio_path, language='ar')
        call_kwargs = transcriber.groq.audio.transcriptions.create.call_args[1]
        assert call_kwargs.get('language') == 'ar'

    def test_local_lazy_loads_on_fallback(self, transcriber):
        transcriber.groq.audio.transcriptions.create.side_effect = Exception('fail')

        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([], MagicMock(language='en'))
        mock_model.transcribe.return_value = ([MagicMock(text='hi')], MagicMock(language='en'))

        with patch('faster_whisper.WhisperModel', return_value=mock_model):
            transcriber._local = None
            result = transcriber.transcribe(transcriber._audio_path)
        assert transcriber._local is not None


class TestTranscriberTextStripping:
    def test_groq_strips_whitespace(self, transcriber):
        mock_resp = _mock_groq_response('  hello  ')
        transcriber.groq.audio.transcriptions.create.return_value = mock_resp
        result = transcriber._try_groq(transcriber._audio_path)
        assert result['text'] == 'hello'

    def test_local_strips_whitespace(self, transcriber):
        seg = MagicMock(); seg.text = '  world  '
        mock_info = MagicMock(); mock_info.language = 'en'
        mock_local = MagicMock()
        mock_local.transcribe.return_value = ([seg], mock_info)
        transcriber._local = mock_local
        result = transcriber._try_local(transcriber._audio_path)
        assert result['text'] == 'world'
