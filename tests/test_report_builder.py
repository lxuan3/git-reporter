# tests/test_report_builder.py
from report_builder import translate_message, resolve_name, build_report, compute_score
from config import Config, RepoConfig, ScoringConfig
from git_collector import CommitData
from datetime import date

# ── translate_message ──────────────────────────────────────────────
def test_translate_feat():
    assert translate_message("feat: add login") == "[新功能] add login"

def test_translate_fix_with_scope():
    assert translate_message("fix(auth): token expiry") == "[修复] token expiry"

def test_translate_unknown_prefix():
    assert translate_message("update readme") == "update readme"

def test_translate_chore():
    assert translate_message("chore: bump deps") == "[维护] bump deps"

def test_translate_case_insensitive():
    assert translate_message("Feat: something") == "[新功能] something"

# ── resolve_name ───────────────────────────────────────────────────
def test_resolve_by_email():
    members = {"a@b.com": "张三", "lisi": "李四"}
    assert resolve_name("a@b.com", "alice", members) == "张三"

def test_resolve_by_username():
    members = {"a@b.com": "张三", "lisi": "李四"}
    assert resolve_name("unknown@x.com", "lisi", members) == "李四"

def test_resolve_fallback():
    members = {"a@b.com": "张三"}
    assert resolve_name("x@y.com", "wangwu", members) == "wangwu"

# ── build_report ───────────────────────────────────────────────────
def _make_config():
    return Config(
        feishu_webhook_url="http://fake",
        members={"a@b.com": "张三", "lisi": "李四"},
        repos=[RepoConfig("repo1", "/tmp/r1", [])],
        scoring=ScoringConfig(commit_weight=10, lines_weight=1),
    )

def _make_commit(hash, email, name, msg, added=10, deleted=2, files=2):
    return CommitData(hash=hash, author_email=email, author_name=name,
                      message=msg, files_changed=files,
                      lines_added=added, lines_deleted=deleted)

def test_active_person_appears_first():
    commits = [_make_commit("h1", "a@b.com", "alice", "feat: x")]
    report = build_report({"repo1": commits}, _make_config(), date(2026, 3, 29))
    persons = report["persons"]
    assert persons[0].display_name == "张三"    # 有 commit
    assert persons[-1].display_name == "李四"   # 无 commit，在末尾

def test_inactive_person_has_zero_commits():
    commits = [_make_commit("h1", "a@b.com", "alice", "fix: y")]
    report = build_report({"repo1": commits}, _make_config(), date(2026, 3, 29))
    inactive = [p for p in report["persons"] if p.total_commits == 0]
    assert len(inactive) == 1
    assert inactive[0].display_name == "李四"

def test_totals():
    commits = [
        _make_commit("h1", "a@b.com", "alice", "feat: a", added=10, deleted=2),
        _make_commit("h2", "a@b.com", "alice", "fix: b", added=5, deleted=1),
    ]
    report = build_report({"repo1": commits}, _make_config(), date(2026, 3, 29))
    assert report["total_commits"] == 2
    assert report["total_lines_added"] == 15
    assert report["total_lines_deleted"] == 3
    assert report["active_count"] == 1

def test_top_two():
    cfg = Config(
        feishu_webhook_url="http://fake",
        members={"a@b.com": "张三", "b@b.com": "李四", "c@b.com": "王五"},
        repos=[RepoConfig("repo1", "/tmp/r1", [])],
        scoring=ScoringConfig(commit_weight=10, lines_weight=1),
    )
    commits = [
        _make_commit("h1", "a@b.com", "a", "feat: x", added=100),  # score=110
        _make_commit("h2", "b@b.com", "b", "fix: y", added=50),    # score=60
        _make_commit("h3", "c@b.com", "c", "chore: z", added=5),   # score=15
    ]
    report = build_report({"repo1": commits}, cfg, date(2026, 3, 29))
    assert report["top"][0].display_name == "张三"
    assert report["top"][1].display_name == "李四"
    assert len(report["top"]) == 2

def test_top_one_when_only_one_active():
    commits = [_make_commit("h1", "a@b.com", "alice", "feat: x")]
    report = build_report({"repo1": commits}, _make_config(), date(2026, 3, 29))
    assert len(report["top"]) == 1

def test_messages_translated():
    commits = [_make_commit("h1", "a@b.com", "alice", "feat: add page")]
    report = build_report({"repo1": commits}, _make_config(), date(2026, 3, 29))
    person = report["persons"][0]
    assert "[新功能] add page" in person.repos["repo1"].messages
