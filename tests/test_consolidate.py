import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from consolidation import measure

from tiered_memory_agent import consolidate, server
from tiered_memory_agent.search import chunk_tree

NORM = "semantic/food-preparation/rdc.md"


class FakeLLM:
    """Stands in for google.genai.Client: answers each request with the next scripted JSON."""

    def __init__(self, *replies):
        self.replies, self.requests = list(replies), []
        self.models = self

    def generate_content(self, **request):
        self.requests.append(request)
        return SimpleNamespace(text=json.dumps(self.replies.pop(0)))


@pytest.fixture(autouse=True)
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "ROOT", tmp_path)
    monkeypatch.setattr(consolidate, "nearest", lambda text, k=5: [])
    folder = tmp_path / "semantic" / "food-preparation"
    folder.mkdir(parents=True)
    (folder / "index.md").write_text(
        "# Preparação do alimento\n\n## Arquivos\n\n- [semantic/food-preparation/rdc.md]\n"
    )
    (folder / "rdc.md").write_text(
        '---\nnorm: "RDC"\n---\n\n# Preparação — RDC\n\n'
        "4.8.11 Os óleos devem ser aquecidos a temperaturas não superiores a 180ºC.\n\n"
        "4.8.14 Os alimentos descongelados não devem ser recongelados.\n"
    )
    return tmp_path


def episode(title: str) -> str:
    return Path(server.remember(title, f"{title}.", "conversa sintética")).stem


def proposal(title, note, item, episodes):
    return {"title": title, "topic": "food-preparation", "note": note, "path": NORM, "item": item, "episodes": episodes}


def checks(contradiction=True):
    return {
        "faithful": {"passed": True, "reason": "é o que os episódios dizem"},
        "supported": {"passed": True, "reason": "o item diz isso"},
        "contradiction": {"passed": contradiction, "reason": "ok" if contradiction else "o item proíbe"},
        "duplicate": {"passed": True, "reason": "nenhuma igual"},
    }


def test_a_proposal_passes_only_when_every_check_passes_and_the_llm_checks_run_last(root):
    oil, oil_again, refreeze = episode("Óleo até 180"), episode("Óleo não passa de 180"), episode("Pode recongelar")
    llm = FakeLLM(
        {
            "proposals": [
                proposal("Óleo até 180 °C", "Não aqueça o óleo acima de 180 °C.", "4.8.11", [oil, oil_again]),
                proposal("Recongelar", "Pode recongelar se estiver gelado.", "4.8.14", [refreeze]),
                proposal("Óleo", "Dúvidas: ligue (11) 90000-0000.", "4.8.11", [oil]),
                proposal("Óleo", "Troque o óleo toda semana.", "9.9.9", [oil]),
                proposal("Óleo", "Não aqueça o óleo acima de 180 °C.", "4.8.11", ["2020-01-01-unknown"]),
            ]
        },
        checks(),
        checks(contradiction=False),
    )

    result = consolidate.consolidate(consolidate.load_episodes(root), llm)

    assert [p["passed"] for p in result] == [True, False, False, False, False]
    assert len(llm.requests) == 3  # the proposals, then the LLM checks of the two that passed the others
    assert result[0]["episodes"] == [oil, oil_again]
    assert result[1]["checks"]["contradiction"] == {"passed": False, "reason": "o item proíbe"}
    assert result[2]["checks"]["personal_data"] == {"passed": False, "reason": "encontrado: telefone"}
    assert "supported" not in result[2]["checks"]
    assert result[3]["checks"]["source"]["reason"] == "item não encontrado na norma"
    assert result[4]["checks"]["source"]["reason"] == "nenhum episódio de origem"


def test_proposal_files_mark_their_episodes_as_consolidated_and_never_keep_personal_data(root):
    oil, refreeze = episode("Óleo até 180"), episode("Pode recongelar")
    review = {"checks": {"personal_data": {"passed": False, "reason": "encontrado: telefone"}}, "passed": False}
    leak = proposal("Óleo", "Dúvidas: ligue (11) 90000-0000.", "4.8.11", [oil]) | review

    path = consolidate.write_proposal(leak, root)

    assert [e["name"] for e in consolidate.new_episodes(root)] == [refreeze]
    assert "90000" not in path.read_text() and "❌ **Dado pessoal:** encontrado: telefone" in path.read_text()


def test_an_accepted_note_goes_to_the_topic_notes_and_index_and_search_finds_it(root):
    note = proposal("Óleo até 180 °C", "Não aqueça o óleo acima de 180 °C.", "4.8.11", ["2026-10-29-oleo"])

    consolidate.add_note(note, root)
    consolidate.add_note(note | {"title": "Outra"}, root)

    index = (root / "semantic" / "food-preparation" / "index.md").read_text()
    assert index.count(consolidate.notes_entry("food-preparation")) == 1
    found = [c for c in chunk_tree(root / "semantic") if c["path"].endswith("notes.md")]
    assert [c["item"] for c in found] == ["Óleo até 180 °C", "Outra"]
    assert "Fonte: semantic/food-preparation/rdc.md, item 4.8.11" in found[0]["text"]


def test_measure_counts_facts_groups_errors_and_leaks():
    def p(episodes, passed, item="4.8.11", note="ok"):
        return proposal("t", note, item, episodes) | {"passed": passed, "checks": {"source": {"passed": passed}}}

    key = [
        {"episode": "a1", "kind": "fact", "group": "oil", "sources": [{"path": NORM, "item": "4.8.11"}]},
        {"episode": "a2", "kind": "fact", "group": "oil", "sources": [{"path": NORM, "item": "4.8.11"}]},
        {"episode": "x", "kind": "contradiction", "sources": []},
        {
            "episode": "pd",
            "kind": "personal-data",
            "sources": [{"path": NORM, "item": "4.8.14"}],
            "personal_data": ["Fulano"],
        },
    ]
    proposals = [p(["a1", "a2"], True), p(["x"], True), p(["pd"], True, "4.8.14", "Fulano disse")]

    m = measure(proposals, key)

    assert m["facts passed with the right source"] == (3, 3)
    assert m["passed proposals that cite an expected item"] == (2, 3)  # x passed citing an item it lacks
    assert m["repeated facts merged into one proposal"] == (1, 1)
    assert m["planted errors that passed"] == (1, 1)
    assert m["personal data that leaked"] == (1, 1)
