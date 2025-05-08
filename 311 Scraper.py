import requests

API_URL = "https://data.cityofnewyork.us/resource/erm2-nwe9.json"
TARGET_ADDRESS = "952A GREENE AVENUE"
BOROUGH = "BROOKLYN"
ZIP = "11221"

params = {
    "$limit": 10,
    "$order": "created_date DESC",
    "$where": (
        f"incident_address='{TARGET_ADDRESS}' AND "
        f"borough='{BOROUGH}' AND "
        f"incident_zip='{ZIP}'"
    )
}

response = requests.get(API_URL, params=params)
data = response.json()

if not data:
    print("No complaints found.")
else:
    print(f"Detailed 311 complaints for {TARGET_ADDRESS}, {BOROUGH}, NY {ZIP}:\n")
    for d in data:
        print(f"Date: {d.get('created_date', 'N/A')}")
        print(f"Type: {d.get('complaint_type', 'N/A')}")
        print(f"Descriptor: {d.get('descriptor', 'N/A')}")
        print(f"Agency: {d.get('agency', 'N/A')}")
        print(f"Status: {d.get('status', 'N/A')}")
        print(f"Closed Date: {d.get('closed_date', 'N/A')}")
        print(f"Resolution: {d.get('resolution_description', 'N/A')}")
        print(f"Location Type: {d.get('location_type', 'N/A')}")
        print(f"Incident ID: {d.get('incident_id', 'N/A')}")
        print(f"Latitude/Longitude: {d.get('latitude', 'N/A')}, {d.get('longitude', 'N/A')}")
        print("-" * 80)
