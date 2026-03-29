# config.py
import yaml
from dataclasses import dataclass, field

@dataclass
class RepoConfig:
    name: str
    path: str
    branches: list[str]  # 空列表 = 使用当前 checkout 的 branch

@dataclass
class ScoringConfig:
    commit_weight: int = 10
    lines_weight: int = 1

@dataclass
class Config:
    feishu_webhook_url: str
    members: dict[str, str]        # git email/username → 真实姓名
    repos: list[RepoConfig]          # list[RepoConfig]
    scoring: ScoringConfig = field(default_factory=ScoringConfig)

def load_config(path: str = "config.yaml") -> Config:
    with open(path) as f:
        data = yaml.safe_load(f)

    scoring_data = data.get("scoring", {})
    scoring = ScoringConfig(
        commit_weight=scoring_data.get("commit_weight", 10),
        lines_weight=scoring_data.get("lines_weight", 1),
    )

    repos = [
        RepoConfig(
            name=r["name"],
            path=r["path"],
            branches=r.get("branches", []),
        )
        for r in data["repos"]
    ]

    return Config(
        feishu_webhook_url=data["feishu"]["webhook_url"],
        members=data.get("members", {}),
        repos=repos,
        scoring=scoring,
    )
