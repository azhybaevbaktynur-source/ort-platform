"""Platform rule: math_1 is always quantitative comparison (Column A/B), math_2 is always standard multiple choice."""
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.services.csv_service import CsvService

INSTRUCTOR = {"Authorization": "Bearer mock_instructor_token"}

MC_QUESTION = {
    "language": "ru",
    "topic": "Алгебра",
    "difficulty": "medium",
    "stem": "$2 + 2 = ?$",
    "option_a": "3",
    "option_b": "4",
    "option_c": "5",
    "option_d": "6",
    "correct_option": "B",
}


@pytest.mark.asyncio
async def test_api_rejects_math_1_without_columns_and_math_2_with_columns():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/api/v1/questions", headers=INSTRUCTOR, json={**MC_QUESTION, "section": "math_1"})
        assert res.status_code == 422
        assert "Колонк" in res.json()["detail"]

        res = await client.post("/api/v1/questions", headers=INSTRUCTOR,
                                json={**MC_QUESTION, "section": "math_2", "column_a": "$x$", "column_b": "$y$"})
        assert res.status_code == 422

        res = await client.post("/api/v1/questions", headers=INSTRUCTOR, json={**MC_QUESTION, "section": "math_2"})
        assert res.status_code == 200
        q_id = res.json()["id"]

        # Moving a multiple-choice question into math_1 without columns is refused
        res = await client.put(f"/api/v1/questions/{q_id}", headers=INSTRUCTOR, json={"section": "math_1"})
        assert res.status_code == 422

        res = await client.post("/api/v1/questions", headers=INSTRUCTOR,
                                json={**MC_QUESTION, "section": "math_1", "stem": "", "column_a": "$x$", "column_b": "$y$",
                                      "option_a": "", "option_b": "", "option_c": "", "option_d": "", "correct_option": "C"})
        assert res.status_code == 200


def test_csv_enforces_math_rule_and_comparison_aliases():
    csv_text = """section,stem,column_a,column_b,option_a,option_b,option_c,option_d,correct_option
math_1,Без колонок,,,1,2,3,4,A
math_2,С колонками,$x$,$y$,,,,,A
салыштыруу,,$2x$,$x+1$,,,,,D
math_1,,$a$,$b$,,,,,E
"""
    report = CsvService.validate_csv(csv_text.encode("utf-8"), language="ky")
    assert report.validRowsCount == 1
    assert report.previewQuestions[0].section.value == "math_1"
    assert {(e.rowNumber, e.field) for e in report.errors} == {
        (2, "column_a"), (3, "column_a"), (5, "correct_option"),
    }
