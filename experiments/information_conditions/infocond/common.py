"""Small shared helpers: config loading, hashing, canonical JSON, timestamps."""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .paths import CONFIG_PATH


def load_config(path: Path | None = None) -> dict:
    with open(path or CONFIG_PATH) as f:
        return json.load(f)


def canonical_json(obj: Any) -> str:
    """Deterministic JSON serialisation used for hashing and cache identity."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path | str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def utc_stamp() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _atomic_write(path: Path, text: str) -> None:
    """Write via a temporary file in the same directory and rename.

    A crash mid-write then leaves either the previous file or nothing at all,
    never a half-written record that later runs cannot parse.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        with open(tmp, "w") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def write_text(path: Path, text: str) -> None:
    _atomic_write(path, text)


def write_json(path: Path, obj: Any) -> None:
    _atomic_write(path, json.dumps(obj, indent=2, sort_keys=False, ensure_ascii=False) + "\n")


def read_json(path: Path) -> Any:
    with open(path) as f:
        return json.load(f)
