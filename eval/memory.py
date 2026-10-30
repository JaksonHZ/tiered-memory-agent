"""Comparison 2: does a reviewed base answer better than the raw conversations? Costs API tokens.

uv run --env-file .env python eval/memory.py [--reps N]

The same agent, prompt and search tool, over three memories:
- reviewed: semantic/, the norms plus the notes that went in by pull request;
- episodic: episodic/ only, the conversations as they were stored, without review;
- mixed: both, a memory that keeps the conversations next to the norms without review.

The questions (eval/memory_questions.jsonl) ask about what the synthetic conversations say: right facts, and the
planted errors (rules the norms do not have, rules that contradict them). The sentence that marks a conversation as
synthetic is left out of what the agent reads: a real conversation would not carry it.

Answers go to eval/runs/memory-<model>.jsonl, and running again resumes. Every answer, answerable question or not, is
graded against the reference answer with the rubric of eval/score.py, in the fields "verdict" and "judge"; on a planted
error, "incorrect" means the answer repeated it. The table counts the graded answers.
"""

import argparse
import json
import logging
import re
import time
from pathlib import Path

from google.genai import types
from retrieval import ROOT, load_questions

from tiered_memory_agent import agent
from tiered_memory_agent.consolidate import load_episodes
from tiered_memory_agent.search import SemanticIndex, chunk_tree, format_results

ARMS = ("reviewed", "episodic", "mixed")
SYNTHETIC = "Conversa sintética, criada para testar a consolidação. "
SYSTEM = (
    "You answer questions from restaurant owners and staff about Brazilian food-safety rules, using only what the "
    "memory search returns, never general knowledge. Answer in Portuguese, briefly. Cite every entry your answer "
    "relies on with its path and item exactly as the search returns them. If the memory does not answer the "
    "question, say so and set answered to false. Finish by calling answer."
)
SEARCH = types.FunctionDeclaration(
    name="search",
    description="Search the memory. Returns the k most similar entries, each with the path and item to cite.",
    parameters_json_schema={
        "type": "object",
        "properties": {"query": {"type": "string"}, "k": {"type": "integer", "description": "1 to 20, default 5"}},
        "required": ["query"],
    },
)


def conversations(root: Path) -> list[dict]:
    """One search entry per episodic note, cited by its title."""
    return [
        {
            "path": f"episodic/{e['name']}.md",
            "item": e["title"],
            "title": e["title"],
            "context": "",
            "text": re.sub(r"^# .*\n", "", e["text"].strip()).replace(SYNTHETIC, "").strip(),
        }
        for e in load_episodes(root)
    ]


def memories(root: Path) -> dict[str, list[dict]]:
    norms, talks = chunk_tree(root / "semantic"), conversations(root)
    return {"reviewed": norms, "episodic": talks, "mixed": norms + talks}


def load_memory_questions() -> list[dict]:
    """Each line names a question of eval/questions.jsonl and its kind, or is a whole new question."""
    known = {q["id"]: q for q in load_questions()}
    lines = (ROOT / "eval" / "memory_questions.jsonl").read_text(encoding="utf-8").splitlines()
    return [known.get((m := json.loads(line))["id"], {}) | m for line in lines if line.strip()]


def summarize(records: list[dict], questions: dict) -> dict[str, dict]:
    """Per memory: right facts, planted errors repeated, and answers that cite a conversation."""
    table = {}
    for arm in ARMS:
        rows = [r for r in records if r["arm"] == arm and r.get("verdict")]
        facts = [r for r in rows if questions[r["id"]]["kind"] == "fact"]
        errors = [r for r in rows if questions[r["id"]]["kind"] != "fact"]
        talk = [r for r in rows if any(c["path"].startswith("episodic/") for c in r["citations"])]
        table[arm] = {
            "facts right": (sum(r["verdict"] == "correct" for r in facts), len(facts)),
            "planted errors repeated": (sum(r["verdict"] == "incorrect" for r in errors), len(errors)),
            "cites a conversation": (len(talk), len(rows)),
        }
    return table


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reps", type=int, default=3, help="runs of every question in every memory")
    args = parser.parse_args()
    logging.getLogger().setLevel(logging.WARNING)
    questions = load_memory_questions()
    out = ROOT / "eval" / "runs" / f"memory-{agent.MODEL}.jsonl"
    records = [json.loads(line) for line in out.read_text().splitlines()] if out.exists() else []
    done = {(r["id"], r["arm"], r["rep"]) for r in records}
    todo = [(q, a, n) for n in range(args.reps) for a in ARMS for q in questions if (q["id"], a, n) not in done]

    if todo:
        client = agent.make_client()
        indexes = {arm: SemanticIndex(chunks, cache_dir=ROOT / ".cache") for arm, chunks in memories(ROOT).items()}
        with out.open("a", encoding="utf-8") as f:
            for n, (q, arm, rep) in enumerate(todo, 1):
                index = indexes[arm]
                tools = {"search": lambda query, k=5, index=index: format_results(index.search(query, int(k)))}
                start = time.perf_counter()
                result = agent.run(q["question"], SYSTEM, [SEARCH], tools, client)
                record = {"id": q["id"], "arm": arm, "rep": rep, "model": agent.MODEL, **result}
                record["latency"] = round(time.perf_counter() - start, 2)
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                f.flush()  # a crash midway keeps the answers already paid for
                records.append(record)
                print(f"{n}/{len(todo)} {arm} {q['id']} {record['error'] or ''}")
        print(f"-> {out.relative_to(ROOT)}")

    for arm, row in summarize(records, {q["id"]: q for q in questions}).items():
        print(arm, " | ".join(f"{name} {right}/{total}" for name, (right, total) in row.items()))


if __name__ == "__main__":
    main()
