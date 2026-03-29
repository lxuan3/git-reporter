# Git Reporter Visualization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 git_reporter 添加 SQLite 历史数据持久化、每周飞书周报、以及三 Tab 本地 HTML 仪表盘。

**Architecture:** 新增三个独立模块（`data_store.py` / `weekly_reporter.py` / `dashboard.py`），对现有代码改动最小。仪表盘为纯静态 HTML，内嵌 Chart.js CDN，数据以 JSON 写入 `<script>` 标签。

**Tech Stack:** Python 3.9+, sqlite3 (stdlib), json (stdlib), webbrowser (stdlib), Chart.js 4.x (CDN), requests（已有）

---

## File Map

| 文件 | 操作 | 职责 |
|------|------|------|
| `data_store.py` | 新建 | SQLite 读写，`save_snapshot` / `query_range` |
| `weekly_reporter.py` | 新建 | 周报聚合逻辑 + 飞书推送 |
| `dashboard.py` | 新建 | HTML 仪表盘生成器 |
| `tests/test_data_store.py` | 新建 | data_store 单元测试 |
| `tests/test_weekly_reporter.py` | 新建 | weekly_reporter 单元测试 |
| `tests/test_dashboard.py` | 新建 | dashboard 生成测试 |
| `main.py` | 修改 | 日常运行后调用 save_snapshot；支持 `--weekly` |
| `.gitignore` | 修改 | 追加 `git_reporter.db` |

---

## Task 1: data_store.py — SQLite 持久化

**Files:**
- Create: `data_store.py`
- Create: `tests/test_data_store.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_data_store.py
import json
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
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /Users/hypernode/Github/git_reporter
python -m pytest tests/test_data_store.py -v
```

Expected: `ModuleNotFoundError: No module named 'data_store'`

- [ ] **Step 3: 实现 data_store.py**

```python
# data_store.py
import json
import os
import sqlite3
from datetime import date

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS daily_snapshots (
    date          TEXT NOT NULL,
    person        TEXT NOT NULL,
    repo          TEXT NOT NULL,
    commits       INTEGER NOT NULL,
    lines_added   INTEGER NOT NULL,
    lines_deleted INTEGER NOT NULL,
    files_changed INTEGER NOT NULL,
    messages      TEXT NOT NULL
)
"""

def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(_CREATE_TABLE)
    conn.commit()
    return conn

def save_snapshot(report: dict, target_date: date, db_path: str = "git_reporter.db") -> None:
    """将 build_report() 返回的 report 写入 SQLite。同一 (date, person, repo) 幂等。"""
    date_str = target_date.isoformat()
    conn = _connect(db_path)
    try:
        for person in report["persons"]:
            for repo_name, stats in person.repos.items():
                conn.execute(
                    "DELETE FROM daily_snapshots WHERE date=? AND person=? AND repo=?",
                    (date_str, person.display_name, repo_name),
                )
                conn.execute(
                    "INSERT INTO daily_snapshots VALUES (?,?,?,?,?,?,?,?)",
                    (
                        date_str,
                        person.display_name,
                        repo_name,
                        stats.commits,
                        stats.lines_added,
                        stats.lines_deleted,
                        stats.files_changed,
                        json.dumps(stats.messages, ensure_ascii=False),
                    ),
                )
        conn.commit()
    finally:
        conn.close()

def query_range(start: date, end: date, db_path: str = "git_reporter.db") -> list[dict]:
    """返回 [start, end] 日期范围内的所有快照行，按 date ASC 排序。DB 不存在时返回 []。"""
    if not os.path.exists(db_path):
        return []
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM daily_snapshots WHERE date >= ? AND date <= ? ORDER BY date ASC",
            (start.isoformat(), end.isoformat()),
        ).fetchall()
        return [
            {
                "date": row["date"],
                "person": row["person"],
                "repo": row["repo"],
                "commits": row["commits"],
                "lines_added": row["lines_added"],
                "lines_deleted": row["lines_deleted"],
                "files_changed": row["files_changed"],
                "messages": json.loads(row["messages"]),
            }
            for row in rows
        ]
    finally:
        conn.close()
```

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m pytest tests/test_data_store.py -v
```

Expected: 4 tests PASSED

- [ ] **Step 5: 提交**

```bash
git add data_store.py tests/test_data_store.py
git commit -m "feat: add SQLite persistence layer (data_store)"
```

---

## Task 2: main.py — 集成 save_snapshot + --weekly 标志

**Files:**
- Modify: `main.py`
- Modify: `.gitignore`

- [ ] **Step 1: 更新 .gitignore**

在 `.gitignore` 末尾追加：

```
git_reporter.db
```

- [ ] **Step 2: 修改 main.py**

将现有 `run()` 函数和 `__main__` 块替换为以下版本（新增内容已标注）：

```python
# main.py
import sys
import json
from datetime import date, timedelta
from typing import Optional
from config import load_config
from git_collector import collect_repo
from report_builder import build_report, PersonReport
from feishu_sender import build_payload, send_report, send_warnings
from data_store import save_snapshot, query_range          # NEW
from weekly_reporter import build_weekly_report, send_weekly_report  # NEW

def _print_dry_run(report: dict, warnings: list[str]) -> None:
    d = report["date"].strftime("%Y-%m-%d")
    print(f"\n=== DRY RUN: {d} ===\n")
    for person in report["persons"]:
        if person.total_commits > 0:
            print(f"👤 {person.display_name}")
            for repo_name, stats in person.repos.items():
                print(f"  • {repo_name}  {stats.commits} commits | +{stats.lines_added}/-{stats.lines_deleted} 行 | {stats.files_changed} 个文件")
                for msg in stats.messages:
                    print(f"    - {msg}")
        else:
            print(f"👤 {person.display_name}（今日无提交）")
    print()
    print(f"汇总：活跃 {report['active_count']}/{report['total_count']} 人 | {report['total_commits']} commits | +{report['total_lines_added']}/-{report['total_lines_deleted']} 行")
    if report["top"]:
        medals = ["🥇", "🥈"]
        for medal, p in zip(medals, report["top"]):
            print(f"{medal} {p.display_name}（{p.total_commits} commits · +{p.total_lines_added} 行）")
    if warnings:
        print(f"\n⚠️  警告：")
        for w in warnings:
            print(f"  - {w}")

def run(config_path: str = "config.yaml", target_date: Optional[date] = None, dry_run: bool = False):
    if target_date is None:
        target_date = date.today()

    cfg = load_config(config_path)

    repo_commits = {}
    all_warnings = []

    for repo in cfg.repos:
        commits, warnings = collect_repo(repo.path, repo.branches, target_date, remote=repo.remote)
        repo_commits[repo.name] = commits
        all_warnings.extend(warnings)

    report = build_report(repo_commits, cfg, target_date)

    save_snapshot(report, target_date)          # NEW: always persist, even on dry_run

    if dry_run:
        _print_dry_run(report, all_warnings)
        return

    send_report(cfg.feishu_webhook_url, report)

    if all_warnings:
        send_warnings(cfg.feishu_webhook_url, all_warnings)

def run_weekly(config_path: str = "config.yaml"):           # NEW
    cfg = load_config(config_path)
    today = date.today()
    # 上周一到昨天（周日），再往前取一周用于对比
    week_end = today - timedelta(days=1)
    week_start = week_end - timedelta(days=6)
    prev_start = week_start - timedelta(days=7)
    rows = query_range(prev_start, week_end)
    report = build_weekly_report(rows, cfg, week_start)
    send_weekly_report(cfg.feishu_webhook_url, report)

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry_run = "--dry-run" in sys.argv
    weekly = "--weekly" in sys.argv                         # NEW

    config_path = args[0] if len(args) > 0 else "config.yaml"

    if weekly:                                              # NEW
        run_weekly(config_path)
    else:
        if len(args) > 1:
            target_date = date.fromisoformat(args[1])
        else:
            target_date = date.today()
        run(config_path, target_date, dry_run=dry_run)
```

- [ ] **Step 3: 确认现有测试仍通过**

```bash
python -m pytest tests/ -v
```

Expected: 全部 PASSED（现有 30 个测试）

- [ ] **Step 4: 提交**

```bash
git add main.py .gitignore
git commit -m "feat: persist daily snapshot to SQLite; add --weekly flag"
```

---

## Task 3: weekly_reporter.py — 周报聚合与飞书推送

**Files:**
- Create: `weekly_reporter.py`
- Create: `tests/test_weekly_reporter.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_weekly_reporter.py
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
    week_end = week_start + timedelta(days=6)
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
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_weekly_reporter.py -v
```

Expected: `ModuleNotFoundError: No module named 'weekly_reporter'`

- [ ] **Step 3: 实现 weekly_reporter.py**

```python
# weekly_reporter.py
from collections import defaultdict
from datetime import date, timedelta

import requests

from config import Config


def _find_backup_risks(rows: list[dict], week_start: date, week_end: date) -> list[dict]:
    """返回当周内仅 1 人有提交的 repo 列表。"""
    repo_contributors: dict[str, set[str]] = defaultdict(set)
    ws, we = week_start.isoformat(), week_end.isoformat()
    for row in rows:
        if ws <= row["date"] <= we and row["commits"] > 0:
            repo_contributors[row["repo"]].add(row["person"])
    return [
        {"repo": repo, "person": next(iter(contributors))}
        for repo, contributors in repo_contributors.items()
        if len(contributors) == 1
    ]


def _find_silent_persons(all_names: list[str], rows: list[dict], week_start: date) -> list[dict]:
    """返回整周（7天）零提交的成员列表，带 silent_days=7。"""
    active_persons: set[str] = set()
    week_end = (week_start + timedelta(days=6)).isoformat()
    ws = week_start.isoformat()
    for row in rows:
        if ws <= row["date"] <= week_end and row["commits"] > 0:
            active_persons.add(row["person"])
    return [
        {"name": name, "silent_days": 7}
        for name in all_names
        if name not in active_persons
    ]


def build_weekly_report(rows: list[dict], cfg: Config, week_start: date) -> dict:
    """
    rows: query_range(prev_start, week_end) 的结果，包含当周和上周数据。
    week_start: 当周开始日期（周一）。
    """
    week_end = week_start + timedelta(days=6)
    prev_start = week_start - timedelta(days=7)

    ws, we = week_start.isoformat(), week_end.isoformat()
    ps = prev_start.isoformat()
    prev_end = (week_start - timedelta(days=1)).isoformat()

    curr_rows = [r for r in rows if ws <= r["date"] <= we]
    prev_rows = [r for r in rows if ps <= r["date"] <= prev_end]

    # 聚合当周每人数据
    person_commits: dict[str, int] = defaultdict(int)
    person_lines: dict[str, int] = defaultdict(int)
    person_repos: dict[str, set[str]] = defaultdict(set)
    for row in curr_rows:
        person_commits[row["person"]] += row["commits"]
        person_lines[row["person"]] += row["lines_added"]
        if row["commits"] > 0:
            person_repos[row["person"]].add(row["repo"])

    # 上周每人 commits（用于趋势对比）
    prev_person_commits: dict[str, int] = defaultdict(int)
    for row in prev_rows:
        prev_person_commits[row["person"]] += row["commits"]

    all_names = list(cfg.members.values())

    persons = []
    for name in all_names:
        curr = person_commits[name]
        prev = prev_person_commits[name]
        vs_pct = round((curr - prev) / prev * 100) if prev > 0 else None
        persons.append({
            "name": name,
            "total_commits": curr,
            "total_lines_added": person_lines[name],
            "repos_active": len(person_repos[name]),
            "vs_prev_week_pct": vs_pct,
        })

    active = [p for p in persons if p["total_commits"] > 0]
    top_person = max(active, key=lambda p: p["total_commits"]) if active else None

    total_curr = sum(person_commits[n] for n in all_names)
    total_prev = sum(prev_person_commits[n] for n in all_names)
    team_momentum_pct = round((total_curr - total_prev) / total_prev * 100) if total_prev > 0 else None

    week_label = (
        f"{week_start.strftime('%Y-W%V')}"
        f"（{week_start.strftime('%m/%d')}–{week_end.strftime('%m/%d')}）"
    )

    return {
        "week_label": week_label,
        "week_start": ws,
        "week_end": we,
        "persons": persons,
        "top_person": top_person,
        "silent_persons": _find_silent_persons(all_names, curr_rows, week_start),
        "backup_risks": _find_backup_risks(rows, week_start, week_end),
        "team_momentum_pct": team_momentum_pct,
        "total_commits": total_curr,
    }


def send_weekly_report(webhook_url: str, report: dict) -> None:
    """将周报 dict 格式化为飞书 post 富文本消息并推送。"""

    def _line(text: str) -> list:
        return [{"tag": "text", "text": text}]

    total = report["total_commits"]
    momentum = report["team_momentum_pct"]
    if momentum is not None:
        sign = "↑" if momentum >= 0 else "↓"
        momentum_str = f" {sign}{abs(momentum)}% vs 上周"
    else:
        momentum_str = ""

    lines = [
        _line(f"📊 研发周报 · {report['week_label']}"),
        _line(f"团队总计：{total} commits{momentum_str}"),
    ]

    if report["top_person"]:
        p = report["top_person"]
        lines.append(_line(f"🔥 本周最强：{p['name']}（{p['total_commits']} commits）"))

    for s in report["silent_persons"]:
        lines.append(_line(f"📉 需关注：{s['name']}（整周无提交）"))

    for risk in report["backup_risks"]:
        lines.append(_line(f"⚠ 备份风险：{risk['repo']} 仅 {risk['person']} 1 人"))

    lines.append(_line("━" * 20))

    for p in sorted(report["persons"], key=lambda x: x["total_commits"], reverse=True):
        if p["total_commits"] > 0:
            lines.append(_line(
                f"  {p['name']}  {p['total_commits']} commits"
                f" · +{p['total_lines_added']}行 · {p['repos_active']}个项目"
            ))

    payload = {
        "msg_type": "post",
        "content": {
            "post": {
                "zh_cn": {
                    "title": f"研发周报 · {report['week_label']}",
                    "content": lines,
                }
            }
        },
    }
    resp = requests.post(webhook_url, json=payload, timeout=10)
    resp.raise_for_status()
```

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m pytest tests/test_weekly_reporter.py -v
```

Expected: 7 tests PASSED

- [ ] **Step 5: 提交**

```bash
git add weekly_reporter.py tests/test_weekly_reporter.py
git commit -m "feat: add weekly reporter with backup risk and momentum analysis"
```

---

## Task 4: dashboard.py — 静态 HTML 仪表盘

**Files:**
- Create: `dashboard.py`
- Create: `tests/test_dashboard.py`

- [ ] **Step 1: 写失败测试**

```python
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
    # inline JSON should contain rows data
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
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_dashboard.py -v
```

Expected: `ModuleNotFoundError: No module named 'dashboard'`

- [ ] **Step 3: 实现 dashboard.py**

```python
# dashboard.py
import argparse
import json
import os
import webbrowser
from datetime import date, timedelta

from config import load_config
from data_store import query_range
from git_collector import collect_repo
from report_builder import build_report


def _build_all_data(rows: list[dict], persons: list[str]) -> dict:
    """将 query_range 返回的行转换为仪表盘所需的 JSON 数据结构。"""
    # 收集所有日期和 repo
    all_dates = sorted(set(r["date"] for r in rows))
    all_repos = sorted(set(r["repo"] for r in rows))

    # 时间线：每人每天的 commits 总数
    timeline: dict[str, list[int]] = {p: [] for p in persons}
    for d in all_dates:
        day_rows = {(r["person"], r["repo"]): r for r in rows if r["date"] == d}
        for person in persons:
            total = sum(
                day_rows[(person, repo)]["commits"]
                for repo in all_repos
                if (person, repo) in day_rows
            )
            timeline[person].append(total)

    # 覆盖矩阵：{person: {repo: total_commits}}
    coverage: dict[str, dict[str, int]] = {p: {r: 0 for r in all_repos} for p in persons}
    for row in rows:
        if row["person"] in coverage and row["repo"] in coverage[row["person"]]:
            coverage[row["person"]][row["repo"]] += row["commits"]

    # 每周团队总 commits（近8周，倒序）
    today = date.fromisoformat(all_dates[-1]) if all_dates else date.today()
    weekly_totals = []
    for w in range(8):
        w_end = today - timedelta(days=w * 7)
        w_start = w_end - timedelta(days=6)
        total = sum(
            r["commits"] for r in rows
            if w_start.isoformat() <= r["date"] <= w_end.isoformat()
        )
        weekly_totals.insert(0, {"label": w_start.strftime("W%V"), "total": total})

    return {
        "generated_at": date.today().isoformat(),
        "persons": persons,
        "repos": all_repos,
        "dates": all_dates,
        "timeline": timeline,
        "coverage": coverage,
        "rows": rows,
        "weekly_totals": weekly_totals,
    }


def generate_html(rows: list[dict], persons: list[str], initial_range: int = 30) -> str:
    """生成完整的自包含 HTML 字符串。rows 应包含至多 90 天数据，initial_range 设置初始显示范围。"""
    data = _build_all_data(rows, persons)
    data_json = json.dumps(data, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<title>Git Reporter Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#0d1117;color:#e6edf3;min-height:100vh}}
  #header{{display:flex;align-items:center;justify-content:space-between;padding:16px 24px;border-bottom:1px solid #21262d}}
  h1{{font-size:16px;color:#e6edf3}}
  #range-btns button,#tab-btns button{{background:none;border:1px solid #30363d;color:#8b949e;padding:4px 12px;border-radius:6px;cursor:pointer;font-size:13px}}
  #range-btns button.active,#tab-btns button.active{{background:#1f6feb;border-color:#1f6feb;color:#fff}}
  #tab-btns{{display:flex;gap:4px;padding:12px 24px;border-bottom:1px solid #21262d}}
  .tab-content{{display:none;padding:20px 24px}}
  .tab-content.active{{display:block}}
  .cards{{display:flex;gap:12px;margin-bottom:20px;flex-wrap:wrap}}
  .card{{flex:1;min-width:180px;background:#161b22;border:1px solid #30363d;border-radius:8px;padding:14px}}
  .card-label{{font-size:11px;color:#8b949e;margin-bottom:4px}}
  .card-value{{font-size:20px;font-weight:700}}
  .card-sub{{font-size:11px;color:#8b949e;margin-top:2px}}
  .card.risk{{border-color:#d29922;background:#272115}}
  .card.positive{{border-color:#238636;background:#0d1117}}
  .card.warning{{border-color:#8957e5;background:#1a1329}}
  canvas{{max-height:260px}}
  table{{width:100%;border-collapse:collapse;font-size:13px}}
  th,td{{padding:8px 12px;border:1px solid #21262d;text-align:left}}
  th{{background:#161b22;color:#8b949e;font-weight:500}}
  td.risk-cell{{background:#27211577;color:#d29922;font-weight:600}}
  td.zero{{color:#484f58}}
  .section-title{{font-size:12px;text-transform:uppercase;letter-spacing:1px;color:#8b949e;margin-bottom:12px;margin-top:20px}}
  .person-cards{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px}}
  .person-card{{flex:1;min-width:200px;background:#161b22;border:1px solid #30363d;border-radius:8px;padding:14px}}
  .person-name{{font-size:15px;font-weight:600;margin-bottom:6px}}
  .person-stat{{font-size:12px;color:#8b949e;line-height:1.8}}
  .trend-up{{color:#3fb950}}.trend-down{{color:#f85149}}.trend-flat{{color:#8b949e}}
  .filter-row{{display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap}}
  .filter-btn{{background:#161b22;border:1px solid #30363d;color:#e6edf3;padding:3px 10px;border-radius:4px;cursor:pointer;font-size:12px}}
  .filter-btn.active{{background:#1f6feb;border-color:#1f6feb}}
</style>
</head>
<body>
<div id="header">
  <h1>📊 Git Reporter Dashboard</h1>
  <div id="range-btns">
    <button onclick="setRange(7)">7天</button>
    <button onclick="setRange(30)" class="active">30天</button>
    <button onclick="setRange(90)">90天</button>
  </div>
</div>
<div id="tab-btns">
  <button class="active" onclick="showTab('insights',this)">📈 洞察</button>
  <button onclick="showTab('timeline',this)">⏱ 时间线</button>
  <button onclick="showTab('members',this)">👥 成员</button>
</div>

<div id="tab-insights" class="tab-content active">
  <div class="cards" id="insight-cards"></div>
  <div class="section-title">团队动能（近8周）</div>
  <canvas id="momentum-chart"></canvas>
  <div class="section-title" style="margin-top:24px">成员派生指标</div>
  <table id="derived-metrics"></table>
</div>

<div id="tab-timeline" class="tab-content">
  <div class="filter-row" id="person-filter"></div>
  <canvas id="timeline-chart"></canvas>
</div>

<div id="tab-members" class="tab-content">
  <div class="person-cards" id="person-cards"></div>
  <div class="section-title">Repo × 人员覆盖矩阵（commits 数）</div>
  <table id="coverage-matrix"></table>
</div>

<script>
const ALL_DATA = {data_json};
const COLORS = ["#e94560","#1f6feb","#8957e5","#3fb950","#f0883e","#58a6ff","#bc8cff","#ffa657"];

let currentRange = {initial_range};
let timelineChart = null;
let momentumChart = null;
let activePersons = new Set(ALL_DATA.persons);

function getFilteredRows(days) {{
  const cutoff = new Date(ALL_DATA.generated_at);
  cutoff.setDate(cutoff.getDate() - days + 1);
  const cutoffStr = cutoff.toISOString().slice(0, 10);
  return ALL_DATA.rows.filter(r => r.date >= cutoffStr);
}}

function getFilteredDates(days) {{
  const rows = getFilteredRows(days);
  return [...new Set(rows.map(r => r.date))].sort();
}}

function setRange(days) {{
  currentRange = days;
  document.querySelectorAll("#range-btns button").forEach((b, i) => {{
    b.classList.toggle("active", [7,30,90][i] === days);
  }});
  renderAll();
}}

function showTab(name, btn) {{
  document.querySelectorAll(".tab-content").forEach(el => el.classList.remove("active"));
  document.getElementById("tab-" + name).classList.add("active");
  document.querySelectorAll("#tab-btns button").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
}}

function renderInsights() {{
  const rows = getFilteredRows(currentRange);
  const persons = ALL_DATA.persons;

  // per-person commits in current range
  const personCommits = {{}};
  const personLines = {{}};
  const personRepos = {{}};
  persons.forEach(p => {{ personCommits[p] = 0; personLines[p] = 0; personRepos[p] = new Set(); }});
  rows.forEach(r => {{
    personCommits[r.person] = (personCommits[r.person] || 0) + r.commits;
    personLines[r.person] = (personLines[r.person] || 0) + r.lines_added;
    if (r.commits > 0) (personRepos[r.person] = personRepos[r.person] || new Set()).add(r.repo);
  }});

  // backup risks: repos with only 1 contributor
  const repoPeople = {{}};
  rows.forEach(r => {{ if (r.commits > 0) {{ repoPeople[r.repo] = repoPeople[r.repo] || new Set(); repoPeople[r.repo].add(r.person); }} }});
  const risks = Object.entries(repoPeople).filter(([,v]) => v.size === 1).map(([repo,v]) => ({{repo, person: [...v][0]}}));

  // top person
  const topPerson = persons.reduce((a, b) => personCommits[a] >= personCommits[b] ? a : b, persons[0]);
  const totalCommits = Object.values(personCommits).reduce((a, b) => a + b, 0);

  // render insight cards
  const cards = document.getElementById("insight-cards");
  cards.innerHTML = "";

  const riskCard = risks.length > 0
    ? `<div class="card risk"><div class="card-label">⚠ 备份风险</div><div class="card-value" style="font-size:15px">${{risks.map(r => r.repo).join(", ")}}</div><div class="card-sub">仅 ${{risks.map(r=>r.person).join("/")}}</div></div>`
    : `<div class="card positive"><div class="card-label">✅ 备份覆盖</div><div class="card-value" style="font-size:15px">无风险</div><div class="card-sub">所有 repo 多人覆盖</div></div>`;
  cards.innerHTML += riskCard;

  if (topPerson && personCommits[topPerson] > 0) {{
    cards.innerHTML += `<div class="card positive"><div class="card-label">🔥 最强贡献</div><div class="card-value">${{topPerson}}</div><div class="card-sub">${{personCommits[topPerson]}} commits</div></div>`;
  }}

  const silent = persons.filter(p => personCommits[p] === 0);
  if (silent.length > 0) {{
    cards.innerHTML += `<div class="card warning"><div class="card-label">📉 无提交</div><div class="card-value" style="font-size:15px">${{silent.join(", ")}}</div><div class="card-sub">本周期内</div></div>`;
  }}

  cards.innerHTML += `<div class="card"><div class="card-label">📊 周期总量</div><div class="card-value">${{totalCommits}}</div><div class="card-sub">过去 ${{currentRange}} 天</div></div>`;

  // derived metrics table
  const table = document.getElementById("derived-metrics");
  const rows2 = `<tr><th>成员</th><th>总 commits</th><th>平均每 commit 行数</th><th>活跃 repo 数</th></tr>` +
    persons.map(p => {{
      const commits = personCommits[p] || 0;
      const lines = personLines[p] || 0;
      const avgLines = commits > 0 ? Math.round(lines / commits) : 0;
      const repoCount = (personRepos[p] || new Set()).size;
      return `<tr><td>${{p}}</td><td>${{commits}}</td><td>${{avgLines}}</td><td>${{repoCount}}</td></tr>`;
    }}).join("");
  table.innerHTML = rows2;

  // momentum chart (weekly totals from all data)
  const wt = ALL_DATA.weekly_totals;
  if (momentumChart) momentumChart.destroy();
  const mCtx = document.getElementById("momentum-chart").getContext("2d");
  momentumChart = new Chart(mCtx, {{
    type: "bar",
    data: {{
      labels: wt.map(w => w.label),
      datasets: [{{ label: "团队总 commits", data: wt.map(w => w.total), backgroundColor: "#1f6feb", borderRadius: 4 }}]
    }},
    options: {{ plugins: {{ legend: {{ display: false }} }}, scales: {{ x: {{ ticks: {{ color: "#8b949e" }} }}, y: {{ ticks: {{ color: "#8b949e" }}, grid: {{ color: "#21262d" }} }} }} }}
  }});
}}

function renderTimeline() {{
  const dates = getFilteredDates(currentRange);
  const rows = getFilteredRows(currentRange);

  // rebuild filter buttons
  const filterDiv = document.getElementById("person-filter");
  filterDiv.innerHTML = ALL_DATA.persons.map((p, i) =>
    `<button class="filter-btn ${{activePersons.has(p)?'active':''}}" onclick="togglePerson('${{p}}')" style="border-color:${{COLORS[i%COLORS.length]}}">${{p}}</button>`
  ).join("");

  const datasets = ALL_DATA.persons.filter(p => activePersons.has(p)).map((p, i) => {{
    const data = dates.map(d => {{
      const dayRows = rows.filter(r => r.date === d && r.person === p);
      return dayRows.reduce((sum, r) => sum + r.commits, 0);
    }});
    return {{ label: p, data, backgroundColor: COLORS[i % COLORS.length], stack: "stack" }};
  }});

  // mark weekends with lighter background using afterDatasetsDraw
  const weekendPlugin = {{
    id: "weekends",
    beforeDraw(chart) {{
      const {{ctx, chartArea, scales}} = chart;
      if (!chartArea) return;
      ctx.save();
      dates.forEach((d, i) => {{
        const dow = new Date(d).getUTCDay();
        if (dow === 0 || dow === 6) {{
          const x = scales.x.getPixelForValue(i);
          const bw = scales.x.width / dates.length;
          ctx.fillStyle = "rgba(255,255,255,0.03)";
          ctx.fillRect(x - bw / 2, chartArea.top, bw, chartArea.height);
        }}
      }});
      ctx.restore();
    }}
  }};

  if (timelineChart) timelineChart.destroy();
  const ctx = document.getElementById("timeline-chart").getContext("2d");
  timelineChart = new Chart(ctx, {{
    type: "bar",
    plugins: [weekendPlugin],
    data: {{ labels: dates, datasets }},
    options: {{
      plugins: {{ legend: {{ labels: {{ color: "#8b949e" }} }} }},
      scales: {{
        x: {{ stacked: true, ticks: {{ color: "#8b949e", maxRotation: 45 }} }},
        y: {{ stacked: true, ticks: {{ color: "#8b949e" }}, grid: {{ color: "#21262d" }} }}
      }}
    }}
  }});
}}

function togglePerson(name) {{
  if (activePersons.has(name)) {{ if (activePersons.size > 1) activePersons.delete(name); }}
  else activePersons.add(name);
  renderTimeline();
}}

function renderMembers() {{
  const rows = getFilteredRows(currentRange);
  const allRows90 = ALL_DATA.rows;
  const cutoff = new Date(ALL_DATA.generated_at);
  cutoff.setDate(cutoff.getDate() - currentRange + 1);
  const prevCutoff = new Date(cutoff);
  prevCutoff.setDate(prevCutoff.getDate() - currentRange);
  const cutoffStr = cutoff.toISOString().slice(0, 10);
  const prevStr = prevCutoff.toISOString().slice(0, 10);
  const prevPeriodRows = allRows90.filter(r => r.date >= prevStr && r.date < cutoffStr);

  const personCommits = {{}};
  const personLines = {{}};
  const personRepos = {{}};
  ALL_DATA.persons.forEach(p => {{ personCommits[p] = 0; personLines[p] = 0; personRepos[p] = new Set(); }});
  rows.forEach(r => {{
    personCommits[r.person] = (personCommits[r.person]||0) + r.commits;
    personLines[r.person] = (personLines[r.person]||0) + r.lines_added;
    if (r.commits>0) personRepos[r.person].add(r.repo);
  }});

  const prevCommits = {{}};
  prevPeriodRows.forEach(r => {{ prevCommits[r.person] = (prevCommits[r.person]||0) + r.commits; }});

  // person cards
  const cardsDiv = document.getElementById("person-cards");
  cardsDiv.innerHTML = ALL_DATA.persons.map((p, i) => {{
    const c = personCommits[p]||0, l = personLines[p]||0, rv = (personRepos[p]||new Set()).size;
    const prev = prevCommits[p]||0;
    let trendHtml = "";
    if (prev > 0) {{
      const pct = Math.round((c - prev) / prev * 100);
      const cls = pct > 0 ? "trend-up" : pct < 0 ? "trend-down" : "trend-flat";
      trendHtml = `<span class="${{cls}}">${{pct > 0 ? "↑" : pct < 0 ? "↓" : "→"}}${{Math.abs(pct)}}% vs 上期</span>`;
    }}
    return `<div class="person-card" style="border-left:3px solid ${{COLORS[i%COLORS.length]}}">
      <div class="person-name">${{p}}</div>
      <div class="person-stat">${{c}} commits · +${{l.toLocaleString()}} 行 · ${{rv}} repos</div>
      ${{trendHtml}}
    </div>`;
  }}).join("");

  // coverage matrix
  const repos = ALL_DATA.repos;
  const repoPeople = {{}};
  rows.forEach(r => {{
    if (!repoPeople[r.repo]) repoPeople[r.repo] = {{}};
    repoPeople[r.repo][r.person] = (repoPeople[r.repo][r.person]||0) + r.commits;
  }});

  const matrix = document.getElementById("coverage-matrix");
  const header = `<tr><th>Repo</th>${{ALL_DATA.persons.map(p=>`<th>${{p}}</th>`).join("")}}</tr>`;
  const bodyRows = repos.map(repo => {{
    const isSingle = ALL_DATA.persons.filter(p => (repoPeople[repo]||{{}})[p]>0).length === 1;
    const repoLabel = isSingle ? `⚠ ${{repo}}` : repo;
    const cells = ALL_DATA.persons.map(p => {{
      const v = (repoPeople[repo]||{{}})[p]||0;
      const cls = v===0 ? "zero" : isSingle ? "risk-cell" : "";
      return `<td class="${{cls}}">${{v===0?"—":v}}</td>`;
    }}).join("");
    return `<tr><td${{isSingle?' style="color:#d29922"':''}}>${{repoLabel}}</td>${{cells}}</tr>`;
  }}).join("");
  matrix.innerHTML = header + bodyRows;
}}

function renderAll() {{
  renderInsights();
  renderTimeline();
  renderMembers();
}}

renderAll();
</script>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(description="生成 Git Reporter 仪表盘")
    parser.add_argument("--days", type=int, default=30, help="数据天数（默认 30）")
    parser.add_argument("--config", default="config.yaml", help="配置文件路径")
    parser.add_argument("--rescan", action="store_true", help="重新从 git history 扫描数据")
    parser.add_argument("--output", default="dashboard.html", help="输出 HTML 路径")
    args = parser.parse_args()

    cfg = load_config(args.config)
    persons = list(cfg.members.values())
    today = date.today()
    start = today - timedelta(days=args.days - 1)

    if args.rescan:
        from data_store import save_snapshot as _save
        print(f"Rescanning {args.days} days of git history...")
        for i in range(args.days):
            d = start + timedelta(days=i)
            repo_commits = {}
            for repo in cfg.repos:
                commits, _ = collect_repo(repo.path, repo.branches, d, remote=repo.remote)
                repo_commits[repo.name] = commits
            report = build_report(repo_commits, cfg, d)
            _save(report, d)
            print(f"  {d.isoformat()} ✓")

    # 始终嵌入最多 90 天数据，时间范围选择器在前端过滤
    embed_start = today - timedelta(days=89)
    rows = query_range(embed_start, today)
    html = generate_html(rows, persons, initial_range=args.days)

    output_path = os.path.abspath(args.output)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Dashboard generated: {output_path}")
    webbrowser.open(f"file://{output_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m pytest tests/test_dashboard.py -v
```

Expected: 5 tests PASSED

- [ ] **Step 5: 运行全部测试确认无回归**

```bash
python -m pytest tests/ -v
```

Expected: 全部 PASSED（共约 39 个测试）

- [ ] **Step 6: 手动验证仪表盘生成（可选，需有 SQLite 数据）**

如果没有真实数据，先用 `--dry-run` 跑几天积累数据：

```bash
python3 main.py config.yaml 2026-03-28 --dry-run
python3 main.py config.yaml 2026-03-29 --dry-run
python3 dashboard.py --days 30
```

预期：浏览器自动打开 `dashboard.html`，三个 tab 可切换，图表正常渲染。

- [ ] **Step 7: 提交**

```bash
git add dashboard.py tests/test_dashboard.py
git commit -m "feat: add HTML dashboard with 3-tab visualization (insights, timeline, members)"
```

---

## 验收清单

- [ ] `python -m pytest tests/ -v` 全部通过
- [ ] `python3 main.py config.yaml --dry-run` 运行后 `git_reporter.db` 存在
- [ ] `python3 dashboard.py` 生成 `dashboard.html` 并在浏览器打开
- [ ] 仪表盘三个 tab 可切换；时间范围 7/30/90 天可切换
- [ ] `python3 main.py --weekly` 正常调用（无 webhook 时抛 ConnectionError 属正常）
- [ ] `crontab -l` 可加入 `0 9 * * 1 ... python3 main.py --weekly`
