# feishu_sender.py
from datetime import datetime

import requests

FEISHU_TIMEOUT_SECONDS = 20


def _log(message: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {message}", flush=True)

def _text(t: str) -> dict:
    return {"tag": "text", "text": t}

def _line(*texts) -> list:
    return [_text(t) for t in texts]

def build_payload(report: dict) -> dict:
    """Build Feishu webhook payload from report dict.

    Expects report['persons'] to be pre-sorted: active (total_commits > 0) first,
    inactive last. Call build_report() from report_builder to get this ordering.
    """
    if report["total_commits"] == 0:
        return {"msg_type": "text", "content": {"text": "📊 今日暂无提交记录"}}

    d = report["date"].strftime("%Y-%m-%d")
    sep = "━" * 20
    lines = []

    lines.append(_line(f"📊 每日研发工作报告 · {d}"))
    lines.append(_line(sep))

    active_done = False
    for person in report["persons"]:
        if person.total_commits == 0 and not active_done:
            lines.append(_line(sep))
            active_done = True
        if person.total_commits > 0:
            lines.append(_line(f"👤 {person.display_name}"))
            for repo_name, stats in person.repos.items():
                lines.append(_line(
                    f"  • {repo_name}  {stats.commits} commits"
                    f" | +{stats.lines_added}/-{stats.lines_deleted} 行"
                    f" | {stats.files_changed} 个文件"
                ))
                for msg in stats.messages:
                    lines.append(_line(f"    - {msg}"))
        else:
            lines.append(_line(f"👤 {person.display_name}（今日无提交）"))

    lines.append(_line(sep))

    summary = (
        f"汇总：今日活跃 {report['active_count']}/{report['total_count']} 人"
        f" | 总计 {report['total_commits']} commits"
        f" | +{report['total_lines_added']}/-{report['total_lines_deleted']} 行"
    )
    lines.append(_line(summary))

    top = report["top"]
    if len(top) >= 1:
        p = top[0]
        lines.append(_line(f"🥇 {p.display_name}（{p.total_commits} commits · +{p.total_lines_added} 行）"))
    if len(top) >= 2:
        p = top[1]
        lines.append(_line(f"🥈 {p.display_name}（{p.total_commits} commits · +{p.total_lines_added} 行）"))

    return {
        "msg_type": "post",
        "content": {
            "post": {
                "zh_cn": {
                    "title": f"每日研发工作报告 · {d}",
                    "content": lines,
                }
            }
        },
    }

def send_report(webhook_url: str, report: dict) -> bool:
    payload = build_payload(report)
    _log("开始发送飞书日报")
    resp = requests.post(webhook_url, json=payload, timeout=FEISHU_TIMEOUT_SECONDS)
    resp.raise_for_status()
    ok = resp.json().get("code") == 0
    _log(f"飞书日报发送完成 success={ok}")
    return ok

def send_warnings(webhook_url: str, warnings: list[str]) -> None:
    if not warnings:
        return
    text = "⚠️ Git 报告采集警告：\n" + "\n".join(f"- {w}" for w in warnings)
    _log(f"开始发送飞书警告 count={len(warnings)}")
    resp = requests.post(
        webhook_url,
        json={"msg_type": "text", "content": {"text": text}},
        timeout=FEISHU_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    _log("飞书警告发送完成")
