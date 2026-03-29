# tests/test_dashboard.py
import json
from datetime import date, timedelta
from dashboard import generate_html

def _rows(persons: list[str], repos: list[str], days: int) -> list[dict]:
    rows = []
    start = date(2026, 3, 1)
    for i in range(days):
        d = (start + timedelta(days=i)).isoformat()
        for person in persons:
            for repo in repos:
                rows.append({
                    "date": d, "person": person, "repo": repo,
                    "commits": i % 3 + 1, "lines_added": 50, "lines_deleted": 10,
                    "files_changed": 2, "messages": ["feat: x"],
                })
    return rows

def test_html_has_canvas_elements():
    rows = _rows(["张三", "李四"], ["api", "web"], 30)
    html = generate_html(rows, ["张三", "李四"])
    assert 'id="timeline-chart"' in html
    assert 'id="momentum-chart"' in html
    assert 'id="coverage-matrix"' in html

def test_html_embeds_person_names():
    rows = _rows(["张三", "李四"], ["api"], 7)
    html = generate_html(rows, ["张三", "李四"])
    assert "张三" in html
    assert "李四" in html

def test_html_embeds_inline_json():
    rows = _rows(["张三"], ["api"], 5)
    html = generate_html(rows, ["张三"])
    assert '"commits"' in html
    assert '"lines_added"' in html

def test_html_is_valid_structure():
    rows = _rows(["张三"], ["api"], 5)
    html = generate_html(rows, ["张三"])
    assert html.startswith("<!DOCTYPE html>")
    assert "</html>" in html

def test_empty_rows_generates_html():
    html = generate_html([], [])
    assert "<!DOCTYPE html>" in html
    assert "</html>" in html
