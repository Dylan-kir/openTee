import requests
from datetime import datetime, timedelta
import json

# Supabase config
SUPABASE_URL = "https://thjwkelgihbtqtevcfyp.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InRoandrZWxnaWhidHF0ZXZjZnlwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzUxODgwODQsImV4cCI6MjA5MDc2NDA4NH0.abn1XtZLRiFVwS3osFGYOcXcffgVbWQmfrD2BRLTMlU"

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

# City of Denver course IDs on their booking system (TeeQuest/EZLinks)
DENVER_COURSES = [
    {"name": "City Park Golf Course",    "facility_id": "city-park"},
    {"name": "Wellshire Golf Course",    "facility_id": "wellshire"},
    {"name": "Willis Case Golf Course",  "facility_id": "willis-case"},
    {"name": "Kennedy Golf Course",      "facility_id": "kennedy"},
    {"name": "Overland Park Golf Course","facility_id": "overland-park"},
]

def get_course_db_id(name):
    """Look up the course ID in Supabase by name."""
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/courses",
        headers=HEADERS,
        params={"name": f"eq.{name}", "select": "id"}
    )
    data = res.json()
    if data:
        return data[0]["id"]
    return None

def clear_old_tee_times():
    """Delete tee times older than now to keep database clean."""
    now = datetime.utcnow().isoformat()
    requests.delete(
        f"{SUPABASE_URL}/rest/v1/tee_times",
        headers=HEADERS,
        params={"tee_time": f"lt.{now}"}
    )
    print("Cleared old tee times.")

def save_tee_times(tee_times):
    """Insert a batch of tee times into Supabase."""
    if not tee_times:
        return
    res = requests.post(
        f"{SUPABASE_URL}/rest/v1/tee_times",
        headers={**HEADERS, "Prefer": "resolution=merge-duplicates"},
        json=tee_times
    )
    print(f"Saved {len(tee_times)} tee times. Status: {res.status_code}")

def scrape_denver_city_golf():
    """
    Scrape City of Denver Golf tee times.
    Denver uses the EZLinks/ForeUp booking platform.
    API endpoint: https://foreupsoftware.com/index.php/api/booking/times
    """
    all_tee_times = []

    # Scrape next 2 days
    for day_offset in range(2):
        date = (datetime.now() + timedelta(days=day_offset)).strftime("%m-%d-%Y")

        for course in DENVER_COURSES:
            course_db_id = get_course_db_id(course["name"])
            if not course_db_id:
                print(f"Could not find DB id for {course['name']}, skipping.")
                continue

            # ForeUp API - used by City of Denver Golf
            # These are the real booking IDs for Denver courses
            foreup_ids = {
                "city-park":    "19172",
                "wellshire":    "19173",
                "willis-case":  "19174",
                "kennedy":      "19175",
                "overland-park":"19176",
            }

            foreup_id = foreup_ids.get(course["facility_id"])
            if not foreup_id:
                continue

            url = "https://foreupsoftware.com/index.php/api/booking/times"
            params = {
                "time":         "all",
                "date":         date,
                "holes":        "all",
                "players":      "0",
                "booking_class":"1",
                "schedule_id":  foreup_id,
                "schedule_ids[]": foreup_id,
                "specials_only":"0",
                "api_key":      "no_limits",
            }
            headers_foreup = {
                "X-Authorization": "no_limits",
                "Referer": "https://foreupsoftware.com/",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            }

            try:
                res = requests.get(url, params=params, headers=headers_foreup, timeout=10)
                if res.status_code != 200:
                    print(f"  {course['name']} on {date}: HTTP {res.status_code}")
                    continue

                times = res.json()
                print(f"  {course['name']} on {date}: {len(times)} times found")

                for t in times:
                    try:
                        # Parse the time from ForeUp format
                        tee_dt = datetime.strptime(f"{date} {t.get('time','')}", "%m-%d-%Y %I:%M%p")
                        tee_iso = tee_dt.isoformat()
                    except Exception:
                        continue

                    all_tee_times.append({
                        "course_id":        course_db_id,
                        "tee_time":         tee_iso,
                        "price":            float(t.get("green_fee", 0) or 0),
                        "spots_available":  int(t.get("available_spots", 4) or 4),
                        "holes":            int(t.get("holes", 18) or 18),
                        "source_url":       f"https://foreupsoftware.com/index.php/booking/{foreup_id}",
                        "scraped_at":       datetime.utcnow().isoformat(),
                    })

            except requests.exceptions.RequestException as e:
                print(f"  Error scraping {course['name']}: {e}")
                continue

    return all_tee_times

def run():
    print(f"\n--- OpenTee Scraper started at {datetime.now().strftime('%H:%M:%S')} ---")
    clear_old_tee_times()
    tee_times = scrape_denver_city_golf()
    if tee_times:
        save_tee_times(tee_times)
        print(f"Done. Total tee times saved: {len(tee_times)}")
    else:
        print("No tee times found — Denver courses may be closed or API changed.")
    print("--- Scraper finished ---\n")

if __name__ == "__main__":
    run()
