"""Tests for terminal module (OSC 8 hyperlinks)."""

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
_ENV_VARS = terminal._TERMINAL_MARKERS + ("TERM", "TERM_PROGRAM", "TMUX", "VTE_VERSION")


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


def test_hyperlink_byte_sequence() -> None:
    """Emits OSC 8 with ESC-backslash terminators, not BEL."""
    assert hyperlink("https://example.com/browse/T-1", "T-1") == (
        "\033]8;;https://example.com/browse/T-1\033\\T-1\033]8;;\033\\"
    )


@pytest.mark.parametrize(
    "env, expected",
    [
        pytest.param(
            {"TERM": "xterm-ghostty", "TERM_PROGRAM": "ghostty"}, True, id="ghostty"
        ),
        pytest.param(
            {"TERM": "xterm-256color", "GHOSTTY_RESOURCES_DIR": "/opt/ghostty"},
            True,
            id="ghostty-resources-dir",
        ),
        pytest.param({"TERM": "xterm-kitty", "KITTY_WINDOW_ID": "1"}, True, id="kitty"),
        pytest.param(
            {"TERM": "xterm-256color", "TERM_PROGRAM": "iTerm.app"}, True, id="iterm"
        ),
        pytest.param(
            {"TERM": "xterm-256color", "VTE_VERSION": "6003"}, True, id="vte-new"
        ),
        pytest.param(
            {"TERM": "xterm-256color", "VTE_VERSION": "4205"}, False, id="vte-old"
        ),
        pytest.param(
            {"TERM": "xterm-256color", "TERM_PROGRAM": "Apple_Terminal"},
            False,
            id="apple-terminal",
        ),
        pytest.param({"TERM": "xterm-256color"}, False, id="unknown"),
        pytest.param({"TERM": "dumb", "TERM_PROGRAM": "ghostty"}, False, id="dumb"),
        pytest.param(
            {"TERM": "screen-256color", "TERM_PROGRAM": "ghostty"}, False, id="screen"
        ),
        pytest.param(
            {"TERM": "xterm-ghostty", "TMUX": "/tmp/tmux-501/default,1,0"},
            False,
            id="tmux",
        ),
    ],
)
def test_detection(
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
    env: dict[str, str],
    expected: bool,
) -> None:
    """The allow list decides support in auto mode."""
    for name, value in env.items():
        monkeypatch.setenv(name, value)

    assert supports_hyperlinks() is expected


def test_not_a_tty(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Piped output never gets escape sequences."""
    monkeypatch.setenv("TERM", "xterm-ghostty")
    monkeypatch.setattr("sys.stdout.isatty", lambda: False, raising=False)

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

    def test_oversized_key_is_not_truncated(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A key wider than the column gets no negative padding."""
        set_mode(monkeypatch, "never")
        set_site(monkeypatch, "example.atlassian.net")

        assert ticket_key_cell("VERYLONGPROJECT-1", 5) == "VERYLONGPROJECT-1"
