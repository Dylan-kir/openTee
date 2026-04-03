import requests
import os
from datetime import datetime, timedelta

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://thjwkelgihbtqtevcfyp.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

# Supreme Golf course slugs — from supremegolf.com URLs
COURSES = [
    {"name": "City Park Golf Course",       "slug": "city-park-golf-course-colorado",         "location": "Denver",     "type": "Municipal"},
    {"name": "Wellshire Golf Course",        "slug": "wellshire-golf-course-colorado",          "location": "Denver",     "type": "Municipal"},
    {"name": "Willis Case Golf Course",      "slug": "willis-case-golf-course-colorado",        "location": "Denver",     "type": "Municipal"},
    {"name": "Kennedy Golf Course",          "slug": "kennedy-golf-course-colorado",            "location": "Denver",     "type": "Municipal"},
    {"name": "Overland Park Golf Course",    "slug": "overland-park-golf-course-colorado",      "location": "Denver",     "type": "Municipal"},
    {"name": "Arrowhead Golf Club",          "slug": "arrowhead-golf-club-colorado",            "location": "Littleton",  "type": "Public"},
    {"name": "Raccoon Creek Golf Course",    "slug": "raccoon-creek-golf-course-colorado",      "location": "Littleton",  "type": "Public"},
    {"name": "CommonGround Golf Course",     "slug": "commonground-golf-course-colorado",       "location": "Aurora",     "type": "Public"},
    {"name": "Murphy Creek Golf Course",     "slug": "murphy-creek-golf-course-colorado",       "location": "Aurora",     "type": "Public"},
    {"name": "Saddle Rock Golf Course",      "slug": "saddle-rock-golf-course-colorado",        "location": "Aurora",     "type": "Public"},
    {"name": "Meadow Hills Golf Course",     "slug": "meadow-hills-golf-course-colorado",       "location": "Aurora",     "type": "Public"},
    {"name": "Aurora Hills Golf Course",     "slug": "aurora-hills-golf-course-colorado",       "location": "Aurora",     "type": "Municipal"},
    {"name": "Heather Ridge Golf Course",    "slug": "heather-ridge-golf-course-colorado",      "location": "Aurora",     "type": "Public"},
    {"name": "Foothills Golf Course",        "slug": "foothills-golf-course-colorado",          "location": "Denver",     "type": "Public"},
    {"name": "Green Valley Ranch Golf Club", "slug": "green-valley-ranch-golf-club-colorado",   "location": "Denver",     "type": "Public"},
    {"name": "Evergreen Golf Course",        "slug": "evergreen-golf-course-colorado",          "location": "Evergreen",  "type": "Public"},
    {"name": "Omni Interlocken Resort",      "slug": "omni-interlocken-resort-golf-club-colorado", "location": "Broomfield", "type": "Resort"},
]

def ensure_course_exists(course):
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/courses",
        headers=SUPABASE_HEADERS,
        params={"name": f"eq.{course['name']}", "select": "id"},
        timeout=10
    )
    data = res.json()
    if data:
        return data[0]["id"]

    insert_res = requests.post(
        f"{SUPABASE_URL}/rest/v1/courses",
        headers={**SUPABASE_HEADERS, "Prefer": "return=representation"},
        json={
            "name": course["name"],
            "location": course["location"],
            "course_type": course["type"],
            "source": "Supreme Golf",
            "holes": 18,
        },
        timeout=10
    )
    inserted = insert_res.json()
    if isinstance(inserted, list) and inserted:
        print(f"  Added new course to DB: {course['name']}")
        return inserted[0]["id"]
    return None

def clear_old_tee_times():
    now = datetime.utcnow().isoformat()
    requests.delete(
        f"{SUPABASE_URL}/rest/v1/tee_times",
        headers=SUPABASE_HEADERS,
        params={"tee_time": f"lt.{now}"},
        timeout=10
    )
    print("Cleared old tee times.")

def save_tee_times(tee_times):
    if not tee_times:
        return
    for i in range(0, len(tee_times), 50):
        batch = tee_times[i:i+50]
        res = requests.post(
            f"{SUPABASE_URL}/rest/v1/tee_times",
            headers={**SUPABASE_HEADERS, "Prefer": "resolution=merge-duplicates"},
            json=batch,
            timeout=15
        )
        print(f"  Saved batch of {len(batch)}, status {res.status_code}")

def scrape_supreme_golf(course, date, db_id):
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Referer": "https://supremegolf.com/",
        "Origin": "https://supremegolf.com",
    }

    # Supreme Golf API endpoint
    url = "https://supremegolf.com/api/search/tee-times"
    params = {
        "date": date,
        "holes": 18,
        "players": 1,
        "courseSlug": course["slug"],
    }

    try:
        res = requests.get(url, params=params, headers=headers, timeout=15)
        print(f"  {course['name']} on {date}: HTTP {res.status_code}")

        if res.status_code != 200:
            return []

        data = res.json()

        # Supreme Golf returns results in various structures
        times = []
        if isinstance(data, list):
            times = data
        elif isinstance(data, dict):
            times = (
                data.get("teeTimes") or
                data.get("tee_times") or
                data.get("results") or
                data.get("data") or
                data.get("times") or []
            )

        results = []
        for t in times:
            try:
                time_str = (
                    t.get("time") or t.get("teeTime") or
                    t.get("startTime") or t.get("datetime") or ""
                )
                if not time_str:
                    continue

                tee_dt = None
                for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ",
                            "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%d %H:%M:%S"]:
                    try:
                        tee_dt = datetime.strptime(time_str[:19], fmt)
                        break
                    except ValueError:
                        continue
                if not tee_dt:
                    for fmt in ["%H:%M", "%I:%M %p", "%I:%M%p"]:
                        try:
                            tee_dt = datetime.strptime(f"{date} {time_str}", f"%Y-%m-%d {fmt}")
                            break
                        except ValueError:
                            continue

                if not tee_dt:
                    continue

                price = float(
                    t.get("price") or t.get("rate") or
                    t.get("greenFee") or t.get("lowestRate") or
                    t.get("totalPrice") or 0
                )
                spots = int(
                    t.get("availableSpots") or t.get("spotsAvailable") or
                    t.get("players") or t.get("maxPlayers") or 4
                )
                holes = int(t.get("holes") or 18)

                booking_url = (
                    t.get("bookingUrl") or
                    t.get("url") or
                    f"https://supremegolf.com/explore/united-states/colorado/{course['location'].lower()}/{course['slug']}"
                )

                results.append({
                    "course_id": db_id,
                    "tee_time": tee_dt.isoformat(),
                    "price": price,
                    "spots_available": min(spots, 4),
                    "holes": holes,
                    "source_url": booking_url,
                    "scraped_at": datetime.utcnow().isoformat(),
                })
            except Exception as e:
                continue

        return results

    except requests.exceptions.RequestException as e:
        print(f"  Request error for {course['name']}: {e}")
        return []

def run():
    print(f"\n--- OpenTee Scraper (Supreme Golf) started at {datetime.now().strftime('%H:%M:%S')} ---")
    print(f"Scraping {len(COURSES)} Denver metro courses")

    if not SUPABASE_KEY:
        print("ERROR: SUPABASE_KEY not set.")
        return

    clear_old_tee_times()

    all_tee_times = []
    dates = [
        (datetime.now() + timedelta(days=i)).strftime("%Y-%m-%d")
        for i in range(2)
    ]

    for course in COURSES:
        db_id = ensure_course_exists(course)
        if not db_id:
            print(f"  Skipping {course['name']} — no DB id")
            continue

        course_total = 0
        for date in dates:
            times = scrape_supreme_golf(course, date, db_id)
            all_tee_times.extend(times)
            course_total += len(times)

        print(f"  → {course['name']}: {course_total} total times")

    if all_tee_times:
        save_tee_times(all_tee_times)
        print(f"\nDone. {len(all_tee_times)} tee times saved across {len(COURSES)} courses.")
    else:
        print("\nNo tee times found. Will retry in 2 minutes.")

    print("--- Scraper finished ---\n")

if __name__ == "__main__":
    run()
