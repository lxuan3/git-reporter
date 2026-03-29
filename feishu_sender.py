# feishu_sender.py
import requests

def _text(t: str) -> dict:
    return {"tag": "text", "text": t}

def _line(*texts) -> list:
    return [_text(t) for t in texts]

def build_payload(report: dict) -> dict:
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
    resp = requests.post(webhook_url, json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json().get("code") == 0

def send_warnings(webhook_url: str, warnings: list) -> None:
    if not warnings:
        return
    text = "⚠️ Git 报告采集警告：\n" + "\n".join(f"- {w}" for w in warnings)
    requests.post(webhook_url, json={"msg_type": "text", "content": {"text": text}}, timeout=10)
