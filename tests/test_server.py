import asyncio
from pathlib import Path

import pytest
from mcp import Client
from mcp.server.mcpserver.exceptions import ToolError

from tiered_memory_agent import server


@pytest.fixture(autouse=True)
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "ROOT", tmp_path)
    (tmp_path / "semantic" / "pests").mkdir(parents=True)
    (tmp_path / "semantic" / "index.md").write_text("# root")
    (tmp_path / "semantic" / "pests" / "index.md").write_text("# pests")
    (tmp_path / "semantic" / "pests" / "rdc.md").write_text("4.3.1 text")
    (tmp_path / "secret.md").write_text("outside")
    return tmp_path


def test_remember_writes_frontmatter_links_and_never_overwrites(root):
    first = server.remember("Arroz: resfriamento", "texto", "conversa sintética", tags=["temperatura"])
    stem = Path(first).stem
    second = server.remember("Arroz: resfriamento", "outro texto", "conversa sintética", links=[stem])

    assert first.startswith("episodic/") and first.endswith("-arroz-resfriamento.md")
    assert second == f"episodic/{stem}-2.md"
    assert (
        (root / first)
        .read_text()
        .startswith('---\ntitle: "Arroz: resfriamento"\nsource: "conversa sintética"\ndate: "')
    )
    assert 'tags: ["temperatura"]' in (root / first).read_text()
    assert f"- [{stem}]({stem}.md)" in (root / second).read_text()


@pytest.mark.parametrize("link", ["missing-note", "../semantic/index"])
def test_remember_rejects_unknown_links(link):
    with pytest.raises(ToolError):
        server.remember("t", "text", "s", links=[link])


def test_read_index_and_doc():
    assert server.read_index() == "# root"
    assert server.read_index("semantic/pests") == "# pests"
    assert server.read_doc("semantic/pests/rdc.md") == "4.3.1 text"


@pytest.mark.parametrize("path", ["secret.md", "semantic/../secret.md", "/etc/passwd", "semantic/pests"])
def test_read_doc_refuses_paths_outside_memory(path):
    with pytest.raises(ToolError):
        server.read_doc(path)


def test_read_index_refuses_paths_outside_semantic():
    with pytest.raises(ToolError):
        server.read_index("..")


def test_tools_over_mcp():
    async def run():
        async with Client(server.mcp) as client:
            tools = {tool.name for tool in (await client.list_tools()).tools}
            ok = await client.call_tool("read_index", {"path": "semantic/pests"})
            refused = await client.call_tool("read_doc", {"path": "secret.md"})
            return tools, ok, refused

    tools, ok, refused = asyncio.run(run())
    assert tools == {"remember", "read_index", "read_doc", "search"}
    assert not ok.is_error and ok.content[0].text == "# pests"
    assert refused.is_error and "must be inside" in refused.content[0].text
