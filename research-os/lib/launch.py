"""Official local launch path. Run-directory writers and plugins are trusted."""
import hashlib
import json
import os
import re
import sys
import tempfile

import plugin_snapshot as plugins
from pathlib import Path

from compile import CompileError, compile_protocol
from datasets import DatasetRegistry, DatasetStatus, load_dataset_with_label_info, verify_loaded_dataset
from runner import append_result, run_one, _runner_self_hash


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def digest(blob):
    return "sha256:" + hashlib.sha256(blob).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def create(path, value):
    with path.open("xb") as f:
        f.write(encode(value) + b"\n")
        f.flush()
        os.fsync(f.fileno())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def proposal(run):
    p = read(run / "proposal.json")
    scoop = run / "scoop.json"
    if scoop.exists():
        return p, digest(encode({"proposal": p, "scoop": read(scoop)}))
    return p, digest(encode(p))


def active(run):
    require(not (run / "launch.jsonl").exists() and not (run / "results.jsonl").exists(),
            "launch already reserved or results already exist; create a new run")


def approved(run, gate, expected):
    artifact = read(run / (gate + ".json"))
    require(artifact == {"gate": gate, "confirmed_hash": expected}, gate + " mismatch")


def classification_inputs(reg, name):
    import numpy as np

    entry = reg.get_dataset(name)
    require(entry is not None, f"Dataset {name}: blocked:needs_data: unregistered dataset")
    status = entry.get("status")
    if status == DatasetStatus.NEEDS_LOADER:
        loader = entry.get("loader", "undeclared")
        detail = "MATLAB v7.3 requires h5py support" if loader == "mat_v73" else f"loader {loader!r} is unavailable"
        raise ValueError(f"Dataset {name}: blocked:needs_data: {detail}")
    if status == DatasetStatus.NEEDS_DATA:
        source = entry.get("label_source")
        labels = source.get("path") if isinstance(source, dict) else entry.get("labels")
        files = ", ".join(path for path in (entry.get("data"), labels) if isinstance(path, str))
        raise ValueError(f"Dataset {name}: blocked:needs_data: required files unavailable (needs_data): {files or 'paths undeclared'}")
    require(status in (DatasetStatus.READY, DatasetStatus.READY_WITH_SCIPY),
            f"Dataset {name}: invalid registry status {status!r}")

    try:
        x, y, hashes, has_labels = load_dataset_with_label_info(entry, reg.get_root())
        require(x.ndim == 2, f"expected a 2D feature matrix, got shape {x.shape}")
        ok, error = verify_loaded_dataset(entry, x, hashes)
    except (FileNotFoundError, ImportError) as exc:
        raise ValueError(f"Dataset {name}: blocked:needs_data: {exc}") from exc
    except (OSError, ValueError, TypeError, KeyError, RuntimeError, AttributeError) as exc:
        raise ValueError(f"Dataset {name}: invalid_data: {exc}") from exc
    require(ok, f"Dataset {name}: invalid_data: {error}")

    require(entry.get("usage") != "clustering", f"Dataset {name}: not_ready:clustering_only")
    require(len(x) > 0, f"Dataset {name}: not_ready:empty")
    require(has_labels, f"Dataset {name}: not_ready:no_labels")
    require(len(np.unique(y)) >= 2, f"Dataset {name}: not_ready:single_class")
    return x, y, hashes


def inputs(p, sha):
    import numpy as np
    from sklearn.model_selection import train_test_split

    protocol = compile_protocol({"payload": p["prereg"]}, sha)
    require(protocol["stage"] in ("pilot", "full"), "unsupported stage")
    from pilot_claims import plans
    if declared := plans(p):
        protocol["paired_claims"] = declared
    require(protocol["metric"] == "ACC", "supported metric: ACC")
    require(set(protocol["split"]) == {"test_size", "stratify"}, "invalid split configuration")
    fraction, stratify = protocol["split"]["test_size"], protocol["split"]["stratify"]
    require(type(fraction) is float and 0 < fraction < 1 and type(stratify) is bool, "invalid split")
    seeds, names, arms = (protocol[k] for k in ("seeds", "datasets", "arms"))
    for seq in (seeds, names):
        require(type(seq) is list and seq and len(set(seq)) == len(seq), "empty or duplicate matrix axis")
    require(all(type(s) is int and 0 <= s < 2**32 for s in seeds), "invalid seed")
    require(type(arms) is dict and arms, "no methods declared")
    require(all(re.fullmatch(r"[a-zA-Z0-9_-]+", n) for n in [*names, *arms]), "invalid ID")
    registry_path = Path(p["registry"])
    require(registry_path.is_absolute(), "registry path must be absolute")
    require(registry_path.exists(), f"blocked:needs_data: dataset registry not found: {registry_path}")
    reg = DatasetRegistry(registry_path)
    methods, snapshots = {}, {}
    for name, arm in arms.items():
        path = Path(arm["directory"])
        require(path.is_absolute(), "method directory must be absolute")
        require(type(arm["budget_s"]) is int and arm["budget_s"] > 0, "invalid row budget")
        require(set(arm) == {"directory", "budget_s"}, "unsupported plugin declaration")
        require(".." not in path.parts, "plugin path traversal is unsupported")
        snapshots[name] = plugins.capture(path)
        methods[name] = digest(snapshots[name]["method.py"])
    planned_seconds = len(names) * len(seeds) * sum(a["budget_s"] + 2 for a in arms.values())
    require(protocol.get("compute_budget_minutes", 0) * 60 >= planned_seconds, "matrix exceeds budget")
    data, splits, arrays = {}, {}, {}
    for name in names:
        x, y, hashes = classification_inputs(reg, name)
        data[name] = {"source": hashes, "loaded": [digest(a.tobytes()) for a in (x, y)],
                      "shape": list(x.shape)}
        for seed in seeds:
            train, test = train_test_split(np.arange(len(y)), random_state=seed,
                                           test_size=fraction, stratify=y if stratify else None)
            key = name + ":" + str(seed)
            splits[key] = digest(encode([train.tolist(), test.tolist()]))
            arrays[key] = (x[train], y[train], x[test], y[test])
    frozen = {"proposal_sha256": sha, "protocol_sha256": digest(encode(protocol)),
              "data": data, "split": splits, "method": methods, "runner": _runner_self_hash(),
              "registry": digest(registry_path.read_bytes()), "planned_seconds": planned_seconds}
    frozen["plugins"] = {name: plugins.manifest(files) for name, files in snapshots.items()}
    frozen["environment"] = plugins.environment()
    return protocol, frozen, arrays, snapshots


def dispatch(args):
    run = args.run_dir.resolve()
    command = args.command
    if command == "retry":
        from run_health import retry
        return retry(args.parent.resolve(), run, args.reason)
    if command == "init":
        p = read(args.proposal)
        require("retry" not in p, "use retry command for linked attempts")
        require(type(p) is dict and bool(p.get("idea")), "proposal requires an idea")
        if args.memory_idea_id is not None:
            from research_memory import advisory, store_path
            advisory(store_path(args.memory_store), args.memory_idea_id)
        elif args.memory_store is not None:
            raise ValueError("--memory-store requires --memory-idea-id")
        run.mkdir(parents=True, exist_ok=False)
        create(run / "proposal.json", p)
    p, sha = proposal(run)
    if command in ("init", "proposal"):
        result = {"proposal": p, "proposal_sha256": sha}
        if (run / "scoop.json").exists():
            result["scoop"] = read(run / "scoop.json")
        print(encode(result).decode())
        return 0
    if command in ("review-target", "review", "decide", "passport"):
        from review_decision import dispatch as review_dispatch
        return review_dispatch(args, run, p, sha)
    if command == "review-package":
        from review_packet import export
        return export(run, p, sha, args.max_bytes)
    if command != "scoop-replay":
        active(run)
    mode = p.get("mode", "exploratory")
    require(mode in ("formal", "exploratory"), "unsupported proposal mode")
    if command in ("scoop", "scoop-replay") or "scoop" in p or mode == "formal":
        from scoop import collect
        cfg = p["scoop"]
        directory = Path(cfg["cards"])
        require(directory.is_absolute(), "card directory must be absolute")
        if mode == "formal":
            from source_evidence import formal, ready
            current = formal(directory, cfg, p)
        else:
            current = collect(directory, cfg["queries"])
        if command == "scoop":
            require(not (run / "H1.json").exists(), "already confirmed")
            create(run / "scoop.json", current)
            print(encode(current).decode())
            return 0
        require(current == read(run / "scoop.json"), "scoop replay mismatch")
        if command == "scoop-replay":
            print(encode(current).decode())
            return 0
        require(all(axis["status"] in ("hits", "zero_hits") for axis in current["axes"].values()),
                "scoop coverage incomplete")
        if mode == "formal":
            ready(current)
    if command == "approve":
        expected = sha
        if args.gate == "H2":
            approved(run, "H1", sha)
            frozen = read(run / "freeze.json")
            require(frozen["proposal_sha256"] == sha and p["prereg"]["stage"] == "full", "invalid H2 target")
            expected = digest(encode(frozen))
        require(args.hash == expected, "confirmation hash mismatch")
        create(run / (args.gate + ".json"), {"gate": args.gate, "confirmed_hash": expected})
        return 0
    approved(run, "H1", sha)
    protocol, frozen, arrays, snapshots = inputs(p, sha)
    frozen["sealed_results"] = True
    if "retry" in p:
        from run_health import check_retry
        check_retry(run, p, frozen)
    freeze_hash = digest(encode(frozen))
    if command == "freeze":
        create(run / "freeze.json", frozen)
        print(freeze_hash)
        return 0
    require(read(run / "freeze.json") == frozen, "frozen inputs changed")
    if protocol["stage"] == "full":
        approved(run, "H2", freeze_hash)
    create(run / "launch.jsonl", {"event": "launch", "freeze_sha256": freeze_hash,
                                  "protocol_sha256": frozen["protocol_sha256"]})
    for ds in protocol["datasets"]:
        for name, arm in protocol["arms"].items():
            for seed in protocol["seeds"]:
                key = ds + ":" + str(seed)
                x, y, xt, yt = arrays[key]
                with tempfile.TemporaryDirectory() as temp:
                    path = Path(temp) / name
                    plugins.materialize(path, snapshots[name])
                    require(plugins.manifest(plugins.capture(path)) == frozen["plugins"][name], "plugin snapshot mismatch")
                    require(plugins.environment() == frozen["environment"], "execution environment changed")
                    row = run_one(arm_dir=path, dataset_id=ds, X_train=x, y_train=y, X_test=xt, y_test=yt,
                                  seed=seed, budget_s=arm["budget_s"], protocol_sha256=frozen["protocol_sha256"],
                                  portable=True)
                    require(plugins.manifest(plugins.capture(path)) == frozen["plugins"][name], "plugin snapshot changed during execution")
                    require(plugins.environment() == frozen["environment"], "execution environment changed")
                row.update(plugin_sha256=digest(encode(frozen["plugins"][name])),
                           environment_sha256=digest(encode(frozen["environment"])))
                if row["method_sha256"] != frozen["method"][name]:
                    row.update(status="invalid", metric=None)
                row.update(arm=name, row_key=[ds, name, seed, 1], attempt=1, budget_s=arm["budget_s"],
                           split_sha256=frozen["split"][key], input_sha256=digest(encode(frozen["data"][ds])),
                           freeze_sha256=freeze_hash)
                append_result(run / "results.jsonl", row)
    create(run / "completion.json", {"freeze_sha256": freeze_hash,
           "results_sha256": digest((run / "results.jsonl").read_bytes()),
           "rows": len(protocol["datasets"]) * len(protocol["arms"]) * len(protocol["seeds"])})
    print(freeze_hash)
    return 0


def add_commands(sub):
    for name in ("init", "proposal", "scoop", "scoop-replay", "approve", "freeze", "run", "review-package",
                 "review-target", "review", "decide", "passport", "retry"):
        parser = sub.add_parser(name)
        parser.add_argument("run_dir", type=Path)
        if name == "retry":
            parser.add_argument("parent", type=Path)
            parser.add_argument("reason", choices=("failed", "interrupted"))
        if name == "init":
            parser.add_argument("proposal", type=Path)
            parser.add_argument("--memory-idea-id", help="Report local prior records for this Idea on stderr")
            parser.add_argument("--memory-store", type=Path, help="Override the local memory path")
        if name == "approve":
            parser.add_argument("gate", choices=("H1", "H2"))
            parser.add_argument("hash")
        if name == "review":
            parser.add_argument("review_input", type=Path)
        if name == "review-package":
            parser.add_argument("--max-bytes", type=int, default=1000000)
        parser.set_defaults(launch_dispatch=True)


def main(args):
    try:
        return dispatch(args)
    except (OSError, ValueError, TypeError, KeyError, RuntimeError, AttributeError, CompileError) as exc:
        print(f"Launch refused: {exc}", file=sys.stderr)
        return 2
