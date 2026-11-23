import json
import urllib.request
from datetime import datetime, timezone
from xml.sax.saxutils import escape

SITE_URL = "https://aniguide.aniguide-hub.workers.dev/"
ANILIST_API = "https://graphql.anilist.co"

QUERY = """
query ($page: Int) {
  Page(page: $page, perPage: 3) {
    media(type: MANGA, sort: TRENDING_DESC, isAdult: false) {
      id
      title { english romaji }
      description(asHtml: false)
      coverImage { extraLarge large }
      genres
    }
  }
}
"""

def fetch_manga():
    # Rotate page (1 to 10) based on day of month so Pins stay fresh every day
    day_page = (datetime.now(timezone.utc).day % 10) + 1
    payload = json.dumps({"query": QUERY, "variables": {"page": day_page}}).encode("utf-8")
    req = urllib.request.Request(
        ANILIST_API,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "KomaVelt-RSS-Bot/1.0"
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["data"]["Page"]["media"]

def build_rss(items):
    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    date_tag = datetime.now(timezone.utc).strftime("%Y%m%d")
    xml_items = []

    for m in items:
        title = m["title"].get("english") or m["title"].get("romaji") or "Top Manga"
        img = m["coverImage"].get("extraLarge") or m["coverImage"].get("large") or ""
        genres = ", ".join((m.get("genres") or [])[:3])
        raw_desc = (m.get("description") or "").replace("\n", " ")
        short_desc = (raw_desc[:140] + "...") if len(raw_desc) > 140 else raw_desc

        pin_title = f"{title} Original Manga & Watch Guide | KomaVelt India"
        pin_desc = f"Explore {title} ({genres}) on KomaVelt. Check original manga deals on Amazon India, canon watch orders & more. {short_desc}"
        link = f"{SITE_URL}?manga={m['id']}&utm_source=pinterest&utm_medium=auto_pin"
        guid = f"komavelt-{m['id']}-{date_tag}"

        xml_items.append(f"""    <item>
      <title>{escape(pin_title)}</title>
      <link>{escape(link)}</link>
      <guid isPermaLink="false">{escape(guid)}</guid>
      <pubDate>{now}</pubDate>
      <description>{escape(pin_desc)}</description>
      <enclosure url="{escape(img)}" type="image/jpeg" />
      <media:content url="{escape(img)}" medium="image" />
    </item>""")

    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
  <channel>
    <title>KomaVelt — Original Manga Deals &amp; Anime Guides</title>
    <link>{SITE_URL}</link>
    <description>Daily trending manga, box set deals in India, and anime watch orders from KomaVelt.</description>
    <lastBuildDate>{now}</lastBuildDate>
{chr(10).join(xml_items)}
  </channel>
</rss>
"""
    with open("rss.xml", "w", encoding="utf-8") as f:
        f.write(rss)
    print(f"Generated rss.xml with {len(items)} items.")

if __name__ == "__main__":
    manga_list = fetch_manga()
    build_rss(manga_list)
