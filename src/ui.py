import streamlit as st
import json
from pathlib import Path
import subprocess
import time
from datetime import datetime, timedelta
import pytz

# === CONFIG ===
SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_DIR = SCRIPT_DIR.parent / "config"
DB_DIR = SCRIPT_DIR.parent / "dbs"
ADDRESS_FILE = CONFIG_DIR / "addresses.txt"
WEBHOOK_FILE = CONFIG_DIR / "webhook.txt"
SCHEDULE_FILE = CONFIG_DIR / "schedule.json"
PROXY_FILE = CONFIG_DIR / "proxy.txt"

# Ensure directories exist
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
DB_DIR.mkdir(parents=True, exist_ok=True)

def load_proxy():
    if PROXY_FILE.exists():
        with open(PROXY_FILE, 'r') as f:
            return f.read().strip()
    return "http://customer-kappy_nrNdL-cc-US:3tGCOHQaFsfv1pzlrDAm+@pr.oxylabs.io:7777"

def save_proxy(proxy_url):
    with open(PROXY_FILE, 'w') as f:
        f.write(proxy_url)

def load_schedule():
    if SCHEDULE_FILE.exists():
        with open(SCHEDULE_FILE, 'r') as f:
            return json.load(f)
    return {"times": [8, 12, 20]}

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

def calculate_next_run(schedule):
    now = datetime.now(pytz.timezone('America/New_York'))
    today_times = [datetime.combine(now.date(), datetime.min.time().replace(hour=t)) for t in schedule["times"]]
    today_times = [t.replace(tzinfo=pytz.timezone('America/New_York')) for t in today_times]
    future_times = [t for t in today_times if t > now]
    if future_times:
        return min(future_times)
    tomorrow = now.date() + timedelta(days=1)
    next_time = datetime.combine(tomorrow, datetime.min.time().replace(hour=schedule["times"][0]))
    return next_time.replace(tzinfo=pytz.timezone('America/New_York'))

# === UI Setup ===
st.set_page_config(page_title="Building Monitor Control Panel", layout="wide")

st.title("🏢 Building Monitor Control Panel")

# Create tabs
tab1, tab2, tab3, tab4 = st.tabs(["Dashboard", "Schedule", "Addresses", "Connections"])

# Dashboard Tab
with tab1:
    # Quick Actions
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        if st.button("Run Check Now", use_container_width=True):
            with st.spinner("Running check..."):
                try:
                    subprocess.run(["python", str(SCRIPT_DIR / "building_monitor.py")], check=True)
                    st.success("Check completed successfully!")
                except Exception as e:
                    st.error(f"Error running check: {e}")
    with col2:
        proxy_url = load_proxy()
        if st.button(
            "Proxy: " + ("ON" if proxy_url else "OFF"),
            use_container_width=True,
            type="primary" if proxy_url else "secondary"
        ):
            if proxy_url:
                save_proxy("")  # Turn off
            else:
                save_proxy("http://customer-kappy_nrNdL-cc-US:3tGCOHQaFsfv1pzlrDAm+@pr.oxylabs.io:7777")  # Turn on
            st.experimental_rerun()
    
    # Status Metrics
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Last Run", datetime.now().strftime("%m-%d %H:%M"))
    with col2:
        addresses = load_addresses()
        st.metric("Active Addresses", len(addresses))
    
    # Address Stats
    st.subheader("Address Statistics")
    for address in addresses:
        with st.expander(address):
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Last Check", "N/A")
            with col2:
                st.metric("Status", "Unknown")
    
    # Recent Logs
    st.subheader("Recent Activity")
    log_content = get_log_tail(10)
    st.code(log_content, language="text")

# Schedule Tab
with tab2:
    st.subheader("Schedule Settings")
    schedule = load_schedule()
    times = schedule["times"]
    
    col1, col2 = st.columns([3, 1])
    with col1:
        st.write("Configure run times (24-hour format):")
        new_times = []
        for i, time in enumerate(times):
            new_time = st.number_input(f"Run Time {i+1}", min_value=0, max_value=23, value=time, step=1)
            new_times.append(new_time)
    with col2:
        st.write("")  # Spacer
        if st.button("Add Time Slot"):
            new_times.append(8)
            st.experimental_rerun()
        if st.button("Save Schedule"):
            schedule["times"] = sorted(list(set(new_times)))
            save_schedule(schedule)
            st.success("Schedule saved!")

# Addresses Tab
with tab3:
    st.subheader("Address Management")
    
    # Add new address
    col1, col2 = st.columns([3, 1])
    with col1:
        new_address = st.text_input("Add New Address", 
                                   placeholder="Enter address in format: 123 Main St, Borough, NY ZIP")
    with col2:
        st.write("")  # Spacer
        if st.button("Add Address"):
            if new_address:
                addresses.append(new_address)
                save_addresses(addresses)
                st.success("Address added!")
                st.experimental_rerun()
    
    # Current addresses
    st.write("Current Addresses:")
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

# Connections Tab
with tab4:
    st.subheader("Discord Webhook Settings")
    webhook = load_webhook()
    new_webhook = st.text_input("Discord Webhook URL", value=webhook, type="password")
    if st.button("Save Webhook"):
        save_webhook(new_webhook)
        st.success("Webhook URL saved!") 