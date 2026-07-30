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
ACCENT = "#3b82f6"
PURPLE, INDIGO, CYAN = ACCENT, ACCENT, ACCENT
BG1, BG2 = "#0a0a0b", "#0a0a0b"
BORDER = "#1c1c20"
TEXT, TEXT_DIM, TEXT_META = "#f4f4f5", "#a1a1aa", "#52525a"

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
  <rect x="0" y="12" width="2" height="{h - 24}" fill="{ACCENT}"/>
  {corner}
  {body}
</svg>'''


def overview_svg(s):
    w, h = 420, 200
    blocks = [
        (str(s["total_contribs"]), "KATKI / 1Y"),
        (str(s["total_repos"]), "REPOSITORY"),
        (str(s["total_stars"]), "YILDIZ"),
        (str(s["followers"]), "TAKİPÇİ"),
    ]
    col_w, row_h = w / 2, (h - 40) / 2
    items = []
    for i, (value, label) in enumerate(blocks):
        col, row = i % 2, i // 2
        cx = col_w * col + col_w / 2
        cy = 40 + row_h * row
        items.append(f'''
    <text x="{cx}" y="{cy + 38}" text-anchor="middle" font-family="{SANS}" font-size="34" font-weight="600" fill="{TEXT}" letter-spacing="-0.8">{xml_escape(value)}</text>
    <text x="{cx}" y="{cy + 62}" text-anchor="middle" font-family="{MONO}" font-size="10.5" fill="{TEXT_META}" letter-spacing="2.4">{xml_escape(label)}</text>''')
    items.append(f'<line x1="{col_w}" y1="46" x2="{col_w}" y2="{h - 20}" stroke="{BORDER}" stroke-width="1"/>')
    items.append(f'<line x1="24" y1="{40 + row_h}" x2="{w - 24}" y2="{40 + row_h}" stroke="{BORDER}" stroke-width="1"/>')
    return shell(w, h, "\n".join(items), title="OVERVIEW")


def streak_svg(s):
    w, h = 420, 200
    body = f'''
  <text x="70" y="72" font-family="{MONO}" font-size="10.5" fill="{TEXT_META}" letter-spacing="2.4">GÜNLÜK SERİ</text>
  <text x="70" y="122" font-family="{SANS}" font-size="52" font-weight="600" fill="{TEXT}" letter-spacing="-1.4">{s['current_streak']}</text>
  <text x="70" y="146" font-family="{MONO}" font-size="11" fill="{TEXT_DIM}" letter-spacing="1">gün · aktif</text>

  <line x1="{w/2}" y1="46" x2="{w/2}" y2="{h - 20}" stroke="{BORDER}" stroke-width="1"/>

  <text x="240" y="72" font-family="{MONO}" font-size="10.5" fill="{TEXT_META}" letter-spacing="2.4">EN UZUN SERİ</text>
  <text x="240" y="122" font-family="{SANS}" font-size="52" font-weight="600" fill="{TEXT}" letter-spacing="-1.4">{s['longest_streak']}</text>
  <text x="240" y="146" font-family="{MONO}" font-size="11" fill="{TEXT_DIM}" letter-spacing="1">gün · rekor</text>
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
            rows.append(f'''
    <text x="24" y="{y + 12}" font-family="{SANS}" font-size="13" fill="{TEXT}">{xml_escape(name)}</text>
    <rect x="{bar_x}" y="{y + 4}" width="{bar_max_w}" height="4" rx="2" fill="{BORDER}"/>
    <rect x="{bar_x}" y="{y + 4}" width="{bw:.1f}" height="4" rx="2" fill="{safe_color}"/>
    <text x="{bar_x + bar_max_w + 14}" y="{y + 12}" font-family="{MONO}" font-size="11.5" fill="{TEXT_DIM}">{pct * 100:.1f}%</text>''')
    else:
        rows.append(f'<text x="{w/2}" y="{h/2}" text-anchor="middle" fill="{TEXT_DIM}" font-family="{SANS}" font-size="13">Henüz dil verisi yok</text>')
    return shell(w, h, "\n".join(rows), title="LANGUAGES")


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
    pad_l, pad_r, pad_t, pad_b = 40, 40, 60, 40
    chart_w, chart_h = w - pad_l - pad_r, h - pad_t - pad_b
    max_v = max(weekly) or 1
    n = len(weekly)
    step = chart_w / max(n - 1, 1)
    points = [(pad_l + i * step, pad_t + chart_h - (v / max_v) * chart_h) for i, v in enumerate(weekly)]
    line_path = smooth_path(points)
    area_path = line_path + f" L {points[-1][0]:.1f},{pad_t + chart_h:.1f} L {points[0][0]:.1f},{pad_t + chart_h:.1f} Z"
    avg = sum(weekly) / n if n else 0

    grid = "\n".join(
        f'<line x1="{pad_l}" y1="{pad_t + chart_h * f:.1f}" x2="{pad_l + chart_w}" y2="{pad_t + chart_h * f:.1f}" stroke="{BORDER}" stroke-width="1"/>'
        for f in (0.0, 0.5, 1.0)
    )
    body = f'''
  <text x="{pad_l}" y="42" font-family="{MONO}" font-size="10.5" fill="{TEXT_META}" letter-spacing="2.4">{xml_escape(s['first_date'])}  →  {xml_escape(s['last_date'])}</text>
  <text x="{pad_l + chart_w}" y="42" text-anchor="end" font-family="{MONO}" font-size="10.5" fill="{TEXT_META}" letter-spacing="2.4">HAFTALIK ORT. <tspan fill="{TEXT}" font-weight="600">{avg:.1f}</tspan></text>
  {grid}
  <path d="{area_path}" fill="{ACCENT}" fill-opacity="0.08" stroke="none"/>
  <path d="{line_path}" fill="none" stroke="{ACCENT}" stroke-width="1.6"/>
'''
    return shell(w, h, body, title="ACTIVITY")


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
