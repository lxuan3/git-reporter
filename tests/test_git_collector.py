# tests/test_git_collector.py
from git_collector import _parse_git_log, CommitData

# git log --format="COMMIT|%H|%ae|%an|%s" --numstat --no-merges 的典型输出
SAMPLE_OUTPUT = """\
COMMIT|abc123|alice@example.com|alice|feat: add login page

5\t2\tsrc/login.py
1\t0\tsrc/app.py

COMMIT|def456|bob@example.com|bob|fix: correct typo

0\t1\tREADME.md

"""

def test_parse_basic():
    commits = _parse_git_log(SAMPLE_OUTPUT)
    assert len(commits) == 2

def test_parse_first_commit():
    commits = _parse_git_log(SAMPLE_OUTPUT)
    c = commits[0]
    assert c.hash == "abc123"
    assert c.author_email == "alice@example.com"
    assert c.author_name == "alice"
    assert c.message == "feat: add login page"
    assert c.lines_added == 6   # 5+1
    assert c.lines_deleted == 2
    assert c.files_changed == 2

def test_parse_second_commit():
    commits = _parse_git_log(SAMPLE_OUTPUT)
    c = commits[1]
    assert c.hash == "def456"
    assert c.lines_added == 0
    assert c.lines_deleted == 1
    assert c.files_changed == 1

def test_parse_empty():
    assert _parse_git_log("") == []

def test_parse_binary_file():
    # 二进制文件 numstat 显示 "-\t-\tfile.png"
    output = "COMMIT|aaa|x@x.com|x|chore: add image\n\n-\t-\tlogo.png\n3\t1\tsrc/a.py\n\n"
    commits = _parse_git_log(output)
    assert commits[0].files_changed == 2   # 二进制文件也计入文件数
    assert commits[0].lines_added == 3     # 二进制不计行数
    assert commits[0].lines_deleted == 1

def test_dedup_across_branches():
    """collect_repo 对同一 hash 只计一次"""
    from unittest.mock import patch, MagicMock
    from datetime import date
    from git_collector import collect_repo

    same_output = "COMMIT|abc123|a@b.com|a|feat: x\n\n1\t0\tf.py\n\n"

    def fake_run(cmd, **kwargs):
        m = MagicMock()
        if "checkout" in cmd or "pull" in cmd:
            m.returncode = 0
        elif "log" in cmd:
            m.returncode = 0
            m.stdout = same_output
        return m

    with patch("git_collector.subprocess.run", side_effect=fake_run):
        commits, warnings = collect_repo("/fake/repo", ["main", "develop"], date(2026, 3, 29))

    assert len(commits) == 1    # 两个 branch 里的同一 commit 只计一次
    assert warnings == []

def test_pull_failure_returns_warning():
    from unittest.mock import patch, MagicMock
    from datetime import date
    from git_collector import collect_repo

    def fake_run(cmd, **kwargs):
        m = MagicMock()
        m.returncode = 1   # 所有命令都失败
        m.stdout = ""
        return m

    with patch("git_collector.subprocess.run", side_effect=fake_run):
        commits, warnings = collect_repo("/fake/repo", ["main"], date(2026, 3, 29))

    assert commits == []
    assert len(warnings) == 1
