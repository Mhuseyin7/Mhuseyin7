#!/usr/bin/env python3
"""
GitHub istatistik kartlarını (overview, streak, langs, activity) GitHub'ın kendi
GraphQL API'sinden veri çekerek, mor/indigo/cyan temalı, tamamen özgün SVG kartlar
olarak üretir.

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

PURPLE, INDIGO, CYAN = "#a855f7", "#6366f1", "#22d3ee"
BG1, BG2 = "#120b2e", "#03121f"
TEXT, TEXT_DIM = "#e2e8f0", "#94a3b8"

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

    cal = user["contributionsCollection"]["contributionCalendar"]
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

    return {
        "total_repos": total_repos,
        "total_stars": total_stars,
        "followers": followers,
        "total_contribs": total_contribs,
        "current_streak": current,
        "longest_streak": longest,
        "weekly": weekly,
        "top_langs": [(n, s / total_lang_size, lang_color.get(n, PURPLE)) for n, s in top_langs],
        "first_date": days[0][0] if days else "",
        "last_date": days[-1][0] if days else "",
    }


# ───────────────────────── SVG katmanı ─────────────────────────

def shell(w, h, body, title=""):
    corner = (
        f'<text x="{w - 24}" y="28" text-anchor="end" font-family="Consolas, monospace" '
        f'font-size="11" fill="{CYAN}" opacity="0.55">{xml_escape(title)}</text>'
        if title else ""
    )
    return f'''<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" fill="none" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="neon" x1="0" y1="0" x2="{w}" y2="0" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="{PURPLE}"/>
      <stop offset="0.5" stop-color="{INDIGO}"/>
      <stop offset="1" stop-color="{CYAN}"/>
    </linearGradient>
    <linearGradient id="bg" x1="0" y1="0" x2="{w}" y2="{h}" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="{BG1}"/>
      <stop offset="1" stop-color="{BG2}"/>
    </linearGradient>
    <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
      <feGaussianBlur stdDeviation="2.6" result="b"/>
      <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
  </defs>
  <rect x="1.5" y="1.5" width="{w - 3}" height="{h - 3}" rx="14" fill="url(#bg)" stroke="url(#neon)" stroke-width="1.6"/>
  {corner}
  {body}
</svg>'''


def overview_svg(s):
    w, h = 420, 200
    blocks = [
        ("📈", str(s["total_contribs"]), "Katkı (1 yıl)"),
        ("📦", str(s["total_repos"]), "Repository"),
        ("⭐", str(s["total_stars"]), "Yıldız"),
        ("🧑‍🤝‍🧑", str(s["followers"]), "Takipçi"),
    ]
    col_w, row_h = w / 2, (h - 40) / 2
    items = []
    for i, (icon, value, label) in enumerate(blocks):
        col, row = i % 2, i // 2
        cx = col_w * col + col_w / 2
        cy = 40 + row_h * row
        delay = 0.12 * i
        items.append(f'''
    <g opacity="0">
      <animate attributeName="opacity" from="0" to="1" dur="0.6s" begin="{delay:.2f}s" fill="freeze"/>
      <text x="{cx}" y="{cy + 20}" text-anchor="middle" font-size="22">{icon}</text>
      <text x="{cx}" y="{cy + 46}" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" font-size="24" font-weight="800" fill="url(#neon)" filter="url(#glow)">{xml_escape(value)}</text>
      <text x="{cx}" y="{cy + 64}" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" font-size="11" fill="{TEXT_DIM}">{xml_escape(label)}</text>
    </g>''')
    items.append(f'<line x1="{col_w}" y1="30" x2="{col_w}" y2="{h - 20}" stroke="{PURPLE}" stroke-opacity="0.16"/>')
    items.append(f'<line x1="30" y1="{40 + row_h}" x2="{w - 30}" y2="{40 + row_h}" stroke="{PURPLE}" stroke-opacity="0.16"/>')
    return shell(w, h, "\n".join(items), title="GENEL BAKIŞ")


def streak_svg(s):
    w, h = 420, 200
    cx, cy, r = 105, 95, 56
    circumference = 2 * 3.14159265 * r
    ratio = (s["current_streak"] / s["longest_streak"]) if s["longest_streak"] else 0
    dash = max(circumference * min(max(ratio, 0.05), 1), 6)
    body = f'''
  <circle cx="{cx}" cy="{cy}" r="{r}" stroke="{PURPLE}" stroke-opacity="0.15" stroke-width="7" fill="none"/>
  <circle cx="{cx}" cy="{cy}" r="{r}" stroke="url(#neon)" stroke-width="7" fill="none"
          stroke-linecap="round" stroke-dasharray="{dash:.1f} {circumference:.1f}" filter="url(#glow)"
          transform="rotate(-90 {cx} {cy})">
    <animateTransform attributeName="transform" type="rotate" from="-90 {cx} {cy}" to="270 {cx} {cy}" dur="18s" repeatCount="indefinite"/>
  </circle>
  <text x="{cx}" y="88" text-anchor="middle" font-size="24">🔥</text>
  <text x="{cx}" y="124" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" font-size="28" font-weight="800" fill="{TEXT}">{s['current_streak']}</text>
  <text x="{cx}" y="146" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" font-size="11" fill="{TEXT_DIM}">GÜNLÜK SERİ</text>

  <line x1="205" y1="34" x2="205" y2="{h - 30}" stroke="{PURPLE}" stroke-opacity="0.18"/>

  <text x="312" y="76" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" font-size="12" fill="{TEXT_DIM}">En Uzun Seri</text>
  <text x="312" y="112" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" font-size="26" font-weight="800" fill="url(#neon)" filter="url(#glow)">{s['longest_streak']}</text>
  <text x="312" y="132" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" font-size="11" fill="{TEXT_DIM}">gün</text>
'''
    return shell(w, h, body, title="STREAK")


def langs_svg(s):
    langs = s["top_langs"]
    w = 880
    row_h, top_pad = 32, 46
    h = top_pad + row_h * max(len(langs), 1) + 22
    bar_x = 190
    bar_max_w = w - bar_x - 90
    rows = []
    if langs:
        for i, (name, pct, color) in enumerate(langs):
            y = top_pad + i * row_h
            bw = max(bar_max_w * pct, 4)
            delay = 0.1 * i
            safe_color = color if re.match(r"^#[0-9a-fA-F]{6}$", color or "") else PURPLE
            rows.append(f'''
    <text x="24" y="{y + 13}" font-family="Segoe UI, Arial, sans-serif" font-size="13" fill="{TEXT}">{xml_escape(name)}</text>
    <rect x="{bar_x}" y="{y}" width="{bar_max_w}" height="11" rx="5.5" fill="{PURPLE}" fill-opacity="0.12"/>
    <rect x="{bar_x}" y="{y}" width="0" height="11" rx="5.5" fill="{safe_color}" filter="url(#glow)">
      <animate attributeName="width" from="0" to="{bw:.1f}" dur="0.9s" begin="{delay:.2f}s" fill="freeze"/>
    </rect>
    <text x="{bar_x + bar_max_w + 14}" y="{y + 10}" font-family="Consolas, monospace" font-size="12" fill="{TEXT_DIM}">{pct * 100:.1f}%</text>''')
    else:
        rows.append(f'<text x="{w/2}" y="{h/2}" text-anchor="middle" fill="{TEXT_DIM}" font-family="Segoe UI, Arial, sans-serif" font-size="13">Henüz dil verisi yok</text>')
    return shell(w, h, "\n".join(rows), title="EN ÇOK KULLANILAN DİLLER")


def smooth_path(points):
    if not points:
        return ""
    d = f"M {points[0][0]:.1f},{points[0][1]:.1f} "
    for i in range(1, len(points)):
        x0, y0 = points[i - 1]
        x1, y1 = points[i]
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        d += f"Q {x0:.1f},{y0:.1f} {mx:.1f},{my:.1f} "
    d += f"L {points[-1][0]:.1f},{points[-1][1]:.1f}"
    return d


def activity_svg(s):
    w, h = 880, 220
    weekly = s["weekly"] or [0]
    pad_l, pad_r, pad_t, pad_b = 40, 40, 46, 34
    chart_w, chart_h = w - pad_l - pad_r, h - pad_t - pad_b
    max_v = max(weekly) or 1
    n = len(weekly)
    step = chart_w / max(n - 1, 1)
    points = [(pad_l + i * step, pad_t + chart_h - (v / max_v) * chart_h) for i, v in enumerate(weekly)]
    line_path = smooth_path(points)
    area_path = line_path + f" L {points[-1][0]:.1f},{pad_t + chart_h:.1f} L {points[0][0]:.1f},{pad_t + chart_h:.1f} Z"
    avg = sum(weekly) / n if n else 0
    path_len = int(chart_w + chart_h) * 2 + 200

    grid = "\n".join(
        f'<line x1="{pad_l}" y1="{pad_t + chart_h * f:.1f}" x2="{pad_l + chart_w}" y2="{pad_t + chart_h * f:.1f}" stroke="{PURPLE}" stroke-opacity="0.08"/>'
        for f in (0.0, 0.33, 0.66, 1.0)
    )
    body = f'''
  {grid}
  <path d="{area_path}" fill="url(#neon)" fill-opacity="0.12" stroke="none"/>
  <path d="{line_path}" fill="none" stroke="url(#neon)" stroke-width="2.4" filter="url(#glow)"
        stroke-dasharray="{path_len}" stroke-dashoffset="{path_len}">
    <animate attributeName="stroke-dashoffset" from="{path_len}" to="0" dur="1.8s" begin="0.1s" fill="freeze"/>
  </path>
  <circle r="4" fill="{CYAN}" filter="url(#glow)">
    <animateMotion dur="7s" begin="2s" repeatCount="indefinite" path="{line_path}"/>
  </circle>
  <text x="{pad_l}" y="26" font-family="Consolas, monospace" font-size="12" fill="{TEXT_DIM}">{xml_escape(s['first_date'])}</text>
  <text x="{pad_l + chart_w}" y="26" text-anchor="end" font-family="Consolas, monospace" font-size="12" fill="{TEXT_DIM}">{xml_escape(s['last_date'])}</text>
  <text x="{w / 2}" y="26" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" font-size="13" fill="{TEXT}">haftalık ort. <tspan fill="{CYAN}" font-weight="700">{avg:.1f}</tspan> katkı</text>
'''
    return shell(w, h, body, title="KATKI AKTİVİTESİ")


# ───────────────────────── orkestrasyon ─────────────────────────

def build_all(stats):
    return {
        "overview.svg": overview_svg(stats),
        "streak.svg": streak_svg(stats),
        "langs.svg": langs_svg(stats),
        "activity.svg": activity_svg(stats),
    }


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
