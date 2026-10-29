# tiered-memory-agent

> **PT:** Projeto pessoal, desenvolvido no meu tempo livre. Não tem relação com meu empregador e não usa código, dados ou
> informações dele. O desenho parte da literatura pública sobre memória de agentes e recuperação de conhecimento.
>
> **EN:** Personal project, built in my own time. It is not affiliated with my employer and uses none of its code, data or
> information. The design builds on public research on agent memory and knowledge retrieval.

Em construção.

## O que já existe

- `semantic/`: memória semântica. As RDCs ANVISA 216/2004 e 275/2002 e as Portarias CVS 3/2026 e 9/2026 de São Paulo
  divididas por tema, com o texto literal das normas e um `index.md` em cada pasta. É gerada por
  `scripts/build_semantic.py` a partir de `sources/` (ver [sources/SOURCES.md](sources/SOURCES.md)).
- `episodic/`: memória episódica. Notas em markdown com frontmatter (título, fonte, data, tags) e links entre notas;
  entram sem revisão.
- `src/tiered_memory_agent/server.py`: servidor MCP com as tools `remember`, `read_index`, `read_doc` e `search`.
- Duas estratégias de recuperação: (a) navegação por índice, em que o agente desce pelos `index.md` com `read_index`
  e `read_doc`; (b) busca por embeddings (`search`, em `search.py`), com o modelo local
  [multilingual-e5-small](https://huggingface.co/intfloat/multilingual-e5-small) e um trecho por item de norma.
- `eval/questions.jsonl`: perguntas com resposta e item-fonte esperados, inclusive perguntas sem resposta na base.
  `eval/retrieval.py` mede se a busca (b) traz o item esperado entre os k primeiros, sem LLM.
- Harness de avaliação: `src/tiered_memory_agent/agent.py` é o agente (Gemini 3.5 Flash-Lite) que responde cada
  pergunta com as mesmas tools do servidor MCP, numa estratégia por vez. `eval/run.py` guarda as respostas em
  `eval/runs/<modelo>-<estratégia>.jsonl` e `eval/score.py` mede acerto (Gemini 3.5 Flash como juiz, com rubrica),
  citação certa, recusa certa, tokens e latência. O juiz é conferido contra uma amostra corrigida à mão
  (`eval/human_labels.jsonl`).

## Resultados (parciais)

São 77 perguntas: 67 têm resposta na base e 10 não têm. O agente é o Gemini 3.5 Flash-Lite. A estratégia (b) ainda
não terminou, porque o plano gratuito do Gemini tem limite diário; ela entra nesta tabela quando acabar.

| estratégia | correta | parcial | citação certa | recusa certa | recusa indevida | tokens (mediana) | latência (mediana) | erros |
|---|---|---|---|---|---|---|---|---|
| (a) índice | 88% | 9% | 66% | 90% | 0% | 12.242 | 51 s | 0 |

- **Correta e parcial:** nota do juiz sobre o conteúdo, nas 67 perguntas com resposta. Recusar uma delas conta como
  incorreta.
- **Citação certa:** a resposta cita o item esperado, ou um item que o contém ou que está contido nele. É conferida
  sem LLM.
- **Recusa certa:** fração das 10 perguntas sem resposta em que o agente disse que as normas não respondem.
- **Recusa indevida:** fração das 67 perguntas com resposta em que o agente recusou responder.
- **Tokens:** entrada mais saída, somados em todos os turnos da pergunta.

O que os erros da estratégia (a) mostram:

- **Duas respostas erradas:**
  - Em uma, o agente deu o prazo geral de 5 dias para maionese, que pela norma de São Paulo dura 2 dias.
  - Na outra, falou de como guardar caixas de papelão, sem dizer que elas não podem entrar na cozinha.
- **Seis parciais.** Duas apresentam uma regra só de São Paulo como se valesse no país todo, e uma diz que as normas
  não tratam de um assunto que a RDC 216 trata.
- **Citações abaixo do conteúdo.** O agente acerta o conteúdo bem mais vezes do que a citação. Muitas vezes cita um
  bloco inteiro, como "Capítulo III, seção III (arts. 49 a 68)", em vez do item exato.
- **Recusas.** Recusou 9 das 10 perguntas sem resposta na base e nunca recusou uma que tinha resposta.

Limitações:

- **Quem julgou.** As notas publicadas foram dadas pelo Claude Opus 5.5, numa sessão do Claude Code, com a mesma
  rubrica do `score.py`. O juiz recebeu só a pergunta, a resposta de referência e a resposta do agente, sem saber a
  estratégia nem as citações. O juiz automático do `score.py`, o Gemini 3.5 Flash, aceita só 20 chamadas por dia no
  plano gratuito. Nas 18 respostas que ele chegou a julgar, deu a mesma nota que o Claude em todas. Cada nota fica no
  arquivo da rodada com o motivo e o campo `judge`. A amostra corrigida à mão ainda falta.
- **Margem de erro.** Foi uma rodada por estratégia, sem repetição. Com 67 perguntas, a margem fica em torno de 8
  pontos percentuais para cima ou para baixo.
- **Latência.** Ela inclui as esperas impostas pelo limite de requisições do plano gratuito. Serve para comparar as
  estratégias na mesma conta, não como tempo de resposta real.
- **Gabarito.** O gabarito (`eval/questions.jsonl`) ainda está em revisão.

## Como rodar

Requer Python 3.12 e [uv](https://docs.astral.sh/uv/).

```sh
uv sync
uv run pytest
uv run ruff check .
uv run python eval/retrieval.py   # baixa o modelo de embeddings (~470 MB) na primeira vez
```

A avaliação com LLM chama a API do Gemini e lê a chave de um `.env` (`GEMINI_API_KEY=...`), que fica fora do
git. O plano gratuito basta: crie a chave no [Google AI Studio](https://aistudio.google.com/apikey) num projeto sem
faturamento vinculado. Ele tem limite diário: 500 chamadas no Flash-Lite, o que dá cerca de um dia e meio para as
duas estratégias, e 20 no juiz Flash. Quando o limite estoura, basta rodar de novo no dia seguinte para continuar de
onde parou. O `score.py` só chama o juiz nas respostas que ainda não têm nota; nas rodadas que estão em `eval/runs/`,
ele apenas refaz a tabela. Os testes usam um LLM falso e não precisam da chave.

```sh
uv run --env-file .env python eval/run.py --limit 2  # rodada de teste
uv run --env-file .env python eval/run.py            # todas as perguntas; rodar de novo continua de onde parou
uv run --env-file .env python eval/score.py eval/runs/*.jsonl
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
