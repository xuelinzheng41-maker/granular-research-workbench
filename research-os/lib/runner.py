"""
Research OS v2 - Experiment Runner (DESIGN.md §6)

One subprocess per (dataset, arm, seed). Fixed budget_s timeout.
Method hash verified before/after — changed method -> row marked invalid.
Writes results.jsonl lines (never reads back, never overwrites).
Failure details go to failures/<dataset>-<arm>-<seed>.json.
"""
import hashlib
import json
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional


# ── Helpers ────────────────────────────────────────────────────────────────

def _sha256_file(path: Path) -> str:
    with open(path, "rb") as f:
        return "sha256:" + hashlib.sha256(f.read()).hexdigest()


def _sha256_bytes(b: bytes) -> str:
    return "sha256:" + hashlib.sha256(b).hexdigest()


def _runner_self_hash() -> str:
    return _sha256_file(Path(__file__))


def _env_snapshot() -> Dict[str, str]:
    env: Dict[str, str] = {"python": platform.python_version()}
    for pkg in ("numpy", "sklearn", "scipy"):
        try:
            import importlib
            m = importlib.import_module(pkg if pkg != "sklearn" else "sklearn")
            env[pkg] = m.__version__
        except Exception:
            pass
    return env


# ── Worker script run in child process ────────────────────────────────────

_WORKER_TMPL = """
import json, sys
import numpy as np
sys.path.insert(0, {arm_dir!r})
from method import fit_predict

X_train = np.load({x_train!r})
y_train = np.load({y_train!r})
X_test  = np.load({x_test!r})

result = fit_predict(X_train, y_train, X_test, seed={seed}, budget_s={budget_s})

preds = np.array(result["predictions"], dtype=float)
np.save({preds_out!r}, preds)
meta = {{"coverage": result.get("coverage"), "ball_count": result.get("artifacts", {{}}).get("ball_count")}}
with open({meta_out!r}, "w") as f:
    json.dump(meta, f)
"""


# ── Core run_one ──────────────────────────────────────────────────────────

def run_one(
    *,
    arm_dir: Path,
    dataset_id: str,
    X_train, y_train, X_test, y_test,
    seed: int,
    budget_s: int,
    protocol_sha256: str,
    runner_sha256: Optional[str] = None,
    portable: bool = False,
) -> Dict[str, Any]:
    """Run one (dataset, arm, seed) combination in an isolated subprocess."""
    method_path = arm_dir / "method.py"
    if not method_path.exists():
        raise FileNotFoundError(f"method.py not found: {method_path}")

    hash_before = _sha256_file(method_path)
    runner_sha = runner_sha256 or _runner_self_hash()
    env_snap = _env_snapshot()
    arm_name = arm_dir.name

    base = {
        "dataset": dataset_id, "arm": arm_name, "seed": seed,
        "method_sha256": hash_before, "protocol_sha256": protocol_sha256,
        "runner_sha256": runner_sha, "executed_on": "local", "env": env_snap,
    }

    with tempfile.TemporaryDirectory() as _tmp:
        tmp = Path(_tmp)
        import numpy as np

        np.save(tmp / "X_train.npy", X_train)
        np.save(tmp / "y_train.npy", y_train)
        np.save(tmp / "X_test.npy",  X_test)

        preds_out = str(tmp / "preds.npy")
        meta_out  = str(tmp / "meta.json")

        script = _WORKER_TMPL.format(
            arm_dir=str(arm_dir),
            x_train=str(tmp / "X_train.npy"),
            y_train=str(tmp / "y_train.npy"),
            x_test=str(tmp / "X_test.npy"),
            seed=seed, budget_s=budget_s,
            preds_out=preds_out, meta_out=meta_out,
        )
        (tmp / "worker.py").write_text(script, encoding="utf-8")

        t0 = time.monotonic()
        try:
            proc = subprocess.run(
                [sys.executable, "-B", *(["-I"] if portable else []), str(tmp / "worker.py")],
                cwd=arm_dir if portable else None,
                timeout=budget_s + 2,
                capture_output=True, text=True,
            )
            elapsed = round(time.monotonic() - t0, 3)
        except subprocess.TimeoutExpired:
            elapsed = round(time.monotonic() - t0, 3)
            return {**base, "metric": None, "coverage": None,
                    "runtime_s": elapsed, "ball_count": None,
                    "status": "timeout", "predictions_sha256": None}

        # Verify method unchanged
        hash_after = _sha256_file(method_path)
        if hash_after != hash_before:
            return {**base, "metric": None, "coverage": None,
                    "runtime_s": elapsed, "ball_count": None,
                    "status": "invalid", "predictions_sha256": None}

        if proc.returncode != 0:
            cause = "error"
            if "MemoryError" in proc.stderr: cause = "memory"
            elif "nan" in proc.stderr.lower(): cause = "nan"
            return {**base, "metric": None, "coverage": None,
                    "runtime_s": elapsed, "ball_count": None,
                    "status": cause, "predictions_sha256": None}

        try:
            preds = np.load(preds_out)
            preds_sha = _sha256_bytes(preds.tobytes())
            from sklearn.metrics import accuracy_score
            metric_val = float(accuracy_score(y_test, preds))
            meta: Dict = {}
            if Path(meta_out).exists():
                with open(meta_out) as f:
                    meta = json.load(f)
        except Exception:
            return {**base, "metric": None, "coverage": None,
                    "runtime_s": elapsed, "ball_count": None,
                    "status": "error", "predictions_sha256": None}

        return {**base,
                "metric": metric_val,
                "coverage": meta.get("coverage"),
                "runtime_s": elapsed,
                "ball_count": meta.get("ball_count"),
                "status": "ok",
                "predictions_sha256": preds_sha}


# ── IO helpers ────────────────────────────────────────────────────────────

def append_result(results_path: Path, row: Dict[str, Any]) -> None:
    """Append one JSON line to results.jsonl."""
    results_path.parent.mkdir(parents=True, exist_ok=True)
    with open(results_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_failure(failures_dir: Path, row: Dict[str, Any]) -> None:
    """Write failure record to failures/<dataset>-<arm>-<seed>.json."""
    failures_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{row['dataset']}-{row['arm']}-{row['seed']}.json"
    with open(failures_dir / fname, "w", encoding="utf-8") as f:
        json.dump({
            "cause": row["status"], "message": "",
            "dataset": row["dataset"], "arm": row["arm"], "seed": row["seed"],
        }, f, ensure_ascii=False, indent=2)
