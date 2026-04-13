from collections import defaultdict
from datetime import date, datetime, timedelta

import requests

from config import Config

FEISHU_TIMEOUT_SECONDS = 20


def _log(message: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {message}", flush=True)


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
    """返回整周（7天）零提交的成员列表。"""
    active_persons: set[str] = set()
    week_end = (week_start + timedelta(days=6)).isoformat()
    ws = week_start.isoformat()
    for row in rows:
        if ws <= row["date"] <= week_end and row["commits"] > 0:
            active_persons.add(row["person"])
    return [
        {"name": name}
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

    all_names = list(dict.fromkeys(cfg.members.values()))

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
        "backup_risks": _find_backup_risks(curr_rows, week_start, week_end),
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
    _log("开始发送飞书周报")
    resp = requests.post(webhook_url, json=payload, timeout=FEISHU_TIMEOUT_SECONDS)
    resp.raise_for_status()
    _log("飞书周报发送完成")
