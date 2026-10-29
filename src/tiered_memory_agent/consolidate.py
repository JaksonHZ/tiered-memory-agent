"""Consolidation (reflection): turn new episodic notes into proposed changes to the semantic memory.

An LLM groups the episodes that state the same rule into one note, backed by a norm item. Each proposal then goes
through checks (personal data, unsupported claim, contradiction with the base, duplicate) and only one that passes
them all becomes a pull request, with the checks as its review. Merging the PR is the human review: semantic/ changes
only that way.

uv run --env-file .env python -m tiered_memory_agent.consolidate [--pr]

Episodes already cited by a file in proposals/ are not new; delete the file to propose them again.
"""

import argparse
import json
import logging
import re
import subprocess
from datetime import date
from pathlib import Path

from google.genai import types

from tiered_memory_agent import agent, server
from tiered_memory_agent.search import chunk_tree, cites

MODEL = agent.MODEL
NOTES = "notes.md"
PERSONAL_DATA = {
    "CPF": re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"),
    "telefone": re.compile(r"\(?\b\d{2}\)?\s?9?\d{4}-?\d{4}\b"),
    "e-mail": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
}

PROPOSE_SYSTEM = (
    "You consolidate the episodic memory of an assistant for restaurants (unreviewed notes taken from conversations) "
    "into its semantic memory (Brazilian food-safety norms). Group the episodes that state the same practical rule "
    "and write one proposal per rule; every episode goes into exactly one proposal. Each proposal has a short note "
    "in Portuguese, written as guidance for restaurant staff, that says what its episodes say, the one candidate norm "
    "item closest to the rule, with its path and item exactly as listed, and the names of the episodes. Propose "
    "every rule the episodes state, even one you doubt or know to be wrong, without correcting it: a later step checks "
    "each proposal against the norms. Never copy personal data (names, CPF, phone numbers, e-mails) into a note."
)
CHECK_SYSTEM = (
    "You review a note proposed for the semantic memory of a food-safety assistant, before a human sees it. "
    "Answer four checks, each with passed and a short reason in Portuguese.\n"
    "faithful: the note says what the source episodes say, without correcting them or adding to them.\n"
    "supported: the cited norm item says what the note says; the note may simplify, but adds no rule, number or "
    "condition the item lacks.\n"
    "contradiction: passed when the note contradicts neither the cited item nor the related norm items.\n"
    "duplicate: passed when no existing note of the topic already says the same."
)
LLM_CHECKS = ("faithful", "supported", "contradiction", "duplicate")
CHECK = {
    "type": "object",
    "properties": {"passed": {"type": "boolean"}, "reason": {"type": "string"}},
    "required": ["passed", "reason"],
}
CHECKS_SCHEMA = {
    "type": "object",
    "properties": {name: CHECK for name in LLM_CHECKS},
    "required": list(LLM_CHECKS),
}
LABELS = {
    "personal_data": "Dado pessoal",
    "source": "Fonte na norma",
    "faithful": "Fiel aos episódios",
    "supported": "Afirmação sustentada pelo item",
    "contradiction": "Contradição com a base",
    "duplicate": "Duplicata",
}


def frontmatter(text: str) -> tuple[dict, str]:
    """The key: json-value lines between the leading --- markers, and the body after them."""
    _, head, body = text.split("---\n", 2)
    return {k: json.loads(v) for k, v in (line.split(": ", 1) for line in head.splitlines())}, body.strip()


def load_episodes(root: Path) -> list[dict]:
    episodes = []
    for path in sorted((root / "episodic").glob("*.md")):
        meta, body = frontmatter(path.read_text(encoding="utf-8"))
        episodes.append(meta | {"name": path.stem, "text": body})
    return episodes


def new_episodes(root: Path) -> list[dict]:
    """Episodes no proposal cites yet."""
    proposals = (root / "proposals").glob("*.md")
    done = {name for p in proposals for name in frontmatter(p.read_text(encoding="utf-8"))[0]["episodes"]}
    return [e for e in load_episodes(root) if e["name"] not in done]


def nearest(text: str, k: int = 5) -> list[dict]:
    """The k norm items closest to text, by the embedding search of strategy (b)."""
    return server._index(server.ROOT).search(text, k)


def item_text(chunk: dict) -> str:
    """An inciso or parágrafo means little without the caput of its article."""
    return f"{chunk['context']}\n{chunk['text']}".strip()


def generate(client, model: str, system: str, contents: str, schema: dict) -> dict:
    config = types.GenerateContentConfig(
        system_instruction=system, response_mime_type="application/json", response_json_schema=schema
    )
    return json.loads(client.models.generate_content(model=model, contents=contents, config=config).text)


def propose(episodes: list[dict], client, model: str = MODEL) -> list[dict]:
    """The LLM's proposals for these episodes: {title, topic, note, path, item, episodes}."""
    topics = sorted(p.name for p in (server.ROOT / "semantic").iterdir() if p.is_dir())
    blocks = []
    for e in episodes:
        candidates = "\n".join(f"- {c['path']} | {c['item']}: {item_text(c)[:400]}" for c in nearest(e["text"]))
        blocks.append(f"## Episode {e['name']}\n\n{e['text']}\n\nCandidate norm items:\n{candidates}")
    proposal = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "topic": {"type": "string", "enum": topics},
            "note": {"type": "string"},
            "path": {"type": "string"},
            "item": {"type": "string"},
            "episodes": {"type": "array", "items": {"type": "string", "enum": [e["name"] for e in episodes]}},
        },
        "required": ["title", "topic", "note", "path", "item", "episodes"],
    }
    schema = {"type": "object", "properties": {"proposals": {"type": "array", "items": proposal}}}
    return generate(client, model, PROPOSE_SYSTEM, "\n\n".join(blocks), schema).get("proposals", [])


def review(proposal: dict, chunks: list[dict], known: dict[str, str], client, model: str = MODEL) -> dict:
    """Every check on one proposal. The LLM checks run only when the ones without LLM pass."""
    text = f"{proposal['title']}\n{proposal['note']}"
    found = [name for name, pattern in PERSONAL_DATA.items() if pattern.search(text)]
    cited = [c for c in chunks if cites(proposal, c)]
    sources = [e for e in proposal["episodes"] if e in known]
    source = f"{proposal['path']}, {proposal['item']}; episódios {', '.join(sources)}"
    if not sources:
        source = "nenhum episódio de origem"
    if not cited:
        source = "item não encontrado na norma"
    checks = {
        "personal_data": {"passed": not found, "reason": f"encontrado: {', '.join(found)}" if found else "nenhum"},
        "source": {"passed": bool(cited and sources), "reason": source},
    }
    if all(c["passed"] for c in checks.values()):
        notes = server.ROOT / "semantic" / proposal["topic"] / NOTES
        related = "\n\n".join(f"{c['path']} | {c['item']}: {item_text(c)}" for c in nearest(proposal["note"]))
        contents = (
            f"Proposed note: {proposal['note']}\n\n"
            "Source episodes:\n" + "\n\n".join(known[e] for e in sources) + "\n\n"
            f"Cited item ({proposal['path']}, {proposal['item']}):\n" + "\n".join(item_text(c) for c in cited) + "\n\n"
            f"Related norm items:\n{related}\n\n"
            f"Existing notes of the topic:\n{notes.read_text(encoding='utf-8') if notes.exists() else '(none)'}"
        )
        checks |= generate(client, model, CHECK_SYSTEM, contents, CHECKS_SCHEMA)
    return {"episodes": sources, "checks": checks, "passed": all(c["passed"] for c in checks.values())}


def consolidate(episodes: list[dict], client, model: str = MODEL) -> list[dict]:
    """Proposals for these episodes, each with its checks; passed is True only when every check passes."""
    if not episodes:
        return []
    chunks = chunk_tree(server.ROOT / "semantic")
    known = {e["name"]: e["text"] for e in episodes}
    return [p | review(p, chunks, known, client, model) for p in propose(episodes, client, model)]


def opinion(proposal: dict) -> str:
    """The review that goes into the proposal file and the PR body."""
    lines = [
        f"- {'✅' if c['passed'] else '❌'} **{LABELS[name]}:** {c['reason']}" for name, c in proposal["checks"].items()
    ]
    return "\n".join(lines)


def write_proposal(proposal: dict, root: Path) -> Path:
    """proposals/<date>-<slug>.md with the note and its review. A note with personal data keeps only the review."""
    meta = {k: proposal[k] for k in ("title", "topic", "episodes", "passed")}
    head = "\n".join(f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in meta.items())
    leak = not proposal["checks"]["personal_data"]["passed"]
    note = "(texto omitido: a proposta trazia dado pessoal)" if leak else proposal["note"]
    body = (
        f"---\n{head}\n---\n\n# {proposal['title']}\n\n{note}\n\n"
        f"Fonte: `{proposal['path']}`, item {proposal['item']}.\n\n## Parecer\n\n{opinion(proposal)}\n"
    )
    folder = root / "proposals"
    folder.mkdir(exist_ok=True)
    stem, n = f"{date.today().isoformat()}-{server.slugify(proposal['title'])}", 1
    while (path := folder / (f"{stem}.md" if n == 1 else f"{stem}-{n}.md")).exists():
        n += 1
    path.write_text(body, encoding="utf-8")
    return path


def notes_entry(topic: str) -> str:
    """The line of a topic's index.md that points to its consolidated notes (scripts/build_semantic.py keeps it)."""
    return (
        f"- [semantic/{topic}/{NOTES}]({NOTES}): orientações consolidadas das conversas, cada uma com o item da norma"
    )


def add_note(proposal: dict, root: Path) -> Path:
    """Append the note to semantic/<topic>/notes.md, creating it and its index entry the first time."""
    folder = root / "semantic" / proposal["topic"]
    notes = folder / NOTES
    if not notes.exists():
        title = (folder / "index.md").read_text(encoding="utf-8").splitlines()[0].removeprefix("# ")
        head = 'kind: "orientações consolidadas"\nreview: "cada orientação entra por pull request aprovado"'
        notes.write_text(f"---\n{head}\n---\n\n# Orientações consolidadas — {title}\n", encoding="utf-8")
        with (folder / "index.md").open("a", encoding="utf-8") as f:
            f.write(notes_entry(proposal["topic"]) + "\n")
    with notes.open("a", encoding="utf-8") as f:
        f.write(
            f"\n## {proposal['title']}\n\n{proposal['note']}\n\n"
            f"Fonte: {proposal['path']}, item {proposal['item']}. Episódios: {', '.join(proposal['episodes'])}.\n"
        )
    return notes


def open_pr(proposal: dict, proposal_file: Path, root: Path) -> str:
    """Commit the note on a branch of its own, push it and open the PR; returns the PR's URL."""

    def run(*cmd: str) -> str:
        return subprocess.run(cmd, cwd=root, check=True, capture_output=True, text=True).stdout.strip()

    if run("git", "status", "--porcelain", "semantic"):
        raise SystemExit("semantic/ has uncommitted changes: commit or stash them first")
    branch = f"consolidation/{proposal_file.stem}"
    run("git", "switch", "-c", branch, "main")
    try:
        add_note(proposal, root)
        run("git", "add", "semantic")
        run("git", "commit", "-m", f"Consolidate: {proposal['title']}")
        run("git", "push", "-u", "origin", branch)
        body = (
            f"{proposal['note']}\n\nFonte: `{proposal['path']}`, item {proposal['item']}.\n"
            f"Episódios: {', '.join(proposal['episodes'])}.\n\n## Parecer\n\n{opinion(proposal)}\n"
        )
        return run(
            "gh", "pr", "create", "--base", "main", "--head", branch, "--title", proposal["title"], "--body", body
        )
    finally:
        run("git", "switch", "-")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pr", action="store_true", help="open a pull request for each proposal that passes")
    args = parser.parse_args()
    logging.getLogger().setLevel(logging.WARNING)
    if not (episodes := new_episodes(server.ROOT)):
        print("no new episodes")
        return
    for proposal in consolidate(episodes, agent.make_client()):
        path = write_proposal(proposal, server.ROOT)
        url = open_pr(proposal, path, server.ROOT) if args.pr and proposal["passed"] else ""
        print(f"{'passed ' if proposal['passed'] else 'blocked'} {path.relative_to(server.ROOT)} {url}")


if __name__ == "__main__":
    main()
