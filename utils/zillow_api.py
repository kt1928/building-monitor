import requests
import json
import time

ZILLOW_API_KEY = "c97dc4f002mshddcd297a818f8ccp126d95jsncdba699b2502"
BASE_URL = "https://zillow-com1.p.rapidapi.com"

HEADERS = {
    "X-RapidAPI-Key": ZILLOW_API_KEY,
    "X-RapidAPI-Host": "zillow-com1.p.rapidapi.com"
}


def get_zillow_data(zip_code=None, latitude=None, longitude=None, radius=None, min_price=0, max_price=None, status_type="ForSale", min_beds=0, home_types="HOUSES"):
    url = "https://zillow-com1.p.rapidapi.com/propertyExtendedSearch"
    headers = {
        "X-RapidAPI-Key": "c97dc4f002mshddcd297a818f8ccp126d95jsncdba699b2502",
        "X-RapidAPI-Host": "zillow-com1.p.rapidapi.com"
    }

    all_results = []
    page = 1
    max_pages = 10

    while page <= max_pages:
        params = {
            "page": page,
            "minPrice": min_price,
            "minBeds": min_beds,
            "status_type": status_type,
            "home_type": home_types
        }

        # Either use ZIP or lat/lon + radius
        if zip_code:
            params["location"] = zip_code
        elif latitude and longitude and radius:
            params["latitude"] = latitude
            params["longitude"] = longitude
            params["radius"] = radius
        else:
            raise ValueError("Must provide either zip_code or (latitude, longitude, radius)")

        if max_price:
            params["maxPrice"] = max_price

        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 429:
            print("⏳ Rate limit hit. Sleeping 5 seconds...")
            time.sleep(5)
            continue
        elif response.status_code != 200:
            raise Exception(f"Zillow API error: {response.status_code} - {response.text}")

        result = response.json()
        props = result.get("props", [])
        if not props:
            break

        all_results.extend(props)
        page += 1
        time.sleep(0.5)  # Respect rate limit

    return all_results

def get_property_details(address):
    """
    Uses the /property endpoint to retrieve detailed property info by address.
    Includes exponential backoff on 429 errors.
    """
    url = f"{BASE_URL}/property"
    retries = 5
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=HEADERS, params={"address": address})
            if resp.status_code == 429:
                wait_time = 2 ** attempt
                print(f"Rate limit hit. Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
                continue
            resp.raise_for_status()
            data = resp.json()
            return {
                "price": data.get("price"),
                "livingAreaValue": data.get("livingArea"),
                "dateSold": data.get("dateSold"),
                "bedrooms": data.get("bedrooms"),
                "bathrooms": data.get("bathrooms"),
                "latitude": data.get("latitude"),
                "longitude": data.get("longitude")
            }

        except Exception as e:
            print(f"⚠️ Attempt {attempt + 1} failed for {address}: {e}")
            if attempt == retries - 1:
                return {}

def get_property_comps(address, limit=20):
    """
    Get comparable properties using the /propertyComps endpoint
    """
    url = f"{BASE_URL}/property"
    try:
        # Step 1: Get zpid from address
        zpid_resp = requests.get(url, headers=HEADERS, params={"address": address})
        zpid_resp.raise_for_status()
        zpid_data = zpid_resp.json()
        zpid = zpid_data.get("zpid")
        if not zpid:
            raise ValueError("ZPID not found for this address.")

        # Step 2: Use zpid to get comparable properties
        comps_url = f"{BASE_URL}/propertyComps"
        comps_resp = requests.get(comps_url, headers=HEADERS, params={"zpid": zpid, "count": limit})
        comps_resp.raise_for_status()
        comps_data = comps_resp.json()
        return comps_data.get("comps", [])
    except requests.RequestException as e:
        raise RuntimeError(f"Zillow API error: {e}")
    except Exception as ex:
        raise RuntimeError(f"Failed to retrieve property comps: {ex}")
