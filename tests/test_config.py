# tests/test_config.py
import pytest
from config import load_config, Config, RepoConfig, ScoringConfig

VALID_YAML = """
feishu:
  webhook_url: "https://open.feishu.cn/open-apis/bot/v2/hook/abc"
members:
  "a@b.com": "张三"
  "lisi": "李四"
repos:
  - name: "repo1"
    path: "/tmp/repo1"
    branches: ["main", "dev"]
  - name: "repo2"
    path: "/tmp/repo2"
"""

def test_load_valid_config(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(VALID_YAML)
    cfg = load_config(str(p))
    assert cfg.feishu_webhook_url == "https://open.feishu.cn/open-apis/bot/v2/hook/abc"
    assert cfg.members["a@b.com"] == "张三"
    assert cfg.members["lisi"] == "李四"
    assert len(cfg.repos) == 2
    assert cfg.repos[0].name == "repo1"
    assert cfg.repos[0].branches == ["main", "dev"]
    assert cfg.repos[1].branches == []

def test_default_scoring(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(VALID_YAML)
    cfg = load_config(str(p))
    assert cfg.scoring.commit_weight == 10
    assert cfg.scoring.lines_weight == 1

def test_custom_scoring(tmp_path):
    yaml_str = VALID_YAML + "\nscoring:\n  commit_weight: 5\n  lines_weight: 2\n"
    p = tmp_path / "config.yaml"
    p.write_text(yaml_str)
    cfg = load_config(str(p))
    assert cfg.scoring.commit_weight == 5
    assert cfg.scoring.lines_weight == 2

def test_missing_feishu_raises(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("members:\n  a: b\nrepos: []\n")
    with pytest.raises(KeyError):
        load_config(str(p))
