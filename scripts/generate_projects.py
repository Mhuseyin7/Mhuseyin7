#!/usr/bin/env python3
"""
"Projeler" bloğunu muhammedkoca.com.tr/projeler sayfasından çeker ve
README'deki <!-- PROJECTS:START --> / <!-- PROJECTS:END --> işaretleri
arasındaki tabloyu yeniden yazar.

Neden HTML kazıma: /projeler sayfası React/Astro tarafından render edilir ve
her proje için ayrı bir og:image kurmaya gerek yoktur — kart yapısı sayfada
zaten hazırdır (article.projects-card > h2, p.projects-card__desc, tag'ler).

Güvenlik: Herhangi bir adımda hata olursa README.md dosyasına DOKUNMAZ (mevcut
içerik olduğu gibi kalır) ve non-zero exit code ile çıkar.

Kullanım: python3 scripts/generate_projects.py README.md
"""
import re
import sys
import urllib.request
from html import unescape, escape as html_escape

SITE = "https://www.muhammedkoca.com.tr"
LIST_URL = f"{SITE}/projeler"
README_PATH = sys.argv[1] if len(sys.argv) > 1 else "README.md"
MAX_PROJECTS = 10
MAX_TAGS = 4
START_MARK = "<!-- PROJECTS:START -->"
END_MARK = "<!-- PROJECTS:END -->"
UA = {"User-Agent": "Mozilla/5.0 (compatible; readme-projects/1.0)"}


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="replace")


def strip_tags(text):
    return re.sub(r"<[^<]+?>", "", text).strip()


def truncate(text, n=140):
    if len(text) <= n:
        return text
    return text[:n].rsplit(" ", 1)[0].rstrip(",.;:") + "…"


def parse_projects(html_text):
    """article.projects-card blocklarını sırayla ayıklar; her karttan slug,
    başlık, kısa açıklama ve ilk birkaç tag'i çıkarır."""
    article_re = re.compile(
        r'<article class="projects-card[^"]*">(.*?)</article>',
        re.DOTALL,
    )
    items = []
    for m in article_re.finditer(html_text):
        block = m.group(1)
        href_m = re.search(r'href="/projeler/([^"]+)"', block)
        title_m = re.search(r"<h2[^>]*>([^<]+)</h2>", block)
        desc_m = re.search(
            r'<p class="projects-card__desc"[^>]*>(.*?)</p>', block, re.DOTALL
        )
        tag_matches = re.findall(
            r'<span class="projects-card__tag"[^>]*>([^<]+)</span>', block
        )
        if not (href_m and title_m):
            continue
        items.append({
            "slug": href_m.group(1),
            "title": unescape(title_m.group(1)).strip(),
            "desc": truncate(unescape(strip_tags(desc_m.group(1))) if desc_m else ""),
            "tags": [unescape(t).strip() for t in tag_matches[:MAX_TAGS]],
        })
        if len(items) >= MAX_PROJECTS:
            break
    return items


def build_cell(p):
    title = html_escape(p["title"])
    desc = html_escape(p["desc"])
    url = f"{SITE}/projeler/{p['slug']}"
    tag_line = ""
    if p["tags"]:
        tag_line = " · ".join(f"<code>{html_escape(t)}</code>" for t in p["tags"])
        tag_line = f'<br/><sub>{tag_line}</sub>'
    return (
        f'      <sub>▸</sub> <b><a href="{url}">{title}</a></b><br/>\n'
        f'      <sub>{desc}</sub>{tag_line}'
    )


def build_table(items):
    if not items:
        raise RuntimeError("Hiç proje kartı okunamadı")
    rows = []
    for i in range(0, len(items), 2):
        left = build_cell(items[i])
        right = build_cell(items[i + 1]) if i + 1 < len(items) else ""
        right_cell = (
            f'    <td width="50%" valign="top">\n{right}\n    </td>'
            if right else '    <td width="50%" valign="top"></td>'
        )
        rows.append(
            "  <tr>\n"
            f'    <td width="50%" valign="top">\n{left}\n    </td>\n'
            f"{right_cell}\n"
            "  </tr>"
        )
    return "<table>\n" + "\n".join(rows) + "\n</table>"


def main():
    items = parse_projects(fetch(LIST_URL))
    if not items:
        raise RuntimeError("Projeler sayfasında hiç kart bulunamadı")
    block = build_table(items)

    with open(README_PATH, "r", encoding="utf-8") as f:
        readme = f.read()

    if START_MARK not in readme or END_MARK not in readme:
        raise RuntimeError(f"README içinde {START_MARK} / {END_MARK} işaretleri bulunamadı")

    pattern = re.compile(re.escape(START_MARK) + r".*?" + re.escape(END_MARK), re.DOTALL)
    new_readme = pattern.sub(START_MARK + "\n" + block + "\n" + END_MARK, readme, count=1)

    if new_readme == readme:
        print("Değişiklik yok, README zaten güncel.")
    else:
        with open(README_PATH, "w", encoding="utf-8") as f:
            f.write(new_readme)
    print(f"[OK] {len(items)} proje kartı işlendi")


if __name__ == "__main__":
    try:
        # Windows terminalinde Unicode print için stdout'u UTF-8'e çevir (varsa)
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        main()
    except Exception as e:
        print(f"[HATA] {e}", file=sys.stderr)
        sys.exit(1)
