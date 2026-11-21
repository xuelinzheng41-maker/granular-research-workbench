"""Local research memory. Advisory only; never grants approval or runs code."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import unicodedata

from launch import encode, proposal

OUTCOMES = ("supported_in_scope", "negative", "inconclusive", "blocked")
REUSE = ("candidate", "validated", "integrated")
IDENT = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")


def require(ok, message):
    if not ok:
        raise ValueError(message)


def identifier(value):
    require(type(value) is str and IDENT.fullmatch(value), "invalid record or idea ID")
    return value


def text(value):
    require(type(value) is str and 0 < len(value.strip()) <= 4000, "missing or oversized text")
    return value.strip()


def file_ref(value):
    require(type(value) is str and Path(value).is_absolute(), "evidence must be an absolute local file path")
    path = Path(value).resolve(strict=True)
    require(path.is_file(), "evidence is not a file")
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(chunk)
    return {"path": str(path), "sha256": "sha256:" + sha.hexdigest()}


def store_path(path=None):
    location = path or os.environ.get("GRW_MEMORY_PATH") or Path.home() / ".granular-research-workbench" / "memory.sqlite3"
    path = Path(location).expanduser().resolve()
    require(not any((parent / ".git").exists() for parent in path.parents),
            "memory must live outside Git worktrees")
    return path


def run_ref(run):
    from run_health import health

    run = run.resolve(strict=True)
    p, sha = proposal(run)
    state, results = health(run, p, sha)
    return {"path": str(run), "state": state, "proposal_sha256": sha,
            "results_sha256": (results or {}).get("results_sha256"),
            "failed_rows": (results or {}).get("failed")}


def normalize(raw, run=None):
    fields = {"id", "idea_id", "outcome", "scope", "summary", "next_step", "evidence"}
    require(type(raw) is dict and fields <= raw.keys() <= fields | {"tags", "components"}, "invalid memory record fields")
    for key in ("id", "idea_id"):
        identifier(raw[key])
    outcome = raw["outcome"]
    require(outcome in OUTCOMES, "invalid outcome")
    refs = raw["evidence"]
    require(type(refs) is list and 0 < len(refs) <= 32, "provide 1 to 32 evidence files")
    tags = raw.get("tags", [])
    require(type(tags) is list and len(tags) <= 32, "invalid tags")
    components = raw.get("components", [])
    require(type(components) is list and len(components) <= 32, "invalid components")
    normalized = []
    for item in components:
        require(type(item) is dict and item.keys() == {"name", "status", "basis", "artifact"}, "invalid component fields")
        status = item["status"]
        require(status in REUSE, "invalid component status")
        require(status == "candidate" or outcome == "supported_in_scope", "validated/integrated components require a supported record")
        normalized.append({"name": text(item["name"]), "status": status, "basis": text(item["basis"]),
                           "artifact": file_ref(item["artifact"])})
    source = run_ref(run) if run is not None else None
    if source and outcome in ("supported_in_scope", "negative"):
        require(source["state"] in ("complete", "archived") and source["failed_rows"] == 0,
                "directional run evidence requires a verified complete run without failures")
    return {"schema_version": 1, "id": raw["id"], "idea_id": raw["idea_id"], "outcome": outcome,
            **{key: text(raw[key]) for key in ("scope", "summary", "next_step")},
            "tags": list(dict.fromkeys(map(text, tags))), "evidence": [file_ref(item) for item in refs],
            "components": normalized, "run": source}


def record(path, item):
    path.parent.mkdir(parents=True, exist_ok=True)
    body = encode(item).decode("utf-8")
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, idea_id TEXT NOT NULL, outcome TEXT NOT NULL, body TEXT NOT NULL)")
        db.execute("CREATE INDEX IF NOT EXISTS records_idea ON records (idea_id)")
        cur = db.execute("INSERT OR IGNORE INTO records VALUES (?, ?, ?, ?)",
                         (item["id"], item["idea_id"], item["outcome"], body))
        if cur.rowcount:
            return True
        (old,) = db.execute("SELECT body FROM records WHERE id = ?", (item["id"],)).fetchone()
        require(old == body, "record ID already exists with different content; use a new ID")
        return False


def find(path, *, idea_id=None, outcome=None, record_id=None):
    if not path.exists():
        return []
    where = []
    params = []
    for field, value in (("idea_id", idea_id), ("outcome", outcome), ("id", record_id)):
        if value is not None:
            where.append(field + " = ?")
            params.append(value)
    sql = "SELECT body FROM records" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY id"
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        return [json.loads(body) for (body,) in db.execute(sql, params)]


def fold(value):
    return unicodedata.normalize("NFKC", value).casefold()


def search(path, query="", *, idea_id=None, outcome=None):
    words = fold(query).split()
    rows = find(path, idea_id=idea_id, outcome=outcome)
    keys = ("id", "idea_id", "outcome", "summary", "scope", "next_step", "tags")
    results = []
    for item in rows:
        relevant = {key: item[key] for key in keys}
        relevant["components"] = [{key: c[key] for key in ("name", "status", "basis")} for c in item["components"]]
        searchable = fold(encode(relevant).decode("utf-8"))
        if all(word in searchable for word in words):
            results.append(relevant)
    return results


def verify(item):
    refs = item["evidence"] + [c["artifact"] for c in item["components"]]
    differences = []
    for ref in refs:
        try:
            require(file_ref(ref["path"]) == ref, "evidence digest or identity changed")
        except (OSError, ValueError) as exc:
            differences.append({"path": ref["path"], "error": str(exc)})
    ref = item["run"]
    if ref:
        try:
            require(run_ref(Path(ref["path"])) == ref, "linked run identity or state changed")
        except (OSError, ValueError, TypeError, KeyError, AttributeError, RuntimeError) as exc:
            differences.append({"path": ref["path"], "error": str(exc)})
    return differences


def advisory(path, idea_id):
    try:
        rows = search(path, idea_id=identifier(idea_id))
    except sqlite3.Error as exc:
        raise ValueError(f"could not read local research memory: {exc}") from exc
    print(encode({"memory_advisory": rows, "idea_id": idea_id, "authorizes_run": False}).decode(), file=sys.stderr)


def add_commands(sub):
    parser = sub.add_parser("memory", help="Record and search private prior results and reusable components")
    parser.add_argument("--store", type=Path, help="Local SQLite path outside Git (default: GRW_MEMORY_PATH or home directory)")
    commands = parser.add_subparsers(dest="memory_command", required=True)
    add = commands.add_parser("record", help="Record explicit outcome and local evidence; never overwrites")
    add.add_argument("input", type=Path)
    add.add_argument("--run", type=Path, help="Verify and link an existing run without rerunning it")
    find_cmd = commands.add_parser("search", help="Search summaries, tags and reusable components")
    find_cmd.add_argument("query", nargs="?", default="")
    find_cmd.add_argument("--idea-id", type=identifier)
    find_cmd.add_argument("--outcome", choices=OUTCOMES)
    for name in ("show", "verify"):
        commands.add_parser(name).add_argument("id", type=identifier)
    parser.set_defaults(memory_dispatch=True)


def main(args):
    try:
        path = store_path(args.store)
        if args.memory_command == "record":
            item = normalize(json.loads(args.input.read_bytes()), args.run)
            result = {"id": item["id"], "inserted": record(path, item)}
        elif args.memory_command == "search":
            result = search(path, args.query, idea_id=args.idea_id, outcome=args.outcome)
        else:
            rows = find(path, record_id=args.id)
            require(rows, "memory ID not found")
            result = rows[0]
            if args.memory_command == "verify":
                differences = verify(result)
                print(encode({"id": args.id, "verified": not differences, "differences": differences}).decode())
                return 2 if differences else 0
        print(encode(result).decode())
        return 0
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RuntimeError, sqlite3.Error) as exc:
        print(f"Memory refused: {exc}", file=sys.stderr)
        return 2
