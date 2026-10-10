#!/usr/bin/env python3
"""
Contribution Traffic: the GitHub contribution calendar as a grid with a
top-down car driving through it.

The car holds a lane, changes lanes smoothly toward busier stretches and knocks
every contribution square it touches out of the way. Squares grow back when the
loop restarts. Hit times come from the real route geometry (constant speed), so
each square reacts exactly when the bumper reaches it.

Plain SMIL only (no JS), so it animates inside <img> on github.com.
Writes contribution-car.svg (light) and contribution-car-dark.svg (dark).
"""

import json
import math
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

# Grid geometry
X0, Y0, STEP, SIZE = 102, 52, 14, 10
ROWS = 7

# Car and route
BUMPER = 13.0          # distance from car centre to front bumper
SPEED = 90.0           # px per second
ENTRY_X, EXIT_X = 30.0, 872.0
SAMPLE = 2.0           # route sampling step in px
LANE_WINDOW = 8        # columns per lane decision
LANE_GAIN = 3          # a lane must beat the current one by this much to be worth a change
LANE_STEP = 2          # lanes crossed per change, at most
HOLD = 3.0             # seconds between loops
KNOCK = 0.55           # seconds a square takes to fly off
REGROW_AT = 0.8        # seconds after the drive ends
REGROW_FOR = 0.6

THEMES = {
    "light": {
        "bg": "#f8fafc", "border": "#cbd5e1", "text": "#0f172a", "muted": "#64748b",
        "cells": ["#e2e8f0", "#bfdbfe", "#93c5fd", "#3b82f6", "#1d4ed8"],
        "body": "#1e293b", "roof": "#0f172a", "glass": "#94a3b8",
        "outline": "#f8fafc", "beam": 0.12,
    },
    "dark": {
        "bg": "#0f172a", "border": "#334155", "text": "#f8fafc", "muted": "#94a3b8",
        "cells": ["#1e293b", "#1e3a8a", "#1d4ed8", "#3b82f6", "#93c5fd"],
        "body": "#e2e8f0", "roof": "#cbd5e1", "glass": "#0f172a",
        "outline": "#0f172a", "beam": 0.18,
    },
}


def fetch_calendar():
    if not TOKEN:
        raise RuntimeError("GITHUB_TOKEN not found")
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
        raise RuntimeError(f"GitHub GraphQL error: {payload['errors']}")
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


def read_levels(calendar):
    weeks = calendar["weeks"][-53:]
    counts = []
    for week in weeks:
        by_weekday = {d["weekday"]: d["contributionCount"] for d in week["contributionDays"]}
        counts.append([by_weekday.get(row, 0) for row in range(ROWS)])
    maximum = max((c for column in counts for c in column), default=1)
    return [[level(c, maximum) for c in column] for column in counts]


def lane_y(row):
    return Y0 + row * STEP + SIZE / 2


def smoothstep(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def plan_lanes(levels):
    """One lane per window of columns: move toward the busiest row, but only
    when it is clearly better than the current lane and by at most LANE_STEP rows."""
    lane, lanes = 3, []
    for start in range(0, len(levels), LANE_WINDOW):
        window = levels[start:start + LANE_WINDOW]
        gain = [sum(column[row] for column in window) for row in range(ROWS)]
        best = max(range(ROWS), key=lambda r: (gain[r], -abs(r - lane)))
        if gain[best] - gain[lane] >= LANE_GAIN:
            lane += max(-LANE_STEP, min(LANE_STEP, best - lane))
        lanes.append(lane)
    return lanes


def build_route(lanes):
    """Densely sampled (x, y) polyline. Lane changes are smoothstep blends whose
    length grows with the number of lanes crossed, so the heading stays natural."""
    events = []
    for i in range(1, len(lanes)):
        if lanes[i] != lanes[i - 1]:
            length = 36 + 20 * abs(lanes[i] - lanes[i - 1])
            boundary = X0 + i * LANE_WINDOW * STEP - (STEP - SIZE) / 2
            events.append((boundary - length / 2, length, lane_y(lanes[i - 1]), lane_y(lanes[i])))

    def y_at(x):
        y = lane_y(lanes[0])
        for start, length, y_from, y_to in events:
            if x < start:
                break
            y = y_from + (y_to - y_from) * smoothstep((x - start) / length)
        return y

    points, x = [], ENTRY_X
    while x < EXIT_X:
        points.append((x, y_at(x)))
        x += SAMPLE
    points.append((EXIT_X, y_at(EXIT_X)))
    return points


def measure(points):
    distance, headings, total = [0.0], [], 0.0
    for i in range(1, len(points)):
        total += math.dist(points[i - 1], points[i])
        distance.append(total)
    for i in range(len(points)):
        a, b = (points[i], points[i + 1]) if i + 1 < len(points) else (points[i - 1], points[i])
        headings.append(math.atan2(b[1] - a[1], b[0] - a[0]))
    return distance, headings


def find_hits(points, distance, headings, levels):
    """For every non-empty square, the first moment the bumper reaches it while
    the body overlaps its lane. Returns {(col, row): (time, hx, hy, lateral)}."""
    hits = {}
    for col, column in enumerate(levels):
        cx = X0 + col * STEP + SIZE / 2
        for row, lv in enumerate(column):
            if lv == 0:
                continue
            cy = lane_y(row)
            for i, (px, py) in enumerate(points):
                if abs(px - cx) > 40:
                    continue
                hx, hy = math.cos(headings[i]), math.sin(headings[i])
                dx, dy = cx - (px + BUMPER * hx), cy - (py + BUMPER * hy)
                along = dx * hx + dy * hy
                lateral = -dx * hy + dy * hx
                if -25 <= along <= SIZE / 2 and abs(lateral) <= 10.5:
                    hits[(col, row)] = (distance[i] / SPEED, hx, hy, lateral)
                    break
    return hits


def knock_vector(col, row, hx, hy, lateral):
    """Where a hit square ends up: pushed forward and away from the car's centre line."""
    seed = ((col * 73856093) ^ (row * 19349663)) % 1000 / 1000.0
    side = 1 if lateral > 1.5 else -1 if lateral < -1.5 else (1 if seed > 0.5 else -1)
    forward = 12 + 10 * seed
    sideways = side * (3 + 6 * ((seed * 7) % 1))
    tx = hx * forward - hy * sideways
    ty = hy * forward + hx * sideways
    angle = side * (25 + 45 * ((seed * 13) % 1))
    return tx, ty, angle


def square_markup(col, row, lv, palette, hit, cycle, regrow):
    x, y = X0 + col * STEP, Y0 + row * STEP
    cx, cy = x + SIZE / 2, y + SIZE / 2
    empty = palette["cells"][0]
    base = f'<rect x="{x}" y="{y}" width="{SIZE}" height="{SIZE}" rx="2" fill="{empty}"/>'
    if lv == 0:
        return base
    fill = palette["cells"][lv]
    if hit is None:
        return f'<rect x="{x}" y="{y}" width="{SIZE}" height="{SIZE}" rx="2" fill="{fill}"/>'

    when, hx, hy, lateral = hit
    tx, ty, angle = knock_vector(col, row, hx, hy, lateral)
    t_a, t_b = when / cycle, (when + KNOCK) / cycle
    t_c, t_r = (regrow - 0.05) / cycle, regrow / cycle
    t_e = (regrow + REGROW_FOR) / cycle
    move_keys = f"0;{t_a:.4f};{t_b:.4f};{t_c:.4f};{t_r:.4f};1"
    fade_keys = f"0;{t_a:.4f};{t_b:.4f};{t_r:.4f};{t_e:.4f};1"
    dur = f"{cycle:.2f}s"
    return (
        f'{base}<rect x="{x}" y="{y}" width="{SIZE}" height="{SIZE}" rx="2" fill="{fill}">'
        f'<animate attributeName="opacity" dur="{dur}" repeatCount="indefinite" '
        f'values="1;1;0;0;1;1" keyTimes="{fade_keys}"/>'
        f'<animateTransform attributeName="transform" type="translate" dur="{dur}" '
        f'repeatCount="indefinite" values="0 0;0 0;{tx:.1f} {ty:.1f};{tx:.1f} {ty:.1f};0 0;0 0" '
        f'keyTimes="{move_keys}"/>'
        f'<animateTransform attributeName="transform" type="rotate" additive="sum" dur="{dur}" '
        f'repeatCount="indefinite" values="0 {cx} {cy};0 {cx} {cy};{angle:.0f} {cx} {cy};'
        f'{angle:.0f} {cx} {cy};0 {cx} {cy};0 {cx} {cy}" keyTimes="{move_keys}"/>'
        f'</rect>'
    )


def car_markup(palette, route_path, drive, cycle):
    p = palette
    dur = f"{cycle:.2f}s"
    fade_keys = f"0;{0.4 / cycle:.4f};{(drive - 0.5) / cycle:.4f};{drive / cycle:.4f};1"
    return f'''<g opacity="0">
    <animate attributeName="opacity" dur="{dur}" repeatCount="indefinite" values="0;1;1;0;0" keyTimes="{fade_keys}"/>
    <g>
      <animateMotion dur="{dur}" repeatCount="indefinite" rotate="auto" calcMode="linear" keyPoints="0;1;1" keyTimes="0;{drive / cycle:.4f};1" path="{route_path}"/>
      <path d="M 13 -4 L 42 -12 L 42 12 L 13 4 Z" fill="url(#beam)"/>
      <rect x="-12.5" y="-4.4" width="28" height="13" rx="5.2" fill="#000" opacity=".26"/>
      <g fill="#020617">
        <rect x="5" y="-7.6" width="6.4" height="3" rx="1.2"/>
        <rect x="5" y="4.6" width="6.4" height="3" rx="1.2"/>
        <rect x="-11" y="-7.6" width="6.4" height="3" rx="1.2"/>
        <rect x="-11" y="4.6" width="6.4" height="3" rx="1.2"/>
      </g>
      <rect x="-14" y="-6.2" width="28" height="12.4" rx="5.2" fill="{p["body"]}" stroke="{p["outline"]}" stroke-width=".8"/>
      <rect x="6.8" y="-4.6" width="6" height="9.2" rx="3" fill="#fff" opacity=".18"/>
      <rect x="-12.6" y="-4.4" width="3.4" height="8.8" rx="1.6" fill="#fff" opacity=".12"/>
      <path d="M 3.2 -4.9 L 6.4 -3.6 L 6.4 3.6 L 3.2 4.9 Z" fill="{p["glass"]}"/>
      <rect x="-6.6" y="-4.5" width="9.4" height="9" rx="2" fill="{p["roof"]}"/>
      <path d="M -6.9 -4.4 L -9.6 -3.2 L -9.6 3.2 L -6.9 4.4 Z" fill="{p["glass"]}"/>
      <rect x="3.6" y="-7.9" width="2.2" height="1.8" rx=".8" fill="{p["body"]}" stroke="{p["outline"]}" stroke-width=".5"/>
      <rect x="3.6" y="6.1" width="2.2" height="1.8" rx=".8" fill="{p["body"]}" stroke="{p["outline"]}" stroke-width=".5"/>
      <rect x="12.4" y="-5.2" width="1.8" height="2.6" rx=".9" fill="#fef9c3"/>
      <rect x="12.4" y="2.6" width="1.8" height="2.6" rx=".9" fill="#fef9c3"/>
      <rect x="-14" y="-5.2" width="1.6" height="2.4" rx=".8" fill="#ef4444"/>
      <rect x="-14" y="2.8" width="1.6" height="2.4" rx=".8" fill="#ef4444"/>
    </g>
  </g>'''


def render(total, levels, simulation, palette):
    points, drive, hits = simulation
    cycle = drive + HOLD
    regrow = drive + REGROW_AT
    route_path = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in points)
    squares = "".join(
        square_markup(col, row, lv, palette, hits.get((col, row)), cycle, regrow)
        for col, column in enumerate(levels)
        for row, lv in enumerate(column)
    )
    cars = car_markup(palette, route_path, drive, cycle)
    return f'''<svg width="880" height="170" viewBox="0 0 880 170" preserveAspectRatio="xMidYMid meet" fill="none" xmlns="http://www.w3.org/2000/svg">
  <title>{USERNAME} contribution traffic</title>
  <desc>A car drives through {total} contributions, knocking aside the squares in its lane.</desc>
  <defs>
    <linearGradient id="beam" gradientUnits="userSpaceOnUse" x1="13" y1="0" x2="42" y2="0">
      <stop offset="0" stop-color="#fef9c3" stop-opacity="{palette["beam"]}"/>
      <stop offset="1" stop-color="#fef9c3" stop-opacity="0"/>
    </linearGradient>
  </defs>
  <rect x="0.5" y="0.5" width="879" height="169" rx="12" fill="{palette["bg"]}" stroke="{palette["border"]}"/>
  <text x="28" y="31" fill="{palette["text"]}" font-family="Inter,Segoe UI,Arial,sans-serif" font-size="13" font-weight="600" letter-spacing="1">CONTRIBUTION TRAFFIC</text>
  <text x="852" y="31" text-anchor="end" fill="{palette["muted"]}" font-family="JetBrains Mono,Consolas,monospace" font-size="11" letter-spacing="1.5">{total} CONTRIBUTIONS</text>
  <g>{squares}</g>
  {cars}
</svg>'''


def simulate(levels):
    lanes = plan_lanes(levels)
    points = build_route(lanes)
    distance, headings = measure(points)
    hits = find_hits(points, distance, headings, levels)
    return points, distance[-1] / SPEED, hits


def main():
    calendar = fetch_calendar()
    levels = read_levels(calendar)
    simulation = simulate(levels)
    total = calendar["totalContributions"]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "contribution-car.svg").write_text(
        render(total, levels, simulation, THEMES["light"]), encoding="utf-8")
    (OUT_DIR / "contribution-car-dark.svg").write_text(
        render(total, levels, simulation, THEMES["dark"]), encoding="utf-8")
    print(f"{USERNAME}: {total} contributions, car knocks {len(simulation[2])} squares per lap")


if __name__ == "__main__":
    main()
