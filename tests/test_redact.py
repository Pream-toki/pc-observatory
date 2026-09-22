"""Tests for command-line secret redaction — the app must never leak a secret."""
from __future__ import annotations

from app.utils.redact import HIDDEN, redact_cmdline


def test_flag_equals_value_is_hidden():
    out = redact_cmdline(["tool", "--api-key=sk-super-secret-123"])
    assert "sk-super-secret-123" not in out
    assert "--api-key=" + HIDDEN in out


def test_flag_space_value_is_hidden():
    out = redact_cmdline(["tool", "--token", "abc123"])
    assert "abc123" not in out
    assert HIDDEN in out


def test_normal_command_line_untouched():
    out = redact_cmdline(["python", "backup.py", "--verbose", "C:\\dev\\backup"])
    assert out == "python backup.py --verbose C:\\dev\\backup"


def test_words_containing_secret_words_are_not_flagged():
    # 'keyboard' contains no whole secret word; 'authorize' is not 'auth' as a token.
    out = redact_cmdline(["tool", "--keyboard-layout=us", "--authorize-redirect=x"])
    assert HIDDEN not in out


def test_password_flag_variants():
    for flag in ("--password", "--PWD", "/token", "--private-key", "--client_secret"):
        out = redact_cmdline(["tool", f"{flag}=whatever"])
        assert "whatever" not in out, flag
        assert HIDDEN in out, flag


def test_empty_and_single_args():
    assert redact_cmdline([]) == ""
    assert redact_cmdline(["ping"]) == "ping"
