# dashboard.py
import argparse
import json
import os
import webbrowser
from datetime import date, timedelta

from config import load_config
from data_store import query_range
from git_collector import collect_repo
from report_builder import build_report


def _build_all_data(rows: list[dict], persons: list[str]) -> dict:
    """将 query_range 返回的行转换为仪表盘所需的 JSON 数据结构。"""
    all_dates = sorted(set(r["date"] for r in rows))
    all_repos = sorted(set(r["repo"] for r in rows))

    timeline: dict[str, list[int]] = {p: [] for p in persons}
    for d in all_dates:
        day_rows = {(r["person"], r["repo"]): r for r in rows if r["date"] == d}
        for person in persons:
            total = sum(
                day_rows[(person, repo)]["commits"]
                for repo in all_repos
                if (person, repo) in day_rows
            )
            timeline[person].append(total)

    coverage: dict[str, dict[str, int]] = {p: {r: 0 for r in all_repos} for p in persons}
    for row in rows:
        if row["person"] in coverage and row["repo"] in coverage[row["person"]]:
            coverage[row["person"]][row["repo"]] += row["commits"]

    today = date.fromisoformat(all_dates[-1]) if all_dates else date.today()
    weekly_totals = []
    for w in range(8):
        w_end = today - timedelta(days=w * 7)
        w_start = w_end - timedelta(days=6)
        total = sum(
            r["commits"] for r in rows
            if w_start.isoformat() <= r["date"] <= w_end.isoformat()
        )
        weekly_totals.insert(0, {"label": w_start.strftime("W%V"), "total": total})

    return {
        "generated_at": date.today().isoformat(),
        "persons": persons,
        "repos": all_repos,
        "dates": all_dates,
        "timeline": timeline,
        "coverage": coverage,
        "rows": rows,
        "weekly_totals": weekly_totals,
    }


def generate_html(rows: list[dict], persons: list[str], initial_range: int = 30) -> str:
    """生成完整的自包含 HTML 字符串。rows 应包含至多 90 天数据，initial_range 设置初始显示范围。"""
    data = _build_all_data(rows, persons)
    data_json = json.dumps(data, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<title>Git Reporter Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#0d1117;color:#e6edf3;min-height:100vh}}
  #header{{display:flex;align-items:center;justify-content:space-between;padding:16px 24px;border-bottom:1px solid #21262d}}
  h1{{font-size:16px;color:#e6edf3}}
  #range-btns button,#tab-btns button{{background:none;border:1px solid #30363d;color:#8b949e;padding:4px 12px;border-radius:6px;cursor:pointer;font-size:13px}}
  #range-btns button.active,#tab-btns button.active{{background:#1f6feb;border-color:#1f6feb;color:#fff}}
  #tab-btns{{display:flex;gap:4px;padding:12px 24px;border-bottom:1px solid #21262d}}
  .tab-content{{display:none;padding:20px 24px}}
  .tab-content.active{{display:block}}
  .cards{{display:flex;gap:12px;margin-bottom:20px;flex-wrap:wrap}}
  .card{{flex:1;min-width:180px;background:#161b22;border:1px solid #30363d;border-radius:8px;padding:14px}}
  .card-label{{font-size:11px;color:#8b949e;margin-bottom:4px}}
  .card-value{{font-size:20px;font-weight:700}}
  .card-sub{{font-size:11px;color:#8b949e;margin-top:2px}}
  .card.risk{{border-color:#d29922;background:#272115}}
  .card.positive{{border-color:#238636;background:#0d1117}}
  .card.warning{{border-color:#8957e5;background:#1a1329}}
  canvas{{max-height:260px}}
  table{{width:100%;border-collapse:collapse;font-size:13px}}
  th,td{{padding:8px 12px;border:1px solid #21262d;text-align:left}}
  th{{background:#161b22;color:#8b949e;font-weight:500}}
  td.risk-cell{{background:#27211577;color:#d29922;font-weight:600}}
  td.zero{{color:#484f58}}
  .section-title{{font-size:12px;text-transform:uppercase;letter-spacing:1px;color:#8b949e;margin-bottom:12px;margin-top:20px}}
  .person-cards{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px}}
  .person-card{{flex:1;min-width:200px;background:#161b22;border:1px solid #30363d;border-radius:8px;padding:14px}}
  .person-name{{font-size:15px;font-weight:600;margin-bottom:6px}}
  .person-stat{{font-size:12px;color:#8b949e;line-height:1.8}}
  .trend-up{{color:#3fb950}}.trend-down{{color:#f85149}}.trend-flat{{color:#8b949e}}
  .filter-row{{display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap}}
  .filter-btn{{background:#161b22;border:1px solid #30363d;color:#e6edf3;padding:3px 10px;border-radius:4px;cursor:pointer;font-size:12px}}
  .filter-btn.active{{background:#1f6feb;border-color:#1f6feb}}
</style>
</head>
<body>
<div id="header">
  <h1>📊 Git Reporter Dashboard</h1>
  <div id="range-btns">
    <button onclick="setRange(7)">7天</button>
    <button onclick="setRange(30)" class="active">30天</button>
    <button onclick="setRange(90)">90天</button>
  </div>
</div>
<div id="tab-btns">
  <button class="active" onclick="showTab('insights',this)">📈 洞察</button>
  <button onclick="showTab('timeline',this)">⏱ 时间线</button>
  <button onclick="showTab('members',this)">👥 成员</button>
</div>

<div id="tab-insights" class="tab-content active">
  <div class="cards" id="insight-cards"></div>
  <div class="section-title">团队动能（近8周）</div>
  <canvas id="momentum-chart"></canvas>
  <div class="section-title" style="margin-top:24px">成员派生指标</div>
  <table id="derived-metrics"></table>
</div>

<div id="tab-timeline" class="tab-content">
  <div class="filter-row" id="person-filter"></div>
  <canvas id="timeline-chart"></canvas>
</div>

<div id="tab-members" class="tab-content">
  <div class="person-cards" id="person-cards"></div>
  <div class="section-title">Repo × 人员覆盖矩阵（commits 数）</div>
  <table id="coverage-matrix"></table>
</div>

<script>
const ALL_DATA = {data_json};
const COLORS = ["#e94560","#1f6feb","#8957e5","#3fb950","#f0883e","#58a6ff","#bc8cff","#ffa657"];

let currentRange = {initial_range};
let timelineChart = null;
let momentumChart = null;
let activePersons = new Set(ALL_DATA.persons);

function getFilteredRows(days) {{
  const cutoff = new Date(ALL_DATA.generated_at);
  cutoff.setDate(cutoff.getDate() - days + 1);
  const cutoffStr = cutoff.toISOString().slice(0, 10);
  return ALL_DATA.rows.filter(r => r.date >= cutoffStr);
}}

function getFilteredDates(days) {{
  const rows = getFilteredRows(days);
  return [...new Set(rows.map(r => r.date))].sort();
}}

function setRange(days) {{
  currentRange = days;
  document.querySelectorAll("#range-btns button").forEach((b, i) => {{
    b.classList.toggle("active", [7,30,90][i] === days);
  }});
  renderAll();
}}

function showTab(name, btn) {{
  document.querySelectorAll(".tab-content").forEach(el => el.classList.remove("active"));
  document.getElementById("tab-" + name).classList.add("active");
  document.querySelectorAll("#tab-btns button").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
}}

function renderInsights() {{
  const rows = getFilteredRows(currentRange);
  const persons = ALL_DATA.persons;

  const personCommits = {{}};
  const personLines = {{}};
  const personRepos = {{}};
  persons.forEach(p => {{ personCommits[p] = 0; personLines[p] = 0; personRepos[p] = new Set(); }});
  rows.forEach(r => {{
    personCommits[r.person] = (personCommits[r.person] || 0) + r.commits;
    personLines[r.person] = (personLines[r.person] || 0) + r.lines_added;
    if (r.commits > 0) (personRepos[r.person] = personRepos[r.person] || new Set()).add(r.repo);
  }});

  const repoPeople = {{}};
  rows.forEach(r => {{ if (r.commits > 0) {{ repoPeople[r.repo] = repoPeople[r.repo] || new Set(); repoPeople[r.repo].add(r.person); }} }});
  const risks = Object.entries(repoPeople).filter(([,v]) => v.size === 1).map(([repo,v]) => ({{repo, person: [...v][0]}}));

  const topPerson = persons.reduce((a, b) => personCommits[a] >= personCommits[b] ? a : b, persons[0]);
  const totalCommits = Object.values(personCommits).reduce((a, b) => a + b, 0);

  const cards = document.getElementById("insight-cards");
  cards.innerHTML = "";

  const riskCard = risks.length > 0
    ? `<div class="card risk"><div class="card-label">⚠ 备份风险</div><div class="card-value" style="font-size:15px">${{risks.map(r => r.repo).join(", ")}}</div><div class="card-sub">仅 ${{risks.map(r=>r.person).join("/")}}</div></div>`
    : `<div class="card positive"><div class="card-label">✅ 备份覆盖</div><div class="card-value" style="font-size:15px">无风险</div><div class="card-sub">所有 repo 多人覆盖</div></div>`;
  cards.innerHTML += riskCard;

  if (topPerson && personCommits[topPerson] > 0) {{
    cards.innerHTML += `<div class="card positive"><div class="card-label">🔥 最强贡献</div><div class="card-value">${{topPerson}}</div><div class="card-sub">${{personCommits[topPerson]}} commits</div></div>`;
  }}

  const silent = persons.filter(p => personCommits[p] === 0);
  if (silent.length > 0) {{
    cards.innerHTML += `<div class="card warning"><div class="card-label">📉 无提交</div><div class="card-value" style="font-size:15px">${{silent.join(", ")}}</div><div class="card-sub">本周期内</div></div>`;
  }}

  cards.innerHTML += `<div class="card"><div class="card-label">📊 周期总量</div><div class="card-value">${{totalCommits}}</div><div class="card-sub">过去 ${{currentRange}} 天</div></div>`;

  const table = document.getElementById("derived-metrics");
  const rows2 = `<tr><th>成员</th><th>总 commits</th><th>平均每 commit 行数</th><th>活跃 repo 数</th></tr>` +
    persons.map(p => {{
      const commits = personCommits[p] || 0;
      const lines = personLines[p] || 0;
      const avgLines = commits > 0 ? Math.round(lines / commits) : 0;
      const repoCount = (personRepos[p] || new Set()).size;
      return `<tr><td>${{p}}</td><td>${{commits}}</td><td>${{avgLines}}</td><td>${{repoCount}}</td></tr>`;
    }}).join("");
  table.innerHTML = rows2;

  const wt = ALL_DATA.weekly_totals;
  if (momentumChart) momentumChart.destroy();
  const mCtx = document.getElementById("momentum-chart").getContext("2d");
  momentumChart = new Chart(mCtx, {{
    type: "bar",
    data: {{
      labels: wt.map(w => w.label),
      datasets: [{{ label: "团队总 commits", data: wt.map(w => w.total), backgroundColor: "#1f6feb", borderRadius: 4 }}]
    }},
    options: {{ plugins: {{ legend: {{ display: false }} }}, scales: {{ x: {{ ticks: {{ color: "#8b949e" }} }}, y: {{ ticks: {{ color: "#8b949e" }}, grid: {{ color: "#21262d" }} }} }} }}
  }});
}}

function renderTimeline() {{
  const dates = getFilteredDates(currentRange);
  const rows = getFilteredRows(currentRange);

  const filterDiv = document.getElementById("person-filter");
  filterDiv.innerHTML = ALL_DATA.persons.map((p, i) =>
    `<button class="filter-btn ${{activePersons.has(p)?'active':''}}" onclick="togglePerson('${{p}}')" style="border-color:${{COLORS[i%COLORS.length]}}">${{p}}</button>`
  ).join("");

  const datasets = ALL_DATA.persons.filter(p => activePersons.has(p)).map((p, i) => {{
    const data = dates.map(d => {{
      const dayRows = rows.filter(r => r.date === d && r.person === p);
      return dayRows.reduce((sum, r) => sum + r.commits, 0);
    }});
    return {{ label: p, data, backgroundColor: COLORS[i % COLORS.length], stack: "stack" }};
  }});

  const weekendPlugin = {{
    id: "weekends",
    beforeDraw(chart) {{
      const {{ctx, chartArea, scales}} = chart;
      if (!chartArea) return;
      ctx.save();
      dates.forEach((d, i) => {{
        const dow = new Date(d).getUTCDay();
        if (dow === 0 || dow === 6) {{
          const x = scales.x.getPixelForValue(i);
          const bw = scales.x.width / dates.length;
          ctx.fillStyle = "rgba(255,255,255,0.03)";
          ctx.fillRect(x - bw / 2, chartArea.top, bw, chartArea.height);
        }}
      }});
      ctx.restore();
    }}
  }};

  if (timelineChart) timelineChart.destroy();
  const ctx = document.getElementById("timeline-chart").getContext("2d");
  timelineChart = new Chart(ctx, {{
    type: "bar",
    plugins: [weekendPlugin],
    data: {{ labels: dates, datasets }},
    options: {{
      plugins: {{ legend: {{ labels: {{ color: "#8b949e" }} }} }},
      scales: {{
        x: {{ stacked: true, ticks: {{ color: "#8b949e", maxRotation: 45 }} }},
        y: {{ stacked: true, ticks: {{ color: "#8b949e" }}, grid: {{ color: "#21262d" }} }}
      }}
    }}
  }});
}}

function togglePerson(name) {{
  if (activePersons.has(name)) {{ if (activePersons.size > 1) activePersons.delete(name); }}
  else activePersons.add(name);
  renderTimeline();
}}

function renderMembers() {{
  const rows = getFilteredRows(currentRange);
  const allRows90 = ALL_DATA.rows;
  const cutoff = new Date(ALL_DATA.generated_at);
  cutoff.setDate(cutoff.getDate() - currentRange + 1);
  const prevCutoff = new Date(cutoff);
  prevCutoff.setDate(prevCutoff.getDate() - currentRange);
  const cutoffStr = cutoff.toISOString().slice(0, 10);
  const prevStr = prevCutoff.toISOString().slice(0, 10);
  const prevPeriodRows = allRows90.filter(r => r.date >= prevStr && r.date < cutoffStr);

  const personCommits = {{}};
  const personLines = {{}};
  const personRepos = {{}};
  ALL_DATA.persons.forEach(p => {{ personCommits[p] = 0; personLines[p] = 0; personRepos[p] = new Set(); }});
  rows.forEach(r => {{
    personCommits[r.person] = (personCommits[r.person]||0) + r.commits;
    personLines[r.person] = (personLines[r.person]||0) + r.lines_added;
    if (r.commits>0) personRepos[r.person].add(r.repo);
  }});

  const prevCommits = {{}};
  prevPeriodRows.forEach(r => {{ prevCommits[r.person] = (prevCommits[r.person]||0) + r.commits; }});

  const cardsDiv = document.getElementById("person-cards");
  cardsDiv.innerHTML = ALL_DATA.persons.map((p, i) => {{
    const c = personCommits[p]||0, l = personLines[p]||0, rv = (personRepos[p]||new Set()).size;
    const prev = prevCommits[p]||0;
    let trendHtml = "";
    if (prev > 0) {{
      const pct = Math.round((c - prev) / prev * 100);
      const cls = pct > 0 ? "trend-up" : pct < 0 ? "trend-down" : "trend-flat";
      trendHtml = `<span class="${{cls}}">${{pct > 0 ? "↑" : pct < 0 ? "↓" : "→"}}${{Math.abs(pct)}}% vs 上期</span>`;
    }}
    return `<div class="person-card" style="border-left:3px solid ${{COLORS[i%COLORS.length]}}">
      <div class="person-name">${{p}}</div>
      <div class="person-stat">${{c}} commits · +${{l.toLocaleString()}} 行 · ${{rv}} repos</div>
      ${{trendHtml}}
    </div>`;
  }}).join("");

  const repos = ALL_DATA.repos;
  const repoPeople = {{}};
  rows.forEach(r => {{
    if (!repoPeople[r.repo]) repoPeople[r.repo] = {{}};
    repoPeople[r.repo][r.person] = (repoPeople[r.repo][r.person]||0) + r.commits;
  }});

  const matrix = document.getElementById("coverage-matrix");
  const header = `<tr><th>Repo</th>${{ALL_DATA.persons.map(p=>`<th>${{p}}</th>`).join("")}}</tr>`;
  const bodyRows = repos.map(repo => {{
    const isSingle = ALL_DATA.persons.filter(p => (repoPeople[repo]||{{}})[p]>0).length === 1;
    const repoLabel = isSingle ? `⚠ ${{repo}}` : repo;
    const cells = ALL_DATA.persons.map(p => {{
      const v = (repoPeople[repo]||{{}})[p]||0;
      const cls = v===0 ? "zero" : isSingle ? "risk-cell" : "";
      return `<td class="${{cls}}">${{v===0?"—":v}}</td>`;
    }}).join("");
    return `<tr><td${{isSingle?' style="color:#d29922"':''}}>${{repoLabel}}</td>${{cells}}</tr>`;
  }}).join("");
  matrix.innerHTML = header + bodyRows;
}}

function renderAll() {{
  renderInsights();
  renderTimeline();
  renderMembers();
}}

renderAll();
</script>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(description="生成 Git Reporter 仪表盘")
    parser.add_argument("--days", type=int, default=30, help="数据天数（默认 30）")
    parser.add_argument("--config", default="config.yaml", help="配置文件路径")
    parser.add_argument("--rescan", action="store_true", help="重新从 git history 扫描数据")
    parser.add_argument("--output", default="dashboard.html", help="输出 HTML 路径")
    args = parser.parse_args()

    cfg = load_config(args.config)
    persons = list(cfg.members.values())
    today = date.today()
    start = today - timedelta(days=args.days - 1)

    if args.rescan:
        from data_store import save_snapshot as _save
        print(f"Rescanning {args.days} days of git history...")
        for i in range(args.days):
            d = start + timedelta(days=i)
            repo_commits = {}
            for repo in cfg.repos:
                commits, _ = collect_repo(repo.path, repo.branches, d, remote=repo.remote)
                repo_commits[repo.name] = commits
            report = build_report(repo_commits, cfg, d)
            _save(report, d)
            print(f"  {d.isoformat()} ✓")

    # 始终嵌入最多 90 天数据，时间范围选择器在前端过滤
    embed_start = today - timedelta(days=89)
    rows = query_range(embed_start, today)
    html = generate_html(rows, persons, initial_range=args.days)

    output_path = os.path.abspath(args.output)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Dashboard generated: {output_path}")
    webbrowser.open(f"file://{output_path}")


if __name__ == "__main__":
    main()
