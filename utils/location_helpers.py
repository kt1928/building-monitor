from geopy.geocoders import Nominatim
from geopy.distance import distance as geopy_distance
import pgeocode
import pandas as pd

def get_zipcodes_within_radius(address, radius_miles=10):
    geolocator = Nominatim(user_agent="zillow-radius-search")
    location = geolocator.geocode(address)
    if not location:
        raise ValueError(f"Could not geocode address: {address}")

    lat, lon = location.latitude, location.longitude
    nomi = pgeocode.Nominatim('US')
    zip_data = nomi._data
    zip_data = zip_data[zip_data["latitude"].notnull() & zip_data["longitude"].notnull()]

    zip_data["distance"] = zip_data.apply(
        lambda row: geopy_distance((lat, lon), (row["latitude"], row["longitude"])).miles,
        axis=1
    )

    nearby = zip_data[zip_data["distance"] <= radius_miles]
    return nearby["postal_code"].dropna().astype(str).tolist()
