#!/usr/bin/env python3
"""
GitHub istatistik kartlarını (overview, streak, langs, activity) GitHub'ın kendi
GraphQL API'sinden veri çekerek, "Sunset Forge" (altın/turuncu/mercan) temalı,
tamamen özgün SVG kartlar olarak üretir.

Hiçbir dış render servisine (vercel.app, demolab.com vb.) bağımlı DEĞİLDİR.
Tek bağımlılık: api.github.com (GITHUB_TOKEN veya GH_PAT ile).

Güvenlik: Herhangi bir adımda hata olursa script staging dizininde durur,
assets/cache/ altındaki ESKİ dosyalara DOKUNMAZ ve non-zero exit code ile çıkar.
Böylece bir API hatası profildeki kartları asla kırık göstermez — en kötü
ihtimalle bir önceki (geçerli) sürüm görünmeye devam eder.

Kullanım:
    GH_USERNAME=Mhuseyin7 python3 scripts/generate_stats.py assets/cache
"""
import json
import os
import re
import sys
import urllib.request
from datetime import date
from xml.sax.saxutils import escape as xml_escape
import xml.dom.minidom as minidom

USERNAME = os.environ.get("GH_USERNAME", "Mhuseyin7")
TOKEN = os.environ.get("GH_PAT") or os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
OUT_DIR = sys.argv[1] if len(sys.argv) > 1 else "assets/cache"

# ── "Enterprise Minimal" teması: tek aksan disiplini, hairline sınırlar ──
# (Değişken adları geriye dönük uyum için korunur.)
ACCENT = "#60a5fa"
PURPLE, INDIGO, CYAN = ACCENT, ACCENT, ACCENT
BG1, BG2 = "#0f172a", "#0f172a"
BORDER = "#334155"
TEXT, TEXT_DIM, TEXT_META = "#f8fafc", "#cbd5e1", "#94a3b8"

QUERY = """
query($login: String!) {
  user(login: $login) {
    followers { totalCount }
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC) {
      totalCount
      nodes {
        stargazerCount
        languages(first: 8, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      totalPullRequestReviewContributions
      restrictedContributionsCount
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""


# ───────────────────────── veri katmanı ─────────────────────────

def fetch_user_json():
    if not TOKEN:
        raise RuntimeError("GH_TOKEN / GITHUB_TOKEN bulunamadı (env)")
    body = json.dumps({"query": QUERY, "variables": {"login": USERNAME}}).encode("utf-8")
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": f"{USERNAME}-readme-stats",
            "Accept": "application/vnd.github+json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if "errors" in payload:
        raise RuntimeError(f"GraphQL hata: {payload['errors']}")
    user = payload["data"]["user"]
    if user is None:
        raise RuntimeError(f"Kullanıcı bulunamadı: {USERNAME}")
    return user


def compute_stats(user: dict) -> dict:
    repos = user["repositories"]["nodes"]
    total_repos = user["repositories"]["totalCount"]
    total_stars = sum(r["stargazerCount"] for r in repos)
    followers = user["followers"]["totalCount"]

    lang_size, lang_color = {}, {}
    for r in repos:
        for edge in r["languages"]["edges"]:
            name = edge["node"]["name"]
            lang_size[name] = lang_size.get(name, 0) + edge["size"]
            lang_color[name] = edge["node"].get("color") or PURPLE

    contribs = user["contributionsCollection"]
    total_commits = contribs["totalCommitContributions"]
    total_prs = contribs["totalPullRequestContributions"]
    total_issues = contribs["totalIssueContributions"]
    total_reviews = contribs["totalPullRequestReviewContributions"]
    total_restricted = contribs["restrictedContributionsCount"]

    cal = contribs["contributionCalendar"]
    total_contribs = cal["totalContributions"]
    days = []
    for week in cal["weeks"]:
        for d in week["contributionDays"]:
            days.append((d["date"], d["contributionCount"]))
    days.sort(key=lambda x: x[0])

    longest = run = 0
    for _, count in days:
        if count > 0:
            run += 1
            longest = max(longest, run)
        else:
            run = 0

    today_iso = date.today().isoformat()
    current = 0
    for d, count in reversed(days):
        if d == today_iso and count == 0:
            continue
        if count > 0:
            current += 1
        else:
            break

    # Weekly buckets (kept for backward compatibility)
    weekly, bucket = [], []
    for _, count in days:
        bucket.append(count)
        if len(bucket) == 7:
            weekly.append(sum(bucket))
            bucket = []
    if bucket:
        weekly.append(sum(bucket))
    weekly = weekly[-26:] if len(weekly) > 26 else weekly
    if not weekly:
        weekly = [0]

    total_lang_size = sum(lang_size.values()) or 1
    top_langs = sorted(lang_size.items(), key=lambda kv: -kv[1])[:6]

    # Daily heatmap grid: last N complete weeks aligned to Sunday-start (GitHub style)
    HEATMAP_WEEKS = 26
    heatmap_cells = days[-(HEATMAP_WEEKS * 7):] if len(days) >= HEATMAP_WEEKS * 7 else days
    max_day = max((c for _, c in heatmap_cells), default=0) or 1
    active_days = sum(1 for _, c in heatmap_cells if c > 0)

    return {
        "total_repos": total_repos,
        "total_stars": total_stars,
        "followers": followers,
        "total_contribs": total_contribs,
        "total_commits": total_commits,
        "total_prs": total_prs,
        "total_issues": total_issues,
        "total_reviews": total_reviews,
        "total_restricted": total_restricted,
        "current_streak": current,
        "longest_streak": longest,
        "weekly": weekly,
        "heatmap": heatmap_cells,
        "heatmap_max": max_day,
        "active_days": active_days,
        "top_langs": [(n, s / total_lang_size, lang_color.get(n, PURPLE)) for n, s in top_langs],
        "first_date": days[0][0] if days else "",
        "last_date": days[-1][0] if days else "",
    }


# ───────────────────────── SVG katmanı ─────────────────────────

SANS = "'Inter', 'Segoe UI', Arial, sans-serif"
MONO = "'JetBrains Mono', Consolas, monospace"


def shell(w, h, body, title=""):
    corner = (
        f'<text x="{w - 20}" y="26" text-anchor="end" font-family="{MONO}" '
        f'font-size="10.5" fill="{TEXT_META}" letter-spacing="2.4">{xml_escape(title)}</text>'
        if title else ""
    )
    return f'''<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid meet" fill="none" xmlns="http://www.w3.org/2000/svg">
  <rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="12" fill="{BG1}" stroke="{BORDER}" stroke-width="1"/>
  <rect x="0" y="12" width="2" height="{h - 24}" fill="{ACCENT}" opacity="0.6">
    <animate attributeName="opacity" values="0.5;0.9;0.5" dur="4s" repeatCount="indefinite"/>
  </rect>
  {corner}
  {body}
</svg>'''


def overview_svg(s):
    w, h = 420, 260
    blocks = [
        (str(s["total_contribs"]), "CONTRIBS / 1Y"),
        (str(s["total_commits"]), "COMMITS / 1Y"),
        (str(s["total_prs"]), "PULL REQUESTS"),
        (str(s["total_issues"]), "ISSUES OPENED"),
        (str(s["total_repos"]), "REPOSITORIES"),
        (str(s["total_stars"]), "STARS"),
    ]
    col_w = w / 2
    grid_top = 44
    row_h = (h - grid_top - 20) / 3  # 3 rows
    items = []
    for i, (value, label) in enumerate(blocks):
        col, row = i % 2, i // 2
        cx = col_w * col + col_w / 2
        cy = grid_top + row_h * row + row_h / 2
        delay = 0.1 + i * 0.12
        items.append(f'''
    <g opacity="0">
      <animate attributeName="opacity" from="0" to="1" dur="0.6s" begin="{delay:.2f}s" fill="freeze"/>
      <text x="{cx}" y="{cy - 2}" text-anchor="middle" font-family="{SANS}" font-size="28" font-weight="600" fill="{TEXT}" letter-spacing="-0.6">{xml_escape(value)}</text>
      <text x="{cx}" y="{cy + 20}" text-anchor="middle" font-family="{MONO}" font-size="9.5" fill="{TEXT_META}" letter-spacing="0.24em">{xml_escape(label)}</text>
    </g>''')
    # inner grid lines
    items.append(f'<line x1="{col_w}" y1="{grid_top + 6}" x2="{col_w}" y2="{h - 20}" stroke="{BORDER}" stroke-width="1"/>')
    for r in range(1, 3):
        y = grid_top + row_h * r
        items.append(f'<line x1="24" y1="{y}" x2="{w - 24}" y2="{y}" stroke="{BORDER}" stroke-width="1"/>')
    return shell(w, h, "\n".join(items), title="OVERVIEW")


def streak_svg(s):
    w, h = 420, 260
    active = s.get("active_days", 0)
    body = f'''
  <g opacity="0">
    <animate attributeName="opacity" from="0" to="1" dur="0.6s" begin="0.1s" fill="freeze"/>
    <text x="30" y="60" font-family="{MONO}" font-size="9.5" fill="{TEXT_META}" letter-spacing="0.24em">CURRENT STREAK</text>
    <text x="30" y="108" font-family="{SANS}" font-size="52" font-weight="600" fill="{TEXT}" letter-spacing="-1.4">{s['current_streak']}</text>
    <text x="30" y="128" font-family="{MONO}" font-size="10" fill="{TEXT_DIM}" letter-spacing="0.06em">days · active</text>
  </g>

  <line x1="{w/2}" y1="44" x2="{w/2}" y2="{h/2 + 14}" stroke="{BORDER}" stroke-width="1"/>

  <g opacity="0">
    <animate attributeName="opacity" from="0" to="1" dur="0.6s" begin="0.25s" fill="freeze"/>
    <text x="240" y="60" font-family="{MONO}" font-size="9.5" fill="{TEXT_META}" letter-spacing="0.24em">LONGEST STREAK</text>
    <text x="240" y="108" font-family="{SANS}" font-size="52" font-weight="600" fill="{TEXT}" letter-spacing="-1.4">{s['longest_streak']}</text>
    <text x="240" y="128" font-family="{MONO}" font-size="10" fill="{TEXT_DIM}" letter-spacing="0.06em">days · record</text>
  </g>

  <line x1="24" y1="{h/2 + 22}" x2="{w - 24}" y2="{h/2 + 22}" stroke="{BORDER}" stroke-width="1"/>

  <g opacity="0">
    <animate attributeName="opacity" from="0" to="1" dur="0.6s" begin="0.4s" fill="freeze"/>
    <text x="30" y="{h/2 + 54}" font-family="{MONO}" font-size="9.5" fill="{TEXT_META}" letter-spacing="0.24em">REVIEWS / 1Y</text>
    <text x="30" y="{h/2 + 92}" font-family="{SANS}" font-size="34" font-weight="600" fill="{TEXT}" letter-spacing="-0.8">{s['total_reviews']}</text>
  </g>

  <g opacity="0">
    <animate attributeName="opacity" from="0" to="1" dur="0.6s" begin="0.55s" fill="freeze"/>
    <text x="240" y="{h/2 + 54}" font-family="{MONO}" font-size="9.5" fill="{TEXT_META}" letter-spacing="0.24em">ACTIVE DAYS</text>
    <text x="240" y="{h/2 + 92}" font-family="{SANS}" font-size="34" font-weight="600" fill="{TEXT}" letter-spacing="-0.8">{active}</text>
  </g>
'''
    return shell(w, h, body, title="STREAK")


def langs_svg(s):
    langs = s["top_langs"]
    w = 880
    row_h, top_pad = 34, 60
    h = top_pad + row_h * max(len(langs), 1) + 20
    bar_x = 200
    bar_max_w = w - bar_x - 90
    rows = []
    if langs:
        for i, (name, pct, color) in enumerate(langs):
            y = top_pad + i * row_h
            bw = max(bar_max_w * pct, 4)
            safe_color = color if re.match(r"^#[0-9a-fA-F]{6}$", color or "") else ACCENT
            delay = 0.1 + i * 0.1
            rows.append(f'''
    <g opacity="0">
      <animate attributeName="opacity" from="0" to="1" dur="0.4s" begin="{delay:.2f}s" fill="freeze"/>
      <text x="24" y="{y + 12}" font-family="{SANS}" font-size="13" fill="{TEXT}">{xml_escape(name)}</text>
      <text x="{bar_x + bar_max_w + 14}" y="{y + 12}" font-family="{MONO}" font-size="11.5" fill="{TEXT_DIM}">{pct * 100:.1f}%</text>
    </g>
    <rect x="{bar_x}" y="{y + 4}" width="{bar_max_w}" height="4" rx="2" fill="{BORDER}"/>
    <rect x="{bar_x}" y="{y + 4}" width="0" height="4" rx="2" fill="{safe_color}">
      <animate attributeName="width" from="0" to="{bw:.1f}" dur="0.9s" begin="{delay + 0.15:.2f}s" fill="freeze" calcMode="spline" keySplines="0.4 0 0.2 1" keyTimes="0;1"/>
    </rect>''')
    else:
        rows.append(f'<text x="{w/2}" y="{h/2}" text-anchor="middle" fill="{TEXT_DIM}" font-family="{SANS}" font-size="13">No language data yet</text>')
    return shell(w, h, "\n".join(rows), title="LANGUAGES")


def _heatmap_color(count, max_v):
    """5-step opacity ramp on ACCENT — GitHub-style intensity bucketing."""
    if count <= 0:
        return f'{ACCENT}" fill-opacity="0.06'
    q = count / max_v if max_v else 0
    if q < 0.20:
        return f'{ACCENT}" fill-opacity="0.25'
    if q < 0.45:
        return f'{ACCENT}" fill-opacity="0.45'
    if q < 0.70:
        return f'{ACCENT}" fill-opacity="0.70'
    return f'{ACCENT}" fill-opacity="1'


def activity_svg(s):
    """GitHub-style contribution heatmap — 7 rows × N weeks grid.
    Cells colored by daily contribution intensity. An "MK" glyph overlay
    is painted on top so the wall spells out the initials in bright blue
    while the underlying real data stays readable in the empty cells."""
    cells = s.get("heatmap") or []
    max_v = s.get("heatmap_max") or 1
    active = s.get("active_days", 0)
    weeks = []
    week = []
    for i, (d, c) in enumerate(cells):
        week.append(c)
        if len(week) == 7:
            weeks.append(week)
            week = []
    if week:
        weeks.append(week + [0] * (7 - len(week)))

    n_weeks = len(weeks) or 1
    cell, gap = 12, 3
    grid_w = n_weeks * (cell + gap) - gap
    grid_h = 7 * (cell + gap) - gap
    w = 880
    pad_l = (w - grid_w) // 2
    pad_t = 68
    h = pad_t + grid_h + 60

    # Cells with wave fade-in (column-by-column left→right).
    rects = []
    for wi, wk in enumerate(weeks):
        delay = 0.1 + wi * 0.025
        for di, count in enumerate(wk):
            x = pad_l + wi * (cell + gap)
            y = pad_t + di * (cell + gap)
            style = _heatmap_color(count, max_v)
            rects.append(
                f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2.5" fill="{style}" opacity="0">'
                f'<animate attributeName="opacity" from="0" to="1" dur="0.5s" begin="{delay:.2f}s" fill="freeze"/>'
                f'</rect>'
            )
    cells_svg = "\n  ".join(rects)

    # "MK" glyph overlay — commit-graph spells out the initials.
    # Each pattern is 5 cols × 7 rows; a 2-col gap sits between them.
    M_PATTERN = [
        [1,0,0,0,1],
        [1,1,0,1,1],
        [1,0,1,0,1],
        [1,0,0,0,1],
        [1,0,0,0,1],
        [1,0,0,0,1],
        [1,0,0,0,1],
    ]
    K_PATTERN = [
        [1,0,0,0,1],
        [1,0,0,1,0],
        [1,0,1,0,0],
        [1,1,0,0,0],
        [1,0,1,0,0],
        [1,0,0,1,0],
        [1,0,0,0,1],
    ]
    overlay = []
    mk_width = 12  # 5 + 2 gap + 5
    mk_start = max(0, (n_weeks - mk_width) // 2)
    for ci, char_pattern in ((0, M_PATTERN), (7, K_PATTERN)):
        for row_idx, row in enumerate(char_pattern):
            for col_idx, val in enumerate(row):
                if not val:
                    continue
                wcol = mk_start + ci + col_idx
                if wcol >= n_weeks:
                    continue
                x = pad_l + wcol * (cell + gap)
                y = pad_t + row_idx * (cell + gap)
                delay = 1.2 + (ci + col_idx) * 0.06
                overlay.append(
                    f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2.5" fill="#93c5fd" opacity="0">'
                    f'<animate attributeName="opacity" values="0;1;1" keyTimes="0;0.3;1" dur="0.7s" begin="{delay:.2f}s" fill="freeze"/>'
                    f'<animate attributeName="opacity" values="0.85;1;0.85" dur="3s" begin="{delay + 0.8:.2f}s" repeatCount="indefinite"/>'
                    f'</rect>'
                )
    mk_overlay_svg = "\n  ".join(overlay)

    # Day-of-week labels (Mon/Wed/Fri, GitHub style)
    dow_labels = ""
    for idx, name in [(1, "Mon"), (3, "Wed"), (5, "Fri")]:
        y = pad_t + idx * (cell + gap) + cell - 2
        dow_labels += f'<text x="{pad_l - 10}" y="{y}" text-anchor="end" font-family="{MONO}" font-size="9" fill="{TEXT_META}" letter-spacing="0.1em">{name}</text>\n  '

    # Legend
    legend_x = pad_l + grid_w - 130
    legend_y = pad_t + grid_h + 26
    legend = f'<text x="{legend_x - 8}" y="{legend_y + 9}" text-anchor="end" font-family="{MONO}" font-size="9" fill="{TEXT_META}" letter-spacing="0.12em">less</text>'
    for i, op in enumerate([0.06, 0.25, 0.45, 0.70, 1.0]):
        legend += f'<rect x="{legend_x + i * 15}" y="{legend_y}" width="11" height="11" rx="2" fill="{ACCENT}" fill-opacity="{op}"/>'
    legend += f'<text x="{legend_x + 5 * 15 + 4}" y="{legend_y + 9}" font-family="{MONO}" font-size="9" fill="{TEXT_META}" letter-spacing="0.12em">more</text>'

    body = f'''
  <text x="{pad_l}" y="42" font-family="{MONO}" font-size="10" fill="{TEXT_META}" letter-spacing="0.24em">{xml_escape(s['first_date'])}  →  {xml_escape(s['last_date'])}</text>
  <text x="{pad_l + grid_w}" y="42" text-anchor="end" font-family="{MONO}" font-size="10" fill="{TEXT_META}" letter-spacing="0.24em">{active} ACTIVE DAYS · MAX <tspan fill="{TEXT}" font-weight="600">{max_v}</tspan></text>
  {dow_labels}
  {cells_svg}
  {mk_overlay_svg}
  {legend}
'''
    return shell(w, h, body, title="ACTIVITY")


# ───────────────────────── orkestrasyon ─────────────────────────

def build_all(stats):
    from theme_light import to_light, light_name

    dark = {
        "overview.svg": overview_svg(stats),
        "streak.svg": streak_svg(stats),
        "langs.svg": langs_svg(stats),
        "activity.svg": activity_svg(stats),
    }
    files = dict(dark)
    for name, svg in dark.items():
        files[light_name(name)] = to_light(svg)
    return files


def main():
    stats = compute_stats(fetch_user_json())
    files = build_all(stats)

    staging = "/tmp/stats_staging"
    os.makedirs(staging, exist_ok=True)
    for name, svg in files.items():
        path = os.path.join(staging, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(svg)
        minidom.parse(path)  # geçersiz XML ise burada patlar → assets/cache'e hiç dokunulmaz

    os.makedirs(OUT_DIR, exist_ok=True)
    for name, svg in files.items():
        with open(os.path.join(OUT_DIR, name), "w", encoding="utf-8") as f:
            f.write(svg)

    print(f"✓ {len(files)} kart üretildi → {OUT_DIR}")
    summary = {k: v for k, v in stats.items() if k != "top_langs"}
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"✗ HATA: {e}", file=sys.stderr)
        sys.exit(1)
