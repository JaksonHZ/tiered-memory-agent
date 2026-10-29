"""Measure consolidation on the synthetic episodes against eval/consolidation_key.jsonl. Costs a few API calls.

uv run --env-file .env python eval/consolidation.py

The proposals and their checks go to eval/runs/consolidation-<model>.jsonl; running again overwrites it. Nothing is
written to proposals/, so the episodes stay new for the consolidate command.
"""

import json
import logging

from retrieval import ROOT

from tiered_memory_agent import agent
from tiered_memory_agent.consolidate import MODEL, consolidate, load_episodes
from tiered_memory_agent.search import cites


def measure(proposals: list[dict], key: list[dict]) -> dict:
    """What a reviewer would want to know: right facts that passed, groups kept together, planted errors that got
    through, personal data that leaked."""
    passed = [p for p in proposals if p["passed"]]

    def through(episode: str) -> list[dict]:
        return [p for p in passed if episode in p["episodes"]]

    facts = [k for k in key if k["kind"] in ("fact", "personal-data")]
    groups: dict[str, list[str]] = {}
    for k in key:
        if "group" in k:
            groups.setdefault(k["group"], []).append(k["episode"])
    errors = [k for k in key if k["kind"] in ("unsupported", "contradiction")]
    planted = [s for k in key for s in k.get("personal_data", [])]
    blocked: dict[str, int] = {}
    for p in proposals:
        for name, check in p["checks"].items():
            blocked[name] = blocked.get(name, 0) + (not check["passed"])
    return {
        "proposals": len(proposals),
        "passed": len(passed),
        "facts passed with the right source": (
            sum(any(cites(p, s) for p in through(k["episode"]) for s in k["sources"]) for k in facts),
            len(facts),
        ),
        "passed proposals that cite an expected item": (
            sum(
                any(cites(p, s) for k in key if k["episode"] in p["episodes"] for s in k.get("sources", []))
                for p in passed
            ),
            len(passed),
        ),
        "repeated facts merged into one proposal": (
            sum(any(set(names) <= set(p["episodes"]) for p in proposals) for names in groups.values()),
            len(groups),
        ),
        "planted errors that passed": (sum(bool(through(k["episode"])) for k in errors), len(errors)),
        "personal data that leaked": (
            sum(any(s in p["title"] + p["note"] for p in passed) for s in planted),
            len(planted),
        ),
        "failed each check": blocked,
    }


def main() -> None:
    logging.getLogger().setLevel(logging.WARNING)
    key = [json.loads(line) for line in (ROOT / "eval" / "consolidation_key.jsonl").read_text().splitlines()]
    names = {k["episode"] for k in key}
    proposals = consolidate([e for e in load_episodes(ROOT) if e["name"] in names], agent.make_client())

    out = ROOT / "eval" / "runs" / f"consolidation-{MODEL}.jsonl"
    out.write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in proposals), encoding="utf-8")
    for name, value in measure(proposals, key).items():
        print(f"{name}: {f'{value[0]}/{value[1]}' if isinstance(value, tuple) else value}")
    print(f"-> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
