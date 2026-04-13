# git-reporter

每晚自动采集团队在多个 Git 仓库的 commit 记录，生成每日工作报告并推送到飞书群。

## 功能

- 支持多个 repo、每个 repo 可配置多个监控 branch
- 跨 repo / branch 按 commit hash 去重，同一个 commit 同步到多个分支只计一次
- 按成员归并 commit，git email 和 username 均可映射到真实姓名
- 自动识别 Conventional Commits 前缀（`feat` → 新功能、`fix` → 修复 等）
- 报告按贡献评分排序，标注 🥇🥈 Top 2 贡献者
- 支持每周汇总报告（`--weekly`）
- 支持生成本地 HTML 仪表盘，查看团队趋势、成员活跃度和 repo 覆盖情况
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
cd git-reporter
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

### 多分支去重说明

同一个 commit 经常被同步（cherry-pick / merge）到多个分支。git-reporter 会在汇总时按 commit hash 全局去重，同一个人的同一个 commit 无论出现在几个 repo/branch 中，只计一次。

## 使用

**手动运行（dry-run，不发送飞书）：**

```bash
python3 main.py config.yaml --dry-run
```

**指定日期：**

```bash
python3 main.py config.yaml 2026-03-29 --dry-run
```

**正式发送到飞书：**

```bash
python3 main.py config.yaml
```

**每周汇总报告：**

```bash
python3 main.py config.yaml --weekly
```

**生成本地仪表盘：**

```bash
python3 dashboard.py --config config.yaml
```

默认会生成 `dashboard.html` 并自动在浏览器中打开。可通过 `--days` 指定初始展示范围，通过 `--output` 指定输出文件路径；如需重新扫描 Git 历史并写入本地数据，可加 `--rescan`。

## 定时任务（macOS launchd）

推荐使用 launchd 而非 crontab，锁屏不影响执行。

创建 `~/Library/LaunchAgents/com.yourname.git-reporter.plist`：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.yourname.git-reporter</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/path/to/git-reporter/main.py</string>
        <string>/path/to/git-reporter/config.yaml</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>20</integer>
        <key>Minute</key>
        <integer>30</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/path/to/git-reporter/launchd.log</string>
    <key>StandardErrorPath</key>
    <string>/path/to/git-reporter/launchd.log</string>
</dict>
</plist>
```

注册：

```bash
launchctl load ~/Library/LaunchAgents/com.yourname.git-reporter.plist
```

验证是否运行：

```bash
launchctl list | grep git-reporter
```

## 项目结构

```
git-reporter/
├── config.py           # 配置加载
├── git_collector.py    # git log 采集与解析
├── report_builder.py   # 数据归并、跨 repo 去重、评分、排序
├── feishu_sender.py    # 飞书消息格式化与推送
├── data_store.py       # 历史数据存储
├── weekly_reporter.py  # 每周汇总报告
├── dashboard.py        # 本地 HTML 仪表盘生成与打开
├── ai_summarizer.py    # AI 总结预留接口（初期为空）
├── main.py             # 入口
├── config.yaml.example # 配置模板
└── tests/              # 单元测试
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
