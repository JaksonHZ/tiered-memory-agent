---
license: cc-by-4.0
language:
- pt
task_categories:
- question-answering
- text-retrieval
pretty_name: Perguntas sobre normas sanitárias para restaurantes
size_categories:
- n<1K
configs:
- config_name: questions
  data_files:
  - split: test
    path: questions.jsonl
- config_name: corpus
  data_files:
  - split: corpus
    path: corpus.jsonl
---

# Perguntas sobre normas sanitárias para restaurantes

> **EN:** 77 questions in Portuguese about food-safety rules for restaurants, each with a reference answer and the
> norm item that supports it (10 have no answer in the norms), plus the norm text split into 578 items. Built to
> compare retrieval strategies for an agent.

Conjunto de avaliação do projeto [tiered-memory-agent](https://github.com/JaksonHZ/tiered-memory-agent). Serve para
medir se um agente responde dúvidas de restaurantes com base nas normas sanitárias, cita o item certo e diz quando as
normas não respondem.

## Arquivos

**`questions.jsonl`:** 77 perguntas; 67 têm resposta nas normas e 10 não têm.

| campo | conteúdo |
|---|---|
| `id` | identificador (`q001`...) |
| `question` | a pergunta, como alguém da cozinha perguntaria |
| `answer` | resposta de referência; nas perguntas sem resposta, diz que as normas não tratam do assunto |
| `sources` | itens que sustentam a resposta: `{"path", "item"}`, que apontam para o `corpus` |
| `answerable` | `false` quando o certo é dizer que as normas não respondem |
| `origin` | `llm`: a pergunta foi redigida por LLM a partir do texto das normas |
| `reviewed` | `true` quando a pergunta já foi revisada por uma pessoa |

**`corpus.jsonl`:** o texto literal das normas, um registro por item (artigo, inciso, subitem ou anexo).

| campo | conteúdo |
|---|---|
| `path` | arquivo da norma no repositório, dentro da pasta do tema (`semantic/<tema>/<norma>.md`) |
| `item` | o item, como a norma o numera (`4.8.14`, `Art. 61, II`...) |
| `title` | tema e norma |
| `context` | o caput, quando o item é um inciso |
| `text` | o texto do item |

As normas:

- RDC ANVISA nº 216/2004: boas práticas para serviços de alimentação;
- RDC ANVISA nº 275/2002: procedimentos operacionais padronizados e lista de verificação das boas práticas;
- Portaria CVS nº 3/2026, de São Paulo: boas práticas para comércio de alimentos e serviços de alimentação;
- Portaria CVS nº 9/2026, de São Paulo: muda a vigência da CVS 3/2026.

As URLs, as datas de download e os hashes estão em
[sources/SOURCES.md](https://github.com/JaksonHZ/tiered-memory-agent/blob/main/sources/SOURCES.md).

## Como usar

No projeto, uma resposta cita certo quando cita o mesmo arquivo e o item de `sources`, o caput dele ou um inciso
dele: `Art. 61` e `Art. 61, II` contam um pelo outro. A conferência está em `cites`, em
[search.py](https://github.com/JaksonHZ/tiered-memory-agent/blob/main/src/tiered_memory_agent/search.py).

Os resultados das duas estratégias do projeto, navegação por índice e busca por embeddings, estão no
[README do repositório](https://github.com/JaksonHZ/tiered-memory-agent#resultados).

## Limitações

- Todas as perguntas foram redigidas por LLM. O campo `reviewed` mostra quais já passaram por revisão humana.
- As normas de São Paulo valem só no estado, e as perguntas misturam regras federais e paulistas.
- O texto das normas foi extraído de HTML e PDF oficiais. Ele não substitui o publicado no Diário Oficial.

## Licença

Perguntas e respostas: CC BY 4.0. O texto das normas é ato oficial e não tem proteção de direito autoral (Lei
9.610/98, art. 8º, IV).
