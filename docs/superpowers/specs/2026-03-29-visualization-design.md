# Git Reporter Visualization Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 git_reporter 添加历史数据持久化、每周飞书周报、以及本地三 tab HTML 仪表盘，帮助团队了解成员工作状态、项目覆盖风险和效率趋势。

**Architecture:** 新增三个独立模块（`data_store.py` / `weekly_reporter.py` / `dashboard.py`），对现有日常流程改动最小（仅 `main.py` 末尾多一行保存快照）。仪表盘为纯静态 HTML，使用 Chart.js CDN，无需服务进程。

**Tech Stack:** Python 3.9+, SQLite (stdlib sqlite3), Chart.js 4.x (CDN), PyYAML, requests（已有依赖）

---

## 模块职责

### `data_store.py`

- `save_snapshot(report: dict, date: date) -> None`
  - 将 `build_report()` 返回的 report 写入 SQLite `git_reporter.db`
  - 表：`daily_snapshots(date TEXT, person TEXT, repo TEXT, commits INTEGER, lines_added INTEGER, lines_deleted INTEGER, files_changed INTEGER, messages TEXT)`
  - `messages` 存 JSON 数组字符串
  - 同一 (date, person, repo) 组合写入时先删后插（幂等）
- `query_range(start: date, end: date) -> list[dict]`
  - 返回 `[{date, person, repo, commits, lines_added, lines_deleted, files_changed, messages}, ...]`
  - 按 date ASC 排序
- DB 文件路径：与 `config.yaml` 同目录，固定名 `git_reporter.db`

### `weekly_reporter.py`

- `build_weekly_report(rows: list[dict], cfg: Config, week_start: date) -> dict`
  - 输入：`query_range` 返回的 7 天数据
  - 输出 dict，包含：
    - `week_label`：如 `"2026-W13（3/23–3/29）"`
    - `persons`：每人汇总（total_commits, total_lines_added, repos_active, vs_prev_week_pct）
    - `top_person`：commits 增幅最大的成员
    - `silent_persons`：连续 3 天以上无提交的成员列表
    - `backup_risks`：30天内仅 1 人有 commits 的 repo 列表（含该人姓名）
    - `team_momentum_pct`：本周总 commits vs 上周总 commits 的变化百分比
- `send_weekly_report(webhook_url: str, report: dict) -> None`
  - 格式化为飞书 `post` 富文本消息推送
  - 内容结构：
    ```
    📊 研发周报 · {week_label}
    团队总计：{total} commits {↑/↓}{pct}% vs 上周
    🔥 本周最强：{top_person}（{commits} commits）
    📉 需关注：{silent}（↓{pct}%，{n}天无提交）   ← 无则省略
    ⚠ 备份风险：{repo} 仅 {person} 1 人              ← 无则省略
    各成员：
      {name}  {commits} commits · +{lines}行 · {repos}个项目
      ...
    ```

### `dashboard.py`

CLI：`python3 dashboard.py [--days 30] [--rescan] [--from YYYY-MM-DD] [--config config.yaml]`

- 默认从 SQLite 读取，`--rescan` 时直接调 `collect_repo` 重扫 git history
- 生成单个 `dashboard.html` 文件（输出到项目目录）
- 自动用 `webbrowser.open()` 打开

**HTML 结构：**
- Tab 导航栏（固定顶部）：`📈 洞察` / `⏱ 时间线` / `👥 成员`
- 右侧：时间范围选择器 `7天 / 30天 / 90天`（切换后重新渲染图表）
- 图表库：Chart.js 4.x via CDN（`https://cdn.jsdelivr.net/npm/chart.js`）
- 所有数据 inline 嵌入 HTML 的 `<script>` 标签（JSON），无需服务端

**Tab 1 — 📈 洞察**

四张洞察卡片（横排）：
1. **备份风险**：列出所选时间范围内仅 1 人活跃的 repo（橙色警告）；无风险则显示"✅ 无风险"
2. **本周最强**：commits 总量最多的成员 + 较上期变化百分比
3. **需关注**：连续 ≥3 天无提交的成员；无则不显示此卡片
4. **团队动能**：本期 vs 上期总 commits 变化

下方：团队近 4 周总 commits 折线图

派生指标表格：

| 成员 | 平均 commit 大小（行）| 专注度（活跃 repo 数）| 一致性（活跃天/总天）|
|------|----------------------|----------------------|---------------------|

**Tab 2 — ⏱ 时间线**

- 堆叠柱状图（Chart.js `bar` stacked），x 轴为日期，每人一种颜色
- 成员过滤复选框（默认全选）
- 周末列自动用浅灰背景区分

**Tab 3 — 👥 成员**

上半部分：成员卡片列表
- 每张卡片：姓名、总 commits、总行数、活跃 repo 数、趋势箭头（vs 上期，绿↑/灰→/红↓）

下半部分：Repo × 人员覆盖矩阵
- 行 = repo，列 = 成员
- 格子内容 = commits 数；0 显示为 `—`
- 仅 1 人有 commits 的 repo 行标橙色 `⚠`

---

## `main.py` 改动

在 `send_report()` 调用之后（或 dry_run 分支之后）加一行：

```python
from data_store import save_snapshot
save_snapshot(report, target_date)
```

dry_run 时也保存数据（方便调试期间积累测试数据）。

---

## crontab 新增

`main.py` 新增 `--weekly` 标志，crontab 加一行：

```cron
# 每周一早 9:00 推送周报
0 9 * * 1 cd /Users/hypernode/Github/git_reporter && /usr/bin/python3 main.py --weekly >> /tmp/git_reporter_weekly.log 2>&1
```

`--weekly` 模式：查询过去 7 天 SQLite 数据，调用 `build_weekly_report` + `send_weekly_report`。

---

## 数据完整性

- `save_snapshot` 幂等：同日期重复运行不会产生重复数据
- `--rescan` 模式不依赖 SQLite，直接从 git history 构建数据用于渲染
- SQLite 文件加入 `.gitignore`

---

## 测试范围

- `data_store.py`：save + query 幂等性，空库查询，跨日期范围
- `weekly_reporter.py`：backup_risk 检测，silent_persons 检测，momentum 计算（正/负/零）
- `dashboard.py`：生成的 HTML 包含必要的 `<canvas>` 元素和 inline JSON 数据（不测视觉）
