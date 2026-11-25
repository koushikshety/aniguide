import re
import datetime, json, urllib.request, html, os

ANILIST_API = "https://graphql.anilist.co"
SITE_URL = "https://aniguide.aniguide-hub.workers.dev/"

DONGHUA_QUERY = """
query ($page: Int, $perPage: Int) {
  Page(page: $page, perPage: $perPage) {
    media(type: ANIME, countryOfOrigin: "CN", sort: POPULARITY_DESC, isAdult: false) {
      id
      title { english romaji }
      genres
      averageScore
      description(asHtml: false)
      coverImage { extraLarge large }
    }
  }
}
"""

def update_daily_donghua(post_to_telegram_fn=None):
    day_num = datetime.date.today().timetuple().tm_yday
    page = ((day_num * 2) % 25) + 1  # Rotates through top 50+ famous Donghua daily
    payload = json.dumps({"query": DONGHUA_QUERY, "variables": {"page": page, "perPage": 2}}).encode("utf-8")
    req = urllib.request.Request(
        ANILIST_API,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "KomaVeltBot/1.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            items = json.loads(resp.read().decode("utf-8"))["data"]["Page"]["media"]
    except Exception as e:
        print("Dynamic Donghua fetch error:", e)
        return

    # Load existing campaigns.json and keep static non-dynamic entries
    camp_path = "ads/campaigns.json"
    campaigns = []
    if os.path.exists(camp_path):
        with open(camp_path, "r", encoding="utf-8") as f:
            campaigns = [c for c in json.load(f) if not c.get("dynamicDaily")]

    for m in items:
        title = m["title"].get("english") or m["title"].get("romaji") or "Top Donghua"
        genres = ", ".join((m.get("genres") or ["Action", "Fantasy"])[:3])
        score = m.get("averageScore") or 80
        raw_desc = re.sub(r"<[^>]+>", "", m.get("description") or "")
        short_desc = html.unescape(raw_desc).strip()[:150].rstrip() + "..."
        target = f"{SITE_URL}donghua-manhua.html?utm_source=social&utm_medium=daily_donghua"

        campaigns.insert(0, {
            "dynamicDaily": True,
            "title": f"{title} ({score}% Rated) — Today's Donghua Pick",
            "channel": "Reels / YouTube Shorts / Telegram",
            "keyword": "DONGHUA",
            "hookHeadline": f"Stop sleeping on {title} 🔥 ({genres})",
            "hookBody": f"{short_desc}\n\nComment DONGHUA for the watch guide & Follow for more! 🔔",
            "dmReply": f"Watch & explore {title} + 5,000+ Donghua here 👉 {target}\n\nJoin @KomaVeltDeals on Telegram for daily drops!",
            "pinterestTitle": f"{title} — Must-Watch Chinese Anime (Donghua) Guide",
            "pinterestDesc": f"{short_desc} Follow KomaVelt for daily anime, donghua & manga deals!",
            "amazonUrl": "https://www.amazon.in/s?k=manga+box+set&tag=aniguide-21",
            "targetUrl": target
        })

        # Post today's dynamic Donghua to Telegram if cover downloads
        if post_to_telegram_fn:
            img_url = (m.get("coverImage") or {}).get("extraLarge") or (m.get("coverImage") or {}).get("large")
            if img_url:
                tmp_img = f"/tmp/donghua_{m['id']}.jpg"
                try:
                    req_img = urllib.request.Request(img_url, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req_img, timeout=20) as r, open(tmp_img, "wb") as out_f:
                        out_f.write(r.read())
                    tg_link = f"{SITE_URL}donghua-manhua.html?utm_source=telegram&utm_medium=channel"
                    post_to_telegram_fn(tmp_img, f"{title} (Donghua)", genres, short_desc, tg_link)
                except Exception as e:
                    print("Donghua TG post error:", e)

    with open(camp_path, "w", encoding="utf-8") as f:
        json.dump(campaigns, f, indent=2, ensure_ascii=False)
    print(f"Updated {camp_path} with {len(items)} dynamic Donghua for day {day_num}")
