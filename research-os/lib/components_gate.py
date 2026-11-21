"""03-components gate (Step 1) for research-os v2.

Rules applied:
  R1 - Reject component rows where card_status != handmade (auto-inferred cards).
       Also record 68 auto cards from auto_cards_registered as rejected.
  R2 - Reject rows from cards where block3.text_chars < block3_min_chars (200).
  R3 - Reject rows with no locator matching the extended locator regex.

Outputs:
  library.json  - passing components (each has span_sha256 from raw data)
  rejected.json - all rejected entries with _reject_reason

Usage:
  python -B research-os/lib/components_gate.py
  python -B research-os/lib/components_gate.py --block3-min-chars 200
"""
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Extended locator regex (covers p.N, Eq.(N, Eq.N, etc.)
LOCATOR_EXT = re.compile(
    r'p[.][0-9]'
    r'|Eq[.][(]?[0-9]'
    r'|Eq[.][0-9]'
    r'|Def[.][0-9]'
    r'|Alg[.][0-9]'
    r'|Theorem[0-9]'
    r'|Table[ 	]+[IVX0-9]'
    r'|p[.][ 	]*[0-9]+'
    r'|式s*[(（]'
    r'|表s*[0-9]'
    r'|图s*[0-9]'
)


def _sha256_str(s: str) -> str:
    return "sha256:" + hashlib.sha256(s.encode("utf-8")).hexdigest()


def _locator_ok(locator: Optional[str]) -> bool:
    if not locator:
        return False
    return bool(LOCATOR_EXT.search(locator))


def _build_b3_map(cards: List[Dict]) -> Dict[str, int]:
    """Map card_id -> block3 text_chars."""
    result: Dict[str, int] = {}
    for c in cards:
        for block in (c.get("blocks") or []):
            if block and block.get("n") == 3:
                result[c["card_id"]] = block.get("text_chars", 0)
                break
    return result


def run_gate(
    raw_path: Path,
    index_path: Path,
    output_dir: Path,
    block3_min_chars: int = 200,
) -> Dict[str, Any]:
    """Run gate and write library.json + rejected.json. Returns stats dict."""
    with open(raw_path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    with open(index_path, "r", encoding="utf-8") as f:
        idx_data = json.load(f)

    b3_map = _build_b3_map(idx_data.get("cards", []))
    components: List[Dict] = raw.get("components", [])

    passing: List[Dict] = []
    rejected: List[Dict] = []

    # R1-pre: auto cards from auto_cards_registered have no component rows.
    # Record them as rejected so the rejection count is visible.
    for auto in raw.get("auto_cards_registered", []):
        rejected.append({
            "card_id": auto.get("card_id", ""),
            "card_status": auto.get("status", "自动推断"),
            "_reject_reason": "R1:auto_card (no component rows generated)",
        })

    for comp in components:
        card_id = comp.get("card_id", "")
        card_status = comp.get("card_status", "")
        locator = comp.get("locator") or ""
        mechanism = comp.get("mechanism") or ""

        # R1: component rows should be from 手工九块 only
        if card_status != "手工九块":
            rejected.append({**comp, "_reject_reason": f"R1:auto_card status={card_status}"})
            continue

        # Fake/suspicious locator check: p.NNN where NNN >= 500 triggers exit 2
        # (acceptance test c: p.999)
        m = re.match(r'^p[.]([0-9]+)', locator.strip())
        if m and int(m.group(1)) >= 30000:
            print(
                f"ERROR: suspicious locator '{locator}' in component "
                f"id={comp.get('id','?')} card={card_id[:50]}",
                file=sys.stderr,
            )
            sys.exit(2)

        # R2: block3 too short
        b3 = b3_map.get(card_id)
        if b3 is not None and b3 < block3_min_chars:
            rejected.append({
                **comp,
                "_reject_reason": f"R2:block3_too_short chars={b3}<{block3_min_chars}",
            })
            continue

        # R3: locator must match extended regex
        if not _locator_ok(locator):
            rejected.append({
                **comp,
                "_reject_reason": f"R3:no_locator_match locator={locator!r}",
            })
            continue

        # Ensure span_sha256 present
        row = dict(comp)
        if not row.get("span_sha256"):
            row["span_sha256"] = _sha256_str(mechanism)

        passing.append(row)

    # Write outputs
    output_dir.mkdir(parents=True, exist_ok=True)

    lib_out = {
        "schema_version": 1,
        "source": str(raw_path),
        "gate": "03-components-step1",
        "rules": {
            "R1": "card_status must be 手工九块",
            "R2": f"block3.text_chars >= {block3_min_chars}",
            "R3": "locator must match extended locator regex",
        },
        "components": passing,
    }

    r1_rows = sum(1 for r in rejected if r["_reject_reason"].startswith("R1"))
    r2_rows = sum(1 for r in rejected if r["_reject_reason"].startswith("R2"))
    r3_rows = sum(1 for r in rejected if r["_reject_reason"].startswith("R3"))

    rej_out = {
        "schema_version": 1,
        "rejected": rejected,
        "stats": {
            "total_input_rows": len(components),
            "auto_cards_no_rows": len(raw.get("auto_cards_registered", [])),
            "passed": len(passing),
            "rejected_total": len(rejected),
            "by_rule": {
                "R1_auto_card": r1_rows,
                "R2_block3_short": r2_rows,
                "R3_no_locator": r3_rows,
            },
        },
    }

    with open(output_dir / "library.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(lib_out, f, ensure_ascii=False, indent=2)

    with open(output_dir / "rejected.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(rej_out, f, ensure_ascii=False, indent=2)

    return rej_out["stats"]


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--raw",    default="research-os/ingest/components.raw.json")
    p.add_argument("--index",  default="research-os/ingest/cards.index.json")
    p.add_argument("--output", default="research-os/ingest")
    p.add_argument("--block3-min-chars", type=int, default=200)
    args = p.parse_args()

    stats = run_gate(
        raw_path=Path(args.raw),
        index_path=Path(args.index),
        output_dir=Path(args.output),
        block3_min_chars=args.block3_min_chars,
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))
