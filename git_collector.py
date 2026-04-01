# git_collector.py
import os
import subprocess
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

GIT_CHECKOUT_TIMEOUT_SECONDS = 30
GIT_PULL_TIMEOUT_SECONDS = 120
GIT_LOG_TIMEOUT_SECONDS = 120

@dataclass
class CommitData:
    hash: str
    author_email: str
    author_name: str
    message: str
    files_changed: int
    lines_added: int
    lines_deleted: int


def _log(message: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {message}", flush=True)


def _summarize_process_output(result: Optional[subprocess.CompletedProcess]) -> str:
    if result is None:
        return "timeout"
    parts = []
    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    if stderr:
        parts.append(f"stderr={stderr.splitlines()[0]}")
    if stdout:
        parts.append(f"stdout={stdout.splitlines()[0]}")
    return " | ".join(parts) if parts else f"returncode={result.returncode}"

def _parse_git_log(output: str) -> list[CommitData]:
    """解析 git log --format='COMMIT|%H|%ae|%an|%s' --numstat 的输出。"""
    commits = []
    current = None
    files_changed = 0
    lines_added = 0
    lines_deleted = 0

    for line in output.splitlines():
        if line.startswith("COMMIT|"):
            if current is not None:
                commits.append(CommitData(
                    hash=current["hash"],
                    author_email=current["email"],
                    author_name=current["name"],
                    message=current["message"],
                    files_changed=files_changed,
                    lines_added=lines_added,
                    lines_deleted=lines_deleted,
                ))
            parts = line.split("|", 4)
            current = {"hash": parts[1], "email": parts[2], "name": parts[3], "message": parts[4]}
            files_changed = 0
            lines_added = 0
            lines_deleted = 0
        elif line.strip() and current is not None:
            parts = line.split("\t")
            if len(parts) >= 3:
                files_changed += 1
                try:
                    lines_added += int(parts[0]) if parts[0] != "-" else 0
                    lines_deleted += int(parts[1]) if parts[1] != "-" else 0
                except ValueError:
                    pass

    if current is not None:
        commits.append(CommitData(
            hash=current["hash"],
            author_email=current["email"],
            author_name=current["name"],
            message=current["message"],
            files_changed=files_changed,
            lines_added=lines_added,
            lines_deleted=lines_deleted,
        ))

    return commits

def _get_current_branch(repo_path: str) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=repo_path, capture_output=True, text=True
    )
    return result.stdout.strip() or "main"


def _run_git(
    args: list[str],
    repo_path: str,
    timeout: int,
) -> Optional[subprocess.CompletedProcess]:
    try:
        return subprocess.run(
            args,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        _log(f"git 命令超时：repo={repo_path} cmd={' '.join(args)} timeout={timeout}s")
        return None

def _pull_branch(repo_path: str, branch: str) -> bool:
    r1 = _run_git(["git", "checkout", branch, "--quiet"], repo_path, GIT_CHECKOUT_TIMEOUT_SECONDS)
    if r1 is None or r1.returncode != 0:
        return False
    r2 = _run_git(["git", "pull", "--quiet"], repo_path, GIT_PULL_TIMEOUT_SECONDS)
    return r2 is not None and r2.returncode == 0

def _ensure_cloned(repo_path: str, remote: str) -> tuple[bool, str]:
    """本地路径不存在时自动 clone。返回 (success, warning_or_empty)。"""
    if os.path.exists(repo_path):
        return True, ""
    if not remote:
        return False, f"路径不存在且未配置 remote：{repo_path}"
    result = subprocess.run(
        ["git", "clone", remote, repo_path],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return False, f"git clone 失败：{remote} → {repo_path}（{result.stderr.strip()}）"
    return True, ""

def collect_repo(repo_path: str, branches: list[str], target_date: date, remote: str = "") -> tuple[list[CommitData], list[str]]:
    """
    Returns (commits: list[CommitData], warnings: list[str]).
    commits 已按 hash 去重。若本地路径不存在且配置了 remote，自动 clone。
    """
    ok, warn = _ensure_cloned(repo_path, remote)
    if not ok:
        return [], [warn]

    since = target_date.strftime("%Y-%m-%d 00:00:00")
    until = target_date.strftime("%Y-%m-%d 23:59:59")

    actual_branches = branches if branches else [_get_current_branch(repo_path)]

    seen = set()
    all_commits = []
    warnings = []

    for branch in actual_branches:
        _log(f"开始采集：repo={repo_path} branch={branch}")
        checkout = _run_git(["git", "checkout", branch, "--quiet"], repo_path, GIT_CHECKOUT_TIMEOUT_SECONDS)
        if checkout is None or checkout.returncode != 0:
            detail = _summarize_process_output(checkout)
            warnings.append(f"git checkout 失败：{repo_path} branch={branch} ({detail})")
            _log(f"采集失败：repo={repo_path} branch={branch} stage=checkout detail={detail}")
            continue

        pull = _run_git(["git", "pull", "--quiet"], repo_path, GIT_PULL_TIMEOUT_SECONDS)
        if pull is None or pull.returncode != 0:
            detail = _summarize_process_output(pull)
            warnings.append(f"git pull 失败：{repo_path} branch={branch} ({detail})")
            _log(f"采集失败：repo={repo_path} branch={branch} stage=pull detail={detail}")
            continue

        result = _run_git(
            ["git", "log",
             f"--since={since}", f"--until={until}",
             "--format=COMMIT|%H|%ae|%an|%s",
             "--numstat", "--no-merges"],
            repo_path,
            GIT_LOG_TIMEOUT_SECONDS,
        )

        if result is None:
            warnings.append(f"git log 超时：{repo_path} branch={branch}")
            _log(f"采集失败：repo={repo_path} branch={branch} stage=log timeout={GIT_LOG_TIMEOUT_SECONDS}s")
            continue

        if result.returncode != 0:
            detail = _summarize_process_output(result)
            warnings.append(f"git log 失败：{repo_path} branch={branch} ({detail})")
            _log(f"采集失败：repo={repo_path} branch={branch} stage=log detail={detail}")
            continue

        branch_commits = 0
        for commit in _parse_git_log(result.stdout):
            if commit.hash not in seen:
                seen.add(commit.hash)
                all_commits.append(commit)
                branch_commits += 1

        _log(f"采集完成：repo={repo_path} branch={branch} commits={branch_commits}")

    return all_commits, warnings
