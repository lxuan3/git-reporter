# tests/test_dashboard.py
import json
from datetime import date, timedelta
from dashboard import _dedupe_persons, generate_html

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

def test_json_is_parseable():
    """The inline JSON in the HTML script block must be valid and parseable."""
    import json as _json
    import re
    rows = _rows(["张三"], ["api"], 5)
    html = generate_html(rows, ["张三"])
    m = re.search(r'const ALL_DATA = (.+?);', html, re.DOTALL)
    assert m, "ALL_DATA not found in HTML"
    data = _json.loads(m.group(1))
    assert data["persons"] == ["张三"]

def test_dedupe_persons_merges_same_display_name_and_keeps_row_only_people():
    rows = [
        {"date": "2026-03-01", "person": "张三", "repo": "api",
         "commits": 1, "lines_added": 10, "lines_deleted": 0, "files_changed": 1, "messages": []},
        {"date": "2026-03-01", "person": "王五", "repo": "web",
         "commits": 1, "lines_added": 5, "lines_deleted": 0, "files_changed": 1, "messages": []},
    ]

    persons = _dedupe_persons(["张三", "李四", "张三"], rows)

    assert persons == ["张三", "李四", "王五"]

def test_build_all_data_timeline_aggregation():
    """_build_all_data should sum commits across repos for the same person+day."""
    from dashboard import _build_all_data
    rows = [
        {"date": "2026-03-01", "person": "张三", "repo": "api",
         "commits": 3, "lines_added": 10, "lines_deleted": 0, "files_changed": 1, "messages": []},
        {"date": "2026-03-01", "person": "张三", "repo": "web",
         "commits": 2, "lines_added": 5, "lines_deleted": 0, "files_changed": 1, "messages": []},
    ]
    data = _build_all_data(rows, ["张三"], generated_at="2026-03-01")
    assert data["generated_at"] == "2026-03-01"
    # rows are preserved
    assert len(data["rows"]) == 2
    assert data["repos"] == ["api", "web"]
