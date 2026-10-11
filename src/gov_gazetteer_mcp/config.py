"""Configuration from environment variables.

=============================  =================================================
``GOV_GAZETTEER_CACHE_DIR``    Directory for the on-disk response cache.
``GOV_GAZETTEER_TIMEOUT``      HTTP timeout in seconds for one request.
``GOV_GAZETTEER_MIN_INTERVAL`` Least seconds between two requests to GOV.
``GOV_GAZETTEER_CONTACT``      An email address or URL appended to the
                               User-Agent, so CompGen can reach whoever runs
                               this server.
=============================  =================================================

None is required: GOV's web services need no key and no account. A ``.env``
file in the working directory supplies any of these that the environment does
not. Nothing here widens what a tool can reach: the one host is fixed in code.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

#: Least seconds between requests to GOV, unless configured otherwise.
DEFAULT_MIN_INTERVAL = 1.0

#: The floor on GOV_GAZETTEER_MIN_INTERVAL. GOV is run by volunteers of a
#: genealogical society; nothing here should ever call it faster than this.
MIN_INTERVAL_FLOOR = 1.0


class ConfigError(RuntimeError):
    """Raised when a setting is present but unusable."""


@dataclass
class Config:
    """Resolved server configuration.

    Attributes
    ----------
    cache_dir : Path
        Directory holding cached responses.
    timeout : float
        HTTP timeout in seconds for one request.
    min_interval : float
        Least seconds between the start of one request to GOV and the next.
    contact : str
        Appended to the User-Agent when set. Empty by default.
    """

    cache_dir: Path = field(default_factory=lambda: Path.home() / ".cache" / "gov-gazetteer-mcp")
    timeout: float = 30.0
    min_interval: float = DEFAULT_MIN_INTERVAL
    contact: str = ""


def load_config() -> Config:
    """Load configuration from the environment.

    A ``.env`` file in the working directory is read if present; real
    environment variables win. Only the working directory is consulted.
    ``load_dotenv()`` with no path searches upward from the *calling
    module's* location instead, which for an installed package is
    ``site-packages``.

    Raises
    ------
    ConfigError
        If a number is unusable or a contact string could break the header.
        The server loads its configuration on the first tool call, so this
        surfaces there as a ``not_configured`` result rather than as a crash.
    """
    load_dotenv(Path.cwd() / ".env")

    cfg = Config()
    if raw := os.environ.get("GOV_GAZETTEER_CACHE_DIR"):
        cfg.cache_dir = Path(raw).expanduser()
    if raw := os.environ.get("GOV_GAZETTEER_TIMEOUT"):
        cfg.timeout = _positive("GOV_GAZETTEER_TIMEOUT", raw)
    if raw := os.environ.get("GOV_GAZETTEER_MIN_INTERVAL"):
        value = _positive("GOV_GAZETTEER_MIN_INTERVAL", raw)
        if value < MIN_INTERVAL_FLOOR:
            raise ConfigError(
                f"GOV_GAZETTEER_MIN_INTERVAL must be at least {MIN_INTERVAL_FLOOR:g}; got {raw!r}."
            )
        cfg.min_interval = value
    if raw := os.environ.get("GOV_GAZETTEER_CONTACT"):
        cfg.contact = _contact(raw)
    return cfg


def _positive(name: str, raw: str) -> float:
    """Parse one numeric setting, naming the variable if it is unusable."""
    try:
        value = float(raw.strip())
    except ValueError:
        raise ConfigError(f"{name} must be a number; got {raw!r}.") from None
    if not math.isfinite(value) or value <= 0:
        raise ConfigError(f"{name} must be greater than zero; got {raw!r}.")
    return value


def _contact(raw: str) -> str:
    """Keep a contact string safe to place inside a User-Agent header.

    A newline would let the value inject a second header, and parentheses
    would close the comment it sits in.
    """
    text = raw.strip()
    if any(ch in text for ch in "\r\n()") or not text.isprintable():
        raise ConfigError(
            "GOV_GAZETTEER_CONTACT must be one line with no parentheses, such as an "
            f"email address or a URL; got {raw!r}."
        )
    return text
