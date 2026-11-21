"""Portable trusted plugin snapshots and version-level environment identity."""
import hashlib
import importlib.metadata
import os
import platform
import stat
import sys
from pathlib import Path


def digest(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def safe(path):
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 1024:
        raise ValueError("plugin symlink or reparse point is unsupported")
    return info.st_mode


def capture(root):
    for parent in (root, *root.parents):
        safe(parent)
    if not root.is_dir():
        raise ValueError("plugin root must be a directory")
    files = {}
    total = 0
    for path in sorted(root.rglob("*")):
        mode = safe(path)
        if stat.S_ISDIR(mode):
            continue
        if not stat.S_ISREG(mode) or path.suffix.lower() in {".pyc", ".pyo", ".pyd", ".so", ".dll", ".pth"}:
            raise ValueError("unsupported plugin file")
        with path.open("rb") as source:
            data = source.read(32_000_001 - total)
        total += len(data)
        if total > 32_000_000 or len(files) >= 4096:
            raise ValueError("plugin snapshot exceeds supported size")
        files[path.relative_to(root).as_posix()] = data
    if "method.py" not in files:
        raise ValueError("plugin has no method.py")
    return files


def manifest(files):
    return {name: digest(data) for name, data in files.items()}


def environment():
    return {"python": sys.version, "implementation": sys.implementation.name,
            "platform": platform.platform(), "machine": platform.machine(),
            "executable_sha256": digest(Path(sys.executable).read_bytes()),
            "distributions": sorted([d.metadata["Name"], d.version] for d in importlib.metadata.distributions())}


def materialize(root, files):
    root.mkdir()
    for name, data in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
