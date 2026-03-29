# report_builder.py
import re
from dataclasses import dataclass, field
from datetime import date

PREFIX_MAP = {
    "feat": "新功能", "fix": "修复", "chore": "维护",
    "refactor": "重构", "docs": "文档", "style": "样式",
    "test": "测试", "perf": "性能优化", "revert": "回滚",
}
_PREFIX_RE = re.compile(
    r"^(" + "|".join(PREFIX_MAP.keys()) + r")(\(.+?\))?:\s*",
    re.IGNORECASE
)

def translate_message(message: str) -> str:
    m = _PREFIX_RE.match(message)
    if not m:
        return message
    label = PREFIX_MAP[m.group(1).lower()]
    rest = message[m.end():]
    return f"[{label}] {rest}"

def resolve_name(author_email: str, author_name: str, members: dict) -> str:
    if author_email in members:
        return members[author_email]
    if author_name in members:
        return members[author_name]
    return author_name

@dataclass
class RepoStats:
    commits: int = 0
    lines_added: int = 0
    lines_deleted: int = 0
    files_changed: int = 0
    messages: list = field(default_factory=list)

@dataclass
class PersonReport:
    display_name: str
    repos: dict = field(default_factory=dict)   # repo_name -> RepoStats

    @property
    def total_commits(self):
        return sum(r.commits for r in self.repos.values())

    @property
    def total_lines_added(self):
        return sum(r.lines_added for r in self.repos.values())

    @property
    def total_lines_deleted(self):
        return sum(r.lines_deleted for r in self.repos.values())

def compute_score(person: PersonReport, scoring) -> float:
    return person.total_commits * scoring.commit_weight + person.total_lines_added * scoring.lines_weight

def build_report(repo_commits: dict, config, target_date: date) -> dict:
    """
    repo_commits: {repo_name: [CommitData]}
    Returns structured report dict.
    """
    person_data: dict[str, PersonReport] = {}

    for repo_name, commits in repo_commits.items():
        for commit in commits:
            name = resolve_name(commit.author_email, commit.author_name, config.members)
            if name not in person_data:
                person_data[name] = PersonReport(display_name=name)
            if repo_name not in person_data[name].repos:
                person_data[name].repos[repo_name] = RepoStats()
            stats = person_data[name].repos[repo_name]
            stats.commits += 1
            stats.lines_added += commit.lines_added
            stats.lines_deleted += commit.lines_deleted
            stats.files_changed += commit.files_changed
            stats.messages.append(translate_message(commit.message))

    # 补充 config 中配置了但今天没有 commit 的成员
    for name in config.members.values():
        if name not in person_data:
            person_data[name] = PersonReport(display_name=name)

    active = [p for p in person_data.values() if p.total_commits > 0]
    inactive = [p for p in person_data.values() if p.total_commits == 0]
    active.sort(key=lambda p: compute_score(p, config.scoring), reverse=True)

    top = active[:2]

    return {
        "date": target_date,
        "persons": active + inactive,
        "total_commits": sum(p.total_commits for p in active),
        "total_lines_added": sum(p.total_lines_added for p in active),
        "total_lines_deleted": sum(p.total_lines_deleted for p in active),
        "active_count": len(active),
        "total_count": len(active) + len(inactive),
        "top": top,
    }
