#!/usr/bin/env python3
"""GitHub katkı takvimini, karelerin arasında ilerleyen araba SVG'si olarak üretir."""

import json
import os
import sys
import urllib.request
from pathlib import Path


USERNAME = os.environ.get("GH_USERNAME", "Mhuseyin7")
TOKEN = os.environ.get("GH_PAT") or os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
OUT_DIR = Path(sys.argv[1] if len(sys.argv) > 1 else "dist")

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { weekday contributionCount } }
      }
    }
  }
}
"""


def fetch_calendar():
    if not TOKEN:
        raise RuntimeError("GITHUB_TOKEN bulunamadı")
    body = json.dumps({"query": QUERY, "variables": {"login": USERNAME}}).encode()
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": f"{USERNAME}-contribution-car",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode())
    if payload.get("errors"):
        raise RuntimeError(f"GitHub GraphQL hatası: {payload['errors']}")
    return payload["data"]["user"]["contributionsCollection"]["contributionCalendar"]


def level(count, maximum):
    if count == 0:
        return 0
    ratio = count / max(maximum, 1)
    if ratio <= 0.25:
        return 1
    if ratio <= 0.50:
        return 2
    if ratio <= 0.75:
        return 3
    return 4


def render(calendar, dark=False):
    weeks = calendar["weeks"][-53:]
    maximum = max(
        (day["contributionCount"] for week in weeks for day in week["contributionDays"]),
        default=1,
    )
    if dark:
        bg, border, text, muted = "#0a0a0b", "#1c1c20", "#f4f4f5", "#71717a"
        colors = ["#161b22", "#312e81", "#6d28d9", "#a855f7", "#22d3ee"]
        road = "#27272a"
    else:
        bg, border, text, muted = "#ffffff", "#d4d4d8", "#18181b", "#71717a"
        colors = ["#ebedf0", "#ddd6fe", "#a78bfa", "#7c3aed", "#0891b2"]
        road = "#d4d4d8"

    squares = []
    x0, y0, step, size = 102, 52, 14, 10
    for column, week in enumerate(weeks):
        by_weekday = {d["weekday"]: d["contributionCount"] for d in week["contributionDays"]}
        for row in range(7):
            count = by_weekday.get(row, 0)
            color = colors[level(count, maximum)]
            squares.append(
                f'<rect x="{x0 + column * step}" y="{y0 + row * step}" width="{size}" '
                f'height="{size}" rx="2" fill="{color}"/>'
            )

    # Araba katkı trafiğinde birkaç kez yumuşak şerit değiştirir.
    route = (
        "M 74 102 C 150 102, 162 65, 238 65 "
        "S 320 126, 395 126 S 480 76, 552 76 "
        "S 634 118, 704 118 S 778 84, 846 84"
    )
    total = calendar.get("totalContributions", 0)
    return f'''<svg width="880" height="170" viewBox="0 0 880 170" fill="none" xmlns="http://www.w3.org/2000/svg">
  <title>{USERNAME} contribution traffic</title>
  <desc>{total} katkı karesinin arasında şerit değiştiren animasyonlu araba</desc>
  <defs>
    <filter id="carGlow" x="-60%" y="-100%" width="220%" height="300%">
      <feGaussianBlur stdDeviation="3" result="blur"/>
      <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
  </defs>
  <rect x="0.5" y="0.5" width="879" height="169" rx="12" fill="{bg}" stroke="{border}"/>
  <text x="28" y="31" fill="{text}" font-family="Inter,Segoe UI,Arial,sans-serif" font-size="13" font-weight="600">CONTRIBUTION TRAFFIC</text>
  <text x="852" y="31" text-anchor="end" fill="{muted}" font-family="JetBrains Mono,Consolas,monospace" font-size="11">{total} CONTRIBUTIONS</text>
  <path d="{route}" stroke="{road}" stroke-width="1" stroke-dasharray="4 8" opacity=".7"/>
  <g>{''.join(squares)}</g>
  <g filter="url(#carGlow)">
    <g>
      <animateMotion dur="9s" repeatCount="indefinite" rotate="auto" path="{route}"/>
      <ellipse cx="0" cy="8" rx="17" ry="4" fill="#000" opacity=".22"/>
      <rect x="-15" y="-8" width="30" height="16" rx="6" fill="#3b82f6" stroke="#bfdbfe" stroke-width="1"/>
      <path d="M-7-8 L-3-13 H8 L13-8 Z" fill="#2563eb" stroke="#bfdbfe" stroke-width="1"/>
      <path d="M-3-8 L0-11 H7 L10-8 Z" fill="#bae6fd" opacity=".9"/>
      <rect x="-11" y="7" width="7" height="3" rx="1.5" fill="#18181b"/>
      <rect x="6" y="7" width="7" height="3" rx="1.5" fill="#18181b"/>
      <circle cx="14" cy="-4" r="2" fill="#fef08a"/>
      <circle cx="14" cy="4" r="2" fill="#fef08a"/>
      <path d="M-20-4 H-32 M-20 3 H-27" stroke="#22d3ee" stroke-width="2" stroke-linecap="round" opacity=".8"/>
    </g>
  </g>
</svg>'''


def main():
    calendar = fetch_calendar()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "contribution-car.svg").write_text(render(calendar), encoding="utf-8")
    (OUT_DIR / "contribution-car-dark.svg").write_text(render(calendar, dark=True), encoding="utf-8")
    print(f"{USERNAME}: {calendar['totalContributions']} katkı ile araba SVG'leri üretildi")


if __name__ == "__main__":
    main()
