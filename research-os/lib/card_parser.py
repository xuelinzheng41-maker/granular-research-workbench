"""V2 paper-card parsing with a strict stdlib fallback."""
import re
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None


def restricted_frontmatter(header):
    """Flat mapping: unsigned integers, plain words, JSON strings and arrays."""
    import json

    meta = {}
    for number, line in enumerate(header.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z_][\w-]*): +(.+?) *", line)
        if not match or match[1] in meta:
            raise ValueError(f"unsupported or duplicate field at line {number}")
        key, value = match.groups()
        if value.startswith(('"', '[')):
            value = json.loads(value)
            if not (isinstance(value, str) or isinstance(value, list) and
                    all(isinstance(item, str) for item in value)):
                raise ValueError(f"expected string or string list at line {number}")
        elif re.fullmatch(r"0|[1-9][0-9]*", value):
            value = int(value)
        elif not re.fullmatch(r"[^\W\d_][\w .-]*", value) or value.lower() in {
            "yes", "no", "on", "off", "true", "false", "null"
        }:
            raise ValueError(f"unsupported scalar at line {number}; use JSON quoting")
        meta[key] = value
    return meta


def read_card(path):
    txt = Path(path).read_text(encoding="utf-8-sig")
    lines = txt.splitlines(keepends=True)
    if not lines or lines[0].rstrip() != "---":
        return {}, txt, txt
    end = next((i for i, line in enumerate(lines[1:], 1) if line.rstrip() == "---"), None)
    if end is None:
        raise ValueError(f"{path}: unterminated front matter")
    header = "".join(lines[1:end])
    try:
        meta = restricted_frontmatter(header) if yaml is None else yaml.safe_load(header)
    except Exception as exc:
        raise ValueError(f"{path}: invalid front matter: {exc}") from exc
    if meta is None and not any(line.strip() and not line.lstrip().startswith("#")
                                for line in header.splitlines()):
        meta = {}
    if not isinstance(meta, dict):
        raise ValueError(f"{path}: front matter must be a mapping")
    return meta, "".join(lines[end + 1:]), txt
