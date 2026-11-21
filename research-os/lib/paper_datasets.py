"""Read-only comparison of paper dataset requirements with a local registry."""

import json
import re
import sys
import unicodedata

import numpy as np

from card_parser import read_card
from datasets import DatasetRegistry, DatasetStatus, load_dataset_with_label_info, verify_loaded_dataset


def _name_key(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Dataset names must be nonempty strings")
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _name_index(entries):
    if not isinstance(entries, list):
        raise ValueError("Registry datasets must be a list")
    index, ids = {}, set()
    for entry in entries:
        ident = entry["id"]
        key = _name_key(ident)
        if key in ids:
            raise ValueError(f"Duplicate dataset ID: {ident}")
        ids.add(key)
        aliases = entry.get("aliases", [])
        if not isinstance(aliases, list):
            raise ValueError(f"Aliases for {ident} must be a list")
        for name in [ident, *aliases]:
            index.setdefault(_name_key(name), {})[ident] = entry
    return index


def _mentions(text, index):
    if not index:
        return {}
    alternatives = "|".join(map(re.escape, sorted(index, key=lambda key: (-len(key), key))))
    # ASCII boundaries also allow names inside Chinese prose, e.g. 使用MNIST数据集.
    pattern = re.compile(r"(?<![a-z0-9_])(?:" + alternatives + r")(?![a-z0-9_])")
    matches = {}
    for number, line in enumerate(text.splitlines(), 1):
        if line.strip():
            for match in pattern.finditer(_name_key(line)):
                matches.setdefault(match[0], set()).add(number)
    return {key: sorted(lines) for key, lines in matches.items()}


def _local_status(entry, root, task):
    status = entry.get("status")
    if status == DatasetStatus.NEEDS_DATA:
        return {"status": "needs_data", "detail": "Registry marks data as unavailable"}
    if status == DatasetStatus.NEEDS_LOADER:
        return {"status": "needs_loader", "detail": f"Registry requires loader: {entry.get('loader', 'unknown')}"}
    if status not in (DatasetStatus.READY, DatasetStatus.READY_WITH_SCIPY):
        return {"status": "invalid_data", "detail": f"Invalid registry status: {status!r}"}

    try:
        x, y, hashes, has_labels = load_dataset_with_label_info(entry, root)
        if x.ndim != 2:
            raise ValueError("Expected a 2D feature matrix")
        ok, error = verify_loaded_dataset(entry, x, hashes)
    except FileNotFoundError as exc:
        return {"status": "needs_data", "detail": str(exc)}
    except ImportError as exc:
        return {"status": "needs_loader", "detail": str(exc)}
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RuntimeError) as exc:
        return {"status": "invalid_data", "detail": str(exc)}
    if not ok:
        return {"status": "integrity_failed", "integrity": "failed", "detail": error}

    result = {
        "status": "ready",
        "integrity": "verified" if hashes.keys() <= (entry.get("sha256") or {}).keys() else "unverified",
        "has_ground_truth": has_labels,
    }
    if task == "classification" and entry.get("usage") == "clustering":
        result.update(status="not_applicable", detail="clustering_only")
    elif not len(x) or not x.shape[1]:
        result.update(status="not_applicable", detail="empty")
    elif task == "classification" and not has_labels:
        result.update(status="not_applicable", detail="no_labels")
    elif task == "classification":
        try:
            if np.unique(y).size < 2:
                result.update(status="not_applicable", detail="single_class")
        except (ValueError, TypeError) as exc:
            result.update(status="invalid_data", detail=f"Invalid labels: {exc}")
    return result


def audit_paper(paper, registry_path, task, confirmed=()):
    suffix = paper.suffix.lower()
    if suffix == ".md":
        metadata, _, text = read_card(paper)
    elif suffix == ".txt":
        metadata, text = {}, paper.read_text(encoding="utf-8-sig")
    else:
        raise ValueError("Use a UTF-8 Markdown paper/card or plain-text export (.md or .txt)")
    if not registry_path.is_file():
        raise ValueError(f"Registry not found: {registry_path}")
    registry = DatasetRegistry(registry_path)
    index = _name_index(registry.registry["datasets"])
    root = registry.get_root()

    declared = metadata.get("datasets", [])
    if not confirmed and not isinstance(declared, list):
        raise ValueError("Paper card datasets must be a list of names; or supply --dataset")
    if confirmed:
        source, requirements, locations = "confirmed", confirmed, {}
    elif declared:
        source, requirements, locations = "card", declared, {}
    else:
        locations = _mentions(text, index)
        source, requirements = "text_mentions", locations

    rows, seen, evaluated = [], set(), {}
    for name in requirements:
        key = _name_key(name)
        if key in seen:
            continue
        seen.add(key)
        matches = index.get(key, {})
        row = {"name": name}
        if key in locations:
            row["lines"] = locations[key]
        if not matches:
            row.update(status="unregistered", detail="Not in this registry; disk presence not determined")
        elif len(matches) > 1:
            row.update(status="ambiguous", candidates=sorted(matches))
        else:
            ident, entry = next(iter(matches.items()))
            if ident not in evaluated:
                evaluated[ident] = _local_status(entry, root, task)
            row.update(dataset_id=ident, **evaluated[ident])
        rows.append(row)

    return {
        "source": source,
        "task": task,
        "status": "needs_confirmation" if source == "text_mentions"
                  else "ready" if all(row["status"] == "ready" for row in rows) else "blocked",
        "datasets": rows,
    }


def run(args):
    try:
        report = audit_paper(args.paper, args.registry, args.task, args.dataset)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        print(f"Paper dataset check refused: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=True))
    else:
        print(f"Paper dataset check: {report['status']} ({report['source']}, {report['task']})")
        for row in report["datasets"]:
            parts = [f"{row['name']}: {row['status']}"]
            for key in ("dataset_id", "integrity", "has_ground_truth", "detail", "candidates", "lines"):
                if key in row:
                    parts.append(f"{key}={row[key]}")
            print(" | ".join(parts))
        if report["status"] == "needs_confirmation":
            print("Text matches include mentions only and can miss unknown names. Confirm required names with --dataset.")
    return 0 if report["status"] == "ready" else 3
