# tiered-memory-agent

> **PT:** Projeto pessoal, desenvolvido no meu tempo livre. Não tem relação com meu empregador e não usa código, dados ou
> informações dele. O desenho parte da literatura pública sobre memória de agentes e recuperação de conhecimento.
>
> **EN:** Personal project, built in my own time. It is not affiliated with my employer and uses none of its code, data or
> information. The design builds on public research on agent memory and knowledge retrieval.

Em construção.

## O que já existe

- `semantic/`: memória semântica. As RDCs ANVISA 216/2004 e 275/2002 e as Portarias CVS 3/2026 e 9/2026 de São Paulo
  divididas por tema, com o texto literal das normas e um `index.md` em cada pasta. É gerada por `scripts/build_semantic.py` a partir de `sources/` (ver
  [sources/SOURCES.md](sources/SOURCES.md)).
- `episodic/`: memória episódica. Notas em markdown com frontmatter (título, fonte, data, tags) e links entre notas;
  entram sem revisão.
- `src/tiered_memory_agent/server.py`: servidor MCP com as tools `remember`, `read_index` e `read_doc`.

## Como rodar

Requer Python 3.12 e [uv](https://docs.astral.sh/uv/).

```sh
uv sync
uv run pytest
uv run ruff check .
```

O servidor MCP roda por stdio. Para conectar um cliente MCP (Claude Desktop, por exemplo):

```json
{
  "mcpServers": {
    "tiered-memory-agent": {
      "command": "uv",
      "args": ["run", "--directory", "/caminho/para/tiered-memory-agent", "tiered-memory-agent"]
    }
  }
}
```
