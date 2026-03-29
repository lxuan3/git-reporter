from datetime import date
from report_builder import PersonReport, RepoStats
from data_store import save_snapshot, query_range

def _make_report(person: str, repo: str, commits: int, lines_added: int, target_date: date) -> dict:
    pr = PersonReport(display_name=person)
    pr.repos[repo] = RepoStats(commits=commits, lines_added=lines_added, lines_deleted=0, files_changed=1, messages=["feat: x"])
    return {
        "date": target_date,
        "persons": [pr],
        "total_commits": commits,
        "total_lines_added": lines_added,
        "total_lines_deleted": 0,
        "active_count": 1,
        "total_count": 1,
        "top": [],
    }

def test_save_and_query(tmp_path):
    db = str(tmp_path / "test.db")
    d = date(2026, 3, 29)
    report = _make_report("张三", "api", 3, 100, d)
    save_snapshot(report, d, db_path=db)
    rows = query_range(date(2026, 3, 28), date(2026, 3, 30), db_path=db)
    assert len(rows) == 1
    assert rows[0]["person"] == "张三"
    assert rows[0]["repo"] == "api"
    assert rows[0]["commits"] == 3
    assert rows[0]["lines_added"] == 100
    assert rows[0]["messages"] == ["feat: x"]

def test_save_idempotent(tmp_path):
    db = str(tmp_path / "test.db")
    d = date(2026, 3, 29)
    report = _make_report("张三", "api", 3, 100, d)
    save_snapshot(report, d, db_path=db)
    save_snapshot(report, d, db_path=db)  # 第二次不应重复
    rows = query_range(date(2026, 3, 29), date(2026, 3, 29), db_path=db)
    assert len(rows) == 1

def test_query_empty_range(tmp_path):
    db = str(tmp_path / "test.db")
    rows = query_range(date(2026, 3, 1), date(2026, 3, 31), db_path=db)
    assert rows == []

def test_query_date_filter(tmp_path):
    db = str(tmp_path / "test.db")
    save_snapshot(_make_report("张三", "api", 1, 10, date(2026, 3, 1)), date(2026, 3, 1), db_path=db)
    save_snapshot(_make_report("张三", "api", 2, 20, date(2026, 3, 15)), date(2026, 3, 15), db_path=db)
    save_snapshot(_make_report("张三", "api", 3, 30, date(2026, 3, 31)), date(2026, 3, 31), db_path=db)
    rows = query_range(date(2026, 3, 10), date(2026, 3, 20), db_path=db)
    assert len(rows) == 1
    assert rows[0]["commits"] == 2
