#!/usr/bin/env python3
"""
SF Tennis Court Availability Checker

Checks all SF Rec & Park tennis courts for open reservable slots
on a given date, optionally filtered by time or time range.

Usage:
    python check_availability.py 2026-04-20                     # Show all availability
    python check_availability.py 2026-04-20 10:00               # Courts available at 10:00 AM
    python check_availability.py 2026-04-20 "3:00 PM"           # Courts available at 3:00 PM
    python check_availability.py 2026-04-20 10:00 14:00         # Courts available between 10am-2pm
    python check_availability.py 2026-04-20 "9:00 AM" "1:00 PM" # Same, 12-hour format
"""

import sys
import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

API_BASE = "https://api.rec.us/v1"

# All SF Rec & Park tennis court locations: (uuid, display_name)
LOCATIONS = [
    ("81cd2b08-8ea6-40ee-8c89-aeba92506576", "Alice Marble"),
    ("c41c7b8f-cb09-415a-b8ea-ad4b82d792b9", "Balboa"),
    ("3f842b1e-13f9-447d-ab12-62b62d954d3e", "Buena Vista"),
    ("779905bd-4c2b-45b3-abd0-48140998bca1", "Crocker Amazon"),
    ("95745483-6b38-4e99-8ba2-a3e23cda8587", "Dolores"),
    ("d3fc78ce-0617-40dc-b7f7-d41ba95f09ef", "DuPont"),
    ("070037ab-f407-486a-9f88-989905be1039", "Fulton"),
    ("16fdf80f-4e50-452a-843f-63d159c798e2", "Glen Canyon"),
    ("8c3b9b04-a149-4080-b648-e3ff8365bbee", "Hamilton"),
    ("3552b6f7-e7bd-4334-9e4a-731b015447e0", "Helen Wills"),
    ("7a8ef25a-dc20-4046-8aab-7212a9a41d20", "J.P. Murphy"),
    ("360736ab-a655-478d-aab5-4e54fea0c140", "Jackson"),
    ("8f8e510f-e0d8-4364-8531-a9a0d0d6b2b8", "Joe DiMaggio"),
    ("c4fc2b3e-d1bc-47d9-b920-76d00d32b20b", "Lafayette"),
    ("9d05fa5b-38fc-49b7-88c5-74825703d936", "McLaren"),
    ("bb6254d3-0ef0-475d-8de9-ac7d6b0323f4", "Minnie & Lovie Ward"),
    ("5a52a5e8-2e9f-4976-8a5c-0bc53d51afe9", "Miraloma"),
    ("fb0d16b1-5f9f-465f-8ebf-fccf5d400c47", "Moscone"),
    ("af2cd971-0c10-479d-a12e-ca63d55f71be", "Mountain Lake"),
    ("5a0b8fa6-11db-433e-9314-bafb956d8622", "Parkside Square"),
    ("032e605f-6065-4794-9675-b1bbebe18159", "Potrero Hill"),
    ("c2f20478-83d8-48c9-af3d-065d7ba22d60", "Presidio Wall"),
    ("95f7e887-5096-463b-834a-09d67889557e", "Richmond"),
    ("ad9e28e1-2d02-4fb5-b31d-b75f63841814", "Rossi"),
    ("25eafd72-ca31-4df7-8850-79c05edf3796", "St. Mary's"),
    ("1a5a0d4b-ef5d-44ab-a8ab-a13f39dcdc7d", "Stern Grove"),
    ("fe61cfdb-abf7-4f52-8ce4-45feb58f10b7", "Sunset"),
    ("2a18ef67-333c-4d9c-a86c-e0709f07f5c3", "Upper Noe"),
]


def parse_time(time_str):
    """Parse a time string into hours as a float (e.g., '14:30' -> 14.5)."""
    time_str = time_str.strip()
    # Try 12-hour format: "3:00 PM", "10:00 AM"
    for fmt in ("%I:%M %p", "%I:%M%p", "%I %p", "%I%p"):
        try:
            t = datetime.strptime(time_str.upper(), fmt)
            return t.hour + t.minute / 60.0
        except ValueError:
            continue
    # Try 24-hour format: "14:30", "9:00"
    try:
        parts = time_str.split(":")
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
        return h + m / 60.0
    except (ValueError, IndexError):
        pass
    raise ValueError(f"Cannot parse time: '{time_str}'")


def format_time(hours_float):
    """Convert hours float to 12-hour display string (e.g., 14.5 -> '2:30 PM')."""
    h = int(hours_float)
    m = int((hours_float - h) * 60)
    period = "AM" if h < 12 else "PM"
    display_h = h if h <= 12 else h - 12
    if display_h == 0:
        display_h = 12
    return f"{display_h}:{m:02d} {period}"


def fetch_schedule(location_id, date_str):
    """Fetch schedule for a location on a given date from the rec.us API."""
    url = f"{API_BASE}/locations/{location_id}/schedule?startDate={date_str}"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def parse_available_slots(schedule_data, date_str):
    """Extract RESERVABLE time slots from schedule data.

    Returns list of dicts: [{"court": "Court 1", "slots": [(start, end), ...]}]
    where start/end are floats representing hours (e.g., 10.5 = 10:30).
    """
    date_key = date_str.replace("-", "")
    courts = schedule_data.get("dates", {}).get(date_key, [])
    results = []

    for court in courts:
        court_name = court.get("courtNumber", "Unknown")
        schedule = court.get("schedule", {})
        reservable = []

        for time_range, details in schedule.items():
            if details.get("referenceType") == "RESERVABLE":
                try:
                    start_str, end_str = time_range.split(", ")
                    start = parse_time(start_str)
                    end = parse_time(end_str)
                    reservable.append((start, end))
                except (ValueError, IndexError):
                    continue

        if reservable:
            reservable.sort()
            results.append({"court": court_name, "slots": reservable})

    return results


def slot_matches(slot_start, slot_end, filter_start, filter_end):
    """Check if a reservable slot overlaps with the requested time window."""
    return slot_start < filter_end and slot_end > filter_start


def print_usage():
    print("Usage: python check_availability.py DATE [TIME] [END_TIME]")
    print()
    print("  DATE       Date to check (YYYY-MM-DD)")
    print("  TIME       Optional: specific time or range start (e.g., 10:00, '3:00 PM')")
    print("  END_TIME   Optional: range end time (e.g., 14:00, '5:00 PM')")
    print()
    print("Examples:")
    print("  python check_availability.py 2026-04-20")
    print("  python check_availability.py 2026-04-20 10:00")
    print('  python check_availability.py 2026-04-20 "9:00 AM" "1:00 PM"')


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print_usage()
        sys.exit(0)

    # Parse date
    date_str = sys.argv[1]
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        print(f"Error: Invalid date format '{date_str}'. Use YYYY-MM-DD.")
        sys.exit(1)

    # Parse optional time filter
    filter_start = None
    filter_end = None
    if len(sys.argv) >= 3:
        try:
            filter_start = parse_time(sys.argv[2])
        except ValueError:
            print(f"Error: Cannot parse time '{sys.argv[2]}'")
            sys.exit(1)

        if len(sys.argv) >= 4:
            try:
                filter_end = parse_time(sys.argv[3])
            except ValueError:
                print(f"Error: Cannot parse end time '{sys.argv[3]}'")
                sys.exit(1)
        else:
            # Single time: find slots that contain this time
            filter_end = filter_start + 0.01  # tiny window to check overlap

    date_display = date_obj.strftime("%A, %B %d, %Y")
    print(f"Checking tennis court availability for {date_display}")
    if filter_start is not None:
        if filter_end and filter_end - filter_start > 0.02:
            print(f"Time range: {format_time(filter_start)} - {format_time(filter_end)}")
        else:
            print(f"Time: {format_time(filter_start)}")
    print(f"Checking {len(LOCATIONS)} locations...\n")

    # Fetch all schedules in parallel
    def fetch_one(loc_tuple):
        loc_id, loc_name = loc_tuple
        data = fetch_schedule(loc_id, date_str)
        if "error" in data:
            return (loc_name, None, data["error"])
        available = parse_available_slots(data, date_str)
        return (loc_name, available, None)

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(fetch_one, LOCATIONS))

    # Filter and display results
    found_any = False
    errors = []

    for loc_name, courts, error in sorted(results, key=lambda x: x[0]):
        if error:
            errors.append((loc_name, error))
            continue
        if not courts:
            continue

        # Filter slots if time specified
        matching_courts = []
        for court_info in courts:
            if filter_start is not None:
                matching_slots = [
                    s for s in court_info["slots"]
                    if slot_matches(s[0], s[1], filter_start, filter_end)
                ]
            else:
                matching_slots = court_info["slots"]

            if matching_slots:
                matching_courts.append({
                    "court": court_info["court"],
                    "slots": matching_slots,
                })

        if matching_courts:
            if not found_any:
                print("=" * 60)
                print("AVAILABLE COURTS")
                print("=" * 60)
            found_any = True
            print(f"\n  {loc_name}")
            for court_info in matching_courts:
                slots_str = ", ".join(
                    f"{format_time(s)}-{format_time(e)}"
                    for s, e in court_info["slots"]
                )
                print(f"    {court_info['court']}: {slots_str}")

    if not found_any:
        print("No available courts found for the specified date/time.")

    if errors:
        print(f"\n({len(errors)} location(s) could not be checked)")

    print()


if __name__ == "__main__":
    main()
