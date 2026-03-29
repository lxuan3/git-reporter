# tests/test_feishu_sender.py
from datetime import date
from unittest.mock import patch, MagicMock
from report_builder import PersonReport, RepoStats
from feishu_sender import build_payload, send_report, send_warnings

def _make_report(active_count=2, total_count=3, total_commits=5,
                 lines_added=100, lines_deleted=30):
    zhang = PersonReport(display_name="张三", repos={
        "repo1": RepoStats(commits=3, lines_added=60, lines_deleted=20,
                           files_changed=4, messages=["[新功能] 新增页面", "[修复] 修复 bug"]),
    })
    li = PersonReport(display_name="李四", repos={
        "repo1": RepoStats(commits=2, lines_added=40, lines_deleted=10,
                           files_changed=2, messages=["[重构] 优化逻辑"]),
    })
    wang = PersonReport(display_name="王五", repos={})  # 无 commit
    return {
        "date": date(2026, 3, 29),
        "persons": [zhang, li, wang],
        "total_commits": total_commits,
        "total_lines_added": lines_added,
        "total_lines_deleted": lines_deleted,
        "active_count": active_count,
        "total_count": total_count,
        "top": [zhang, li],
    }

def test_build_payload_normal():
    report = _make_report()
    payload = build_payload(report)
    assert payload["msg_type"] == "post"
    content = payload["content"]["post"]["zh_cn"]["content"]
    # 拍平所有文本
    flat = " ".join(item["text"] for line in content for item in line)
    assert "张三" in flat
    assert "李四" in flat
    assert "王五（今日无提交）" in flat
    assert "🥇" in flat
    assert "🥈" in flat
    assert "活跃 2/3" in flat

def test_build_payload_no_commits():
    report = _make_report(active_count=0, total_commits=0, lines_added=0, lines_deleted=0)
    report["top"] = []
    report["persons"] = [PersonReport("张三"), PersonReport("李四")]
    payload = build_payload(report)
    assert payload["msg_type"] == "text"
    assert "今日暂无" in payload["content"]["text"]

def test_top_one_when_single_active():
    report = _make_report()
    report["top"] = [report["persons"][0]]   # 只有一个
    payload = build_payload(report)
    flat = " ".join(item["text"] for line in payload["content"]["post"]["zh_cn"]["content"] for item in line)
    assert "🥇" in flat
    assert "🥈" not in flat

def test_send_report_calls_webhook():
    report = _make_report()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"code": 0}
    mock_resp.raise_for_status = MagicMock()

    with patch("feishu_sender.requests.post", return_value=mock_resp) as mock_post:
        result = send_report("http://fake-webhook", report)

    mock_post.assert_called_once()
    assert result is True

def test_send_warnings_skips_if_empty():
    with patch("feishu_sender.requests.post") as mock_post:
        send_warnings("http://fake", [])
    mock_post.assert_not_called()
