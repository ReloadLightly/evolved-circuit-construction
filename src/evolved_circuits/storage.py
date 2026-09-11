"""Compact atomic JSON writes under the task output ceiling."""

import json
import os
from pathlib import Path


def bytes_used(root):
    return sum(p.stat().st_size for p in Path(root).rglob("*") if p.is_file())


def write_text(path, value, root, limit):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = value.encode()
    # Include the temporary copy, so even the atomic write stays under the ceiling.
    if bytes_used(root) + len(data) > limit:
        raise RuntimeError("Task output ceiling reached")
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def write_json(path, value, root, limit):
    write_text(path, json.dumps(value, allow_nan=False, separators=(",", ":")) + "\n", root, limit)


def read_json(path):
    return json.loads(Path(path).read_text())
