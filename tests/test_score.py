from types import SimpleNamespace

from score import agreement, cites, grade, summarize


class FakeJudge:
    def __init__(self):
        self.models, self.calls = self, 0

    def generate_content(self, **request):
        self.calls += 1
        return SimpleNamespace(text='{"reason": "same limit", "verdict": "correct"}')


def test_cites_matches_the_item_or_its_parts_whatever_the_ordinal_mark():
    source = {"path": "semantic/a.md", "item": "Art. 1º, II"}

    assert cites({"path": "semantic/a.md", "item": "Art. 1"}, source)
    assert cites({"path": "./semantic/a.md", "item": "art. 1º, II"}, source)
    assert not cites({"path": "semantic/a.md", "item": "Art. 10"}, source)
    assert not cites({"path": "semantic/b.md", "item": "Art. 1º, II"}, source)


def test_grade_asks_the_judge_only_about_given_answers_and_summarize_counts_them():
    source = {"path": "semantic/a.md", "item": "4.8.16"}
    questions = {
        "q1": {"question": "?", "answer": "Até 2 h.", "answerable": True, "sources": [source]},
        "q2": {"question": "?", "answer": "Sim.", "answerable": True, "sources": [source]},
        "q3": {"question": "?", "answer": "", "answerable": False, "sources": []},
    }
    base = {"strategy": "index", "error": None, "input_tokens": 90, "output_tokens": 10, "latency": 2.0}
    records = [
        base | {"id": "q1", "answer": "2 h", "citations": [source], "answered": True},
        base | {"id": "q2", "answer": "Não sei.", "citations": [], "answered": False},
        base | {"id": "q3", "answer": "Não sei.", "citations": [], "answered": False},
    ]
    judge = FakeJudge()

    for r in records:
        r |= grade(r, questions[r["id"]], judge)
    summary = summarize(records, questions)

    assert judge.calls == 1 and [r["verdict"] for r in records] == ["correct", "incorrect", None]
    assert summary["correct"] == summary["right citation"] == summary["wrong refusal"] == 0.5
    assert summary["right refusal"] == 1.0 and summary["median tokens"] == 100 and summary["errors"] == 0
    labels = [
        {"id": "q1", "strategy": "index", "verdict": "partial"},
        {"id": "q2", "strategy": "index", "verdict": "incorrect"},
    ]
    assert agreement(records, labels) == (0.5, 2)
