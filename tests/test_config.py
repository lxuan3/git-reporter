# tests/test_config.py
import pytest
import yaml
import tempfile, os
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

def _write_tmp(content: str) -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    f.write(content)
    f.close()
    return f.name

def test_load_valid_config():
    path = _write_tmp(VALID_YAML)
    cfg = load_config(path)
    os.unlink(path)
    assert cfg.feishu_webhook_url == "https://open.feishu.cn/open-apis/bot/v2/hook/abc"
    assert cfg.members["a@b.com"] == "张三"
    assert cfg.members["lisi"] == "李四"
    assert len(cfg.repos) == 2
    assert cfg.repos[0].name == "repo1"
    assert cfg.repos[0].branches == ["main", "dev"]
    assert cfg.repos[1].branches == []   # 未配置 branches

def test_default_scoring():
    path = _write_tmp(VALID_YAML)
    cfg = load_config(path)
    os.unlink(path)
    assert cfg.scoring.commit_weight == 10
    assert cfg.scoring.lines_weight == 1

def test_custom_scoring():
    yaml_str = VALID_YAML + "\nscoring:\n  commit_weight: 5\n  lines_weight: 2\n"
    path = _write_tmp(yaml_str)
    cfg = load_config(path)
    os.unlink(path)
    assert cfg.scoring.commit_weight == 5
    assert cfg.scoring.lines_weight == 2

def test_missing_feishu_raises():
    bad = "members:\n  a: b\nrepos: []\n"
    path = _write_tmp(bad)
    with pytest.raises(KeyError):
        load_config(path)
    os.unlink(path)
