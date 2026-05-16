"""v0.13.1 quiet controls — verify attributes and guards exist in source."""


def test_speak_has_silent_mode_check():
    content = open('actions/safe_actions.py', encoding='utf-8').read()
    assert 'silent_mode_check' in content or '_pipeline_ref' in content


def test_pipeline_has_silent_mode_attr():
    content = open('core/pipeline.py', encoding='utf-8').read()
    assert 'self.silent_mode' in content
    assert 'quiet_hours_until' in content


def test_wake_threshold_is_065():
    content = open('core/wake_listener.py', encoding='utf-8').read()
    # WakeListener default is 0.35; pipeline passes 0.65 override
    pipeline = open('core/pipeline.py', encoding='utf-8').read()
    assert 'wake_threshold=0.65' in pipeline


def test_proactive_respects_silent():
    content = open('core/pipeline.py', encoding='utf-8').read()
    assert 'silent_mode' in content
    # Guards appear in scheduler sections
    assert content.count("getattr(self, 'silent_mode'") >= 2


def test_hotkeys_registered():
    content = open('core/pipeline.py', encoding='utf-8').read()
    assert 'ctrl+alt+m' in content
    assert 'ctrl+alt+q' in content
