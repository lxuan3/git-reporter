# git-reporter

每晚自动采集团队在多个 Git 仓库的 commit 记录，生成每日工作报告并推送到飞书群。

## 功能

- 支持多个 repo、每个 repo 可配置多个监控 branch
- 按成员归并 commit，git email 和 username 均可映射到真实姓名
- 自动识别 Conventional Commits 前缀（`feat` → 新功能、`fix` → 修复 等）
- 报告按贡献评分排序，标注 🥇🥈 Top 2 贡献者
- 每晚 20:30 定时推送到飞书群机器人
- 预留 AI 总结接口，初期不启用

## 报告示例

```
📊 每日研发工作报告 · 2026-03-29

━━━━━━━━━━━━━━━━━━━━
👤 张三
  • openclaw-dashboard  3 commits | +120/-45 行 | 5 个文件
    - [新功能] 新增用户列表分页
    - [修复] 修复登录态过期问题
    - [维护] 更新依赖版本

👤 李四
  • service-manager  2 commits | +80/-20 行 | 3 个文件
    - [重构] 优化服务注册逻辑
    - [新功能] 实现数据导出功能

━━━━━━━━━━━━━━━━━━━━
👤 王五（今日无提交）

━━━━━━━━━━━━━━━━━━━━
汇总：今日活跃 2/3 人 | 总计 5 commits | +200/-65 行
🥇 张三（3 commits · +120 行）
🥈 李四（2 commits · +80 行）
```

## 安装

```bash
git clone <repo-url>
cd git_reporter
pip3 install -r requirements.txt
```

## 配置

```bash
cp config.yaml.example config.yaml
```

编辑 `config.yaml`：

```yaml
feishu:
  webhook_url: "https://open.feishu.cn/open-apis/bot/v2/hook/YOUR_TOKEN"

scoring:
  commit_weight: 10   # 综合评分 = commits × commit_weight + lines_added × lines_weight
  lines_weight: 1

members:
  "zhangsan@example.com": "张三"   # 优先匹配 email
  "lisi": "李四"                    # 也支持 git username

repos:
  - name: "openclaw-dashboard"
    path: "/path/to/openclaw-dashboard"
    branches: ["main", "develop"]   # 不填则使用当前 checkout 的 branch
  - name: "service-manager"
    path: "/path/to/service-manager"
```

## 使用

**手动运行（测试用）：**

```bash
# 运行今天的报告
python3 main.py config.yaml

# 指定日期
python3 main.py config.yaml 2026-03-29
```

**定时任务（每晚 20:30）：**

```bash
crontab -e
```

添加：

```cron
30 20 * * * cd /path/to/git_reporter && /usr/bin/python3 main.py config.yaml >> /tmp/git_reporter.log 2>&1
```

## 项目结构

```
git_reporter/
├── config.py           # 配置加载
├── git_collector.py    # git log 采集与解析
├── report_builder.py   # 数据归并、评分、排序
├── feishu_sender.py    # 飞书消息格式化与推送
├── ai_summarizer.py    # AI 总结预留接口（初期为空）
├── main.py             # 入口
├── config.yaml.example # 配置模板
└── tests/              # 30 个单元测试
```

## 测试

```bash
python3 -m pytest tests/ -v
```

## Commit 前缀对照

| 前缀 | 显示标签 |
|------|---------|
| `feat` | 新功能 |
| `fix` | 修复 |
| `chore` | 维护 |
| `refactor` | 重构 |
| `docs` | 文档 |
| `style` | 样式 |
| `test` | 测试 |
| `perf` | 性能优化 |
| `revert` | 回滚 |

## 扩展 AI 总结

实现 `ai_summarizer.py` 中的 `summarize()` 函数即可启用 AI 总结，无需修改其他模块：

```python
# ai_summarizer.py
def summarize(person_data) -> str | None:
    # 接入 Claude / OpenAI 等
    return "今日主要完成了用户模块的功能迭代..."
```
