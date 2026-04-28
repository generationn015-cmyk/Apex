"""YAML config loader with env var interpolation."""
from __future__ import annotations

import os
import re
from pathlib import Path

import yaml
from dotenv import load_dotenv

from .models import Config

_ENV_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)(?::([^}]*))?\}")


def _interpolate(value):
    if isinstance(value, str):
        def repl(match: re.Match) -> str:
            name = match.group(1)
            default = match.group(2) or ""
            return os.environ.get(name, default)
        return _ENV_PATTERN.sub(repl, value)
    if isinstance(value, dict):
        return {k: _interpolate(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_interpolate(v) for v in value]
    return value


def load_config(path: str | Path) -> Config:
    """Load YAML config, interpolate ${ENV_VAR} references, validate via Pydantic."""
    load_dotenv()
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with path.open() as f:
        raw = yaml.safe_load(f) or {}
    return Config.model_validate(_interpolate(raw))
