from datetime import date, timedelta
from config import Config, RepoConfig, ScoringConfig
from weekly_reporter import build_weekly_report, _find_backup_risks, _find_silent_persons

def _cfg(names: list[str]) -> Config:
    return Config(
        feishu_webhook_url="https://x",
        members={n: n for n in names},
        repos=[RepoConfig(name="api", path="/tmp/api", branches=["main"])],
        scoring=ScoringConfig(),
    )

def _row(person: str, repo: str, commits: int, d: date) -> dict:
    return {"date": d.isoformat(), "person": person, "repo": repo,
            "commits": commits, "lines_added": 10, "lines_deleted": 0,
            "files_changed": 1, "messages": []}

def test_backup_risk_single_contributor():
    week_start = date(2026, 3, 23)
    rows = [_row("张三", "api", 5, week_start + timedelta(days=i)) for i in range(3)]
    risks = _find_backup_risks(rows, week_start, week_start + timedelta(days=6))
    assert len(risks) == 1
    assert risks[0]["repo"] == "api"
    assert risks[0]["person"] == "张三"

def test_backup_risk_two_contributors_no_risk():
    week_start = date(2026, 3, 23)
    rows = (
        [_row("张三", "api", 3, week_start)] +
        [_row("李四", "api", 2, week_start + timedelta(days=1))]
    )
    risks = _find_backup_risks(rows, week_start, week_start + timedelta(days=6))
    assert risks == []

def test_silent_persons_flagged():
    week_start = date(2026, 3, 23)
    # 张三整周没有提交
    rows = [_row("李四", "api", 2, week_start)]
    silent = _find_silent_persons(["张三", "李四"], rows, week_start)
    assert any(s["name"] == "张三" for s in silent)

def test_silent_persons_active_not_flagged():
    week_start = date(2026, 3, 23)
    # 张三每天都有提交
    rows = [_row("张三", "api", 1, week_start + timedelta(days=i)) for i in range(7)]
    silent = _find_silent_persons(["张三"], rows, week_start)
    assert silent == []

def test_build_weekly_report_structure():
    week_start = date(2026, 3, 23)
    prev_start = week_start - timedelta(days=7)
    cfg = _cfg(["张三", "李四"])
    # 当周：张三 10 commits，李四 5
    # 上周：张三 8 commits
    curr_rows = [_row("张三", "api", 10, week_start), _row("李四", "api", 5, week_start)]
    prev_rows = [_row("张三", "api", 8, prev_start)]
    rows = prev_rows + curr_rows
    report = build_weekly_report(rows, cfg, week_start)
    assert report["total_commits"] == 15
    assert report["top_person"]["name"] == "张三"
    # 张三 momentum: (10-8)/8 = 25%
    zhang = next(p for p in report["persons"] if p["name"] == "张三")
    assert zhang["vs_prev_week_pct"] == 25

def test_team_momentum_positive():
    week_start = date(2026, 3, 23)
    prev_start = week_start - timedelta(days=7)
    cfg = _cfg(["张三"])
    rows = [
        _row("张三", "api", 8, prev_start),
        _row("张三", "api", 10, week_start),
    ]
    report = build_weekly_report(rows, cfg, week_start)
    assert report["team_momentum_pct"] == 25

def test_team_momentum_no_baseline():
    week_start = date(2026, 3, 23)
    cfg = _cfg(["张三"])
    rows = [_row("张三", "api", 5, week_start)]
    report = build_weekly_report(rows, cfg, week_start)
    assert report["team_momentum_pct"] is None

def test_send_weekly_report_calls_feishu():
    from unittest.mock import patch, MagicMock
    from weekly_reporter import send_weekly_report

    report = {
        "week_label": "2026-W13（03/23–03/29）",
        "total_commits": 15,
        "team_momentum_pct": 25,
        "top_person": {"name": "张三", "total_commits": 10},
        "silent_persons": [],
        "backup_risks": [{"repo": "sdk-core", "person": "李四"}],
        "persons": [
            {"name": "张三", "total_commits": 10, "total_lines_added": 500, "repos_active": 2, "vs_prev_week_pct": 25},
            {"name": "李四", "total_commits": 5, "total_lines_added": 200, "repos_active": 1, "vs_prev_week_pct": None},
        ],
    }

    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None

    with patch("weekly_reporter.requests.post", return_value=mock_resp) as mock_post:
        send_weekly_report("https://example.com/webhook", report)

    mock_post.assert_called_once()
    payload = mock_post.call_args[1]["json"]
    assert payload["msg_type"] == "post"
    content = payload["content"]["post"]["zh_cn"]
    assert "研发周报" in content["title"]
    all_text = " ".join(
        item["text"]
        for line in content["content"]
        for item in line
    )
    assert "张三" in all_text
    assert "sdk-core" in all_text
    assert "↑25%" in all_text
