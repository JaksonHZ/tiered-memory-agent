"""The agent used in the evaluation: an LLM answering one question with the same tools the MCP server exposes.

Strategy "index" gets read_index and read_doc (navigation, strategy a); "search" gets search and read_doc (strategy b).
The agent must call a function on every turn and finishes by calling answer, so the final answer is structured.
"""

import asyncio
import os

from google.genai import types
from mcp.server.mcpserver.exceptions import ToolError

from tiered_memory_agent import server

MODEL = "gemini-3.5-flash-lite"
STRATEGIES = {"index": ("read_index", "read_doc"), "search": ("search", "read_doc")}
TOOLS = {"read_index": server.read_index, "read_doc": server.read_doc, "search": server.search}

SYSTEM = (
    "You answer questions from restaurant owners and staff about Brazilian food-safety rules, using only the norms "
    "in the semantic memory, never general knowledge. Answer in Portuguese, briefly. Cite every item your answer "
    "relies on with the file path and the item exactly as the norm writes them, e.g. path "
    '"semantic/food-preparation/rdc-216-2004.md" and item "4.8.16", or item "Art. 53, III" for an inciso. '
    "If the norms do not answer the question, say so and set answered to false. Finish by calling answer.\n\n"
)
HOW = {
    "index": "Navigate the memory: read_index('semantic'), descend into the index.md of the relevant topic, "
    "then read_doc the norm files that may hold the answer.",
    "search": "Search the memory with search, then read_doc a norm file when you need the text around a result.",
}
ANSWER = types.FunctionDeclaration(
    name="answer",
    description="Give the final answer to the user. Call it once, at the end.",
    parameters_json_schema={
        "type": "object",
        "properties": {
            "answer": {"type": "string"},
            "citations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}, "item": {"type": "string"}},
                    "required": ["path", "item"],
                },
            },
            "answered": {"type": "boolean", "description": "false when the norms do not answer the question"},
        },
        "required": ["answer", "citations", "answered"],
    },
)


def make_client():
    """A Gemini API client on the project's own key from .env, never on another credential found on the machine."""
    from google import genai

    if not (key := os.environ.get("GEMINI_API_KEY")):
        raise SystemExit("GEMINI_API_KEY is not set: put it in .env and run with `uv run --env-file .env ...`")
    retry = types.HttpRetryOptions(attempts=8, max_delay=60)  # the free tier answers 429 when over its rate limit
    return genai.Client(
        api_key=key, vertexai=False, enterprise=False, http_options=types.HttpOptions(retry_options=retry)
    )


def declarations(names: tuple[str, ...]) -> list[types.FunctionDeclaration]:
    """The MCP server's own tool definitions, so the agent sees what an MCP client sees."""
    tools = asyncio.run(server.mcp.list_tools())
    return [
        types.FunctionDeclaration(name=t.name, description=t.description, parameters_json_schema=t.input_schema)
        for t in tools
        if t.name in names
    ]


def answer(question: str, strategy: str, client, model: str = MODEL, max_turns: int = 12) -> dict:
    """Run the agent on one question: its answer, citations, whether it answered, token usage and tool calls."""
    allowed = STRATEGIES[strategy]
    tools = {name: TOOLS[name] for name in allowed}
    return run(question, SYSTEM + HOW[strategy], declarations(allowed), tools, client, model, max_turns)


def run(
    question: str, system: str, offered: list, tools: dict, client, model: str = MODEL, max_turns: int = 12
) -> dict:
    """The function-calling loop: offered are the tool declarations, tools maps each name to the function it runs."""
    config = types.GenerateContentConfig(
        system_instruction=system,
        tools=[types.Tool(function_declarations=[*offered, ANSWER])],
        tool_config=types.ToolConfig(function_calling_config=types.FunctionCallingConfig(mode="ANY")),
    )
    contents = [types.Content(role="user", parts=[types.Part(text=question)])]
    result = {"answer": "", "citations": [], "answered": False, "input_tokens": 0, "output_tokens": 0}
    result |= {"tool_calls": [], "error": None}
    for _ in range(max_turns):
        response = client.models.generate_content(model=model, contents=contents, config=config)
        usage = response.usage_metadata
        result["input_tokens"] += usage.prompt_token_count or 0
        result["output_tokens"] += (usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)
        calls = response.function_calls or []
        if final := next((c for c in calls if c.name == "answer"), None):
            return result | (final.args or {})
        if not calls:
            reason = response.candidates[0].finish_reason if response.candidates else None
            return result | {"error": f"no function call (finish_reason {reason})"}

        parts = []
        for call in calls:
            result["tool_calls"].append({"name": call.name, "input": call.args})
            try:
                if call.name not in tools:
                    raise ToolError(f"unknown tool: {call.name}")
                output = {"result": tools[call.name](**(call.args or {}))}
            except (ToolError, TypeError) as e:
                output = {"error": str(e)}
            parts.append(types.Part.from_function_response(name=call.name, response=output))
        # the model's turn goes back unchanged: it carries the thought signatures Gemini needs
        contents += [response.candidates[0].content, types.Content(role="user", parts=parts)]
    return result | {"error": f"no answer after {max_turns} turns"}
