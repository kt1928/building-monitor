import streamlit as st
import json
from pathlib import Path
import subprocess
import time
from datetime import datetime

# === CONFIG ===
SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_DIR = SCRIPT_DIR / "config"
DB_DIR = SCRIPT_DIR / "dbs"
ADDRESS_FILE = CONFIG_DIR / "addresses.txt"
WEBHOOK_FILE = CONFIG_DIR / "webhook.txt"
SCHEDULE_FILE = CONFIG_DIR / "schedule.json"

# Ensure directories exist
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
DB_DIR.mkdir(parents=True, exist_ok=True)

def load_schedule():
    if SCHEDULE_FILE.exists():
        with open(SCHEDULE_FILE, 'r') as f:
            return json.load(f)
    return {"times": [8, 12, 20]}  # Default schedule

def save_schedule(schedule):
    with open(SCHEDULE_FILE, 'w') as f:
        json.dump(schedule, f, indent=2)

def load_addresses():
    if ADDRESS_FILE.exists():
        with open(ADDRESS_FILE, 'r') as f:
            return f.read().strip().split('\n')
    return []

def save_addresses(addresses):
    with open(ADDRESS_FILE, 'w') as f:
        f.write('\n'.join(addresses))

def load_webhook():
    if WEBHOOK_FILE.exists():
        with open(WEBHOOK_FILE, 'r') as f:
            return f.read().strip()
    return ""

def save_webhook(webhook):
    with open(WEBHOOK_FILE, 'w') as f:
        f.write(webhook)

def get_log_tail(n_lines=50):
    log_file = DB_DIR / "building_monitor.log"
    if log_file.exists():
        try:
            with open(log_file, 'r') as f:
                lines = f.readlines()
                return ''.join(lines[-n_lines:])
        except Exception as e:
            return f"Error reading log file: {e}"
    return "No log file found"

# === UI Setup ===
st.set_page_config(page_title="Building Monitor Control Panel", layout="wide")

st.title("🏢 Building Monitor Control Panel")

# Sidebar for navigation
page = st.sidebar.radio("Navigation", ["Dashboard", "Schedule", "Addresses", "Webhook", "Logs"])

if page == "Dashboard":
    st.header("Dashboard")
    
    # Status
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Last Run", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    with col2:
        st.metric("Next Run", "Calculating...")
    
    # Quick Actions
    st.subheader("Quick Actions")
    if st.button("Run Check Now"):
        with st.spinner("Running check..."):
            try:
                subprocess.run(["python", "building_monitor.py"], check=True)
                st.success("Check completed successfully!")
            except Exception as e:
                st.error(f"Error running check: {e}")

elif page == "Schedule":
    st.header("Schedule Settings")
    
    schedule = load_schedule()
    times = schedule["times"]
    
    st.write("Configure when the script should run (24-hour format):")
    
    # Time selection
    new_times = []
    for i, time in enumerate(times):
        col1, col2 = st.columns([3, 1])
        with col1:
            new_time = st.number_input(f"Run Time {i+1}", min_value=0, max_value=23, value=time, step=1)
            new_times.append(new_time)
        with col2:
            if st.button("Remove", key=f"remove_{i}"):
                new_times.remove(time)
    
    # Add new time
    if st.button("Add Time Slot"):
        new_times.append(8)  # Default to 8am
    
    # Save schedule
    if st.button("Save Schedule"):
        schedule["times"] = sorted(new_times)
        save_schedule(schedule)
        st.success("Schedule saved!")

elif page == "Addresses":
    st.header("Address Management")
    
    addresses = load_addresses()
    
    # Add new address
    new_address = st.text_input("Add New Address", 
                               placeholder="Enter address in format: 123 Main St, Borough, NY ZIP")
    if st.button("Add Address"):
        if new_address:
            addresses.append(new_address)
            save_addresses(addresses)
            st.success("Address added!")
            st.experimental_rerun()
    
    # List and manage addresses
    st.subheader("Current Addresses")
    for i, address in enumerate(addresses):
        col1, col2 = st.columns([3, 1])
        with col1:
            st.write(address)
        with col2:
            if st.button("Remove", key=f"remove_addr_{i}"):
                addresses.pop(i)
                save_addresses(addresses)
                st.success("Address removed!")
                st.experimental_rerun()

elif page == "Webhook":
    st.header("Discord Webhook Settings")
    
    webhook = load_webhook()
    new_webhook = st.text_input("Discord Webhook URL", value=webhook, type="password")
    
    if st.button("Save Webhook"):
        save_webhook(new_webhook)
        st.success("Webhook URL saved!")

elif page == "Logs":
    st.header("Recent Logs")
    
    if st.button("Refresh Logs"):
        st.experimental_rerun()
    
    log_content = get_log_tail()
    st.code(log_content, language="text") 