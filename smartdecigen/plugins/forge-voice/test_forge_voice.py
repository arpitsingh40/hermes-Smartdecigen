"""Tests for forge-voice — the cache-safe persona section.

Run:  python -m pytest test_forge_voice.py -v
"""

import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import __init__ as fv  # noqa: E402


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for v in ("FORGE_VOICE_DISABLE", "FORGE_VOICE_FILE"):
        monkeypatch.delenv(v, raising=False)
    yield


# --------------------------------------------------------------------------- section contract

def test_section_is_under_the_hermes_cap():
    """Hermes caps a plugin section at 4,000 chars and silently skips it when oversized."""
    text = fv.build_section()
    assert 0 < len(text) <= 4000, f"section is {len(text)} chars"


def test_section_carries_the_load_bearing_rules():
    text = fv.build_section()
    for rule in ("WHO YOU ARE", "THE WAY YOU SPEAK", "LEAD WITH VALUE",
                 "HONOR THE REQUEST", "PREDICT THE OUTCOME",
                 "STATE WHAT WOULD CHANGE YOUR MIND"):
        assert rule in text, f"missing voice rule: {rule}"


def test_no_json_output_contract_leaks_in():
    """The source SYSTEM prompt was half a JSON contract Hermes does not use — it must not
    appear in the section, or the model would try to emit JSON instead of prose."""
    text = fv.build_section()
    assert "STRICT JSON" not in text
    assert '"reasoning"' not in text
    assert '"hypotheses"' not in text


def test_disable_flag(monkeypatch):
    monkeypatch.setenv("FORGE_VOICE_DISABLE", "1")
    assert fv.build_section() == ""


def test_file_override(monkeypatch, tmp_path):
    f = tmp_path / "voice.txt"
    f.write_text("You are a laconic pirate.", encoding="utf-8")
    monkeypatch.setenv("FORGE_VOICE_FILE", str(f))
    assert fv.build_section() == "You are a laconic pirate."


def test_bad_file_override_falls_back(monkeypatch):
    monkeypatch.setenv("FORGE_VOICE_FILE", "C:/does/not/exist.txt")
    assert fv.build_section() == fv.PERSONA


def test_empty_file_override_falls_back(monkeypatch, tmp_path):
    f = tmp_path / "empty.txt"
    f.write_text("   ", encoding="utf-8")
    monkeypatch.setenv("FORGE_VOICE_FILE", str(f))
    assert fv.build_section() == fv.PERSONA


def test_oversized_persona_is_trimmed_not_dropped(monkeypatch, tmp_path):
    """An oversized section would be silently skipped by Hermes — trim instead."""
    f = tmp_path / "big.txt"
    f.write_text("\n".join(f"line {i}" for i in range(2000)), encoding="utf-8")
    monkeypatch.setenv("FORGE_VOICE_FILE", str(f))
    text = fv.build_section()
    assert 0 < len(text) <= 4000


def test_section_accepts_session_info():
    """Hermes passes a read-only session mapping; the callable must accept it."""
    assert fv.build_section({"session_id": "s", "model": "m", "provider": "p",
                             "platform": "cli", "profile_name": "default", "cwd": "/x"})


# --------------------------------------------------------------------------- registration

class _Ctx:
    def __init__(self):
        self.sections = []

    def register_system_prompt_section(self, section_id, fn, position=None, max_chars=None):
        self.sections.append((section_id, fn, position, max_chars))


def test_register_uses_the_only_valid_anchor():
    ctx = _Ctx()
    fv.register(ctx)
    assert len(ctx.sections) == 1
    section_id, fn, position, max_chars = ctx.sections[0]
    assert section_id == "forge-voice.operator"
    assert position == "after_memory", "after_memory is the only anchor Hermes accepts"
    assert max_chars <= 4000
    assert fn() == fv.build_section()
