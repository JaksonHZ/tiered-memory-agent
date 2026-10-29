"""Run the agent on every question, once per strategy, and store each answer for eval/score.py. Costs API tokens.

uv run --env-file .env python eval/run.py [--strategy index|search] [--limit N]

Running again resumes eval/runs/<model>-<strategy>.jsonl, skipping questions already answered (the free tier has a
daily limit); delete the file to redo it.
"""

import argparse
import json
import logging
import time

from retrieval import ROOT, load_questions

from tiered_memory_agent import agent, server


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", choices=agent.STRATEGIES, action="append")
    parser.add_argument("--limit", type=int, help="only the first N questions, for a cheap smoke run")
    args = parser.parse_args()
    logging.getLogger().setLevel(logging.WARNING)  # not one line per HTTP request
    client = agent.make_client()
    questions = load_questions()[: args.limit]

    for strategy in args.strategy or agent.STRATEGIES:
        if strategy == "search":
            server.search("aquecimento")  # load the embedding model before timing
        out = ROOT / "eval" / "runs" / f"{agent.MODEL}-{strategy}.jsonl"
        out.parent.mkdir(exist_ok=True)
        done = {json.loads(line)["id"] for line in out.read_text().splitlines()} if out.exists() else set()
        with out.open("a", encoding="utf-8") as f:
            for n, q in enumerate(questions, 1):
                if q["id"] in done:
                    continue
                start = time.perf_counter()
                result = agent.answer(q["question"], strategy, client)
                record = {"id": q["id"], "strategy": strategy, "model": agent.MODEL, **result}
                record["latency"] = round(time.perf_counter() - start, 2)
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                f.flush()  # a crash midway keeps the answers already paid for
                print(f"{strategy} {n}/{len(questions)} {q['id']} {record['error'] or ''}")
        print(f"-> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
