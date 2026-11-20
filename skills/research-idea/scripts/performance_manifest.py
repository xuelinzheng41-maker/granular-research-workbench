#!/usr/bin/env python3
"""Validate a performance pilot manifest: data provenance, split policy, and pilot contract.

A manifest describes the local data files a pilot will use (path, SHA-256, rows,
features, label), the split policy (group column, folds, seeds), and the pilot
contract (stage, threshold, datasets). This checks whether the record is
well formed and self-consistent; it does not prove the numbers themselves.

Exit codes: 0 for a valid manifest, 2 for a malformed or incomplete one.
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
STAGES = ("pilot", "full")
MIN_DATA = 2
MIN_FOLDS = 2
MIN_SEEDS = 3


def _where(prefix, key):
    return f"{prefix}.{key}" if prefix else key


def _object(value, where):
    if not isinstance(value, dict):
        raise ValueError(f"{where} must be an object")
    return value


def _text(obj, key, where):
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{_where(where, key)}: missing or blank")
    return value.strip()


def _positive_int(obj, key, where):
    value = obj.get(key)
    if type(value) is not int or value <= 0:
        raise ValueError(f"{_where(where, key)}: must be a positive integer")
    return value


def _number(value, where):
    if type(value) not in (int, float):
        raise ValueError(f"{where}: must be a number")
    return float(value)


def _data_entry(entry, index, names, paths):
    where = f"data[{index}]"
    entry = _object(entry, where)
    name = _text(entry, "name", where)
    if name in names:
        raise ValueError(f"{where}.name: duplicate dataset name {name!r}")
    names.add(name)
    path = _text(entry, "path", where)
    if ".." in Path(path).parts:
        raise ValueError(f"{where}.path: must not contain '..' segments")
    if path in paths:
        raise ValueError(f"{where}.path: duplicate data path {path!r}")
    paths.add(path)
    sha256 = entry.get("sha256")
    if not isinstance(sha256, str) or not SHA256_RE.match(sha256):
        raise ValueError(f"{where}.sha256: must be 64 lowercase hex characters")
    row = dict(
        name=name,
        path=path,
        sha256=sha256,
        rows=_positive_int(entry, "rows", where),
        features=_positive_int(entry, "features", where),
        label=_text(entry, "label", where),
    )
    if "coverage" in entry:
        coverage = _number(entry["coverage"], f"{where}.coverage")
        if not 0.0 <= coverage <= 1.0:
            raise ValueError(f"{where}.coverage: must be between 0 and 1")
        row["coverage"] = coverage
    if "runtime_s" in entry:
        runtime = _number(entry["runtime_s"], f"{where}.runtime_s")
        if runtime <= 0:
            raise ValueError(f"{where}.runtime_s: must be positive")
        row["runtime_s"] = runtime
    return row


def _split(value):
    split = _object(value, "split")
    group_column = _text(split, "group_column", "split")
    folds = split.get("folds")
    if type(folds) is not int or folds < MIN_FOLDS:
        raise ValueError(f"split.folds: must be an integer >= {MIN_FOLDS}")
    seeds = split.get("seeds")
    if not isinstance(seeds, list) or len(seeds) < MIN_SEEDS:
        raise ValueError(f"split.seeds: must list at least {MIN_SEEDS} seeds")
    clean = []
    for index, seed in enumerate(seeds):
        if type(seed) is not int or seed < 0:
            raise ValueError(f"split.seeds[{index}]: must be a non-negative integer")
        if seed in clean:
            raise ValueError(f"split.seeds[{index}]: duplicate seed {seed}")
        clean.append(seed)
    return dict(group_column=group_column, folds=folds, seeds=clean, seed_count=len(clean))


def _pilot(value, data_names):
    pilot = _object(value, "pilot")
    stage = _text(pilot, "stage", "pilot")
    if stage not in STAGES:
        raise ValueError("pilot.stage: must be one of " + ", ".join(STAGES))
    threshold = _number(pilot.get("threshold"), "pilot.threshold")
    if not 0.0 < threshold <= 1.0:
        raise ValueError("pilot.threshold: must be a number in (0, 1]")
    datasets = pilot.get("datasets")
    if not isinstance(datasets, list) or len(datasets) < MIN_DATA:
        raise ValueError(f"pilot.datasets: must list at least {MIN_DATA} dataset names")
    clean = []
    for index, name in enumerate(datasets):
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"pilot.datasets[{index}]: must be a non-empty dataset name")
        name = name.strip()
        if name not in data_names:
            raise ValueError(f"pilot.datasets[{index}]: unknown dataset {name!r} (not in data)")
        if name in clean:
            raise ValueError(f"pilot.datasets[{index}]: duplicate dataset {name!r}")
        clean.append(name)
    result = dict(stage=stage, threshold=threshold, datasets=clean, dataset_count=len(clean))
    if "metric" in pilot:
        result["metric"] = _text(pilot, "metric", "pilot")
    return result


def _sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_file(row, base_dir):
    path = Path(row["path"])
    resolved = path if path.is_absolute() else Path(base_dir) / path
    if not resolved.is_file():
        raise ValueError(f"{row['name']}: data file not found: {resolved}")
    actual = _sha256_file(resolved)
    if actual != row["sha256"]:
        raise ValueError(
            f"{row['name']}: sha256 mismatch for {resolved} "
            f"(manifest {row['sha256']}, file {actual})"
        )
    return dict(file_present=True, sha256_verified=True)


def validate(manifest, base_dir=None, check_files=False):
    """Return a normalized summary or raise ValueError for a malformed manifest."""
    manifest = _object(manifest, "manifest")
    version = manifest.get("manifest_version", 1)
    if type(version) is not int or version < 1:
        raise ValueError("manifest_version: must be a positive integer")
    entries = manifest.get("data")
    if not isinstance(entries, list) or len(entries) < MIN_DATA:
        raise ValueError(f"data: must list at least {MIN_DATA} datasets")
    names = set()
    paths = set()
    rows = []
    for index, entry in enumerate(entries):
        rows.append(_data_entry(entry, index, names, paths))
    split = _split(manifest.get("split"))
    pilot = _pilot(manifest.get("pilot"), names)

    warnings = []
    missing = [row["name"] for row in rows if row["name"] not in pilot["datasets"]]
    if missing:
        warnings.append(
            "pilot covers %d of %d manifest datasets; not covered: %s"
            % (pilot["dataset_count"], len(rows), ", ".join(missing))
        )

    checks = dict(form="ok", files="not_checked")
    if check_files:
        if base_dir is None:
            raise ValueError("check_files requires a base_dir")
        for row in rows:
            row.update(_verify_file(row, base_dir))
        checks["files"] = "ok"
    else:
        for row in rows:
            row["file_present"] = None
            row["sha256_verified"] = False

    return dict(
        manifest_version=version,
        datasets=len(rows),
        data=rows,
        split=split,
        pilot=pilot,
        checks=checks,
        warnings=warnings,
        limits=(
            "Manifest validation checks declared fields and internal consistency only. "
            "It does not prove that rows/features/label values are true, that the split "
            "is unbiased, or that a path still points at the same bytes unless "
            "--check-files is used."
        ),
    )


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("manifest", type=Path)
    cli.add_argument(
        "--check-files",
        action="store_true",
        help="require every data path to exist and match its declared sha256",
    )
    args = cli.parse_args(argv)
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        summary = validate(
            manifest,
            base_dir=args.manifest.resolve().parent,
            check_files=args.check_files,
        )
    except (OSError, ValueError) as exc:
        print(f"performance_manifest: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
