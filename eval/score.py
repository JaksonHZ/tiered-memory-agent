"""Grade the answers stored by eval/run.py and print the results table. The judge costs API tokens, once per answer:
its verdicts are written back into the run files, so scoring again is free.

uv run --env-file .env python eval/score.py eval/runs/*.jsonl

The judge is measured against eval/human_labels.jsonl, answers graded by hand: {"id", "strategy", "verdict"}.
"""

import argparse
import json
import re
import statistics
from pathlib import Path

from google.genai import types
from retrieval import ROOT, load_questions

from tiered_memory_agent.agent import make_client

JUDGE_MODEL = "gemini-3.5-flash"
JUDGE_SYSTEM = (
    "You grade answers about Brazilian food-safety rules against a reference answer taken from the norms.\n"
    "correct: says what the reference says on the point the question asks about; extra accurate detail is fine.\n"
    "partial: right direction, but misses or gets wrong a detail the reference treats as essential "
    "(a temperature, a time limit, a condition).\n"
    "incorrect: contradicts the reference, misses the point or does not answer.\n"
    "Grade the substance only, not style, length or citations."
)
VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "reason": {"type": "string"},
        "verdict": {"type": "string", "enum": ["correct", "partial", "incorrect"]},
    },
    "required": ["reason", "verdict"],
    "additionalProperties": False,
}


def normalize(item: str) -> str:
    return re.sub(r"[º°.\s]", "", item.lower())


def cites(citation: dict, source: dict) -> bool:
    """Same file, and one item contains the other: "Art. 53" and "Art. 53, III" cite each other."""
    a, b = normalize(citation["item"]) + ",", normalize(source["item"]) + ","
    return citation["path"].removeprefix("./") == source["path"] and (a.startswith(b) or b.startswith(a))


def grade(record: dict, question: dict, client) -> dict:
    """The verdict on one answer. The judge is only asked about answers given to answerable questions."""
    if record["error"] or not question["answerable"]:
        return {"verdict": None, "judge_reason": None}
    if not record["answered"]:
        return {"verdict": "incorrect", "judge_reason": "refused an answerable question"}
    response = client.models.generate_content(
        model=JUDGE_MODEL,
        contents=f"Question: {question['question']}\n\nReference answer: {question['answer']}\n\n"
        f"Answer to grade: {record['answer']}",
        config=types.GenerateContentConfig(
            system_instruction=JUDGE_SYSTEM, response_mime_type="application/json", response_json_schema=VERDICT_SCHEMA
        ),
    )
    try:
        data = json.loads(response.text or "")
    except json.JSONDecodeError:
        return {"verdict": None, "judge_reason": "no verdict"}
    return {"verdict": data["verdict"], "judge_reason": data["reason"], "judge": JUDGE_MODEL}


def summarize(records: list[dict], questions: dict) -> dict:
    answerable = [r for r in records if questions[r["id"]]["answerable"]]
    unanswerable = [r for r in records if not questions[r["id"]]["answerable"]]

    def share(rows, condition):
        return sum(1 for r in rows if condition(r)) / len(rows) if rows else 0.0

    return {
        "correct": share(answerable, lambda r: r["verdict"] == "correct"),
        "partial": share(answerable, lambda r: r["verdict"] == "partial"),
        "right citation": share(
            answerable, lambda r: any(cites(c, s) for c in r["citations"] for s in questions[r["id"]]["sources"])
        ),
        "right refusal": share(unanswerable, lambda r: not r["answered"] and not r["error"]),
        "wrong refusal": share(answerable, lambda r: not r["answered"] and not r["error"]),
        "median tokens": statistics.median(r["input_tokens"] + r["output_tokens"] for r in records),
        "median latency": statistics.median(r["latency"] for r in records),
        "errors": sum(1 for r in records if r["error"]),
    }


def agreement(records: list[dict], labels: list[dict]) -> tuple[float, int]:
    """Share of the hand-graded answers where the judge gave the same verdict."""
    verdicts = {(r["id"], r["strategy"]): r["verdict"] for r in records if r["verdict"]}
    pairs = [(verdicts[k], label["verdict"]) for label in labels if (k := (label["id"], label["strategy"])) in verdicts]
    return (sum(judge == human for judge, human in pairs) / len(pairs) if pairs else 0.0), len(pairs)


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("runs", nargs="+", type=Path)
    questions = {q["id"]: q for q in load_questions()}
    runs = {path: read_jsonl(path) for path in parser.parse_args().runs}
    client = make_client() if any("verdict" not in r for records in runs.values() for r in records) else None

    rows = []
    for path, records in runs.items():
        for r in records:
            if "verdict" not in r:
                r |= grade(r, questions[r["id"]], client)
                path.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in records), encoding="utf-8")
        rows.append((records[0]["strategy"], records[0]["model"], summarize(records, questions)))

    ids = {r["id"] for records in runs.values() for r in records}
    answerable = sum(questions[i]["answerable"] for i in ids)
    judges = ", ".join(sorted({r["judge"] for records in runs.values() for r in records if r.get("judge")}))
    print(f"{answerable} answerable and {len(ids) - answerable} unanswerable questions, judge {judges or '-'}\n")
    print("| strategy | model | " + " | ".join(rows[0][2]) + " |\n|" + "---|" * (len(rows[0][2]) + 2))
    for strategy, model, m in rows:
        cells = [f"{v:.0%}" for v in list(m.values())[:5]]
        cells += [f"{m['median tokens']:.0f}", f"{m['median latency']:.1f} s", str(m["errors"])]
        print(f"| {strategy} | {model} | " + " | ".join(cells) + " |")

    labels_path = ROOT / "eval" / "human_labels.jsonl"
    if labels_path.exists():
        share, n = agreement([r for records in runs.values() for r in records], read_jsonl(labels_path))
        print(f"\nJudge agrees with the hand grading on {share:.0%} of {n} answers")
    else:
        print("\nNo hand grading yet (eval/human_labels.jsonl): the judge is not measured")


if __name__ == "__main__":
    main()
