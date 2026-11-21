"""Deterministic local paper-card search for four preregistered axes."""
import hashlib
from card_parser import read_card

AXES = ("mechanism", "data", "metric", "setting")


def collect(directory, queries):
    if set(queries) != set(AXES):
        raise ValueError("declare mechanism, data, metric and setting queries")
    if not directory.is_dir():
        raise ValueError("card directory is unavailable")
    cards, failures, inventory = {}, [], {}
    for path in sorted(directory.glob("*.md")):
        if path.name.startswith("00-"):
            continue
        try:
            before = path.read_bytes()
            inventory[path.name] = "sha256:" + hashlib.sha256(before).hexdigest()
            _, body, _ = read_card(path)
            if path.read_bytes() != before:
                raise ValueError("card changed while reading")
            cards[path.name] = body.splitlines()
        except (OSError, ValueError) as exc:
            failures.append({"card": path.name, "reason": str(exc)})
    output = {}
    for axis in AXES:
        terms = queries[axis]
        if type(terms) is not list or not terms or not all(type(term) is str and term.strip() for term in terms):
            raise ValueError(f"empty or invalid queries for {axis}")
        hits, excluded = [], []
        for name, lines in cards.items():
            matches = [{"card": name, "body_line": number, "span": line}
                       for number, line in enumerate(lines, 1)
                       if any(term.casefold() in line.casefold() for term in terms)]
            if matches:
                hits.extend(matches)
            else:
                excluded.append({"card": name, "reason": "no literal match in body"})
        output[axis] = {"terms": terms, "hits": hits, "excluded": excluded,
                        "status": ("failed" if not cards else "partial_coverage" if failures
                                   else "hits" if hits else "zero_hits")}
    return {"axes": output, "inventory": inventory, "failures": failures,
            "limits": "Literal case-insensitive body search of local Markdown cards only; not a novelty verdict."}
