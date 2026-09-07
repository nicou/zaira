"""Terminal hyperlinks (OSC 8).

A terminal that implements OSC 8 attaches a URL to a run of text, so a ticket
key prints as plain text but opens the browser on a click. There is no terminfo
capability and no query for OSC 8, so support is an allow list of terminals that
are known to render it. Terminals outside the list, and any non-terminal stdout,
get the bare key: some old terminals print the raw escape bytes instead of
dropping them, and piped output must stay byte-identical for scripts and agents.
"""

import os
import re
import subprocess
import sys

ESC = "\033"
ST = f"{ESC}\\"

# VTE added OSC 8 in 0.50, which reports VTE_VERSION 5000 or higher.
MIN_VTE_VERSION = 5000

# tmux forwards OSC 8 from 3.4. Older versions drop it or pass fragments.
MIN_TMUX_VERSION = (3, 4)

# Environment variables that a terminal with OSC 8 support sets.
_TERMINAL_MARKERS = (
    "KITTY_WINDOW_ID",
    "KONSOLE_VERSION",
    "WT_SESSION",
    "DOMTERM",
    "GHOSTTY_RESOURCES_DIR",
    "GHOSTTY_BIN_DIR",
)

_TERM_SUBSTRINGS = ("kitty", "foot", "ghostty", "wezterm", "contour", "rio")

# Apple_Terminal is absent on purpose: Terminal.app does not render OSC 8.
_TERM_PROGRAMS = (
    "iTerm.app",
    "WezTerm",
    "ghostty",
    "vscode",
    "Hyper",
    "rio",
    "Tabby",
    "mintty",
)

# A Jira issue key: project key, a dash, then the issue number. Anything else
# (a column header, a "?" placeholder) must not become a browse URL.
_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*-\d+$")

_supported: bool | None = None
_site: str | None = None


def reset_cache() -> None:
    """Drop the cached support result and Jira site."""
    global _supported, _site
    _supported = None
    _site = None


def _tmux_forwards_hyperlinks() -> bool:
    """Check whether the running tmux is new enough to forward OSC 8."""
    try:
        out = subprocess.run(
            ["tmux", "-V"], capture_output=True, text=True, timeout=2, check=False
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    digits = "".join(c for c in out if c.isdigit() or c == ".")
    parts = [p for p in digits.split(".") if p]
    if not parts:
        return False
    version = tuple(int(p) for p in parts[:2])
    return version >= MIN_TMUX_VERSION


def _detect_support() -> bool:
    """Decide whether stdout can render OSC 8 hyperlinks."""
    from zaira.project import get_hyperlinks_mode

    mode = get_hyperlinks_mode()
    if mode == "never":
        return False
    if mode == "always":
        return True

    if not sys.stdout.isatty():
        return False

    term = os.environ.get("TERM", "")
    if term in ("", "dumb"):
        return False

    if os.environ.get("TMUX"):
        if not _tmux_forwards_hyperlinks():
            return False
    elif term.startswith("screen"):
        # GNU screen does not forward OSC 8.
        return False

    vte = os.environ.get("VTE_VERSION", "")
    if vte.isdigit() and int(vte) >= MIN_VTE_VERSION:
        return True

    if any(os.environ.get(name) for name in _TERMINAL_MARKERS):
        return True

    if any(s in term for s in _TERM_SUBSTRINGS):
        return True

    return os.environ.get("TERM_PROGRAM", "") in _TERM_PROGRAMS


def supports_hyperlinks() -> bool:
    """Return True if stdout renders OSC 8 hyperlinks. Cached."""
    global _supported
    if _supported is None:
        _supported = _detect_support()
    return _supported


def _jira_site() -> str:
    """Return the Jira site for browse URLs. Cached.

    get_jira_site() reads credentials.toml and can hit the OS keyring, so it
    must not run once per printed row.
    """
    global _site
    if _site is None:
        from zaira.jira_client import get_jira_site

        _site = get_jira_site()
    return _site


def hyperlink(url: str, label: str) -> str:
    """Wrap `label` in an OSC 8 hyperlink to `url`, unconditionally."""
    return f"{ESC}]8;;{url}{ST}{label}{ESC}]8;;{ST}"


def ticket_key(key: str) -> str:
    """Return `key`, linked to its Jira browse URL where the terminal allows."""
    if not _KEY_RE.match(key) or not supports_hyperlinks():
        return key
    site = _jira_site()
    if not site:
        return key
    return hyperlink(f"https://{site}/browse/{key}", key)


def ticket_key_cell(key: str, width: int) -> str:
    """Return a left-aligned `key` column of `width` visible characters.

    Pads on the plain key length: the escape bytes take no columns, so
    f"{ticket_key(key):<{width}}" would eat the padding and break alignment.
    Padding is added outside the link so the clickable run stays on the key.
    """
    return ticket_key(key) + " " * max(0, width - len(key))
