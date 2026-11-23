import io
import json
import os
import textwrap
import urllib.request
from datetime import datetime, timezone
from xml.sax.saxutils import escape
from PIL import Image, ImageDraw, ImageFilter, ImageFont

SITE_URL = "https://aniguide.aniguide-hub.workers.dev/"
ANILIST_API = "https://graphql.anilist.co"
PINS_DIR = "pins"

QUERY = """
query ($page: Int) {
  Page(page: $page, perPage: 3) {
    media(type: MANGA, countryOfOrigin: "JP", sort: TRENDING_DESC, isAdult: false) {
      id
      title { english romaji }
      description(asHtml: false)
      coverImage { extraLarge large }
      genres
    }
  }
}
"""

def load_font(size, bold=True):
    path = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    )
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()

def create_branded_pin(cover_url, title, genres, out_path):
    W, H = 1000, 1500
    req = urllib.request.Request(cover_url, headers={"User-Agent": "KomaVelt-RSS-Bot/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        cover = Image.open(io.BytesIO(resp.read())).convert("RGB")

    # 1. Dark blurred background from the manga cover
    bg = cover.resize((W, H), Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(28))
    overlay = Image.new("RGBA", (W, H), (10, 12, 20, 195))
    canvas = Image.alpha_composite(bg.convert("RGBA"), overlay)
    draw = ImageDraw.Draw(canvas)

    # 2. Top badge
    badge_font = load_font(30, bold=True)
    badge_text = "ORIGINAL MANGA DEALS • AMAZON INDIA"
    bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
    bw, bh = bbox[2] - bbox[0], bbox[3] - bbox[1]
    bx1, by1 = (W - bw) // 2 - 32, 65
    bx2, by2 = (W + bw) // 2 + 32, 65 + bh + 28
    draw.rounded_rectangle([bx1, by1, bx2, by2], radius=24, fill=(230, 0, 35, 255))
    draw.text(((W - bw) // 2, by1 + 12), badge_text, font=badge_font, fill=(255, 255, 255, 255))

    # 3. Centered crisp manga cover with subtle white border
    target_h = 840
    ratio = target_h / cover.height
    target_w = min(int(cover.width * ratio), 640)
    cover_resized = cover.resize((target_w, target_h), Image.Resampling.LANCZOS)
    cx = (W - target_w) // 2
    cy = 185
    draw.rounded_rectangle([cx - 8, cy - 8, cx + target_w + 8, cy + target_h + 8], radius=18, fill=(255, 255, 255, 45))
    canvas.paste(cover_resized, (cx, cy))

    # 4. Bold wrapped manga title
    title_font = load_font(52, bold=True)
    lines = textwrap.wrap(title, width=22)[:2]
    y_text = 1075
    for line in lines:
        tb = draw.textbbox((0, 0), line, font=title_font)
        tw = tb[2] - tb[0]
        draw.text(((W - tw) // 2, y_text), line, font=title_font, fill=(255, 255, 255, 255))
        y_text += 66

    # 5. Genres & CTA footer
    sub_font = load_font(30, bold=False)
    sub_text = f"{genres}  |  Canon Watch Order & Box Sets"
    sb = draw.textbbox((0, 0), sub_text, font=sub_font)
    draw.text(((W - (sb[2] - sb[0])) // 2, y_text + 16), sub_text, font=sub_font, fill=(200, 210, 225, 255))

    brand_font = load_font(34, bold=True)
    brand_text = "KOMAVELT HUB  •  TAP FOR GUIDE"
    bb = draw.textbbox((0, 0), brand_text, font=brand_font)
    draw.text(((W - (bb[2] - bb[0])) // 2, 1390), brand_text, font=brand_font, fill=(0, 229, 255, 255))

    canvas.convert("RGB").save(out_path, "JPEG", quality=90)

def fetch_manga():
    day_page = (datetime.now(timezone.utc).day % 10) + 1
    payload = json.dumps({"query": QUERY, "variables": {"page": day_page}}).encode("utf-8")
    req = urllib.request.Request(
        ANILIST_API,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "KomaVelt-RSS-Bot/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["data"]["Page"]["media"]

def build_rss(items):
    os.makedirs(PINS_DIR, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    date_tag = datetime.now(timezone.utc).strftime("%Y%m%d")
    xml_items = []

    for idx, m in enumerate(items, start=1):
        title = m["title"].get("english") or m["title"].get("romaji") or "Top Manga"
        raw_img = m["coverImage"].get("extraLarge") or m["coverImage"].get("large") or ""
        genres = ", ".join((m.get("genres") or [])[:3])
        raw_desc = (m.get("description") or "").replace("\n", " ")
        short_desc = (raw_desc[:140] + "...") if len(raw_desc) > 140 else raw_desc

        # Overwrite pin_1.jpg..pin_3.jpg daily to keep repo lightweight; cache-bust via ?v=date_tag
        pin_filename = f"pin_{idx}.jpg"
        pin_path = os.path.join(PINS_DIR, pin_filename)
        try:
            create_branded_pin(raw_img, title, genres, pin_path)
            img_url = f"{SITE_URL}{PINS_DIR}/{pin_filename}?v={date_tag}"
        except Exception as e:
            print(f"Pin graphic fallback for {title}: {e}")
            img_url = raw_img

        pin_title = f"{title} Original Manga & Watch Guide | KomaVelt India"
        pin_desc = (
            f"Explore {title} ({genres}) on KomaVelt. Check original manga deals on Amazon India, "
            f"canon watch orders & box sets. {short_desc} "
            f"#MangaIndia #OriginalManga #MangaDeals #AnimeWatchOrder #KomaVelt"
        )
        link = f"{SITE_URL}?manga={m['id']}&utm_source=pinterest&utm_medium=auto_pin"
        guid = f"komavelt-{m['id']}-{date_tag}"

        xml_items.append(f"""    <item>
      <title>{escape(pin_title)}</title>
      <link>{escape(link)}</link>
      <guid isPermaLink="false">{escape(guid)}</guid>
      <pubDate>{now}</pubDate>
      <description>{escape(pin_desc)}</description>
      <enclosure url="{escape(img_url)}" type="image/jpeg" />
      <media:content url="{escape(img_url)}" medium="image" />
    </item>""")

    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
  <channel>
    <title>KomaVelt — Original Manga Deals &amp; Anime Guides</title>
    <link>{SITE_URL}</link>
    <description>Daily trending Japanese manga, box set deals in India, and anime watch orders from KomaVelt.</description>
    <lastBuildDate>{now}</lastBuildDate>
{chr(10).join(xml_items)}
  </channel>
</rss>
"""
    with open("rss.xml", "w", encoding="utf-8") as f:
        f.write(rss)
    print(f"Generated rss.xml and {len(items)} branded Pins.")

if __name__ == "__main__":
    manga_list = fetch_manga()
    build_rss(manga_list)
