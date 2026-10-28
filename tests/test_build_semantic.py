import re
from pathlib import Path

from build_semantic import paragraphs, split, starts_with

REPO = Path(__file__).resolve().parents[1]


def test_split_and_rejoin_paragraphs():
    lines = [
        "Art. 1º Aprovar",
        "o regulamento.",
        "Seção II",
        "Higiene",
        "3. REFERÊNCIAS",
        "BRASIL. Lei",
        "4.1 EDIFICAÇÃO,",
        "MÓVEIS",
        "4.1.1 A edificação deve",
        "ser higiênico-",
        "sanitária, conforme o",
        "SEVISA.",
        "I - item",
        "Saúde",
        "Legis",
    ]
    parts = [("Art. 1º", "scope", "arts"), ("3. REFERÊNCIAS", None, None), ("4.1 EDIFICAÇÃO", "buildings", "4.1")]

    chunks = split(lines, parts, "Saúde")

    assert [(topic, label) for topic, label, _ in chunks] == [("scope", "arts"), ("buildings", "4.1")]
    assert paragraphs(chunks[0][2]) == ["Art. 1º Aprovar o regulamento.", "Seção II Higiene"]
    assert paragraphs(chunks[1][2]) == [
        "4.1 EDIFICAÇÃO, MÓVEIS",
        "4.1.1 A edificação deve ser higiênico-sanitária, conforme o SEVISA.",
        "I - item",
    ]
    assert not starts_with("Seção II", "Seção I")


def test_every_index_link_works_for_github_and_for_the_tools():
    """Link targets are relative (GitHub); link texts are the repo paths the agent passes to the tools."""
    semantic = REPO / "semantic"
    for folder in [semantic, *(p for p in semantic.rglob("*") if p.is_dir())]:
        index = folder / "index.md"
        assert index.is_file(), folder
        for text, target in re.findall(r"\[([^\]]+)\]\(([^)]+)\)", index.read_text(encoding="utf-8")):
            resolved = (folder / target).resolve()
            assert resolved.is_file(), (index, target)
            assert resolved in {(REPO / text).resolve(), (REPO / text / "index.md").resolve()}, (index, text)
