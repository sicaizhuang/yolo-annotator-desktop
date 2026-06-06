from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile


def atomic_write_text(path: str | Path, text: str, encoding: str = "utf-8") -> Path:
    """Write a text file atomically so a crash cannot leave a partial file."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=target.parent,
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding=encoding, newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return target


def atomic_write_json(path: str | Path, payload, *, ensure_ascii: bool = False, indent: int = 2) -> Path:
    return atomic_write_text(
        path,
        json.dumps(payload, ensure_ascii=ensure_ascii, indent=indent) + "\n",
    )
