from types import SimpleNamespace

import pytest

from tiered_memory_agent import agent, server


class FakeClient:
    """Stands in for google.genai.Client: returns scripted responses and keeps the requests it got."""

    def __init__(self, *responses):
        self.responses, self.requests = list(responses), []
        self.models = self

    def generate_content(self, **request):
        self.requests.append(request)
        return self.responses.pop(0)


def reply(*calls, finish="STOP"):
    usage = SimpleNamespace(prompt_token_count=100, candidates_token_count=10, thoughts_token_count=None)
    candidate = SimpleNamespace(content=SimpleNamespace(role="model"), finish_reason=finish)
    return SimpleNamespace(function_calls=list(calls) or None, candidates=[candidate], usage_metadata=usage)


def call(name, **args):
    return SimpleNamespace(name=name, args=args)


def offered(request):
    return {d.name for d in request["config"].tools[0].function_declarations}


@pytest.fixture(autouse=True)
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "ROOT", tmp_path)
    (tmp_path / "semantic" / "pests").mkdir(parents=True)
    (tmp_path / "semantic" / "index.md").write_text("# root: pests")
    (tmp_path / "semantic" / "pests" / "rdc.md").write_text("4.3.1 Controle integrado de vetores.")
    return tmp_path


def test_index_strategy_navigates_with_the_mcp_tools_and_returns_a_cited_answer():
    final = {"answer": "Controle integrado.", "citations": [{"path": "semantic/pests/rdc.md", "item": "4.3.1"}]}
    client = FakeClient(
        reply(call("read_index", path="semantic")),
        reply(call("read_doc", path="semantic/pests/rdc.md"), call("read_doc", path="../x"), call("search", query="x")),
        reply(call("answer", **final, answered=True)),
    )

    result = agent.answer("Como controlar pragas?", "index", client)

    assert result["answer"] == "Controle integrado." and result["answered"] and result["error"] is None
    assert result["citations"] == final["citations"]
    assert (result["input_tokens"], result["output_tokens"]) == (300, 30)
    assert [c["name"] for c in result["tool_calls"]] == ["read_index", "read_doc", "read_doc", "search"]
    assert offered(client.requests[0]) == {"read_index", "read_doc", "answer"}
    contents = client.requests[2]["contents"]
    first, second = (c.parts for c in contents[2::2])
    assert first[0].function_response.response == {"result": "# root: pests"}
    assert second[0].function_response.response == {"result": "4.3.1 Controle integrado de vetores."}
    assert "error" in second[1].function_response.response
    assert second[2].function_response.response == {"error": "unknown tool: search"}


def test_search_strategy_offers_search_and_a_turn_without_function_call_is_an_error():
    client = FakeClient(reply(finish="SAFETY"))

    result = agent.answer("?", "search", client)

    assert offered(client.requests[0]) == {"search", "read_doc", "answer"}
    assert result["error"] == "no function call (finish_reason SAFETY)" and not result["answered"]
