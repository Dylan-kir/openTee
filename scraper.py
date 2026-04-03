import requests
import os
from datetime import datetime, timedelta

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://thjwkelgihbtqtevcfyp.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

# All Denver metro courses on GolfNow — IDs confirmed from golfnow.com URLs
COURSES = [
    # City of Denver Municipal
    {"name": "City Park Golf Course",          "facility_id": 1946,  "location": "Denver",     "type": "Municipal"},
    {"name": "Wellshire Golf Course",           "facility_id": 1790,  "location": "Denver",     "type": "Municipal"},
    {"name": "Willis Case Golf Course",         "facility_id": 1944,  "location": "Denver",     "type": "Municipal"},
    {"name": "Kennedy Golf Course",             "facility_id": 1942,  "location": "Denver",     "type": "Municipal"},
    {"name": "Overland Park Golf Course",       "facility_id": 1948,  "location": "Denver",     "type": "Municipal"},
    # Littleton / Southwest Denver
    {"name": "Arrowhead Golf Club",             "facility_id": 453,   "location": "Littleton",  "type": "Public"},
    {"name": "Raccoon Creek Golf Course",       "facility_id": 515,   "location": "Littleton",  "type": "Public"},
    # Aurora
    {"name": "CommonGround Golf Course",        "facility_id": 5275,  "location": "Aurora",     "type": "Public"},
    {"name": "Murphy Creek Golf Course",        "facility_id": 17879, "location": "Aurora",     "type": "Public"},
    {"name": "Saddle Rock Golf Course",         "facility_id": 17877, "location": "Aurora",     "type": "Public"},
    {"name": "Meadow Hills Golf Course",        "facility_id": 17880, "location": "Aurora",     "type": "Public"},
    {"name": "Aurora Hills Golf Course",        "facility_id": 17878, "location": "Aurora",     "type": "Municipal"},
    {"name": "Heather Ridge Golf Course",       "facility_id": 9459,  "location": "Aurora",     "type": "Public"},
    # Foothills / West Denver
    {"name": "Foothills Golf Course",           "facility_id": 6826,  "location": "Denver",     "type": "Public"},
    # Broomfield / North Denver
    {"name": "Omni Interlocken Resort",         "facility_id": 594,   "location": "Broomfield", "type": "Resort"},
    # Green Valley Ranch / NE Denver
    {"name": "Green Valley Ranch Golf Club",    "facility_id": 517,   "location": "Denver",     "type": "Public"},
    # Evergreen / Mountain
    {"name": "Evergreen Golf Course",           "facility_id": 14331, "location": "Evergreen",  "type": "Public"},
]

def ensure_course_exists(course):
    """Make sure the course is in Supabase, insert if not."""
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/courses",
        headers=HEADERS,
        params={"name": f"eq.{course['name']}", "select": "id"},
        timeout=10
    )
    data = res.json()
    if data:
        return data[0]["id"]

    # Insert the course
    insert_res = requests.post(
        f"{SUPABASE_URL}/rest/v1/courses",
        headers={**HEADERS, "Prefer": "return=representation"},
        json={
            "name": course["name"],
            "location": course["location"],
            "course_type": course["type"],
            "source": "GolfNow",
            "holes": 18,
        },
        timeout=10
    )
    inserted = insert_res.json()
    if isinstance(inserted, list) and inserted:
        print(f"  Added new course: {course['name']}")
        return inserted[0]["id"]
    return None

def clear_old_tee_times():
    now = datetime.utcnow().isoformat()
    requests.delete(
        f"{SUPABASE_URL}/rest/v1/tee_times",
        headers=HEADERS,
        params={"tee_time": f"lt.{now}"},
        timeout=10
    )
    print("Cleared old tee times.")

def save_tee_times(tee_times):
    if not tee_times:
        return
    # Save in batches of 50
    for i in range(0, len(tee_times), 50):
        batch = tee_times[i:i+50]
        res = requests.post(
            f"{SUPABASE_URL}/rest/v1/tee_times",
            headers={**HEADERS, "Prefer": "resolution=merge-duplicates"},
            json=batch,
            timeout=15
        )
        print(f"  Batch {i//50 + 1}: saved {len(batch)} times, status {res.status_code}")

def scrape_golfnow(course, date, db_id):
    """Scrape tee times for one course on one date."""
    golfnow_headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.golfnow.com/",
    }

    url = "https://api.golfnow.com/v2/tee-times/search"
    params = {
        "facilityId": course["facility_id"],
        "date": date,
        "holes": 18,
        "players": 1,
        "time": "0500-2000",
    }

    try:
        res = requests.get(url, params=params, headers=golfnow_headers, timeout=15)

        if res.status_code != 200:
            print(f"  {course['name']}: HTTP {res.status_code}")
            return []

        data = res.json()
        times = []
        if isinstance(data, list):
            times = data
        elif isinstance(data, dict):
            times = (
                data.get("teeTimes") or
                data.get("tee_times") or
                data.get("results") or
                data.get("data") or []
            )

        results = []
        for t in times:
            try:
                time_str = (
                    t.get("time") or
                    t.get("teeTime") or
                    t.get("startTime") or
                    t.get("TeeTimes") or ""
                )
                if not time_str:
                    continue

                tee_dt = None
                for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ"]:
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
                    t.get("rate") or t.get("price") or
                    t.get("greenFee") or t.get("lowestRate") or
                    t.get("GreenFee") or 0
                )
                spots = int(
                    t.get("availableSpots") or t.get("spotsAvailable") or
                    t.get("players") or t.get("Players") or 4
                )
                holes = int(t.get("holes") or t.get("Holes") or 18)

                results.append({
                    "course_id": db_id,
                    "tee_time": tee_dt.isoformat(),
                    "price": price,
                    "spots_available": min(spots, 4),
                    "holes": holes,
                    "source_url": f"https://www.golfnow.com/tee-times/facility/{course['facility_id']}/search",
                    "scraped_at": datetime.utcnow().isoformat(),
                })
            except Exception as e:
                continue

        return results

    except requests.exceptions.RequestException as e:
        print(f"  Request error for {course['name']}: {e}")
        return []

def run():
    print(f"\n--- OpenTee Scraper started at {datetime.now().strftime('%H:%M:%S')} ---")
    print(f"Scraping {len(COURSES)} courses across Denver metro area")

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
            print(f"  Skipping {course['name']} — could not get DB id")
            continue

        course_total = 0
        for date in dates:
            times = scrape_golfnow(course, date, db_id)
            all_tee_times.extend(times)
            course_total += len(times)

        print(f"  {course['name']} ({course['location']}): {course_total} times found")

    if all_tee_times:
        save_tee_times(all_tee_times)
        print(f"\nDone. Total tee times saved: {len(all_tee_times)} across {len(COURSES)} courses")
    else:
        print("\nNo tee times found this run. GolfNow API may require different auth.")
        print("The scraper will keep retrying every 2 minutes automatically.")

    print("--- Scraper finished ---\n")

if __name__ == "__main__":
    run()
