import os
import time
import requests
import sqlite3
import traceback
from bs4 import BeautifulSoup
import re
import logging
from datetime import datetime
from pathlib import Path

# === Path Setup ===
SCRIPT_DIR = Path(__file__).resolve().parent                     # /mnt/user/scripts/Bis-Monitor/data
BASE_DIR = SCRIPT_DIR.parent                                     # /mnt/user/scripts/Bis-Monitor
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"

ADDRESS_FILE = CONFIG_DIR / "addresses.txt"
WEBHOOK_FILE = CONFIG_DIR / "webhook.txt"
DB_PATH = DATA_DIR / "bis_state.db"
LOG_FILE = DATA_DIR / "bis_monitor.log"

BATCH_SIZE = 10
DELAY_BETWEEN_BATCHES = 3  # seconds

# === Logging Setup ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)

# === Loaders ===
def load_addresses(path=ADDRESS_FILE):
    if not path.exists():
        logging.warning(f"Address file not found: {path}")
        return []
    with path.open("r") as f:
        return [tuple(line.strip().split(",")) for line in f if line.strip()]

def load_webhook(path=WEBHOOK_FILE):
    if path.exists():
        with path.open("r") as f:
            return f.read().strip()
    return ""

# === BIS Summary Scraper ===
def get_bis_summary(house_no, street, boro="3"):
    url = "https://a810-bisweb.nyc.gov/bisweb/PropertyProfileOverviewServlet"
    params = {
        "boro": boro,
        "houseno": house_no,
        "street": street.replace(" ", "+")
    }

    response = requests.get(url, params=params, headers={"User-Agent": "Mozilla/5.0"})
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

# === Alert Sender ===
def send_discord_alert(webhook_url, address, changes):
    msg = f"🚨 **BIS Update for `{address}`**\n"
    for field, (old, new) in changes.items():
        msg += f"- **{field}**: `{old}` → `{new}`\n"
    requests.post(webhook_url, json={"content": msg})

def send_summary_alert(webhook_url, total_addresses, changed_addresses, failed_addresses):
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg = f"📊 **BIS Check Summary** ({current_time})\n"
    msg += f"- Total addresses checked: {total_addresses}\n"
    msg += f"- Addresses with changes: {len(changed_addresses)}\n"
    msg += f"- Failed addresses: {len(failed_addresses)}\n"
    
    if changed_addresses:
        msg += "\n**Changed Addresses:**\n"
        for addr in changed_addresses:
            msg += f"- `{addr}`\n"
    
    if failed_addresses:
        msg += "\n**Failed Addresses:**\n"
        for house_no, street, boro in failed_addresses:
            msg += f"- `{house_no} {street}` (Boro {boro})\n"
    
    requests.post(webhook_url, json={"content": msg})

# === SQLite DB ===
def init_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
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
    conn.commit()
    return conn

def get_all_statuses(conn):
    c = conn.cursor()
    c.execute("SELECT address, complaints, violations_dob, violations_oath FROM bis_status")
    return {row[0]: row[1:] for row in c.fetchall()}

def update_status(conn, address, stats):
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO bis_status (address, complaints, violations_dob, violations_oath)
        VALUES (?, ?, ?, ?)
    """, (address, stats["Complaints"], stats["Violations-DOB"], stats["Violations-OATH/ECB"]))
    conn.commit()

# === Main Logic ===
def run_check():
    logging.info("Starting BIS check...")
    conn = init_db()
    addresses = load_addresses()
    DISCORD_WEBHOOK_URL = load_webhook()

    if not addresses:
        logging.warning(f"No addresses found in {ADDRESS_FILE}")
        return

    old_data = get_all_statuses(conn)
    failed_addresses = []
    changed_addresses = []

    def process_batch(batch):
        for house_no, street, boro in batch:
            full_addr = f"{house_no} {street}"
            try:
                logging.info(f"Checking {full_addr}...")
                new_stats = get_bis_summary(house_no, street, boro)
                
                if full_addr in old_data:
                    old_stats = {
                        "Complaints": old_data[full_addr][0],
                        "Violations-DOB": old_data[full_addr][1],
                        "Violations-OATH/ECB": old_data[full_addr][2],
                    }
                    changes = {
                        key: (old_stats[key], new_stats[key])
                        for key in new_stats
                        if new_stats[key] != old_stats[key]
                    }
                    if changes and DISCORD_WEBHOOK_URL:
                        logging.info(f"Changes detected for {full_addr}: {changes}")
                        send_discord_alert(DISCORD_WEBHOOK_URL, full_addr, changes)
                        changed_addresses.append(full_addr)

                update_status(conn, full_addr, new_stats)
                logging.info(f"Successfully updated {full_addr}")
            except Exception as e:
                logging.error(f"Failed to update {full_addr}: {e}")
                logging.error(traceback.format_exc())
                failed_addresses.append((house_no, street, boro))

    # First pass
    for i in range(0, len(addresses), BATCH_SIZE):
        batch = addresses[i:i + BATCH_SIZE]
        process_batch(batch)
        time.sleep(DELAY_BETWEEN_BATCHES)

    # Retry failed after delay
    if failed_addresses:
        logging.warning(f"Retrying {len(failed_addresses)} failed address(es) in 60 seconds...")
        time.sleep(60)
        logging.info("Retrying failed addresses...")
        process_batch(failed_addresses)

    # Send summary notification
    if DISCORD_WEBHOOK_URL:
        send_summary_alert(DISCORD_WEBHOOK_URL, len(addresses), changed_addresses, failed_addresses)

    conn.close()
    logging.info("BIS check completed.")

if __name__ == "__main__":
    run_check()
