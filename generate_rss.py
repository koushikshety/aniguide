import io
import json
import os
import re
import subprocess
import textwrap
import urllib.request
from datetime import datetime, timezone
from xml.sax.saxutils import escape
from PIL import Image, ImageDraw, ImageFilter, ImageFont

SITE_URL = "https://aniguide.aniguide-hub.workers.dev/"
ANILIST_API = "https://graphql.anilist.co"
PINS_DIR = "pins"
REELS_DIR = "reels"

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

def build_graphic(cover, title, genres, W, H, out_path):
    bg = cover.resize((W, H), Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(28))
    overlay = Image.new("RGBA", (W, H), (10, 12, 20, 195))
    canvas = Image.alpha_composite(bg.convert("RGBA"), overlay)
    draw = ImageDraw.Draw(canvas)

    is_reel = H > 1500
    badge_font = load_font(32 if is_reel else 28, bold=True)
    badge_text = "ORIGINAL MANGA DEALS • AMAZON INDIA"
    bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
    bw, bh = bbox[2] - bbox[0], bbox[3] - bbox[1]
    by1 = 150 if is_reel else 45
    bx1, bx2, by2 = (W - bw) // 2 - 30, (W + bw) // 2 + 30, by1 + bh + 26
    draw.rounded_rectangle([bx1, by1, bx2, by2], radius=22, fill=(230, 0, 35, 255))
    draw.text(((W - bw) // 2, by1 + 11), badge_text, font=badge_font, fill=(255, 255, 255, 255))

    target_h = 920 if is_reel else 680
    ratio = target_h / cover.height
    target_w = min(int(cover.width * ratio), 680 if is_reel else 540)
    cover_resized = cover.resize((target_w, target_h), Image.Resampling.LANCZOS)
    cx = (W - target_w) // 2
    cy = 280 if is_reel else 140
    draw.rounded_rectangle([cx - 8, cy - 8, cx + target_w + 8, cy + target_h + 8], radius=16, fill=(255, 255, 255, 45))
    canvas.paste(cover_resized, (cx, cy))

    title_font = load_font(54 if is_reel else 48, bold=True)
    wrapped = textwrap.wrap(title, width=22 if is_reel else 24)
    lines = wrapped[:2]
    if len(wrapped) > 2:
        lines[1] = lines[1][:19].rstrip() + "..."
    y_text = 1260 if is_reel else 860
    for line in lines:
        tb = draw.textbbox((0, 0), line, font=title_font)
        draw.text(((W - (tb[2] - tb[0])) // 2, y_text), line, font=title_font, fill=(255, 255, 255, 255))
        y_text += 66 if is_reel else 58

    sub_font = load_font(30 if is_reel else 28, bold=False)
    sub_text = f"{genres}  |  Watch Order & Box Sets" if genres else "Canon Watch Order & Box Sets"
    sb = draw.textbbox((0, 0), sub_text, font=sub_font)
    draw.text(((W - (sb[2] - sb[0])) // 2, y_text + 20), sub_text, font=sub_font, fill=(200, 210, 225, 255))

    brand_font = load_font(36 if is_reel else 32, bold=True)
    brand_text = "KOMAVELT HUB  •  LINK IN BIO"
    bb = draw.textbbox((0, 0), brand_text, font=brand_font)
    draw.text(((W - (bb[2] - bb[0])) // 2, 1660 if is_reel else 1155), brand_text, font=brand_font, fill=(0, 229, 255, 255))

    canvas.convert("RGB").save(out_path, "JPEG", quality=90)

def create_reel_video(frame_path, mp4_path):
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", frame_path,
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-vf", "scale=1080:1920,zoompan=z='min(zoom+0.001,1.10)':d=150:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=25",
        "-t", "6",
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest", "-movflags", "+faststart",
        mp4_path,
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

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
    os.makedirs(REELS_DIR, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    date_tag = datetime.now(timezone.utc).strftime("%Y%m%d")
    xml_items = []

    for idx, m in enumerate(items, start=1):
        title = m["title"].get("english") or m["title"].get("romaji") or "Top Manga"
        title = title.replace("<", "").replace(">", "")
        raw_img = m["coverImage"].get("extraLarge") or m["coverImage"].get("large") or ""
        genres = ", ".join((m.get("genres") or [])[:3])

        raw_desc = re.sub(r"<[^>]+>", " ", m.get("description") or "")
        raw_desc = raw_desc.replace("<", "").replace(">", "").replace("\n", " ")
        raw_desc = re.sub(r"\s+", " ", raw_desc).strip()
        short_desc = (raw_desc[:140] + "...") if len(raw_desc) > 140 else raw_desc

        pin_filename = f"pin_{idx}.jpg"
        pin_path = os.path.join(PINS_DIR, pin_filename)
        reel_filename = f"reel_{idx}.mp4"
        reel_path = os.path.join(REELS_DIR, reel_filename)
        tmp_frame = os.path.join(REELS_DIR, f"tmp_{idx}.jpg")

        img_url = raw_img
        video_url = ""
        try:
            req = urllib.request.Request(raw_img, headers={"User-Agent": "KomaVelt-RSS-Bot/1.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                cover = Image.open(io.BytesIO(resp.read())).convert("RGB")
            build_graphic(cover, title, genres, 1000, 1250, pin_path)
            img_url = f"{SITE_URL}{PINS_DIR}/{pin_filename}?v={date_tag}"

            build_graphic(cover, title, genres, 1080, 1920, tmp_frame)
            create_reel_video(tmp_frame, reel_path)
            os.remove(tmp_frame)
            video_url = f"{SITE_URL}{REELS_DIR}/{reel_filename}?v={date_tag}"
        except Exception as e:
            print(f"Media generation fallback for {title}: {e}")

        pin_title = f"{title} Original Manga & Watch Guide | KomaVelt India"
        if len(pin_title) > 100:
            pin_title = pin_title[:97].rstrip() + "..."

        pin_desc = (
            f"Explore {title} ({genres}) on KomaVelt. Check original manga deals on Amazon India, "
            f"canon watch orders & box sets. {short_desc} "
            f"#MangaIndia #OriginalManga #MangaDeals #AnimeWatchOrder #KomaVelt"
        )
        link = f"{SITE_URL}?manga={m['id']}&utm_source=pinterest&utm_medium=auto_pin"
        guid = f"komavelt-{m['id']}-{date_tag}"

        media_tag = (
            f'<media:content url="{escape(video_url)}" medium="video" type="video/mp4" />'
            if video_url
            else f'<media:content url="{escape(img_url)}" medium="image" />'
        )

        xml_items.append(f"""    <item>
      <title>{escape(pin_title)}</title>
      <link>{escape(link)}</link>
      <guid isPermaLink="false">{escape(guid)}</guid>
      <pubDate>{now}</pubDate>
      <description>{escape(pin_desc)}</description>
      <enclosure url="{escape(img_url)}" type="image/jpeg" />
      {media_tag}
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
    print(f"Generated rss.xml, {len(items)} pins, and {len(items)} reels.")

if __name__ == "__main__":
    manga_list = fetch_manga()
    build_rss(manga_list)
