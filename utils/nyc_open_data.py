import requests
import pandas as pd
from datetime import datetime, timedelta

# Basic ZIP to NYPD precinct mapping (expand as needed)
ZIP_TO_PRECINCTS = {
    "11221": ["81", "83"],
    "11206": ["90", "79"],
    "11211": ["90", "94"],
    "11207": ["75", "73"],
    "11238": ["77", "88"],
    # Add more as needed
}

def get_crime_data(precincts, days=1095):  # 3 years
    """
    Fetches NYPD crime complaint data for the given precincts over the last `days` days.
    """
    if not precincts:
        return pd.DataFrame()

    endpoint = "https://data.cityofnewyork.us/resource/qgea-i56i.json"
    since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    precinct_filter = " OR ".join([f"addr_pct_cd='{p}'" for p in precincts])
    where_clause = f"cmplnt_fr_dt >= '{since_date}' AND ({precinct_filter})"

    params = {
        "$limit": 1000,
        "$where": where_clause,
        "$order": "cmplnt_fr_dt DESC"
    }

    response = requests.get(endpoint, params=params)
    if response.status_code == 200:
        return pd.DataFrame(response.json())
    else:
        print(f"❌ Error {response.status_code}: {response.text}")
        return pd.DataFrame()

def get_dob_permits(zip_code, days=1095):  # 3 years
    """
    Fetches DOB permit data for the given zip code over the last `days` days.
    """
    if not zip_code:
        return pd.DataFrame()

    endpoint = "https://data.cityofnewyork.us/resource/ipu4-2q9a.json"
    since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    where_clause = f"zip_code='{zip_code}' AND issuance_date >= '{since_date}'"

    params = {
        "$limit": 1000,
        "$where": where_clause,
        "$order": "issuance_date DESC"
    }

    response = requests.get(endpoint, params=params)
    if response.status_code == 200:
        return pd.DataFrame(response.json())
    else:
        print(f"❌ Error {response.status_code}: {response.text}")
        return pd.DataFrame()
