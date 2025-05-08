import os
import time
import requests
import sqlite3
import traceback
from bs4 import BeautifulSoup
import re
import logging
from datetime import datetime, timedelta
from pathlib import Path
import json
import pytz
import random

# === CONFIG ===
SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_DIR = SCRIPT_DIR.parent / "config"
DB_DIR = SCRIPT_DIR.parent / "dbs"
ADDRESS_FILE = CONFIG_DIR / "addresses.txt"
WEBHOOK_FILE = CONFIG_DIR / "webhook.txt"
PROXY_FILE = CONFIG_DIR / "proxy.txt"
DB_PATH = DB_DIR / "building_monitor.db"
LOG_FILE = DB_DIR / "building_monitor.log"

# Proxy configuration
def load_proxy_config():
    """Load proxy configuration from file."""
    if PROXY_FILE.exists():
        with PROXY_FILE.open('r') as f:
            proxy_url = f.read().strip()
            if proxy_url:
                return {
                    "http": proxy_url,
                    "https": proxy_url
                }
    return {}  # Return empty dict if no proxy

def get_random_proxy():
    """Get a random proxy based on configuration."""
    return load_proxy_config()

# Schedule times (24-hour format)
SCHEDULE_TIMES = [8, 12, 20]  # 8am, 12pm, 8pm

BIS_BORO_CODES = {
    "MANHATTAN": "1",
    "BRONX": "2",
    "BROOKLYN": "3",
    "QUEENS": "4",
    "STATEN ISLAND": "5"
}

# Ensure directories exist
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
DB_DIR.mkdir(parents=True, exist_ok=True)

# === Logging Setup ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)

def get_next_run_time():
    """Calculate the next run time based on the schedule."""
    now = datetime.now()
    current_hour = now.hour
    
    # Find the next scheduled time
    for hour in SCHEDULE_TIMES:
        if hour > current_hour:
            next_run = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            return next_run
    
    # If all times have passed today, schedule for first time tomorrow
    next_run = (now + timedelta(days=1)).replace(hour=SCHEDULE_TIMES[0], minute=0, second=0, microsecond=0)
    return next_run

def wait_until_next_run():
    """Wait until the next scheduled run time."""
    next_run = get_next_run_time()
    wait_seconds = (next_run - datetime.now()).total_seconds()
    
    if wait_seconds > 0:
        logging.info(f"Next run scheduled for {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
        time.sleep(wait_seconds)

# === Loaders ===
def load_addresses(path=ADDRESS_FILE):
    if not path.exists():
        logging.warning(f"Address file not found: {path}")
        return []
    with path.open("r") as f:
        return [line.strip() for line in f if line.strip()]

def load_webhook(path=WEBHOOK_FILE):
    if path.exists():
        with path.open("r") as f:
            return f.read().strip()
    return ""

# === Address Parsing ===
def parse_address_for_bis(address):
    # Example: '952A Greene Ave, Brooklyn, NY 11221'
    try:
        parts = address.split(",")
        house_street = parts[0].strip()
        borough = parts[1].strip().upper()
        house_no, *street_parts = house_street.split(" ")
        street = " ".join(street_parts)
        boro_code = BIS_BORO_CODES.get(borough, None)
        if not boro_code:
            raise ValueError(f"Unknown borough: {borough}")
        return house_no, street, boro_code
    except Exception as e:
        logging.error(f"Failed to parse address for BIS: {address} ({e})")
        return None, None, None

def parse_address_for_311(address):
    # Example: '952A Greene Ave, Brooklyn, NY 11221'
    try:
        parts = address.split(",")
        house_street = parts[0].strip().upper()
        borough = parts[1].strip().upper()
        zip_code = parts[2].strip().split()[-1]
        return house_street, borough, zip_code
    except Exception as e:
        logging.error(f"Failed to parse address for 311: {address} ({e})")
        return None, None, None

# === BIS Summary Scraper ===
def get_bis_summary(house_no, street, boro="3"):
    url = "https://a810-bisweb.nyc.gov/bisweb/PropertyProfileOverviewServlet"
    params = {
        "boro": boro,
        "houseno": house_no,
        "street": street.replace(" ", "+")
    }
    
    # Get a random proxy for this request
    proxies = get_random_proxy()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        response = requests.get(
            url, 
            params=params, 
            headers=headers,
            proxies=proxies,
            timeout=30  # Add timeout to prevent hanging
        )
        response.raise_for_status()  # Raise an exception for bad status codes
        
        soup = BeautifulSoup(response.text, "html.parser")
        text = soup.get_text(separator="\n")
        
        def extract_count(label):
            match = re.search(rf"{label}\s+(\d+)", text)
            return int(match.group(1)) if match else None
            
        data = {
            "Complaints": extract_count("Complaints"),
            "Violations-DOB": extract_count("Violations-DOB"),
            "Violations-OATH/ECB": extract_count("Violations-OATH/ECB"),
        }
        
        if any(v is None for v in data.values()):
            raise ValueError(f"Failed to extract one or more values from BIS page for {house_no} {street}, Boro {boro}")
            
        return data
        
    except requests.exceptions.RequestException as e:
        logging.error(f"Proxy request failed for {house_no} {street}: {str(e)}")
        raise
    except Exception as e:
        logging.error(f"Unexpected error while fetching BIS data for {house_no} {street}: {str(e)}")
        raise

# === 311 Complaint Fetcher ===
API_URL_311 = "https://data.cityofnewyork.us/resource/erm2-nwe9.json"
def get_311_complaints(address, borough, zip_code, limit=20):
    params = {
        "$limit": limit,
        "$order": "created_date DESC",
        "$where": (
            f"incident_address='{address}' AND "
            f"borough='{borough}' AND "
            f"incident_zip='{zip_code}'"
        )
    }
    response = requests.get(API_URL_311, params=params)
    if response.status_code != 200:
        raise Exception(f"311 API error: {response.status_code} - {response.text}")
    return response.json()

# === Alert Sender ===
def send_discord_embed(webhook_url, embed):
    data = {"embeds": [embed]}
    requests.post(webhook_url, json=data)

# === SQLite DB ===
def init_db():
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS bis_status (
            address TEXT PRIMARY KEY,
            complaints INTEGER,
            violations_dob INTEGER,
            violations_oath INTEGER
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS complaints_311 (
            incident_id TEXT PRIMARY KEY,
            address TEXT,
            borough TEXT,
            zip_code TEXT,
            created_date TEXT,
            complaint_type TEXT,
            descriptor TEXT,
            agency TEXT,
            status TEXT,
            closed_date TEXT,
            resolution_description TEXT,
            location_type TEXT,
            latitude TEXT,
            longitude TEXT
        )
    """)
    conn.commit()
    return conn

def get_all_bis_statuses(conn):
    c = conn.cursor()
    c.execute("SELECT address, complaints, violations_dob, violations_oath FROM bis_status")
    return {row[0]: row[1:] for row in c.fetchall()}

def update_bis_status(conn, address, stats):
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO bis_status (address, complaints, violations_dob, violations_oath)
        VALUES (?, ?, ?, ?)
    """, (address, stats["Complaints"], stats["Violations-DOB"], stats["Violations-OATH/ECB"]))
    conn.commit()

def get_all_311_ids(conn):
    c = conn.cursor()
    c.execute("SELECT incident_id FROM complaints_311")
    return set(row[0] for row in c.fetchall())

def insert_311_complaint(conn, complaint):
    c = conn.cursor()
    c.execute("""
        INSERT OR IGNORE INTO complaints_311 (
            incident_id, address, borough, zip_code, created_date, complaint_type, descriptor, agency, status, closed_date, resolution_description, location_type, latitude, longitude
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        complaint.get("incident_id"),
        complaint.get("incident_address"),
        complaint.get("borough"),
        complaint.get("incident_zip"),
        complaint.get("created_date"),
        complaint.get("complaint_type"),
        complaint.get("descriptor"),
        complaint.get("agency"),
        complaint.get("status"),
        complaint.get("closed_date"),
        complaint.get("resolution_description"),
        complaint.get("location_type"),
        complaint.get("latitude"),
        complaint.get("longitude")
    ))
    conn.commit()

# === Main Logic ===
def run_check():
    logging.info("Starting Building Monitor check...")
    conn = init_db()
    addresses = load_addresses()
    DISCORD_WEBHOOK_URL = load_webhook()

    if not addresses:
        logging.warning(f"No addresses found in {ADDRESS_FILE}")
        return

    old_bis_data = get_all_bis_statuses(conn)
    old_311_ids = get_all_311_ids(conn)
    failed_addresses = []
    bis_retry_list = []
    changed_addresses = []
    bis_change_details = []
    new_311_alerts = []
    new_311_details = []

    # First pass
    for address in addresses:
        # --- BIS Check ---
        house_no, street, boro_code = parse_address_for_bis(address)
        bis_success = False
        bis_stats = None
        if not all([house_no, street, boro_code]):
            logging.error(f"Skipping BIS check for {address} due to parse error.")
        else:
            for attempt in range(2):
                try:
                    bis_stats = get_bis_summary(house_no, street, boro_code)
                    bis_success = True
                    break
                except Exception as e:
                    logging.error(f"Failed BIS check for {address} (attempt {attempt+1}): {e}")
                    logging.error(traceback.format_exc())
                    time.sleep(2)
            if not bis_success:
                bis_retry_list.append(address)
            else:
                if address in old_bis_data:
                    old_stats = {
                        "Complaints": old_bis_data[address][0],
                        "Violations-DOB": old_bis_data[address][1],
                        "Violations-OATH/ECB": old_bis_data[address][2],
                    }
                    changes = {
                        key: (old_stats[key], bis_stats[key])
                        for key in bis_stats
                        if bis_stats[key] != old_stats[key]
                    }
                    if changes and DISCORD_WEBHOOK_URL:
                        changed_addresses.append(address)
                        bis_change_details.append({
                            "address": address,
                            "changes": changes,
                            "new_totals": bis_stats
                        })
                update_bis_status(conn, address, bis_stats)
                logging.info(f"BIS checked and updated for {address}")

        # --- 311 Check ---
        addr_311, borough_311, zip_311 = parse_address_for_311(address)
        if not all([addr_311, borough_311, zip_311]):
            logging.error(f"Skipping 311 check for {address} due to parse error.")
        else:
            try:
                complaints = get_311_complaints(addr_311, borough_311, zip_311, limit=20)
                new_complaints = [c for c in complaints if c.get("incident_id") not in old_311_ids]
                for c in new_complaints:
                    insert_311_complaint(conn, c)
                if new_complaints and DISCORD_WEBHOOK_URL:
                    new_311_alerts.append(address)
                    # Find the most recent complaint date and details
                    last_complaint = max(new_complaints, key=lambda c: c.get("created_date", ""))
                    new_311_details.append({
                        "address": address,
                        "last_date": last_complaint.get("created_date", "N/A"),
                        "details": new_complaints
                    })
                logging.info(f"311 checked and updated for {address} ({len(new_complaints)} new)")
            except Exception as e:
                logging.error(f"Failed 311 check for {address}: {e}")
                logging.error(traceback.format_exc())
                failed_addresses.append(address)

    # Retry BIS for failed addresses
    if bis_retry_list:
        logging.info(f"Waiting 60 seconds before retrying BIS for {len(bis_retry_list)} failed address(es)...")
        time.sleep(60)
        still_failed = []
        for address in bis_retry_list:
            house_no, street, boro_code = parse_address_for_bis(address)
            bis_success = False
            bis_stats = None
            for attempt in range(2):
                try:
                    bis_stats = get_bis_summary(house_no, street, boro_code)
                    bis_success = True
                    break
                except Exception as e:
                    logging.error(f"Retry: Failed BIS check for {address} (attempt {attempt+1}): {e}")
                    logging.error(traceback.format_exc())
                    time.sleep(2)
            if not bis_success:
                failed_addresses.append(address)
            else:
                if address in old_bis_data:
                    old_stats = {
                        "Complaints": old_bis_data[address][0],
                        "Violations-DOB": old_bis_data[address][1],
                        "Violations-OATH/ECB": old_bis_data[address][2],
                    }
                    changes = {
                        key: (old_stats[key], bis_stats[key])
                        for key in bis_stats
                        if bis_stats[key] != old_stats[key]
                    }
                    if changes and DISCORD_WEBHOOK_URL:
                        changed_addresses.append(address)
                        bis_change_details.append({
                            "address": address,
                            "changes": changes,
                            "new_totals": bis_stats
                        })
                update_bis_status(conn, address, bis_stats)
                logging.info(f"BIS checked and updated for {address} (after retry)")

    # Summary
    if DISCORD_WEBHOOK_URL:
        # Use local time for the title
        local_now = datetime.now()
        date_str = local_now.strftime('%-m/%-d')
        am_pm = local_now.strftime('%p').lower()
        embed_title = f"Building Monitor Stats - {date_str} - {am_pm}"
        # Format summary time as (MM/DD/YYYY - HH:MM AM/PM)
        summary_time = local_now.strftime('%m/%d/%Y - %I:%M %p')
        embed = {
            "title": embed_title,
            "color": 0x3498db,  # Blue
            "timestamp": local_now.isoformat(),
            "fields": [
                {"name": "Total Addresses Checked", "value": str(len(addresses)), "inline": True},
                {"name": "BIS Changes", "value": str(len(bis_change_details)), "inline": True},
                {"name": "New 311 Complaints", "value": str(len(new_311_details)), "inline": True},
                {"name": "Failed Addresses", "value": str(len(failed_addresses)), "inline": True},
            ],
            "footer": {"text": f"🏢 Generated on {summary_time}"}
        }
        # Add BIS change details
        if bis_change_details:
            for detail in bis_change_details:
                addr = detail["address"]
                changes = detail["changes"]
                new_totals = detail["new_totals"]
                value = ""
                for k, (old, new) in changes.items():
                    value += f"{k}: {old} → {new}\n"
                value += f"New Totals: Complaints={new_totals['Complaints']}, Violations-DOB={new_totals['Violations-DOB']}, Violations-OATH/ECB={new_totals['Violations-OATH/ECB']}"
                embed["fields"].append({"name": f"BIS Change: {addr}", "value": value, "inline": False})
        # Add 311 complaint details
        if new_311_details:
            for detail in new_311_details:
                addr = detail['address']
                last_date = detail['last_date']
                for c in detail['details']:
                    value = (
                        f"Date: {c.get('created_date', 'N/A')}\n"
                        f"Type: {c.get('complaint_type', 'N/A')}\n"
                        f"Descriptor: {c.get('descriptor', 'N/A')}\n"
                        f"Agency: {c.get('agency', 'N/A')}\n"
                        f"Status: {c.get('status', 'N/A')}\n"
                        f"Closed Date: {c.get('closed_date', 'N/A')}\n"
                        f"Resolution: {c.get('resolution_description', 'N/A')}\n"
                        f"Incident ID: {c.get('incident_id', 'N/A')}\n"
                    )
                    embed["fields"].append({"name": f"311 Complaint: {addr} (Last: {last_date})", "value": value, "inline": False})
        # Add failed addresses
        if failed_addresses:
            embed["fields"].append({
                "name": "Failed Addresses",
                "value": "\n".join(failed_addresses),
                "inline": False
            })
        # If nothing changed, add a reassuring message
        if not bis_change_details and not new_311_details and not failed_addresses:
            embed["description"] = "✅ All addresses checked. No new complaints or violations. All properties are in good standing."
        send_discord_embed(DISCORD_WEBHOOK_URL, embed)

    conn.close()
    logging.info("Building Monitor check completed.")

if __name__ == "__main__":
    import sys
    
    # Handle proxy toggle command
    if len(sys.argv) > 1 and sys.argv[1] in ['--proxy', '-p']:
        if len(sys.argv) > 2:
            use_proxy = sys.argv[2].lower() == 'on'
            save_proxy_config({"use_proxy": use_proxy})
            print(f"Proxy usage turned {'on' if use_proxy else 'off'}")
            sys.exit(0)
        else:
            config = load_proxy_config()
            print(f"Proxy is currently {'on' if config.get('use_proxy', True) else 'off'}")
            print("Usage: python building_monitor.py --proxy [on|off]")
            sys.exit(0)
    
    # Normal monitoring loop
    while True:
        try:
            run_check()
            wait_until_next_run()
        except Exception as e:
            logging.error(f"Error in main loop: {e}")
            logging.error(traceback.format_exc())
            # Wait 5 minutes before retrying if there's an error
            time.sleep(300) 