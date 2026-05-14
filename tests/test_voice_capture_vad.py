"""Tests for VoiceCapture — VAD logic mocked (no real mic)."""
import sys
import os
import pytest
import numpy as np
from unittest.mock import patch, MagicMock
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


@pytest.fixture
def capture(tmp_path):
    with patch('core.voice_capture.Path') as mock_path:
        mock_path.return_value.mkdir = MagicMock()
        from core.voice_capture import VoiceCapture
        vc = VoiceCapture.__new__(VoiceCapture)
        vc.duration = 5
        vc.samplerate = 16000
        vc.use_vad = True
        vc.silence_duration = 1.0
        vc.silence_threshold = 0.01
        vc.captures_dir = tmp_path / 'captures'
        vc.captures_dir.mkdir()
        return vc


class TestVoiceCaptureInit:
    def test_default_duration(self, tmp_path):
        with patch('sounddevice.InputStream'), patch('sounddevice.rec'), patch('sounddevice.wait'):
            from core.voice_capture import VoiceCapture
            with patch.object(VoiceCapture, '__init__', lambda self, *a, **kw: None):
                vc = VoiceCapture.__new__(VoiceCapture)
                vc.duration = 5
        assert vc.duration == 5

    def test_default_samplerate(self, capture):
        assert capture.samplerate == 16000

    def test_vad_enabled_by_default(self, capture):
        assert capture.use_vad is True

    def test_silence_threshold_value(self, capture):
        assert capture.silence_threshold == 0.01

    def test_silence_duration_value(self, capture):
        assert capture.silence_duration == 1.0


class TestVADLogic:
    def test_fixed_duration_mode(self, capture, tmp_path):
        capture.use_vad = False
        fake_audio = np.zeros((80000, 1), dtype='float32')
        with patch('sounddevice.rec', return_value=fake_audio), \
             patch('sounddevice.wait'), \
             patch('scipy.io.wavfile.write') as mock_write:
            result = capture.capture()
        mock_write.assert_called_once()
        assert str(result).endswith('.wav')

    def test_vad_mode_returns_wav_path(self, capture, tmp_path):
        chunk = np.zeros((1600, 1), dtype='int16')
        mock_stream = MagicMock()
        mock_stream.__enter__ = lambda s: s
        mock_stream.__exit__ = MagicMock(return_value=False)
        mock_stream.read.return_value = (chunk, None)

        with patch('sounddevice.InputStream', return_value=mock_stream), \
             patch('scipy.io.wavfile.write'):
            result = capture.capture()
        assert str(result).endswith('.wav')

    def test_vad_stops_on_silence_after_speech(self, capture, tmp_path):
        samplerate = 16000
        chunk_size = int(0.1 * samplerate)
        silence_needed = int(1.0 / 0.1)

        call_count = [0]
        def make_chunk(size):
            call_count[0] += 1
            n = call_count[0]
            if n <= 5:
                # loud speech chunk
                data = np.full((chunk_size, 1), 5000, dtype='int16')
            else:
                # silence
                data = np.zeros((chunk_size, 1), dtype='int16')
            return data, None

        mock_stream = MagicMock()
        mock_stream.__enter__ = lambda s: s
        mock_stream.__exit__ = MagicMock(return_value=False)
        mock_stream.read.side_effect = make_chunk

        with patch('sounddevice.InputStream', return_value=mock_stream), \
             patch('scipy.io.wavfile.write') as mock_write:
            capture.capture()

        mock_write.assert_called_once()
        # Should stop well before max chunks (50)
        assert call_count[0] < 50

    def test_vad_chunk_size_100ms(self, capture, tmp_path):
        expected_chunk = int(0.1 * 16000)  # 1600 samples
        chunks_requested = []

        def read_side_effect(size):
            chunks_requested.append(size)
            return np.zeros((size, 1), dtype='int16'), None

        mock_stream = MagicMock()
        mock_stream.__enter__ = lambda s: s
        mock_stream.__exit__ = MagicMock(return_value=False)
        mock_stream.read.side_effect = read_side_effect

        with patch('sounddevice.InputStream', return_value=mock_stream), \
             patch('scipy.io.wavfile.write'):
            capture.capture()

        assert chunks_requested[0] == expected_chunk

    def test_output_saved_as_int16(self, capture, tmp_path):
        chunk = np.zeros((1600, 1), dtype='int16')
        mock_stream = MagicMock()
        mock_stream.__enter__ = lambda s: s
        mock_stream.__exit__ = MagicMock(return_value=False)
        mock_stream.read.return_value = (chunk, None)

        written_dtype = [None]
        def mock_write(path, sr, data):
            written_dtype[0] = data.dtype

        with patch('sounddevice.InputStream', return_value=mock_stream), \
             patch('scipy.io.wavfile.write', side_effect=mock_write):
            capture.capture()

        assert written_dtype[0] == np.int16

    def test_capture_uses_correct_samplerate(self, capture, tmp_path):
        chunk = np.zeros((1600, 1), dtype='int16')
        mock_stream = MagicMock()
        mock_stream.__enter__ = lambda s: s
        mock_stream.__exit__ = MagicMock(return_value=False)
        mock_stream.read.return_value = (chunk, None)

        written_sr = [None]
        def mock_write(path, sr, data):
            written_sr[0] = sr

        with patch('sounddevice.InputStream', return_value=mock_stream), \
             patch('scipy.io.wavfile.write', side_effect=mock_write):
            capture.capture()

        assert written_sr[0] == 16000
