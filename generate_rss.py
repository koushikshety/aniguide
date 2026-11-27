import html
import glob
import io
import json
import os
import random
import re
import subprocess
import textwrap
import urllib.request
from datetime import datetime, timezone
from xml.sax.saxutils import escape
from PIL import Image, ImageDraw, ImageFilter, ImageFont

SITE_URL = "https://aniguide.aniguide-hub.workers.dev/"
RAW_BASE = "https://koushikshety.github.io/aniguide/"
ANILIST_API = "https://graphql.anilist.co"
PINS_DIR = "pins"
REELS_DIR = "reels"
TELEGRAM_CHAT_ID = "@KomaVeltDeals"

QUERY = """
query ($page: Int, $perPage: Int, $sort: [MediaSort]) {
  Page(page: $page, perPage: $perPage) {
    media(type: MANGA, countryOfOrigin: "JP", sort: $sort, isAdult: false) {
      id
      title { english romaji }
      description(asHtml: false)
      coverImage { extraLarge large }
      genres
      averageScore
    }
  }
}
"""

def sanitize_text(text):
    text = html.unescape(text or "")
    text = re.sub(
        r"</?(?:br|i|b|p|em|strong|a|span|div|h[1-6]|ul|ol|li)\b[^>]*>",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    text = text.replace("<", "").replace(">", "").replace("\n", " ")
    return re.sub(r"\s+", " ", text).strip()

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

def pick_bgm():
    tracks = glob.glob("Music/*.mp3") + glob.glob("music/*.mp3")
    if tracks:
        return random.choice(tracks)
    if os.path.exists("bgm.mp3"):
        return "bgm.mp3"
    return None

def draw_pill(draw, W, y, text, font, bg_color, text_color=(255, 255, 255, 255), pad_x=30, pad_y=12):
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x1, x2 = (W - tw) // 2 - pad_x, (W + tw) // 2 + pad_x
    y2 = y + th + pad_y * 2
    draw.rounded_rectangle([x1, y, x2, y2], radius=24, fill=bg_color)
    draw.text(((W - tw) // 2, y + pad_y - 2), text, font=font, fill=text_color)
    return y2

def build_graphic(cover, title, genres, score, W, H, out_path):
    bg = cover.resize((W, H), Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(28))
    overlay = Image.new("RGBA", (W, H), (10, 12, 20, 195))
    canvas = Image.alpha_composite(bg.convert("RGBA"), overlay)
    draw = ImageDraw.Draw(canvas)

    is_reel = H > 1500
    badge_font = load_font(32 if is_reel else 28, bold=True)
    draw_pill(draw, W, 140 if is_reel else 40, "ORIGINAL MANGA DEALS • AMAZON INDIA", badge_font, (230, 0, 35, 255))

    target_h = 880 if is_reel else 650
    ratio = target_h / cover.height
    target_w = min(int(cover.width * ratio), 660 if is_reel else 520)
    cover_resized = cover.resize((target_w, target_h), Image.Resampling.LANCZOS)
    cx = (W - target_w) // 2
    cy = 270 if is_reel else 135

    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        [cx - 12, cy + 16, cx + target_w + 12, cy + target_h + 24], radius=20, fill=(0, 0, 0, 175)
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(22))
    canvas = Image.alpha_composite(canvas, shadow)
    draw = ImageDraw.Draw(canvas)

    draw.rounded_rectangle([cx - 6, cy - 6, cx + target_w + 6, cy + target_h + 6], radius=16, fill=(255, 255, 255, 55))
    canvas.paste(cover_resized, (cx, cy))

    if score:
        score_font = load_font(30 if is_reel else 26, bold=True)
        draw_pill(draw, W, cy + target_h - 28, f"★ {score}% RATED ON ANILIST", score_font, (245, 180, 0, 255), (15, 15, 20, 255), pad_x=24, pad_y=10)

    title_font = load_font(54 if is_reel else 46, bold=True)
    wrapped = textwrap.wrap(title, width=22 if is_reel else 24)
    lines = wrapped[:2]
    if len(wrapped) > 2:
        lines[1] = lines[1][:19].rstrip() + "..."
    y_text = (cy + target_h + 60) if is_reel else (cy + target_h + 52)
    for line in lines:
        tb = draw.textbbox((0, 0), line, font=title_font)
        draw.text(((W - (tb[2] - tb[0])) // 2, y_text), line, font=title_font, fill=(255, 255, 255, 255))
        y_text += 66 if is_reel else 56

    sub_font = load_font(30 if is_reel else 26, bold=False)
    sub_text = f"{genres}  |  Watch Order & Box Sets" if genres else "Canon Watch Order & Box Sets"
    sb = draw.textbbox((0, 0), sub_text, font=sub_font)
    draw.text(((W - (sb[2] - sb[0])) // 2, y_text + 16), sub_text, font=sub_font, fill=(200, 210, 225, 255))

    brand_font = load_font(32 if is_reel else 28, bold=True)
    brand_text = "WATCH ORDER & MANGA  •  LINK IN BIO"
    if is_reel:
        draw_pill(draw, W, 1540, brand_text, brand_font, (0, 180, 216, 255), (10, 12, 20, 255), pad_x=34, pad_y=16)
    else:
        bb = draw.textbbox((0, 0), brand_text, font=brand_font)
        draw.text(((W - (bb[2] - bb[0])) // 2, 1160), brand_text, font=brand_font, fill=(0, 229, 255, 255))

    canvas.convert("RGB").save(out_path, "JPEG", quality=90)

def build_reel_slide2(cover, title, short_desc, out_path):
    W, H = 1080, 1920
    bg = cover.resize((W, H), Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(38))
    overlay = Image.new("RGBA", (W, H), (8, 10, 18, 220))
    canvas = Image.alpha_composite(bg.convert("RGBA"), overlay)
    draw = ImageDraw.Draw(canvas)

    draw_pill(draw, W, 280, "WHY YOU SHOULD READ THIS", load_font(34, bold=True), (0, 200, 230, 255), (10, 12, 20, 255))

    card_x1, card_y1, card_x2, card_y2 = 90, 460, W - 90, 1180
    draw.rounded_rectangle([card_x1, card_y1, card_x2, card_y2], radius=32, fill=(255, 255, 255, 22), outline=(255, 255, 255, 65), width=2)

    hook_font = load_font(42, bold=False)
    hook_text = short_desc if short_desc else f"Discover {title} original manga volumes, box set deals in India, and the complete canon watch order."
    lines = textwrap.wrap(hook_text, width=28)[:7]
    y_text = card_y1 + 85
    for line in lines:
        tb = draw.textbbox((0, 0), line, font=hook_font)
        draw.text(((W - (tb[2] - tb[0])) // 2, y_text), line, font=hook_font, fill=(240, 244, 250, 255))
        y_text += 68

    draw_pill(draw, W, 1290, 'COMMENT "MANGA" FOR DIRECT LINK', load_font(34, bold=True), (230, 0, 35, 255), pad_x=36, pad_y=20)

    cta_font = load_font(32, bold=True)
    cta_text = "KOMAVELT HUB  •  @KomaVeltHub"
    cb = draw.textbbox((0, 0), cta_text, font=cta_font)
    draw.text(((W - (cb[2] - cb[0])) // 2, 1435), cta_text, font=cta_font, fill=(0, 229, 255, 255))

    eng_font = load_font(28, bold=True)
    eng_text = "SUBSCRIBE / FOLLOW  •  COMMENT  •  SHARE"
    eb = draw.textbbox((0, 0), eng_text, font=eng_font)
    draw.text(((W - (eb[2] - eb[0])) // 2, 1500), eng_text, font=eng_font, fill=(255, 215, 0, 255))

    canvas.convert("RGB").save(out_path, "JPEG", quality=90)

def create_reel_video(slide1_path, slide2_path, mp4_path):
    bgm = pick_bgm()
    if bgm:
        start_sec = random.randint(8, 18)
        audio_inputs = ["-i", bgm]
        audio_filter = f"[2:a]atrim=start={start_sec}:duration=6,asetpts=PTS-STARTPTS,afade=t=in:st=0:d=0.4,afade=t=out:st=4.8:d=1.2[a]"
    else:
        audio_inputs = ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
        audio_filter = "[2:a]atrim=duration=6,asetpts=PTS-STARTPTS[a]"

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-t", "3", "-i", slide1_path,
        "-loop", "1", "-t", "3", "-i", slide2_path,
        *audio_inputs,
        "-filter_complex",
        "[0:v]scale=1080:1920,zoompan=z='min(zoom+0.0015,1.08)':d=75:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=25,setsar=1[v0];"
        "[1:v]scale=1080:1920,zoompan=z='min(zoom+0.0015,1.08)':d=75:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=25,setsar=1[v1];"
        f"[v0][v1]concat=n=2:v=1:a=0[v];{audio_filter}",
        "-map", "[v]", "-map", "[a]",
        "-t", "6",
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p", "-r", "25",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
        "-movflags", "+faststart",
        mp4_path,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(res.stderr[-400:])

def post_to_telegram(photo_path, title, genres, short_desc, link):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token or not os.path.exists(photo_path):
        return
    caption = (
        f"📚 {title}\n"
        f"🎭 {genres}\n\n"
        f"{sanitize_text(short_desc)}\n\n"
        f"🔥 Original Manga Deals (Amazon India) & Exact Watch Order:\n"
        f"👉 {link}\n\n"
        f"🐉 5,000+ Donghua & Manhua Hub:\n"
        f"👉 {SITE_URL}donghua-manhua?utm_source=telegram&utm_medium=channel\n\n"
        f"🔔 Follow & Join @KomaVeltDeals for daily anime, donghua & manga deals!\n"
        f"💬 Comment your favorite series below & 📤 Share with an anime friend!"
    )
    res = subprocess.run(
        [
            "curl", "-sS", "-w", "\nHTTP:%{http_code}", "-X", "POST",
            f"https://api.telegram.org/bot{token}/sendPhoto",
            "--form-string", f"chat_id={TELEGRAM_CHAT_ID}",
            "-F", f"photo=@{photo_path}",
            "--form-string", f"caption={caption[:1020]}",
        ],
        capture_output=True,
        text=True,
    )
    print(f"Telegram post ({title}) [code={res.returncode}]: {res.stdout.strip()} {res.stderr.strip()}")

def fetch_page(page, per_page, sort_by):
    payload = json.dumps({
        "query": QUERY,
        "variables": {"page": page, "perPage": per_page, "sort": [sort_by]},
    }).encode("utf-8")
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

def fetch_manga():
    day_of_year = datetime.now(timezone.utc).timetuple().tm_yday
    pop_page = (day_of_year % 25) + 1
    trend_page = (day_of_year % 15) + 1

    popular = fetch_page(pop_page, 2, "POPULARITY_DESC")
    trending = fetch_page(trend_page, 2, "TRENDING_DESC")

    seen = set()
    combined = []
    for item in popular + trending:
        if item["id"] not in seen:
            seen.add(item["id"])
            combined.append(item)
        if len(combined) == 3:
            break
    return combined

def build_rss(items):
    os.makedirs(PINS_DIR, exist_ok=True)
    os.makedirs(REELS_DIR, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    date_tag = datetime.now(timezone.utc).strftime("%Y%m%d")
    xml_items = []

    for idx, m in enumerate(items, start=1):
        title = sanitize_text(m["title"].get("english") or m["title"].get("romaji") or "Top Manga")
        raw_img = m["coverImage"].get("extraLarge") or m["coverImage"].get("large") or ""
        genres = ", ".join((m.get("genres") or [])[:3])
        score = m.get("averageScore")

        raw_desc = sanitize_text(m.get("description") or "")
        short_desc = (raw_desc[:160] + "...") if len(raw_desc) > 160 else raw_desc

        pin_filename = f"pin_{idx}.jpg"
        pin_path = os.path.join(PINS_DIR, pin_filename)
        reel_filename = f"reel_{idx}.mp4"
        reel_path = os.path.join(REELS_DIR, reel_filename)
        tmp_s1 = os.path.join(REELS_DIR, f"tmp_{idx}_1.jpg")
        tmp_s2 = os.path.join(REELS_DIR, f"tmp_{idx}_2.jpg")

        img_url = raw_img
        video_url = ""
        try:
            req = urllib.request.Request(raw_img, headers={"User-Agent": "KomaVelt-RSS-Bot/1.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                cover = Image.open(io.BytesIO(resp.read())).convert("RGB")
            build_graphic(cover, title, genres, score, 1000, 1250, pin_path)
            img_url = f"{RAW_BASE}{PINS_DIR}/{pin_filename}?v={date_tag}"

            build_graphic(cover, title, genres, score, 1080, 1920, tmp_s1)
            build_reel_slide2(cover, title, short_desc, tmp_s2)
            create_reel_video(tmp_s1, tmp_s2, reel_path)
            os.remove(tmp_s1)
            os.remove(tmp_s2)
            video_url = f"{RAW_BASE}{REELS_DIR}/{reel_filename}?v={date_tag}"
        except Exception as e:
            print(f"Media generation fallback for {title}: {e}")

        pin_title = f"{title} Original Manga & Watch Guide | KomaVelt India"
        if len(pin_title) > 100:
            pin_title = pin_title[:97].rstrip() + "..."

        pin_desc = (
            f"Comment \"MANGA\" and I'll send you the direct watch order & Amazon India box set link! 👇🔥\n"
            f"👉 Or tap the Related Video / Channel Bio Link right now.\n\n"
            f"🔔 Subscribe & Follow for daily anime, donghua & manga deals!\n"
            f"💬 Comment your favorite series below & 📤 Share this with an anime fan!\n\n"
            f"📚 KomaVelt Hub: {SITE_URL}\n"
            f"Explore {title} ({genres}) — {short_desc}\n\n"
            f"#MangaIndia #OriginalManga #MangaDeals #AnimeWatchOrder #KomaVelt"
        )
        link = f"{SITE_URL}?manga={m['id']}&utm_source=social&utm_medium=auto"
        tg_link = f"{SITE_URL}?manga={m['id']}&utm_source=telegram&utm_medium=channel"
        guid = f"komavelt-{m['id']}"

        post_to_telegram(pin_path, title, genres, short_desc, tg_link)

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
    <description>Daily popular &amp; trending Japanese manga, box set deals in India, and anime watch orders from KomaVelt.</description>
    <lastBuildDate>{now}</lastBuildDate>
{chr(10).join(xml_items)}
  </channel>
</rss>
"""
    with open("rss.xml", "w", encoding="utf-8") as f:
        f.write(rss)
    print(f"Generated rss.xml, {len(items)} pins, and {len(items)} 2-slide reels.")

if __name__ == "__main__":
    manga_list = fetch_manga()
    build_rss(manga_list)

# Auto-rotate daily Donghua campaigns & Telegram post
from dynamic_donghua import update_daily_donghua
update_daily_donghua(post_to_telegram)
