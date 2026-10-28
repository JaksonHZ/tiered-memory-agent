"""MCP server exposing the agent's tiered memory: episodic notes and the semantic tree."""

import json
import os
import re
import unicodedata
from datetime import date
from itertools import count
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

ROOT = Path(os.environ.get("TMA_ROOT", Path(__file__).resolve().parents[2]))

mcp = MCPServer(
    "tiered-memory-agent",
    instructions=(
        "Answers questions about food-safety rules for restaurants (Brazilian sanitary norms). "
        "Navigate the semantic memory: call read_index('semantic'), descend through the index.md "
        "of the relevant topic, then read_doc the norm file that answers. Cite the file path and "
        "the item number. Use remember to store facts from the conversation; episodic notes are "
        "unreviewed and are never a source for answers."
    ),
)


def slugify(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")[:60].strip("-") or "note"


def _resolve(path: str, *allowed: str) -> Path:
    """Resolve a repo-relative path, refusing anything outside the allowed top-level folders."""
    target = (ROOT / path).resolve()
    if not any(target.is_relative_to((ROOT / folder).resolve()) for folder in allowed):
        raise ToolError(f"path must be inside {' or '.join(allowed)}: {path}")
    return target


@mcp.tool()
def remember(title: str, text: str, source: str, tags: list[str] | None = None, links: list[str] | None = None) -> str:
    """Store an episodic note (unreviewed) and return its path.

    links: names of existing episodic notes this one relates to, e.g. "2026-10-27-cooling-rice".
    """
    if not text.strip():
        raise ToolError("text is empty")
    episodic = ROOT / "episodic"
    for link in links or []:
        if not re.fullmatch(r"[a-z0-9-]+", link) or not (episodic / f"{link}.md").is_file():
            raise ToolError(f"unknown episodic note: {link}")

    today = date.today().isoformat()
    frontmatter = "\n".join(
        f"{key}: {json.dumps(value, ensure_ascii=False)}"
        for key, value in {"title": title, "source": source, "date": today, "tags": tags or []}.items()
    )
    body = f"---\n{frontmatter}\n---\n\n# {title}\n\n{text.strip()}\n"
    if links:
        body += "\n## Links\n\n" + "".join(f"- [{link}]({link}.md)\n" for link in links)

    episodic.mkdir(exist_ok=True)
    stem = f"{today}-{slugify(title)}"
    for n in count(1):
        path = episodic / (f"{stem}.md" if n == 1 else f"{stem}-{n}.md")
        try:
            with path.open("x", encoding="utf-8") as f:
                f.write(body)
        except FileExistsError:
            continue
        return path.relative_to(ROOT).as_posix()
    raise AssertionError("unreachable")


@mcp.tool()
def read_index(path: str = "semantic") -> str:
    """Read the index.md of a folder of the semantic tree, e.g. "semantic" or "semantic/pest-control"."""
    index = _resolve(path, "semantic") / "index.md"
    if not index.is_file():
        raise ToolError(f"no index.md in {path}")
    return index.read_text(encoding="utf-8")


@mcp.tool()
def read_doc(path: str) -> str:
    """Read a markdown file from semantic/ or episodic/, e.g. "semantic/pest-control/rdc-216-2004.md"."""
    doc = _resolve(path, "semantic", "episodic")
    if doc.suffix != ".md" or not doc.is_file():
        raise ToolError(f"no markdown file at {path}")
    return doc.read_text(encoding="utf-8")


def main() -> None:
    mcp.run()
