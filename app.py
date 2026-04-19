#!/usr/bin/env python3
"""
SF Tennis Court Availability Checker — Flask Web App

Provides a web UI and JSON API to check availability across all
SF Rec & Park reservable tennis courts.
"""

import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

API_BASE = "https://api.rec.us/v1"

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


def parse_time_24h(time_str):
    """Parse 'HH:MM' into hours float."""
    parts = time_str.strip().split(":")
    return int(parts[0]) + int(parts[1]) / 60.0


def format_time(hours_float):
    """Convert hours float to '2:30 PM' style string."""
    h = int(hours_float)
    m = int(round((hours_float - h) * 60))
    period = "AM" if h < 12 else "PM"
    display_h = h if h <= 12 else h - 12
    if display_h == 0:
        display_h = 12
    return f"{display_h}:{m:02d} {period}"


def fetch_schedule(location_id, date_str):
    """Fetch schedule JSON from rec.us API."""
    url = f"{API_BASE}/locations/{location_id}/schedule?startDate={date_str}"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def get_availability(date_str, filter_start=None, filter_end=None):
    """Fetch and parse availability for all locations.

    Returns list of dicts sorted by location name:
    [{"location": "...", "courts": [{"court": "Court 1", "slots": ["7:30 AM-12:00 PM"]}]}]
    """

    def fetch_one(loc_tuple):
        loc_id, loc_name = loc_tuple
        data = fetch_schedule(loc_id, date_str)
        if "error" in data:
            return None

        date_key = date_str.replace("-", "")
        courts_data = data.get("dates", {}).get(date_key, [])
        courts = []

        for court in courts_data:
            court_name = court.get("courtNumber", "Unknown")
            schedule = court.get("schedule", {})
            slots = []

            for time_range, details in schedule.items():
                if details.get("referenceType") != "RESERVABLE":
                    continue
                try:
                    start_str, end_str = time_range.split(", ")
                    start = parse_time_24h(start_str)
                    end = parse_time_24h(end_str)
                except (ValueError, IndexError):
                    continue

                if filter_start is not None:
                    if not (start < filter_end and end > filter_start):
                        continue

                slots.append((start, end))

            if slots:
                slots.sort()
                courts.append({
                    "court": court_name,
                    "slots": [f"{format_time(s)}-{format_time(e)}" for s, e in slots],
                })

        if courts:
            return {"location": loc_name, "courts": courts}
        return None

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(fetch_one, LOCATIONS))

    return sorted(
        [r for r in results if r is not None],
        key=lambda r: r["location"],
    )


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/availability")
def api_availability():
    date_str = request.args.get("date")
    if not date_str:
        return jsonify({"error": "date parameter required (YYYY-MM-DD)"}), 400

    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

    time_str = request.args.get("time")
    end_time_str = request.args.get("end_time")

    filter_start = None
    filter_end = None
    if time_str:
        try:
            filter_start = parse_time_24h(time_str)
        except (ValueError, IndexError):
            return jsonify({"error": f"Invalid time: {time_str}"}), 400

        if end_time_str:
            try:
                filter_end = parse_time_24h(end_time_str)
            except (ValueError, IndexError):
                return jsonify({"error": f"Invalid end_time: {end_time_str}"}), 400
        else:
            filter_end = filter_start + 0.01

    results = get_availability(date_str, filter_start, filter_end)
    return jsonify({"date": date_str, "results": results})


if __name__ == "__main__":
    app.run(debug=True, port=5001)
