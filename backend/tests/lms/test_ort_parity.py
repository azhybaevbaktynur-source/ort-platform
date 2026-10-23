"""ORT parity gate (PHASE_4_DESIGN 7.2): the seeded `ort_main` / `ort_subject` v1 reproduce the old
`ScoringService` exactly, for every N in 1..200 and raw in 0..N, against the live oracle and the frozen tables.

Frozen tables `tests/lms/fixtures/ort_parity_{main,subject}.json` were generated once from the oracle with:

    cd backend && venv/bin/python -m tests.lms.test_ort_parity

(`write_fixtures()` below). They keep the gate alive after Phase 5 deletes `app/services/scoring_service.py`.
"""
from __future__ import annotations

import json
import math
from decimal import Decimal
from pathlib import Path

import pytest

from app.lms.grading.params import validate_params
from app.lms.grading.registry import apply, apply_sections, build_version_data
from app.lms.grading.seeds import ORT_MAIN_PARAMS, ORT_SUBJECT_PARAMS

try:  # the oracle is deleted in Phase 5; the frozen tables keep the gate
    from app.services.scoring_service import ScoringService
except ImportError:  # pragma: no cover
    ScoringService = None

N_MAX = 200
FIXTURES = Path(__file__).parent / "fixtures"
KINDS = {"main": ("full_main", ORT_MAIN_PARAMS), "subject": ("subject", ORT_SUBJECT_PARAMS)}


def _version(kind: str):
    _, params = KINDS[kind]
    return build_version_data("piecewise_curve", validate_params("piecewise_curve", params))


def build_table(exam_type: str) -> dict:
    """Oracle table: scaled and percentile per N (index = raw)."""
    scaled, pct = {}, {}
    for n in range(1, N_MAX + 1):
        s = [ScoringService.raw_to_scaled(r, n, exam_type=exam_type) for r in range(n + 1)]
        scaled[str(n)] = s
        pct[str(n)] = [ScoringService.calculate_percentile(x, exam_type=exam_type) for x in s]
    return {"oracle": "app.services.scoring_service.ScoringService", "exam_type": exam_type, "n_max": N_MAX,
            "scaled": scaled, "percentile": pct}


def write_fixtures() -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    for kind, (exam_type, _) in KINDS.items():
        (FIXTURES / f"ort_parity_{kind}.json").write_text(
            json.dumps(build_table(exam_type), separators=(",", ":")) + "\n", encoding="utf-8")


def _frozen(kind: str) -> dict:
    return json.loads((FIXTURES / f"ort_parity_{kind}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("kind", ["main", "subject"])
def test_exhaustive_parity_against_frozen_table(kind):
    exam_type, _ = KINDS[kind]
    v = _version(kind)
    table = _frozen(kind)
    assert table["exam_type"] == exam_type and table["n_max"] == N_MAX
    mismatches = []
    for n in range(1, N_MAX + 1):
        scaled, pct = table["scaled"][str(n)], table["percentile"][str(n)]
        assert len(scaled) == n + 1
        for raw in range(n + 1):
            g = apply(v, raw, n)
            golden = exam_type != "subject" and scaled[raw] >= 219
            if (g.display_value != Decimal(scaled[raw]) or float(g.percentile) != pct[raw]
                    or g.thresholds.get("golden_certificate", False) != golden):
                mismatches.append((n, raw, g, scaled[raw], pct[raw]))
    assert mismatches == []


@pytest.mark.skipif(ScoringService is None, reason="oracle removed (Phase 5)")
@pytest.mark.parametrize("kind", ["main", "subject"])
def test_exhaustive_parity_against_live_oracle(kind):
    exam_type, _ = KINDS[kind]
    v = _version(kind)
    mismatches = []
    for n in range(1, N_MAX + 1):
        for raw in range(n + 1):
            g = apply(v, raw, n)
            scaled = ScoringService.raw_to_scaled(raw, n, exam_type=exam_type)
            pct = ScoringService.calculate_percentile(scaled, exam_type=exam_type)
            golden = exam_type != "subject" and scaled >= ScoringService.GOLDEN_CERTIFICATE_THRESHOLD
            if (g.display_value != Decimal(scaled) or float(g.percentile) != pct
                    or g.thresholds.get("golden_certificate", False) != golden):
                mismatches.append((n, raw, g, scaled, pct))
    assert mismatches == []


@pytest.mark.skipif(ScoringService is None, reason="oracle removed (Phase 5)")
@pytest.mark.parametrize("kind", ["main", "subject"])
def test_frozen_table_matches_live_oracle(kind):
    exam_type, _ = KINDS[kind]
    assert _frozen(kind) == json.loads(json.dumps(build_table(exam_type)))


def test_seeded_versions_have_the_oracle_scale():
    main, subject = _version("main"), _version("subject")
    assert (main.scale_min, main.scale_max) == (Decimal("60.00"), Decimal("245.00"))
    assert (subject.scale_min, subject.scale_max) == (Decimal("60.00"), Decimal("150.00"))
    assert "golden_certificate" not in apply(subject, 30, 30).thresholds


@pytest.mark.skipif(ScoringService is None, reason="oracle removed (Phase 5)")
def test_section_parity_with_evaluate_test_submission():
    """Per-section scaled values via apply_sections == raw_to_scaled per section (test_scoring fixtures)."""
    questions = [
        {"id": "q1", "section": "math_1", "stem": "a", "correctOptionId": "A"},
        {"id": "q2", "section": "math_1", "stem": "b", "correctOptionId": "B"},
        {"id": "q3", "section": "analogies", "stem": "c", "correctOptionId": "C"},
    ]
    answers = {"q1": {"selectedOptionId": "A"}, "q2": {"selectedOptionId": "C"}, "q3": {"selectedOptionId": "C"}}
    res = ScoringService.evaluate_test_submission(
        attempt_id="a", user_id="u", template_id="t", language="ky", user_answers=answers,
        questions_in_test=questions, completed_at="2026-09-23T11:00:00Z")
    v = _version("main")
    sections = [{"pos": i, "key": k, "raw": str(s.rawScore), "possible": str(s.totalQuestions)}
                for i, (k, s) in enumerate(res.sectionScores.items(), start=1)]
    out = apply_sections(v, sections)
    assert [Decimal(o["display_value"]) for o in out] == [Decimal(s.scaledScore) for s in res.sectionScores.values()]
    total = apply(v, res.totalRawScore, res.maxRawScore)
    assert total.display_value == res.totalScaledScore and float(total.percentile) == res.percentile
    assert total.thresholds["golden_certificate"] is res.isGoldenCertificate
    # Exhaustive per-section sizes typical of ORT sections (raw 0..N for N in 1..60).
    for n in range(1, 61):
        secs = [{"pos": 1, "raw": r, "possible": n} for r in range(n + 1)]
        got = [Decimal(apply_sections(v, [s])[0]["display_value"]) for s in secs]
        assert got == [Decimal(ScoringService.raw_to_scaled(r, n)) for r in range(n + 1)]


def test_scoring_suite_reexpressed_on_new_path():
    """Every assertion of tests/test_scoring.py, against the seeded versions."""
    main, subject = _version("main"), _version("subject")

    def sc(v, raw, n):
        return apply(v, raw, n).display_value

    # boundaries
    assert sc(main, 0, 150) == 0 and sc(main, -5, 150) == 0
    assert sc(main, 1, 150) >= 60
    assert sc(main, 150, 150) == 245 and sc(main, 160, 150) == 245
    assert sc(main, 10, 0) == 0
    # median and progression
    assert 148 <= sc(main, 75, 150) <= 152
    scores = [sc(main, r, 150) for r in range(0, 151, 10)]
    assert scores == sorted(scores)
    # golden certificate
    assert main.params["thresholds"] == [{"key": "golden_certificate", "min_value": 219.0}]
    assert apply(main, 135, 150).thresholds["golden_certificate"] is True and sc(main, 135, 150) >= 219
    assert apply(main, 80, 150).thresholds["golden_certificate"] is False and sc(main, 80, 150) < 219
    # percentile (scaled 150 / 60 / 219 come from raw 75/150, 1/1000-ish and the golden edge)
    assert 49.0 <= float(apply(main, 75, 150).percentile) <= 51.0
    assert float(apply(main, 1, 200).percentile) <= 2.0
    raw_219 = next(r for r in range(151) if sc(main, r, 150) >= 219)
    assert float(apply(main, raw_219, 150).percentile) >= 98.0
    # subject scale
    assert sc(subject, 0, 30) == 0 and sc(subject, 1, 30) >= 60
    assert sc(subject, 30, 30) == 150 and sc(subject, 15, 30) == 105 and sc(subject, 35, 30) == 150
    assert sc(main, 30, 30) == 245
    assert apply(subject, 2, 2).thresholds == {}
    # calculate_score with raw 0
    for v, n in ((main, 150), (subject, 40)):
        g = apply(v, 0, n)
        assert g.display_value == 0 and g.percentile == Decimal("0.0")
    g = apply(main, 75, 150)
    assert 148 <= g.display_value <= 152 and float(g.percentile) > 40.0


@pytest.mark.parametrize("kind", ["main", "subject"])
def test_monotonic_and_fractional_raws(kind):
    v = _version(kind)
    for n in (1, 7, 30, 150, 200):
        values = [apply(v, Decimal(r) / 4, n).display_value for r in range(0, 4 * n + 1)]
        assert values == sorted(values)
        assert values[-1] == v.scale_max
    g = apply(v, Decimal("74.5"), 150)
    ratio = 74.5 / 150
    _, params = KINDS[kind]
    lo, mid = params["scale_min"], params["segments"][0]["to_value"]
    assert g.display_value == Decimal(round(lo + (mid - lo) * ((ratio / 0.5) ** 1.05)))


def test_hypothesis_monotonic_in_raw():
    hypothesis = pytest.importorskip("hypothesis")
    st = hypothesis.strategies
    v = _version("main")

    @hypothesis.given(n=st.integers(1, 500), a=st.floats(0, 1), b=st.floats(0, 1))
    @hypothesis.settings(max_examples=300, deadline=None)
    def check(n, a, b):
        lo, hi = sorted((a, b))
        ra, rb = Decimal(repr(lo * n)).quantize(Decimal("0.01")), Decimal(repr(hi * n)).quantize(Decimal("0.01"))
        assert apply(v, ra, n).display_value <= apply(v, rb, n).display_value
        assert not math.isnan(float(apply(v, ra, n).percentile))

    check()


if __name__ == "__main__":  # pragma: no cover
    write_fixtures()
    print("wrote", sorted(p.name for p in FIXTURES.glob("ort_parity_*.json")))
