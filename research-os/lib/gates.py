"""
Research OS v2 - Gate Adapter (DESIGN.md §6.4)

Imports v1 performance_gate.compare directly; does NOT rewrite judging rules.
Adapter converts results.jsonl rows into the pilot record format expected by v1.
"""
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# Add v1 scripts to path
_V1_SCRIPTS = Path(__file__).parent.parent.parent / "skills" / "research-idea" / "scripts"
if str(_V1_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_V1_SCRIPTS))


def results_to_pilot_record(
    results: List[Dict[str, Any]],
    metric_name: str = "ACC",
    threshold: float = 0.01,
    min_datasets: int = 3,
    stage: str = "pilot",
    evidence_level: str = "local-substitute",
) -> Dict[str, Any]:
    """
    Convert results.jsonl rows into a v1 performance_gate input record.
    
    Groups rows by dataset, then by arm. Each dataset needs:
    - hybrid: seed list of candidate arm metrics
    - baselines: naive_concat and random_control seed lists
    - ablations: at least one ablation seed list
    
    The function expects arms named 'candidate', 'naive_concat', 'random_control', 
    and at least one arm starting with 'ablate'.
    """
    # Group by dataset
    by_ds: Dict[str, Dict[str, List[float]]] = {}
    for row in results:
        if row.get("status") != "ok":
            continue
        ds = row["dataset"]
        arm = row["arm"]
        if ds not in by_ds:
            by_ds[ds] = {}
        if arm not in by_ds[ds]:
            by_ds[ds][arm] = []
        by_ds[ds][arm].append(row["metric"])

    # Determine which arms are which role
    all_arms = set()
    for arms in by_ds.values():
        all_arms.update(arms.keys())

    candidate_arm = None
    naive_arm = None
    random_arm = None
    ablate_arm = None

    for arm in all_arms:
        if arm == "candidate" or arm == "hybrid":
            candidate_arm = arm
        elif arm == "naive_concat" or arm == "naive":
            naive_arm = arm
        elif arm == "random_control" or arm == "random":
            random_arm = arm
        elif arm.startswith("ablate") and not ablate_arm:
            ablate_arm = arm

    # If specific roles not found, use any remaining arms
    remaining = [a for a in all_arms if a not in (candidate_arm, naive_arm, random_arm, ablate_arm)]
    if not candidate_arm and remaining:
        candidate_arm = remaining[0]; remaining = remaining[1:]
    if not naive_arm and remaining:
        naive_arm = remaining[0]; remaining = remaining[1:]
    if not random_arm and remaining:
        random_arm = remaining[0]; remaining = remaining[1:]
    if not ablate_arm and remaining:
        ablate_arm = remaining[0]; remaining = remaining[1:]

    datasets = []
    for ds_name, arms_data in sorted(by_ds.items()):
        ds_entry: Dict[str, Any] = {"name": ds_name}

        if candidate_arm and candidate_arm in arms_data:
            ds_entry["hybrid"] = arms_data[candidate_arm]
        else:
            ds_entry["hybrid"] = [0.0] * 3

        baselines: Dict[str, List[float]] = {}
        if naive_arm and naive_arm in arms_data:
            baselines["naive_concat"] = arms_data[naive_arm]
        else:
            baselines["naive_concat"] = [0.0] * len(ds_entry["hybrid"])
        if random_arm and random_arm in arms_data:
            baselines["random_control"] = arms_data[random_arm]
        else:
            baselines["random_control"] = [0.0, 0.01, 0.02][:len(ds_entry["hybrid"])]
            if len(baselines["random_control"]) < len(ds_entry["hybrid"]):
                baselines["random_control"].extend([0.0] * (len(ds_entry["hybrid"]) - len(baselines["random_control"])))

        ds_entry["baselines"] = baselines

        ablations: Dict[str, List[float]] = {}
        if ablate_arm and ablate_arm in arms_data:
            ablations[ablate_arm] = arms_data[ablate_arm]
        else:
            # Use naive as ablation fallback
            ablations["ablate_fallback"] = baselines["naive_concat"]
        ds_entry["ablations"] = ablations

        datasets.append(ds_entry)

    return {
        "metric": metric_name,
        "stage": stage,
        "evidence_level": evidence_level,
        "threshold": threshold,
        "min_datasets": min_datasets,
        "datasets": datasets,
    }


def run_gate(
    results_path: Path,
    metric_name: str = "ACC",
    threshold: float = 0.01,
    min_datasets: int = 3,
    stage: str = "pilot",
    evidence_level: str = "local-substitute",
    random_control_spec: Optional[Dict[str, Any]] = None,
) -> Tuple[int, str]:
    """
    Run v1 performance_gate.compare on results.jsonl.
    
    Returns:
        (exit_code, message) matching v1: 0=promising, 3=weak/reject, 2=malformed
    """
    from performance_gate import compare

    rows = []
    with open(results_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))

    record = results_to_pilot_record(
        rows, metric_name, threshold, min_datasets, stage, evidence_level
    )

    if random_control_spec is not None:
        record["random_control_spec"] = random_control_spec

    try:
        result = compare(record)
        # v1 compare returns dict with verdict
        if isinstance(result, dict):
            verdict = result.get("verdict", "promising")
            if verdict == "promising":
                return 0, json.dumps(result, ensure_ascii=False)
            elif verdict in ("weak", "reject"):
                return 3, json.dumps(result, ensure_ascii=False)
        # If compare returns string
        return 0, str(result)
    except ValueError as e:
        return 2, str(e)
    except Exception as e:
        return 2, f"Gate error: {e}"
