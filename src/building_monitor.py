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
import argparse
import threading

# === CONFIG ===
SCRIPT_DIR = Path(__file__).parent
CONFIG_DIR = SCRIPT_DIR.parent / "config"
DB_DIR = SCRIPT_DIR.parent / "dbs"
DB_PATH = DB_DIR / "building_monitor.db"
ADDRESS_FILE = CONFIG_DIR / "addresses.txt"
PROXY_FILE = CONFIG_DIR / "proxy.txt"
WEBHOOK_FILE = CONFIG_DIR / "webhook.txt"
LOG_FILE = DB_DIR / "building_monitor.log"

# Thread-local storage for current address
thread_local = threading.local()

class AddressLogFormatter(logging.Formatter):
    """Custom formatter that includes the current address in log messages."""
    
    def format(self, record):
        # Get the current address from thread-local storage
        current_address = getattr(thread_local, 'current_address', 'GLOBAL')
        
        # Add address to the log message if it's not already there
        if not hasattr(record, 'address'):
            record.address = current_address
            
        # Format the message with address
        if record.address != 'GLOBAL':
            record.msg = f"[{record.address}] {record.msg}"
        
        return super().format(record)

def set_current_address(address):
    """Set the current address in thread-local storage."""
    thread_local.current_address = address

def clear_current_address():
    """Clear the current address from thread-local storage."""
    thread_local.current_address = 'GLOBAL'

# === LOGGING ===
def setup_logging():
    """Setup logging with custom formatter."""
    formatter = AddressLogFormatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # File handler
    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setFormatter(formatter)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    # Setup root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

# Initialize logging
setup_logging()

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
DB_DIR.mkdir(exist_ok=True)
CONFIG_DIR.mkdir(exist_ok=True)

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
        logging.info(f"Fetching BIS data for {house_no} {street}, Boro {boro}")
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
        
        logging.info(f"Successfully fetched BIS data for {house_no} {street}: {data}")
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
    logging.info(f"Fetching 311 complaints for {address}, {borough}, {zip_code}")
    params = {
        "$limit": limit,
        "$order": "created_date DESC",
        "$where": (
            f"incident_address='{address}' AND "
            f"borough='{borough}' AND "
            f"incident_zip='{zip_code}'"
        )
    }
    try:
        response = requests.get(API_URL_311, params=params)
        response.raise_for_status()
        complaints = response.json()
        logging.info(f"Found {len(complaints)} total 311 complaints for {address}")
        return complaints
    except Exception as e:
        logging.error(f"Error fetching 311 complaints for {address}: {str(e)}")
        raise

# === Alert Sender ===
def send_discord_embed(webhook_url, embed):
    data = {"embeds": [embed]}
    try:
        logging.info(f"Sending Discord webhook to {webhook_url[:30]}...")
        response = requests.post(webhook_url, json=data)
        response.raise_for_status()
        logging.info("Discord webhook sent successfully")
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to send Discord webhook: {str(e)}")
        if hasattr(e.response, 'text'):
            logging.error(f"Discord API response: {e.response.text}")
        raise

# === SQLite DB ===
def init_db():
    """Initialize the database with required tables."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Create owners table
    c.execute('''
        CREATE TABLE IF NOT EXISTS owners (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            discord_webhook TEXT,
            schedule TEXT DEFAULT '[8, 12, 20]'
        )
    ''')
    
    # Create address_owners table for many-to-many relationship
    c.execute('''
        CREATE TABLE IF NOT EXISTS address_owners (
            address TEXT NOT NULL,
            owner_id INTEGER NOT NULL,
            PRIMARY KEY (address, owner_id),
            FOREIGN KEY (owner_id) REFERENCES owners(id)
        )
    ''')
    
    # Create bis_status table with violation columns
    c.execute('''
        CREATE TABLE IF NOT EXISTS bis_status (
            address TEXT PRIMARY KEY,
            bin TEXT,
            last_checked TIMESTAMP,
            dob_violations INTEGER DEFAULT 0,
            ecb_violations INTEGER DEFAULT 0,
            owner_id INTEGER,
            FOREIGN KEY (owner_id) REFERENCES owners(id)
        )
    ''')
    
    # Create complaints_311 table
    c.execute('''
        CREATE TABLE IF NOT EXISTS complaints_311 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_id TEXT UNIQUE,
            address TEXT,
            created_date TIMESTAMP,
            status TEXT,
            complaint_type TEXT,
            descriptor TEXT,
            resolution_description TEXT,
            closed_date TIMESTAMP,
            agency TEXT,
            bis_status_id INTEGER,
            FOREIGN KEY (bis_status_id) REFERENCES bis_status(address)
        )
    ''')
    
    # Check and add missing columns to bis_status table
    try:
        c.execute("SELECT * FROM bis_status LIMIT 1")
        columns = [description[0] for description in c.description]
        
        # Add missing columns if they don't exist
        if 'last_checked' not in columns:
            c.execute("ALTER TABLE bis_status ADD COLUMN last_checked TIMESTAMP")
        if 'dob_violations' not in columns:
            c.execute("ALTER TABLE bis_status ADD COLUMN dob_violations INTEGER DEFAULT 0")
        if 'ecb_violations' not in columns:
            c.execute("ALTER TABLE bis_status ADD COLUMN ecb_violations INTEGER DEFAULT 0")
        if 'owner_id' not in columns:
            c.execute("ALTER TABLE bis_status ADD COLUMN owner_id INTEGER")
            
    except sqlite3.OperationalError:
        # Table doesn't exist yet, which is fine as it will be created with all columns
        pass
    
    # Check and add missing columns to complaints_311 table
    try:
        c.execute("SELECT * FROM complaints_311 LIMIT 1")
        columns = [description[0] for description in c.description]
        
        # Add missing columns if they don't exist
        if 'descriptor' not in columns:
            c.execute("ALTER TABLE complaints_311 ADD COLUMN descriptor TEXT")
        if 'closed_date' not in columns:
            c.execute("ALTER TABLE complaints_311 ADD COLUMN closed_date TIMESTAMP")
        if 'agency' not in columns:
            c.execute("ALTER TABLE complaints_311 ADD COLUMN agency TEXT")
            
    except sqlite3.OperationalError:
        # Table doesn't exist yet, which is fine as it will be created with all columns
        pass
    
    conn.commit()
    return conn

def get_all_bis_statuses(conn):
    c = conn.cursor()
    c.execute("SELECT address, dob_violations, ecb_violations FROM bis_status")
    return {row[0]: (row[1], row[2]) for row in c.fetchall()}

def update_bis_status(conn, address, stats):
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO bis_status (address, dob_violations, ecb_violations)
        VALUES (?, ?, ?)
    """, (address, stats["Violations-DOB"], stats["Violations-OATH/ECB"]))
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

def get_bin_from_address(house_no, street, boro="3"):
    """Get BIN using NYC BIS website"""
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
        logging.info(f"Fetching BIN for {house_no} {street}, Boro {boro}")
        response = requests.get(
            url, 
            params=params, 
            headers=headers,
            proxies=proxies,
            timeout=30
        )
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, "html.parser")
        bin_cell = soup.find('td', class_='maininfo', string=re.compile(r'BIN#'))
        
        if bin_cell:
            bin_match = re.search(r'BIN#\s*(\d+)', bin_cell.text)
            if bin_match:
                bin_number = bin_match.group(1)
                logging.info(f"Successfully found BIN {bin_number} for {house_no} {street}")
                return bin_number
        logging.warning(f"No BIN found for {house_no} {street}")
        return None
    except Exception as e:
        logging.error(f"Error fetching BIN for {house_no} {street}: {str(e)}")
        return None

def update_bin_for_address(conn, address, bin_number):
    """Update BIN for an address in the database"""
    c = conn.cursor()
    c.execute("""
        UPDATE bis_status 
        SET bin = ? 
        WHERE address = ?
    """, (bin_number, address))
    conn.commit()

def get_bin_for_address(conn, address):
    """Get stored BIN for an address"""
    c = conn.cursor()
    c.execute("SELECT bin FROM bis_status WHERE address = ?", (address,))
    result = c.fetchone()
    return result[0] if result else None

def scrape_bins_for_addresses():
    """Scrape BINs for all addresses that don't have one"""
    logging.info("Starting BIN scraping process")
    conn = init_db()
    addresses = load_addresses()
    results = []
    
    for address in addresses:
        logging.info(f"Processing address: {address}")
        stored_bin = get_bin_for_address(conn, address)
        if stored_bin:
            logging.info(f"Address {address} already has BIN: {stored_bin}")
            results.append({
                'address': address,
                'bin': stored_bin,
                'status': 'already_stored'
            })
            continue
            
        house_no, street, boro_code = parse_address_for_bis(address)
        if not all([house_no, street, boro_code]):
            logging.error(f"Failed to parse address for BIN scraping: {address}")
            results.append({
                'address': address,
                'bin': None,
                'status': 'parse_error'
            })
            continue
            
        bin_number = get_bin_from_address(house_no, street, boro_code)
        if bin_number:
            update_bin_for_address(conn, address, bin_number)
            logging.info(f"Successfully scraped and stored BIN {bin_number} for {address}")
            results.append({
                'address': address,
                'bin': bin_number,
                'status': 'scraped'
            })
        else:
            logging.warning(f"Failed to scrape BIN for {address}")
            results.append({
                'address': address,
                'bin': None,
                'status': 'not_found'
            })
        time.sleep(1)  # Be nice to the server
    
    conn.close()
    logging.info(f"BIN scraping completed. Results: {len(results)} addresses processed")
    return results

def get_violations_by_bin(bin_number):
    """Get DOB violations using BIN"""
    if not bin_number:
        return []
        
    base_url = "https://data.cityofnewyork.us/resource/3h2n-5cm9.json"
    
    try:
        params = {
            '$where': f"bin='{bin_number}'",
            '$order': 'issue_date DESC'
        }
        
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        
        return response.json()
    except Exception as e:
        logging.error(f"Error fetching DOB violations for BIN {bin_number}: {str(e)}")
        return []

def get_ecb_violations_by_bin(bin_number):
    """Get ECB violations using BIN"""
    if not bin_number:
        return []
        
    base_url = "https://data.cityofnewyork.us/resource/6bgk-3dad.json"
    
    try:
        params = {
            '$where': f"bin='{bin_number}'",
            '$order': 'issue_date DESC'
        }
        
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        
        return response.json()
    except Exception as e:
        logging.error(f"Error fetching ECB violations for BIN {bin_number}: {str(e)}")
        return []

def get_owner_addresses(conn, owner_id):
    """Get all addresses for a specific owner"""
    c = conn.cursor()
    c.execute("""
        SELECT address FROM address_owners 
        WHERE owner_id = ?
    """, (owner_id,))
    return [row[0] for row in c.fetchall()]

def get_owner_notification_preferences(conn, owner_id):
    """Get notification preferences for an owner"""
    c = conn.cursor()
    c.execute("""
        SELECT name, discord_webhook, email, phone 
        FROM owners 
        WHERE id = ?
    """, (owner_id,))
    row = c.fetchone()
    if row:
        return {
            'name': row[0],
            'discord_webhook': row[1],
            'email': row[2],
            'phone': row[3]
        }
    return None

def get_all_owners(conn):
    """Get all owners and their preferences"""
    c = conn.cursor()
    c.execute("SELECT id, name, discord_webhook, email, phone FROM owners")
    return [{
        'id': row[0],
        'name': row[1],
        'discord_webhook': row[2],
        'email': row[3],
        'phone': row[4]
    } for row in c.fetchall()]

def add_owner(conn, name, discord_webhook=None, email=None, phone=None):
    """Add a new owner"""
    c = conn.cursor()
    c.execute("""
        INSERT INTO owners (name, discord_webhook, email, phone)
        VALUES (?, ?, ?, ?)
    """, (name, discord_webhook, email, phone))
    conn.commit()
    return c.lastrowid

def update_owner_preferences(conn, owner_id, discord_webhook=None, email=None, phone=None):
    """Update owner notification preferences"""
    c = conn.cursor()
    updates = []
    values = []
    if discord_webhook is not None:
        updates.append("discord_webhook = ?")
        values.append(discord_webhook)
    if email is not None:
        updates.append("email = ?")
        values.append(email)
    if phone is not None:
        updates.append("phone = ?")
        values.append(phone)
    
    if updates:
        values.append(owner_id)
        c.execute(f"""
            UPDATE owners 
            SET {', '.join(updates)}
            WHERE id = ?
        """, values)
        conn.commit()

def assign_address_to_owner(conn, address, owner_id):
    """Assign an address to an owner"""
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO address_owners (address, owner_id)
        VALUES (?, ?)
    """, (address, owner_id))
    conn.commit()

def remove_address_from_owner(conn, address, owner_id):
    """Remove an address from an owner"""
    c = conn.cursor()
    c.execute("""
        DELETE FROM address_owners 
        WHERE address = ? AND owner_id = ?
    """, (address, owner_id))
    conn.commit()

# === Main Logic ===
def run_check(owner_id=None):
    """Run a check for all addresses or a specific owner's addresses."""
    logging.info("Starting Building Monitor check...")
    try:
        conn = init_db()
        if not conn:
            logging.error("Failed to initialize database")
            return False

        # Get addresses to check
        if owner_id is not None:
            addresses = get_owner_addresses(conn, owner_id)
            logging.info(f"Running check for owner ID {owner_id} with {len(addresses)} addresses")
            owners_to_notify = [owner_id]  # Only notify the specified owner
        else:
            addresses = load_addresses()
            logging.info(f"Running check for all {len(addresses)} addresses")
            owners_to_notify = None  # Notify all owners
        
        if not addresses:
            logging.warning(f"No addresses found to check")
            conn.close()
            return False

        # Get all owners and their addresses
        owners = get_all_owners(conn)
        logging.info(f"Found {len(owners)} owners")
        owner_addresses = {}
        for owner in owners:
            owner_addresses[owner['id']] = get_owner_addresses(conn, owner['id'])
            logging.info(f"Owner {owner['name']} has {len(owner_addresses[owner['id']])} addresses")

        old_bis_data = get_all_bis_statuses(conn)
        old_311_ids = get_all_311_ids(conn)
        failed_addresses = []
        bis_retry_list = []
        changed_addresses = {}
        bis_change_details = {}
        new_311_alerts = {}
        new_311_details = {}

        # First pass
        for address in addresses:
            # Set current address for logging
            set_current_address(address.split('|')[0])
            
            logging.info("Processing address")
            # Get owner(s) for this address
            c = conn.cursor()
            c.execute("SELECT owner_id FROM address_owners WHERE address = ?", (address.split('|')[0],))
            address_owners = [row[0] for row in c.fetchall()]
            if address_owners:
                logging.info(f"Address is assigned to {len(address_owners)} owners")
            
            # --- BIS Check ---
            house_no, street, boro_code = parse_address_for_bis(address)
            bis_success = False
            bis_stats = None
            if not all([house_no, street, boro_code]):
                logging.error("Skipping BIS check due to parse error.")
            else:
                for attempt in range(2):
                    try:
                        bis_stats = get_bis_summary(house_no, street, boro_code)
                        bis_success = True
                        break
                    except Exception as e:
                        logging.error(f"Failed BIS check (attempt {attempt+1}): {e}")
                        logging.error(traceback.format_exc())
                        time.sleep(2)
                if not bis_success:
                    bis_retry_list.append(address)
                    logging.warning("Added to retry list")
                else:
                    if address.split('|')[0] in old_bis_data:
                        old_dob, old_ecb = old_bis_data[address.split('|')[0]]
                        changes = {}
                        if bis_stats["Violations-DOB"] != old_dob:
                            changes["Violations-DOB"] = (old_dob, bis_stats["Violations-DOB"])
                        if bis_stats["Violations-OATH/ECB"] != old_ecb:
                            changes["Violations-OATH/ECB"] = (old_ecb, bis_stats["Violations-OATH/ECB"])
                        
                        if changes:
                            logging.info(f"Found changes: {changes}")
                            for owner_id in address_owners:
                                if owner_id not in changed_addresses:
                                    changed_addresses[owner_id] = []
                                    bis_change_details[owner_id] = []
                                changed_addresses[owner_id].append(address.split('|')[0])
                                bis_change_details[owner_id].append({
                                    "address": address.split('|')[0],
                                    "changes": changes,
                                    "new_totals": bis_stats
                                })
                    update_bis_status(conn, address.split('|')[0], bis_stats)
                    logging.info("Updated BIS status")

            # --- 311 Check ---
            addr_311, borough_311, zip_311 = parse_address_for_311(address)
            if not all([addr_311, borough_311, zip_311]):
                logging.error("Skipping 311 check due to parse error.")
            else:
                try:
                    logging.info("Starting 311 check")
                    complaints = get_311_complaints(addr_311, borough_311, zip_311, limit=20)
                    new_complaints = [c for c in complaints if c.get("incident_id") not in old_311_ids]
                    if new_complaints:
                        logging.info(f"Found {len(new_complaints)} new 311 complaints")
                        for c in new_complaints:
                            logging.info(f"Inserting new 311 complaint: {c.get('incident_id')} - {c.get('complaint_type')}")
                            insert_311_complaint(conn, c)
                        for owner_id in address_owners:
                            if owner_id not in new_311_alerts:
                                new_311_alerts[owner_id] = []
                                new_311_details[owner_id] = []
                            new_311_alerts[owner_id].append(address.split('|')[0])
                            last_complaint = max(new_complaints, key=lambda c: c.get("created_date", ""))
                            new_311_details[owner_id].append({
                                "address": address.split('|')[0],
                                "last_date": last_complaint.get("created_date", "N/A"),
                                "details": new_complaints
                            })
                            logging.info(f"Added 311 alerts for owner {owner_id}")
                    else:
                        logging.info("No new 311 complaints found")
                except Exception as e:
                    logging.error(f"Failed 311 check: {e}")
                    logging.error(traceback.format_exc())
                    failed_addresses.append(address.split('|')[0])
            
            # Clear current address after processing
            clear_current_address()

        # Send notifications to each owner
        for owner in owners:
            owner_id = owner['id']
            
            # Skip if we're only notifying specific owners and this isn't one of them
            if owners_to_notify is not None and owner_id not in owners_to_notify:
                continue
                
            webhook_url = owner['discord_webhook']
            if not webhook_url:
                logging.warning(f"No webhook URL configured for owner {owner['name']}")
                continue
                
            logging.info(f"Sending notification to owner {owner['name']}")
            # Prepare owner-specific embed
            local_now = datetime.now()
            date_str = local_now.strftime('%-m/%-d')
            time_str = local_now.strftime('%-I:%M %p').lower()
            embed_title = f"Building Monitor Stats - {date_str} - {time_str}"
            
            # Get the addresses that were actually checked for this owner
            checked_addresses = [addr.split('|')[0] for addr in addresses if addr.split('|')[0] in owner_addresses[owner_id]]
            
            embed = {
                "title": embed_title,
                "color": 0x3498db,
                "timestamp": local_now.isoformat(),
                "fields": [
                    {"name": "Owner", "value": owner['name'], "inline": False},
                    {"name": "Addresses Checked", "value": str(len(checked_addresses)), "inline": True},
                    {"name": "BIS Changes", "value": str(len(bis_change_details.get(owner_id, []))), "inline": True},
                    {"name": "New 311 Complaints", "value": str(len(new_311_details.get(owner_id, []))), "inline": True},
                    {"name": "Failed Addresses", "value": str(len(failed_addresses)), "inline": True},
                ],
                "footer": {"text": f"🏢 Generated on {local_now.strftime('%m/%d/%Y - %I:%M %p')}"}
            }
            
            # Add BIS change details
            if owner_id in bis_change_details:
                for detail in bis_change_details[owner_id]:
                    addr = detail["address"]
                    changes = detail["changes"]
                    new_totals = detail["new_totals"]
                    value = ""
                    for k, (old, new) in changes.items():
                        value += f"{k}: {old} → {new}\n"
                    value += f"New Totals: Complaints={new_totals['Complaints']}, Violations-DOB={new_totals['Violations-DOB']}, Violations-OATH/ECB={new_totals['Violations-OATH/ECB']}"
                    embed["fields"].append({"name": f"BIS Change: {addr}", "value": value, "inline": False})
            
            # Add 311 complaint details
            if owner_id in new_311_details:
                for detail in new_311_details[owner_id]:
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
            if not bis_change_details.get(owner_id) and not new_311_details.get(owner_id) and not failed_addresses:
                embed["description"] = "✅ All addresses checked. No new complaints or violations. All properties are in good standing."
            
            send_discord_embed(webhook_url, embed)

        logging.info("Building Monitor check completed successfully")
        return True
        
    except Exception as e:
        logging.error(f"Error in main loop: {e}")
        logging.error(traceback.format_exc())
        return False
    finally:
        if 'conn' in locals():
            conn.close()
            logging.info("Database connection closed")

def run_owner_check(owner_id):
    """Run a check for a specific owner's addresses."""
    return run_check(owner_id)

if __name__ == "__main__":
    import sys
    import argparse
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Building Monitor')
    parser.add_argument('--owner', type=int, help='Run check for specific owner ID')
    args = parser.parse_args()
    
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
            if args.owner:
                # Run check for specific owner
                if not run_owner_check(args.owner):
                    sys.exit(1)
                sys.exit(0)
            else:
                # Normal run for all addresses
                run_check()
                wait_until_next_run()
        except Exception as e:
            logging.error(f"Error in main loop: {e}")
            logging.error(traceback.format_exc())
            if args.owner:
                sys.exit(1)
            # Wait 5 minutes before retrying if there's an error
            time.sleep(300) 