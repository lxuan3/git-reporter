# main.py
import sys
import json
from datetime import date, timedelta
from typing import Optional
from config import load_config
from git_collector import collect_repo
from report_builder import build_report, PersonReport
from feishu_sender import build_payload, send_report, send_warnings
from data_store import save_snapshot, query_range
from weekly_reporter import build_weekly_report, send_weekly_report

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

    save_snapshot(report, target_date)

    if dry_run:
        _print_dry_run(report, all_warnings)
        return

    send_report(cfg.feishu_webhook_url, report)

    if all_warnings:
        send_warnings(cfg.feishu_webhook_url, all_warnings)

def run_weekly(config_path: str = "config.yaml"):
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
    # 支持可选参数：python main.py [config_path] [YYYY-MM-DD] [--dry-run] [--weekly]
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry_run = "--dry-run" in sys.argv
    weekly = "--weekly" in sys.argv

    config_path = args[0] if len(args) > 0 else "config.yaml"

    if weekly:
        run_weekly(config_path)
    else:
        if len(args) > 1:
            target_date = date.fromisoformat(args[1])
        else:
            target_date = date.today()
        run(config_path, target_date, dry_run=dry_run)
