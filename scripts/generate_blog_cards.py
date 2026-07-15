#!/usr/bin/env python3
"""
"Son Yazılar" kart bloğunu muhammedkoca.com.tr'nin RSS feed'inden ve her yazının
KENDİ sayfasındaki <meta property="og:image"> etiketinden üretir.

Neden kendi URL'imizi kurmuyoruz: yazı başlıkları Türkçe karakter, iki nokta,
apostrof gibi karakterler içeriyor; bunları elle URL-encode etmeye çalışmak
kırılgan olur. Onun yerine sitenin KENDİSİNİN her sayfa için önceden doğru
şekilde ürettiği og:image değerini doğrudan kopyalıyoruz — her zaman doğru,
çünkü kaynak sitenin kendi render mantığı.

Güvenlik: Herhangi bir adımda hata olursa README.md dosyasına DOKUNMAZ (mevcut
içerik olduğu gibi kalır) ve non-zero exit code ile çıkar.

Kullanım: python3 scripts/generate_blog_cards.py README.md
"""
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from html import unescape, escape as html_escape

RSS_URL = "https://www.muhammedkoca.com.tr/rss.xml"
SITE = "https://www.muhammedkoca.com.tr"
README_PATH = sys.argv[1] if len(sys.argv) > 1 else "README.md"
MAX_POSTS = 3
START_MARK = "<!-- BLOG-CARDS:START -->"
END_MARK = "<!-- BLOG-CARDS:END -->"
UA = {"User-Agent": "Mozilla/5.0 (compatible; readme-blog-cards/1.0)"}

MONTHS = {
    "Jan": "Oca", "Feb": "Şub", "Mar": "Mar", "Apr": "Nis", "May": "May", "Jun": "Haz",
    "Jul": "Tem", "Aug": "Ağu", "Sep": "Eyl", "Oct": "Eki", "Nov": "Kas", "Dec": "Ara",
}


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_rss(xml_text):
    root = ET.fromstring(xml_text)
    items = []
    for item in root.findall(".//item")[:MAX_POSTS]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        desc_raw = (item.findtext("description") or "").strip()
        desc = re.sub(r"<[^<]+?>", "", unescape(desc_raw)).strip()
        if title and link:
            items.append({"title": title, "link": link, "pubDate": pub_date, "desc": desc})
    return items


def extract_meta(html_text, prop):
    """<meta> etiketlerini bulup içinde property/name=prop geçeni arar, attribute
    sırasından bağımsız şekilde content değerini döndürür."""
    for tag in re.findall(r"<meta\b[^>]*>", html_text, re.IGNORECASE):
        if re.search(rf'(?:property|name)=["\']{re.escape(prop)}["\']', tag, re.IGNORECASE):
            m = re.search(r'content=["\']([^"\']*)["\']', tag, re.IGNORECASE)
            if m:
                return unescape(m.group(1))
    return None


def format_date(pub_date):
    m = re.match(r"\w+,\s*(\d{1,2})\s+(\w{3})\s+(\d{4})", pub_date)
    if m:
        day, mon, year = m.groups()
        return f"{int(day)} {MONTHS.get(mon, mon)} {year}"
    return pub_date


def truncate(text, n=150):
    if len(text) <= n:
        return text
    return text[:n].rsplit(" ", 1)[0].rstrip(",.;:") + "…"


def build_cards(items):
    rows = []
    for it in items:
        page_html = fetch(it["link"])
        cover = extract_meta(page_html, "og:image") or ""
        category = extract_meta(page_html, "article:section") or ""
        if cover.startswith("/"):
            cover = SITE + cover
        if not cover:
            raise RuntimeError(f"og:image bulunamadı: {it['link']}")

        title_safe = html_escape(it["title"])
        desc_safe = html_escape(truncate(it["desc"]))
        date_safe = html_escape(format_date(it["pubDate"]))
        cat_safe = html_escape(category) if category else ""
        cat_badge = f'<img src="https://img.shields.io/badge/{cat_safe.replace(" ", "%20")}-a855f7?style=flat-square" alt="{cat_safe}"/>' if cat_safe else ""

        rows.append(f'''  <tr>
    <td width="260"><a href="{it['link']}"><img src="{cover}" width="240" alt="{title_safe}"/></a></td>
    <td valign="top" width="580">
      {cat_badge} <sub>{date_safe}</sub><br/><br/>
      <a href="{it['link']}"><b>{title_safe}</b></a><br/><br/>
      <sub>{desc_safe}</sub>
    </td>
  </tr>
  <tr><td colspan="2"><img src="assets/divider.svg" alt="" width="100%"/></td></tr>''')

    # son satırın altındaki fazladan divider'ı kaldır
    body = "\n".join(rows)
    body = body.rsplit('\n  <tr><td colspan="2">', 1)[0]
    return "<table>\n" + body + "\n</table>"


def main():
    items = parse_rss(fetch(RSS_URL))
    if not items:
        raise RuntimeError("RSS'ten hiç yazı okunamadı")
    block = build_cards(items)

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
    print(f"✓ {len(items)} yazı kartı işlendi")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"✗ HATA: {e}", file=sys.stderr)
        sys.exit(1)
