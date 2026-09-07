"""Tests for terminal module (OSC 8 hyperlinks)."""

from typing import Any

import pytest

from zaira import terminal
from zaira.terminal import (
    hyperlink,
    supports_hyperlinks,
    ticket_key,
    ticket_key_cell,
)

# Every environment variable the detection looks at, so a test starts from a
# known-empty environment instead of inheriting the developer's terminal.
_ENV_VARS = (
    "TERM",
    "TERM_PROGRAM",
    "TMUX",
    "VTE_VERSION",
    "KITTY_WINDOW_ID",
    "KONSOLE_VERSION",
    "WT_SESSION",
    "DOMTERM",
    "GHOSTTY_RESOURCES_DIR",
    "GHOSTTY_BIN_DIR",
)


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear terminal markers, make stdout a tty, and default the config to auto."""
    for name in _ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True, raising=False)
    monkeypatch.setattr("zaira.project.get_hyperlinks_mode", lambda: "auto")


def set_mode(monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    """Force the configured hyperlink mode."""
    monkeypatch.setattr("zaira.project.get_hyperlinks_mode", lambda: mode)


def set_site(monkeypatch: pytest.MonkeyPatch, site: str) -> None:
    """Force the Jira site used to build browse URLs."""
    monkeypatch.setattr("zaira.jira_client.get_jira_site", lambda: site)


class TestHyperlink:
    """Tests for the raw escape sequence."""

    def test_byte_sequence(self) -> None:
        """Emits OSC 8 with ESC-backslash terminators, not BEL."""
        result = hyperlink("https://example.com/browse/T-1", "T-1")

        assert result == (
            "\033]8;;https://example.com/browse/T-1\033\\T-1\033]8;;\033\\"
        )
        assert "\a" not in result

    def test_label_is_visible_text(self) -> None:
        """The label is the only non-escape text in the sequence."""
        assert "T-1" in hyperlink("https://example.com", "T-1")


class TestSupportsHyperlinks:
    """Tests for terminal detection."""

    def test_ghostty(self, clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        """Ghostty renders OSC 8."""
        monkeypatch.setenv("TERM", "xterm-ghostty")
        monkeypatch.setenv("TERM_PROGRAM", "ghostty")

        assert supports_hyperlinks() is True

    def test_ghostty_by_resources_dir(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Ghostty is recognised by its resources dir alone."""
        monkeypatch.setenv("TERM", "xterm-256color")
        monkeypatch.setenv("GHOSTTY_RESOURCES_DIR", "/opt/ghostty")

        assert supports_hyperlinks() is True

    def test_kitty(self, clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        """kitty renders OSC 8."""
        monkeypatch.setenv("TERM", "xterm-kitty")
        monkeypatch.setenv("KITTY_WINDOW_ID", "1")

        assert supports_hyperlinks() is True

    def test_iterm(self, clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        """iTerm2 renders OSC 8."""
        monkeypatch.setenv("TERM", "xterm-256color")
        monkeypatch.setenv("TERM_PROGRAM", "iTerm.app")

        assert supports_hyperlinks() is True

    def test_vte_new_enough(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """VTE 0.50 and later (VTE_VERSION >= 5000) renders OSC 8."""
        monkeypatch.setenv("TERM", "xterm-256color")
        monkeypatch.setenv("VTE_VERSION", "6003")

        assert supports_hyperlinks() is True

    def test_vte_too_old(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """VTE before 0.50 does not."""
        monkeypatch.setenv("TERM", "xterm-256color")
        monkeypatch.setenv("VTE_VERSION", "4205")

        assert supports_hyperlinks() is False

    def test_apple_terminal(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Terminal.app does not render OSC 8."""
        monkeypatch.setenv("TERM", "xterm-256color")
        monkeypatch.setenv("TERM_PROGRAM", "Apple_Terminal")

        assert supports_hyperlinks() is False

    def test_unknown_terminal(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An unrecognised terminal gets no links."""
        monkeypatch.setenv("TERM", "xterm-256color")

        assert supports_hyperlinks() is False

    def test_dumb_term(self, clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        """TERM=dumb reports no capabilities."""
        monkeypatch.setenv("TERM", "dumb")
        monkeypatch.setenv("TERM_PROGRAM", "ghostty")

        assert supports_hyperlinks() is False

    def test_not_a_tty(self, clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        """Piped output never gets escape sequences."""
        monkeypatch.setenv("TERM", "xterm-ghostty")
        monkeypatch.setattr("sys.stdout.isatty", lambda: False, raising=False)

        assert supports_hyperlinks() is False

    def test_screen_without_tmux(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """GNU screen does not forward OSC 8."""
        monkeypatch.setenv("TERM", "screen-256color")
        monkeypatch.setenv("TERM_PROGRAM", "ghostty")

        assert supports_hyperlinks() is False


class TestTmuxDetection:
    """Tests for the tmux version gate."""

    def _fake_tmux(self, monkeypatch: pytest.MonkeyPatch, version: str) -> None:
        def fake_run(*args: Any, **kwargs: Any) -> Any:
            class Result:
                stdout = version

            return Result()

        monkeypatch.setattr("subprocess.run", fake_run)

    def test_tmux_new_enough(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """tmux 3.4 forwards OSC 8."""
        monkeypatch.setenv("TERM", "screen-256color")
        monkeypatch.setenv("TMUX", "/tmp/tmux-501/default,1,0")
        monkeypatch.setenv("TERM_PROGRAM", "ghostty")
        self._fake_tmux(monkeypatch, "tmux 3.4\n")

        assert supports_hyperlinks() is True

    def test_tmux_too_old(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """tmux before 3.4 drops the sequence."""
        monkeypatch.setenv("TERM", "screen-256color")
        monkeypatch.setenv("TMUX", "/tmp/tmux-501/default,1,0")
        monkeypatch.setenv("TERM_PROGRAM", "ghostty")
        self._fake_tmux(monkeypatch, "tmux 3.3a\n")

        assert supports_hyperlinks() is False

    def test_tmux_missing_binary(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An unreadable tmux version is treated as unsupported."""
        monkeypatch.setenv("TERM", "screen-256color")
        monkeypatch.setenv("TMUX", "/tmp/tmux-501/default,1,0")
        monkeypatch.setenv("TERM_PROGRAM", "ghostty")

        def fail(*args: Any, **kwargs: Any) -> Any:
            raise OSError("no tmux")

        monkeypatch.setattr("subprocess.run", fail)

        assert supports_hyperlinks() is False


class TestConfigMode:
    """Tests for the [terminal] hyperlinks setting."""

    def test_never_beats_supported_terminal(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Mode "never" turns links off in a terminal that supports them."""
        monkeypatch.setenv("TERM", "xterm-ghostty")
        set_mode(monkeypatch, "never")

        assert supports_hyperlinks() is False

    def test_always_beats_non_tty(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Mode "always" skips every check, including the tty test."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False, raising=False)
        set_mode(monkeypatch, "always")

        assert supports_hyperlinks() is True

    def test_result_is_cached(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Detection runs once per process."""
        set_mode(monkeypatch, "always")
        assert supports_hyperlinks() is True

        set_mode(monkeypatch, "never")
        assert supports_hyperlinks() is True

        terminal.reset_cache()
        assert supports_hyperlinks() is False


class TestTicketKey:
    """Tests for ticket key rendering."""

    def test_linked_when_supported(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A supported terminal gets an OSC 8 link to the browse URL."""
        set_mode(monkeypatch, "always")
        set_site(monkeypatch, "example.atlassian.net")

        assert ticket_key("TEST-1") == hyperlink(
            "https://example.atlassian.net/browse/TEST-1", "TEST-1"
        )

    def test_plain_when_unsupported(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An unsupported terminal gets the bare key."""
        set_mode(monkeypatch, "never")
        set_site(monkeypatch, "example.atlassian.net")

        assert ticket_key("TEST-1") == "TEST-1"

    def test_plain_without_site(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No configured site means no URL to link to."""
        set_mode(monkeypatch, "always")
        set_site(monkeypatch, "")

        assert ticket_key("TEST-1") == "TEST-1"

    @pytest.mark.parametrize("value", ["?", "KEY", "not-a-key", "", "TEST-"])
    def test_non_keys_are_left_alone(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch, value: str
    ) -> None:
        """Placeholders and headers must not become browse URLs."""
        set_mode(monkeypatch, "always")
        set_site(monkeypatch, "example.atlassian.net")

        assert ticket_key(value) == value


class TestTicketKeyCell:
    """Tests for column padding."""

    def test_identical_to_ljust_when_unsupported(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Piped output is byte-identical to the old f-string padding."""
        set_mode(monkeypatch, "never")
        set_site(monkeypatch, "example.atlassian.net")

        assert ticket_key_cell("TEST-1", 10) == f"{'TEST-1':<10}"

    def test_visible_width_preserved(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Padding counts the key, not the escape bytes."""
        set_mode(monkeypatch, "always")
        set_site(monkeypatch, "example.atlassian.net")

        cell = ticket_key_cell("TEST-1", 10)

        assert cell.endswith("    ")
        # Two OSC 8 sequences (open and close), each ESC-introduced and
        # ESC-terminated.
        assert cell.count("\033") == 4

    def test_columns_align_across_key_lengths(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Rows with different key lengths end at the same visible column."""
        set_mode(monkeypatch, "always")
        set_site(monkeypatch, "example.atlassian.net")

        short = ticket_key_cell("T-1", 10)
        wide = ticket_key_cell("TEST-1234", 10)

        # Trailing padding brings both to the same visible width.
        assert len(short) - len(short.rstrip(" ")) == 10 - len("T-1")
        assert len(wide) - len(wide.rstrip(" ")) == 10 - len("TEST-1234")

    def test_oversized_key_is_not_truncated(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A key wider than the column gets no negative padding."""
        set_mode(monkeypatch, "never")
        set_site(monkeypatch, "example.atlassian.net")

        assert ticket_key_cell("VERYLONGPROJECT-1", 5) == "VERYLONGPROJECT-1"
