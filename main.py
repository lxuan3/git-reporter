# main.py
import sys
from datetime import date
from config import load_config
from git_collector import collect_repo
from report_builder import build_report
from feishu_sender import send_report, send_warnings

def run(config_path: str = "config.yaml", target_date: date = None):
    if target_date is None:
        target_date = date.today()

    cfg = load_config(config_path)

    repo_commits = {}
    all_warnings = []

    for repo in cfg.repos:
        commits, warnings = collect_repo(repo.path, repo.branches, target_date)
        repo_commits[repo.name] = commits
        all_warnings.extend(warnings)

    report = build_report(repo_commits, cfg, target_date)

    send_report(cfg.feishu_webhook_url, report)

    if all_warnings:
        send_warnings(cfg.feishu_webhook_url, all_warnings)

if __name__ == "__main__":
    # 支持可选参数：python main.py [config_path] [YYYY-MM-DD]
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    if len(sys.argv) > 2:
        target_date = date.fromisoformat(sys.argv[2])
    else:
        target_date = date.today()
    run(config_path, target_date)
