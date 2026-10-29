"""Build the semantic/ tree from the official texts in sources/.

Each norm is cut at its own item headings and every chunk goes to a topic folder. The norm text is
copied verbatim; only the hard line breaks of the source are rejoined into paragraphs.

    uv run python scripts/build_semantic.py
"""

import html
import json
import re
import subprocess
from pathlib import Path

from tiered_memory_agent.consolidate import NOTES, notes_entry

ROOT = Path(__file__).resolve().parents[1]
SEMANTIC = ROOT / "semantic"

# folder -> (title, what it covers). Portuguese, the language of the corpus and of the questions.
TOPICS = {
    "scope-and-definitions": (
        "Alcance e definições",
        "a quem cada norma se aplica, prazos, sanções e o glossário (alimento preparado, contaminantes, "
        "higienização, manipuladores, POP, serviço de alimentação...)",
    ),
    "buildings-and-equipment": (
        "Edificação, instalações, equipamentos, móveis e utensílios",
        "localização, fluxo e layout, pisos, paredes, tetos, portas e janelas, iluminação, ventilação, "
        "instalações sanitárias e vestiários, lavatórios, gás, equipamentos, instrumentos de medição e "
        "utensílios, manutenção e calibração",
    ),
    "cleaning-and-sanitization": (
        "Higienização de instalações, equipamentos, móveis e utensílios",
        "limpeza e desinfecção, frequência, caixas de gordura, produtos saneantes, diluição e tempo de contato",
    ),
    "pest-control": (
        "Controle integrado de vetores e pragas urbanas",
        "medidas preventivas e corretivas, controle químico por empresa especializada",
    ),
    "water-supply": (
        "Abastecimento de água",
        "água potável, gelo, vapor, reservatório e sua higienização, potabilidade",
    ),
    "waste-management": (
        "Manejo dos resíduos",
        "coletores, frequência de retirada e área de armazenamento dos resíduos, materiais recicláveis, "
        "esgotamento sanitário",
    ),
    "food-handlers": (
        "Manipuladores",
        "controle de saúde e exames, asseio, uniforme, lavagem e antissepsia das mãos, hábitos proibidos, "
        "segurança dos funcionários, capacitação e visitantes",
    ),
    "raw-materials": (
        "Matérias-primas, ingredientes e embalagens",
        "seleção de fornecedores, recebimento e inspeção de mercadorias, lotes reprovados ou vencidos, "
        "armazenamento de produtos (temperaturas, estoque, embalagens abertas)",
    ),
    "food-preparation": (
        "Preparação do alimento",
        "contaminação cruzada, descongelamento, cocção, óleos e gorduras de fritura, resfriamento, "
        "conservação a quente e sob refrigeração, higienização de hortifrutícolas, temperaturas e prazos",
    ),
    "storage-and-transport": (
        "Armazenamento, transporte e entrega",
        "identificação e temperatura do alimento preparado à espera do transporte, veículos e condições "
        "do transporte de alimentos, entrega em domicílio (delivery)",
    ),
    "display-and-service": (
        "Distribuição, exposição e consumo",
        "área de exposição e refeitório, equipamentos de exposição e sua temperatura, barreiras de "
        "proteção, self-service, utensílios de consumação, ornamentos e plantas, área de recebimento de "
        "dinheiro e cartões, venda de vegetais a granel",
    ),
    "documentation-and-records": (
        "Documentação e registro",
        "Manual de Boas Práticas, Procedimentos Operacionais Padronizados (POPs), registros, "
        "monitoramento e recolhimento de alimentos",
    ),
    "responsibility-and-training": (
        "Responsabilidade técnica e capacitação",
        "quem responde pelas atividades de manipulação, responsável técnico e cursos de capacitação exigidos",
    ),
    "samples-and-outbreaks": (
        "Guarda de amostras e surtos",
        "coleta e guarda de amostras dos alimentos servidos e o que fazer diante de suspeita de surto de "
        "doenças de transmissão hídrica e alimentar (DTHA)",
    ),
    "consumer-warnings": (
        "Advertências aos consumidores",
        "avisos no cardápio sobre alimentos que causam alergias, glúten, lactose e álcool; lista dos "
        "principais alimentos alergênicos",
    ),
}

# Each part is (line where the chunk starts, topic or None to skip, label). A chunk ends where the next
# part starts, the last one at `end` (None: end of text).
NORMS = {
    "rdc-216-2004": {
        "name": "RDC ANVISA nº 216, de 15 de setembro de 2004",
        "summary": "Regulamento Técnico de Boas Práticas para Serviços de Alimentação (a norma central)",
        "file": "rdc-216-2004.html",
        "url": "https://bvsms.saude.gov.br/bvs/saudelegis/anvisa/2004/res0216_15_09_2004.html",
        "retrieved": "2026-10-27",
        "end": "Saúde",
        "parts": [
            ("Art. 1º", "scope-and-definitions", "arts. 1º a 6º; Anexo, itens 1 (alcance) e 2 (definições)"),
            ("3. REFERÊNCIAS", None, None),
            ("4.1 EDIFICAÇÃO", "buildings-and-equipment", "item 4.1"),
            ("4.2 HIGIENIZAÇÃO", "cleaning-and-sanitization", "item 4.2"),
            ("4.3 CONTROLE", "pest-control", "item 4.3"),
            ("4.4 ABASTECIMENTO", "water-supply", "item 4.4"),
            ("4.5 MANEJO", "waste-management", "item 4.5"),
            ("4.6 MANIPULADORES", "food-handlers", "item 4.6"),
            ("4.7 MATÉRIAS-PRIMAS", "raw-materials", "item 4.7"),
            ("4.8 PREPARAÇÃO", "food-preparation", "item 4.8"),
            ("4.9 ARMAZENAMENTO", "storage-and-transport", "item 4.9"),
            ("4.10 EXPOSIÇÃO", "display-and-service", "item 4.10"),
            ("4.11 DOCUMENTAÇÃO", "documentation-and-records", "item 4.11"),
            ("4.12. RESPONSABILIDADE", "responsibility-and-training", "item 4.12"),
        ],
    },
    "rdc-275-2002": {
        "name": "RDC ANVISA nº 275, de 21 de outubro de 2002",
        "summary": "Procedimentos Operacionais Padronizados (POPs); escrita para a indústria de alimentos, "
        "é a referência dos POPs que a RDC 216 exige",
        "file": "rdc-275-2002.html",
        "url": "https://bvsms.saude.gov.br/bvs/saudelegis/anvisa/2002/rdc0275_21_10_2002.html",
        "retrieved": "2026-10-27",
        # The page carries the text twice (original and republication); the first copy ends here.
        # Annex II (checklist for food industries) is not in the page text.
        "end": "ANEXO II",
        "parts": [
            ("Art. 1º", "scope-and-definitions", "arts. 1º a 7º; Anexo I, itens 1 (alcance) e 2 (definições)"),
            ("3. REFERÊNCIAS", None, None),
            ("4. REQUISITOS", "documentation-and-records", "Anexo I, item 4.1 (requisitos gerais dos POPs)"),
            ("4.2.1.", "cleaning-and-sanitization", "Anexo I, item 4.2.1 (POP de higienização)"),
            ("4.2.2.", "water-supply", "Anexo I, item 4.2.2 (POP de potabilidade da água)"),
            ("4.2.3.", "food-handlers", "Anexo I, item 4.2.3 (POP de higiene e saúde dos manipuladores)"),
            ("4.2.4.", "waste-management", "Anexo I, item 4.2.4 (POP de manejo dos resíduos)"),
            ("4.2.5.", "buildings-and-equipment", "Anexo I, item 4.2.5 (POP de manutenção e calibração)"),
            ("4.2.6.", "pest-control", "Anexo I, item 4.2.6 (POP de controle de vetores e pragas)"),
            ("4.2.7.", "raw-materials", "Anexo I, item 4.2.7 (POP de seleção de matérias-primas)"),
            ("4.2.8.", "documentation-and-records", "Anexo I, item 4.2.8 (programa de recolhimento)"),
            ("5. MONITORAMENTO", "documentation-and-records", "Anexo I, item 5 (monitoramento e registro)"),
        ],
    },
    "cvs-3-2026": {
        "name": "Portaria CVS nº 3, de 3 de julho de 2026 (SP)",
        "summary": "regulamento técnico de boas práticas para estabelecimentos comerciais de alimentos e serviços "
        "de alimentação do Estado de São Paulo; entra em vigor em 01/02/2027, quando revoga a Portaria CVS "
        "5/2013 (datas alteradas pela Portaria CVS nº 9/2026)",
        "file": "portaria-cvs-3-2026.pdf",
        "url": "https://apicvs.saude.sp.gov.br/download/e_pt-cvs-3_030726-rep-280926.pdf",
        "retrieved": "2026-10-27",
        "end": None,
        "parts": [
            ("Art. 1º.", "scope-and-definitions", "arts. 1º a 7º (vigência, objetivo, abrangência e definições)"),
            ("CAPÍTULO II", "food-handlers", "Capítulo II, seções I e II (arts. 8º a 18)"),
            ("Seção III", "responsibility-and-training", "Capítulo II, seção III (arts. 19 a 23)"),
            ("Seção IV", "food-handlers", "Capítulo II, seção IV (art. 24, visitantes)"),
            (
                "CAPÍTULO III",
                "raw-materials",
                "Capítulo III, seções I e II (arts. 25 a 48, recebimento e armazenamento)",
            ),
            ("Seção III", "food-preparation", "Capítulo III, seção III (arts. 49 a 68)"),
            ("Seção IV", "display-and-service", "Capítulo III, seção IV (arts. 69 a 87)"),
            ("Seção V", "display-and-service", "Capítulo III, seção V (arts. 88 a 98, vegetais a granel)"),
            ("Seção VI", "samples-and-outbreaks", "Capítulo III, seções VI e VII (arts. 99 a 102)"),
            (
                "Seção VIII",
                "storage-and-transport",
                "Capítulo III, seções VIII e IX (arts. 103 a 113, transporte e entrega)",
            ),
            ("CAPÍTULO IV", "cleaning-and-sanitization", "Capítulo IV (arts. 114 a 118)"),
            ("CAPÍTULO V", "water-supply", "Capítulo V, seção I (arts. 119 a 125)"),
            ("Seção II", "waste-management", "Capítulo V, seções II e III (arts. 126 a 132)"),
            ("Seção IV", "buildings-and-equipment", "Capítulo V, seção IV (art. 133, gás)"),
            ("Seção V", "pest-control", "Capítulo V, seção V (arts. 134 e 135)"),
            ("CAPÍTULO VI", "buildings-and-equipment", "Capítulo VI (arts. 136 a 169)"),
            ("CAPÍTULO VII", "documentation-and-records", "Capítulo VII (arts. 170 a 181)"),
            ("CAPÍTULO VIII", "consumer-warnings", "Capítulo VIII (arts. 182 a 186)"),
            # Republication note and Annex I, a poster model that is an image in the PDF.
            ("Atualização do texto normativo", None, None),
            ("ANEXO II", "consumer-warnings", "Anexo II (principais alimentos que causam alergias)"),
        ],
    },
    "cvs-9-2026": {
        "name": "Portaria CVS nº 9, de 5 de outubro de 2026 (SP)",
        "summary": "altera os arts. 3º e 4º da Portaria CVS nº 3/2026: a vigência dela e a revogação da Portaria "
        "CVS 5/2013 passam para 01/02/2027",
        "file": "portaria-cvs-9-2026.pdf",
        "url": "https://apicvs.saude.sp.gov.br/download/e_pt-cvs-9_051026.pdf",
        "retrieved": "2026-10-27",
        "end": None,
        "parts": [("Art. 1º", "scope-and-definitions", "arts. 1º a 5º (novas datas de vigência e de revogação)")],
    },
}

# A line that opens a new paragraph: numbered item, lettered item, roman-numbered item, article, paragraph,
# chapter, section or annex.
ITEM = re.compile(
    r"(\d+(\.\d+)+\.?\s|\d+\.\s|\d+ - |[a-z]\)\s|[IVXL]+ - |Art\.\s|§|Parágrafo|CAPÍTULO|Seção [IVXL]+(?!\w)|ANEXO)"
)
# Page headers and footers of the Diário Oficial PDFs.
NOISE = re.compile(
    r"DIÁRIO OFICIAL DO ESTADO|Publicado na Edição de|Este documento pode ser verificado|em https://www\.doe\.sp"
    r"|Documento assinado digitalmente|que institui a Infraestrutura de Chaves|\d+/\d+$|[\d.]{20,}$"
)


def read_lines(path: Path) -> list[str]:
    if path.suffix == ".pdf":
        text = subprocess.run(["pdftotext", path, "-"], capture_output=True, text=True, check=True).stdout
    else:
        raw = path.read_text(encoding="iso-8859-1")
        raw = re.sub(r"(?is)<(script|style).*?</\1>", "", raw)
        raw = re.sub(r"(?i)<br\s*/?>|</p>|</tr>", "\n", raw)
        text = html.unescape(re.sub(r"<[^>]+>", "", raw))
    lines = (re.sub(r"\s+", " ", line).strip() for line in text.splitlines())
    return [line for line in lines if line and not NOISE.match(line)]


def starts_with(line: str, prefix: str) -> bool:
    """Prefix match that does not stop mid-word: "Seção I" matches "Seção I" but not "Seção II"."""
    return re.match(re.escape(prefix) + r"(?!\w)", line) is not None


def split(lines: list[str], parts: list[tuple], end: str | None) -> list[tuple[str, str, list[str]]]:
    """Cut lines into (topic, label, chunk) at each part's start line, in order; drop skipped parts."""
    starts, i = [], 0
    for start, _, _ in parts:
        i = next(n for n in range(i, len(lines)) if starts_with(lines[n], start))
        starts.append(i)
    after_last = range(starts[-1] + 1, len(lines))
    stop = next(n for n in after_last if starts_with(lines[n], end)) if end else len(lines)
    bounds = [*starts[1:], stop]
    return [(topic, label, lines[a:b]) for (_, topic, label), a, b in zip(parts, starts, bounds, strict=True) if topic]


def paragraphs(lines: list[str]) -> list[str]:
    """Rejoin hard-wrapped lines; an uppercase heading may itself wrap over several lines."""
    paras: list[str] = []
    for line in lines:
        # A heading starts or ends where the case flips; a lone uppercase word is an acronym ("SEVISA."), not one.
        case_flip = line.isupper() != paras[-1].isupper() and (" " in line or not line.isupper()) if paras else False
        if not paras or ITEM.match(line) or case_flip:
            paras.append(line)
        else:
            paras[-1] += line if paras[-1].endswith("-") else " " + line
    return paras


def to_markdown(paras: list[str]) -> str:
    def render(p: str) -> str:
        if p.isupper() and (p[0].isdigit() or p.startswith(("ANEXO", "CAPÍTULO"))):
            return f"## {p}"
        return f"### {p}" if p.startswith(("Seção ", "ANEXO")) else p

    return "\n\n".join(render(p) for p in paras)


def build() -> None:
    # the notes.md files come from consolidation PRs, not from sources/: everything else is rebuilt
    for old in SEMANTIC.rglob("*.md"):
        if old.name != NOTES:
            old.unlink()
    files: dict[str, list[tuple[str, str]]] = {topic: [] for topic in TOPICS}  # topic -> [(file, description)]

    for norm_id, norm in NORMS.items():
        by_topic: dict[str, list[tuple[str, list[str]]]] = {}
        for topic, label, chunk in split(read_lines(ROOT / "sources" / norm["file"]), norm["parts"], norm["end"]):
            by_topic.setdefault(topic, []).append((label, chunk))

        for topic, chunks in by_topic.items():
            labels = [label for label, _ in chunks]
            meta = {"norm": norm["name"], "items": labels, "source_url": norm["url"], "retrieved": norm["retrieved"]}
            frontmatter = "\n".join(f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in meta.items())
            body = "\n\n".join(to_markdown(paragraphs(chunk)) for _, chunk in chunks)
            title = f"{TOPICS[topic][0]} — {norm['name']}"
            path = SEMANTIC / topic / f"{norm_id}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"---\n{frontmatter}\n---\n\n# {title}\n\n{body}\n", encoding="utf-8")
            files[topic].append((path.name, f"{norm['name']}: {'; '.join(labels)}"))

    for topic, entries in files.items():
        title, covers = TOPICS[topic]
        lines = [f"# {title}", "", f"Trata de {covers}.", "", "## Arquivos", ""]
        lines += [f"- [semantic/{topic}/{name}]({name}): {desc}" for name, desc in entries]
        lines += [notes_entry(topic)] if (SEMANTIC / topic / NOTES).exists() else []
        (SEMANTIC / topic / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    lines = [
        "# Memória semântica",
        "",
        "Normas sanitárias para serviços de alimentação (restaurantes, lanchonetes, padarias...), "
        "organizadas por tema. Cada pasta tem um index.md com o que há nela; cada arquivo traz o texto "
        "literal de uma norma sobre o tema, com a fonte no cabeçalho.",
        "",
        "## Normas",
        "",
        *[f"- {norm['name']}: {norm['summary']}." for norm in NORMS.values()],
        "",
        "## Temas",
        "",
        *[
            f"- [semantic/{topic}]({topic}/index.md): {title}. Trata de {covers}."
            for topic, (title, covers) in TOPICS.items()
        ],
    ]
    (SEMANTIC / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    build()
