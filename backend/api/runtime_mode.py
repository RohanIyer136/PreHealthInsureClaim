"""Explicit server-side runtime boundary, independent of frontend mode."""

from enum import Enum
import os


class RuntimeMode(str, Enum):
    FULL = "full"
    DEMO = "demo"


def resolve_runtime_mode(mode: RuntimeMode | str | None = None) -> RuntimeMode:
    value = os.environ.get("APP_MODE", "full") if mode is None else mode
    try:
        return RuntimeMode(value)
    except ValueError:
        raise ValueError("APP_MODE must be 'full' or 'demo'") from None
