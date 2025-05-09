import streamlit as st
import json
from pathlib import Path
import subprocess
import time
from datetime import datetime, timedelta
import pytz
import sqlite3
from building_monitor import (
    scrape_bins_for_addresses, get_violations_by_bin, get_ecb_violations_by_bin,
    add_owner, update_owner_preferences, get_all_owners, assign_address_to_owner,
    remove_address_from_owner, get_owner_addresses, parse_address_for_bis,
    init_db
)

# === CONFIG ===
SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_DIR = SCRIPT_DIR.parent / "config"
DB_DIR = SCRIPT_DIR.parent / "dbs"
ADDRESS_FILE = CONFIG_DIR / "addresses.txt"
WEBHOOK_FILE = CONFIG_DIR / "webhook.txt"
SCHEDULE_FILE = CONFIG_DIR / "schedule.json"
PROXY_FILE = CONFIG_DIR / "proxy.txt"
DB_PATH = DB_DIR / "building_monitor.db"

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
            addresses = []
            for line in f:
                line = line.strip()
                if line:
                    # Parse address and BIN if present
                    if '|' in line:
                        address, bin_number = line.split('|')
                        addresses.append({'address': address.strip(), 'bin': bin_number.strip()})
                    else:
                        addresses.append({'address': line, 'bin': None})
            return addresses
    return []

def save_addresses(addresses):
    with open(ADDRESS_FILE, 'w') as f:
        for addr in addresses:
            if addr['bin']:
                f.write(f"{addr['address']}|{addr['bin']}\n")
            else:
                f.write(f"{addr['address']}\n")

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

def get_address_details(address):
    """Get all details for an address including BIN and violations"""
    conn = init_db()
    c = conn.cursor()
    
    # Get BIN
    c.execute("SELECT bin FROM bis_status WHERE address = ?", (address,))
    bin_result = c.fetchone()
    bin_number = bin_result[0] if bin_result else None
    
    # Get violations if we have a BIN
    dob_violations = []
    ecb_violations = []
    if bin_number:
        dob_violations = get_violations_by_bin(bin_number)
        ecb_violations = get_ecb_violations_by_bin(bin_number)
    
    conn.close()
    
    return {
        'bin': bin_number,
        'dob_violations': dob_violations,
        'ecb_violations': ecb_violations
    }

def show_dashboard():
    st.title("🏢 Building Monitor Dashboard")

    # Initialize database
    conn = None
    try:
        conn = init_db()
        c = conn.cursor()
        
        # Quick Actions
        col1, col2 = st.columns([1, 2])
        with col1:
            # Get all owners for the dropdown
            owners = get_all_owners(conn)
            owner_names = {owner['name']: owner['id'] for owner in owners}
            
            selected_owner = st.selectbox(
                "Select Owner",
                ["All Owners"] + list(owner_names.keys()),
                key="owner_select"
            )
            
            if st.button("Run Check Now", use_container_width=True):
                with st.spinner("Running check..."):
                    try:
                        # If a specific owner is selected, pass their ID to the script
                        owner_id = owner_names.get(selected_owner) if selected_owner != "All Owners" else None
                        cmd = ["python", str(SCRIPT_DIR / "building_monitor.py")]
                        if owner_id:
                            cmd.extend(["--owner", str(owner_id)])
                        subprocess.run(cmd, check=True)
                        st.success("Check completed successfully!")
                        time.sleep(1)  # Give user time to see the success message
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error running check: {e}")
        
        # Get all addresses with their BINs
        addresses = load_addresses()
        
        # Create metrics
        total_addresses = len(addresses)
        addresses_with_bins = sum(1 for addr in addresses if addr['bin'])
        addresses_without_bins = total_addresses - addresses_with_bins
        
        # Display metrics in a row
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Addresses", total_addresses)
        with col2:
            st.metric("Addresses with BINs", addresses_with_bins)
        with col3:
            st.metric("Addresses without BINs", addresses_without_bins)
        
        # Display addresses in a table with BIN status
        st.subheader("Address Status")
        address_data = []
        for addr in addresses:
            # Get violation counts from database
            c.execute("""
                SELECT dob_violations, ecb_violations, last_checked
                FROM bis_status
                WHERE LOWER(address) = LOWER(?)
            """, (addr['address'],))
            result = c.fetchone()
            dob_violations = str(result[0]) if result and result[0] is not None else "0"
            ecb_violations = str(result[1]) if result and result[1] is not None else "0"
            last_checked = result[2] if result else "Never"
            
            status = "✅" if addr['bin'] else "❌"
            address_data.append({
                "Address": addr['address'],
                "BIN Status": status,
                "BIN": addr['bin'] or "Not Found",
                "DOB Violations": dob_violations,
                "ECB Violations": ecb_violations,
                "Last Checked": last_checked or "Never"
            })
        
        st.dataframe(
            address_data,
            column_config={
                "Address": st.column_config.TextColumn("Address", width="large"),
                "BIN Status": st.column_config.TextColumn("BIN Status", width="small"),
                "BIN": st.column_config.TextColumn("BIN", width="medium"),
                "DOB Violations": st.column_config.TextColumn("DOB Violations", width="small"),
                "ECB Violations": st.column_config.TextColumn("ECB Violations", width="small"),
                "Last Checked": st.column_config.TextColumn("Last Checked", width="medium")
            },
            hide_index=True
        )
        
    except Exception as e:
        st.error(f"Error initializing database: {e}")
        if st.button("Retry Database Initialization"):
            st.rerun()
    finally:
        if conn:
            conn.close()

def show_insights():
    st.title("📊 Building Monitor Insights")
    
    conn = init_db()
    c = conn.cursor()
    
    # Get addresses from the addresses file
    addresses = load_addresses()
    
    # Create tabs for different insights
    tab1, tab2, tab3 = st.tabs(["Address Details", "Owner Analysis", "Violation Trends"])
    
    with tab1:
        st.subheader("Detailed Address Information")
        for addr_data in addresses:
            address = addr_data['address']
            bin = addr_data['bin']
            
            # Get violation data from database
            c.execute("""
                SELECT 
                    COALESCE(bs.dob_violations, 0) as dob_violations,
                    COALESCE(bs.ecb_violations, 0) as ecb_violations,
                    bs.last_checked,
                    o.name as owner_name,
                    COUNT(DISTINCT c.incident_id) as complaint_count,
                    COUNT(DISTINCT CASE WHEN c.status = 'Open' THEN c.incident_id END) as open_complaints,
                    COUNT(DISTINCT CASE WHEN c.status = 'Closed' THEN c.incident_id END) as closed_complaints
                FROM bis_status bs
                LEFT JOIN address_owners ao ON LOWER(bs.address) = LOWER(ao.address)
                LEFT JOIN owners o ON ao.owner_id = o.id
                LEFT JOIN complaints_311 c ON LOWER(bs.address) = LOWER(c.address)
                WHERE LOWER(bs.address) = LOWER(?)
                GROUP BY LOWER(bs.address)
            """, (address,))
            result = c.fetchone()
            
            if result:
                dob_violations, ecb_violations, last_checked, owner, complaint_count, open_complaints, closed_complaints = result
            else:
                dob_violations = ecb_violations = 0
                last_checked = "Never"
                owner = None
                complaint_count = open_complaints = closed_complaints = 0
            
            # Format the address display with BIN if available
            display_address = f"{address}"
            if bin:
                display_address = f"{address} : BIN#{bin}"
            
            with st.expander(display_address):
                col1, col2 = st.columns(2)
                with col1:
                    st.write("**Basic Information**")
                    st.write(f"BIN: {bin or 'Not Found'}")
                    st.write(f"Owner: {owner or 'Unassigned'}")
                    st.write(f"Last Checked: {last_checked or 'Never'}")
                with col2:
                    st.write("**Violations & Complaints**")
                    st.write(f"DOB Violations: {dob_violations}")
                    st.write(f"ECB Violations: {ecb_violations}")
                    st.write(f"Total 311 Complaints: {complaint_count}")
                    if complaint_count > 0:
                        st.write(f"- Open Complaints: {open_complaints}")
                        st.write(f"- Closed Complaints: {closed_complaints}")
                
                # Show DOB violations if we have a BIN
                if bin:
                    dob_violations = get_violations_by_bin(bin)
                    if dob_violations:
                        st.write("**DOB Violations**")
                        for violation in dob_violations[:5]:  # Show last 5 violations
                            st.write(f"**Violation Details:**")
                            st.write(f"- Date: {violation.get('issue_date', 'N/A')}")
                            st.write(f"- Type: {violation.get('violation_type', 'N/A')}")
                            st.write(f"- Description: {violation.get('description', 'N/A')}")
                            st.write(f"- Status: {violation.get('status', 'N/A')}")
                            st.write(f"- Severity: {violation.get('severity', 'N/A')}")
                            st.write(f"- Disposition: {violation.get('disposition', 'N/A')}")
                            st.write(f"- Disposition Date: {violation.get('disposition_date', 'N/A')}")
                            st.write("---")
                
                # Show ECB violations if we have a BIN
                if bin:
                    ecb_violations = get_ecb_violations_by_bin(bin)
                    if ecb_violations:
                        st.write("**ECB Violations**")
                        for violation in ecb_violations[:5]:  # Show last 5 violations
                            st.write(f"**Violation Details:**")
                            st.write(f"- Date: {violation.get('issue_date', 'N/A')}")
                            st.write(f"- Type: {violation.get('violation_type', 'N/A')}")
                            st.write(f"- Description: {violation.get('description', 'N/A')}")
                            st.write(f"- Status: {violation.get('status', 'N/A')}")
                            st.write(f"- Penalty: {violation.get('penalty', 'N/A')}")
                            st.write(f"- Hearing Status: {violation.get('hearing_status', 'N/A')}")
                            st.write(f"- Hearing Date: {violation.get('hearing_date', 'N/A')}")
                            st.write("---")
                
                # Show recent 311 complaints
                if complaint_count > 0:
                    st.write("**Recent 311 Complaints**")
                    c.execute("""
                        SELECT 
                            created_date,
                            complaint_type,
                            descriptor,
                            status,
                            resolution_description,
                            closed_date,
                            agency
                        FROM complaints_311
                        WHERE LOWER(address) = LOWER(?)
                        ORDER BY created_date DESC
                        LIMIT 5
                    """, (address,))
                    complaints = c.fetchall()
                    for date, type_, descriptor, status, resolution, closed_date, agency in complaints:
                        st.write(f"**Complaint Details:**")
                        st.write(f"- Date: {date}")
                        st.write(f"- Type: {type_}")
                        st.write(f"- Descriptor: {descriptor}")
                        st.write(f"- Status: {status}")
                        st.write(f"- Agency: {agency}")
                        if closed_date:
                            st.write(f"- Closed Date: {closed_date}")
                        if resolution:
                            st.write(f"- Resolution: {resolution}")
                        st.write("---")
    
    with tab2:
        st.subheader("Owner Analysis")
        # Get owner statistics with proper BIN counting and violation details
        c.execute("""
            WITH owner_stats AS (
                SELECT 
                    o.id,
                    o.name,
                    COUNT(DISTINCT LOWER(ao.address)) as address_count,
                    COUNT(DISTINCT CASE WHEN bs.bin IS NOT NULL THEN LOWER(bs.address) END) as addresses_with_bin,
                    SUM(CAST(bs.dob_violations AS INTEGER)) as total_dob_violations,
                    SUM(CAST(bs.ecb_violations AS INTEGER)) as total_ecb_violations,
                    COUNT(DISTINCT c.incident_id) as total_complaints,
                    COUNT(DISTINCT CASE WHEN c.status = 'Open' THEN c.incident_id END) as open_complaints,
                    COUNT(DISTINCT CASE WHEN c.status = 'Closed' THEN c.incident_id END) as closed_complaints
                FROM owners o
                LEFT JOIN address_owners ao ON o.id = ao.owner_id
                LEFT JOIN bis_status bs ON LOWER(ao.address) = LOWER(bs.address)
                LEFT JOIN complaints_311 c ON LOWER(bs.address) = LOWER(c.address)
                GROUP BY o.id, o.name
            )
            SELECT 
                name,
                address_count,
                addresses_with_bin,
                total_dob_violations,
                total_ecb_violations,
                total_complaints,
                open_complaints,
                closed_complaints
            FROM owner_stats
            ORDER BY name
        """)
        owner_stats = c.fetchall()
        
        for name, addr_count, bin_count, dob_viol, ecb_viol, complaints, open_complaints, closed_complaints in owner_stats:
            with st.expander(f"{name}"):
                st.write(f"**Portfolio Overview**")
                st.write(f"Total Addresses: {addr_count}")
                st.write(f"Addresses with BINs: {bin_count}")
                st.write(f"Addresses without BINs: {addr_count - bin_count}")
                
                st.write(f"**Violations & Complaints**")
                st.write(f"Total DOB Violations: {dob_viol or 0}")
                st.write(f"Total ECB Violations: {ecb_viol or 0}")
                st.write(f"Total 311 Complaints: {complaints}")
                if complaints > 0:
                    st.write(f"- Open Complaints: {open_complaints}")
                    st.write(f"- Closed Complaints: {closed_complaints}")
                
                # Show addresses for this owner with detailed stats
                st.write("**Addresses**")
                c.execute("""
                    SELECT 
                        bs.address,
                        bs.bin,
                        bs.dob_violations,
                        bs.ecb_violations,
                        COUNT(DISTINCT c.incident_id) as complaint_count,
                        COUNT(DISTINCT CASE WHEN c.status = 'Open' THEN c.incident_id END) as open_complaints,
                        COUNT(DISTINCT CASE WHEN c.status = 'Closed' THEN c.incident_id END) as closed_complaints
                    FROM address_owners ao
                    JOIN bis_status bs ON LOWER(ao.address) = LOWER(bs.address)
                    LEFT JOIN complaints_311 c ON LOWER(bs.address) = LOWER(c.address)
                    WHERE ao.owner_id = (SELECT id FROM owners WHERE name = ?)
                    GROUP BY LOWER(bs.address)
                    ORDER BY LOWER(bs.address)
                """, (name,))
                owner_addresses = c.fetchall()
                for addr, bin, dob, ecb, comp_count, open_comp, closed_comp in owner_addresses:
                    # Format the address display with BIN if available
                    display_address = f"{addr}"
                    if bin:
                        display_address = f"{addr} : BIN#{bin}"
                    
                    st.write(f"**{display_address}**")
                    st.write(f"- DOB Violations: {dob or '0'}")
                    st.write(f"- ECB Violations: {ecb or '0'}")
                    st.write(f"- Total Complaints: {comp_count}")
                    if comp_count > 0:
                        st.write(f"  - Open: {open_comp}")
                        st.write(f"  - Closed: {closed_comp}")
    
    with tab3:
        st.subheader("Violation Trends")
        # Get violation trends with case-insensitive matching and detailed stats
        c.execute("""
            WITH violation_stats AS (
                SELECT 
                    bs.address,
                    bs.bin,
                    bs.dob_violations,
                    bs.ecb_violations,
                    COUNT(DISTINCT c.incident_id) as complaint_count,
                    COUNT(DISTINCT CASE WHEN c.status = 'Open' THEN c.incident_id END) as open_complaints,
                    COUNT(DISTINCT CASE WHEN c.status = 'Closed' THEN c.incident_id END) as closed_complaints,
                    o.name as owner_name
                FROM bis_status bs
                LEFT JOIN address_owners ao ON LOWER(bs.address) = LOWER(ao.address)
                LEFT JOIN owners o ON ao.owner_id = o.id
                LEFT JOIN complaints_311 c ON LOWER(bs.address) = LOWER(c.address)
                GROUP BY LOWER(bs.address)
                HAVING (CAST(bs.dob_violations AS INTEGER) > 0 OR 
                       CAST(bs.ecb_violations AS INTEGER) > 0 OR 
                       complaint_count > 0)
            )
            SELECT 
                address,
                bin,
                dob_violations,
                ecb_violations,
                complaint_count,
                open_complaints,
                closed_complaints,
                owner_name
            FROM violation_stats
            ORDER BY (CAST(dob_violations AS INTEGER) + 
                     CAST(ecb_violations AS INTEGER) + 
                     complaint_count) DESC
        """)
        violation_trends = c.fetchall()
        
        if violation_trends:
            st.write("**Properties with Violations or Complaints**")
            for addr, bin, dob, ecb, complaints, open_comp, closed_comp, owner in violation_trends:
                # Format the address display with BIN if available
                display_address = f"{addr}"
                if bin:
                    display_address = f"{addr} : BIN#{bin}"
                
                with st.expander(f"{display_address} ({owner or 'Unassigned'})"):
                    st.write(f"**Violation Summary**")
                    st.write(f"DOB Violations: {dob or '0'}")
                    st.write(f"ECB Violations: {ecb or '0'}")
                    st.write(f"Total 311 Complaints: {complaints}")
                    if complaints > 0:
                        st.write(f"- Open Complaints: {open_comp}")
                        st.write(f"- Closed Complaints: {closed_comp}")
                    
                    # Show recent activity with more details
                    c.execute("""
                        SELECT 
                            created_date,
                            complaint_type,
                            descriptor,
                            status,
                            resolution_description,
                            closed_date,
                            agency
                        FROM complaints_311
                        WHERE LOWER(address) = LOWER(?)
                        ORDER BY created_date DESC
                        LIMIT 3
                    """, (addr,))
                    recent_activity = c.fetchall()
                    if recent_activity:
                        st.write("**Recent Activity**")
                        for date, type_, descriptor, status, resolution, closed_date, agency in recent_activity:
                            st.write(f"**Complaint Details:**")
                            st.write(f"- Date: {date}")
                            st.write(f"- Type: {type_}")
                            st.write(f"- Descriptor: {descriptor}")
                            st.write(f"- Status: {status}")
                            st.write(f"- Agency: {agency}")
                            if closed_date:
                                st.write(f"- Closed Date: {closed_date}")
                            if resolution:
                                st.write(f"- Resolution: {resolution}")
                            st.write("---")
        else:
            st.write("No violations or complaints found in the database.")

def show_address_management():
    st.title("📍 Address Management")
    
    # Add new address
    col1, col2 = st.columns([3, 1])
    with col1:
        new_address = st.text_input("Add New Address", 
                                   placeholder="Enter address in format: 123 Main St, Borough, NY ZIP",
                                   key="new_address_input")
    with col2:
        st.write("")  # Spacer
        if st.button("Add Address"):
            if new_address:
                addresses = load_addresses()
                # Check for case-insensitive duplicates
                if not any(addr['address'].lower() == new_address.lower() for addr in addresses):
                    addresses.append({'address': new_address, 'bin': None})
                    save_addresses(addresses)
                    st.success("Address added!")
                    time.sleep(1)  # Give user time to see the success message
                    st.rerun()
                else:
                    st.error("This address already exists (case-insensitive match)")
    
    # Grab BINs button
    if st.button("Grab BINs for Missing Addresses"):
        with st.spinner("Scraping BINs..."):
            addresses = load_addresses()
            results = scrape_bins_for_addresses()
            
            # Update addresses with new BINs
            for result in results:
                for addr in addresses:
                    if addr['address'].lower() == result['address'].lower():
                        if result['status'] == 'scraped' and result['bin']:
                            addr['bin'] = result['bin']
            
            # Save updated addresses
            save_addresses(addresses)
            
            success_count = sum(1 for r in results if r['status'] in ['scraped', 'already_stored'])
            error_count = len(results) - success_count
            
            # Show results
            st.success(f"Completed! Found {success_count} BINs, {error_count} errors")
            
            # Show detailed results
            with st.expander("View Details"):
                for result in results:
                    status_color = {
                        'scraped': '🟢',
                        'already_stored': '🔵',
                        'parse_error': '🔴',
                        'not_found': '🔴',
                        'error': '🔴'
                    }.get(result['status'], '⚪')
                    
                    st.write(f"{status_color} {result['address']}")
                    if result['bin']:
                        st.write(f"   BIN: {result['bin']}")
                    st.write(f"   Status: {result['status']}")
                    if 'error' in result:
                        st.write(f"   Error: {result['error']}")
    
    # Current addresses
    st.write("Current Addresses:")
    addresses = load_addresses()
    # Sort addresses case-insensitively
    addresses.sort(key=lambda x: x['address'].lower())
    
    for i, addr in enumerate(addresses):
        col1, col2 = st.columns([3, 1])
        with col1:
            # Create BIS URL
            house_no, street, boro_code = parse_address_for_bis(addr['address'])
            if all([house_no, street, boro_code]):
                bis_url = f"https://a810-bisweb.nyc.gov/bisweb/PropertyProfileOverviewServlet?boro={boro_code}&houseno={house_no}&street={street.replace(' ', '+')}"
                st.markdown(f"[{addr['address']}]({bis_url})")
                if addr['bin']:
                    st.write(f"BIN: {addr['bin']}")
            else:
                st.write(addr['address'])
            
        with col2:
            if st.button("Remove", key=f"remove_addr_{i}"):
                addresses.pop(i)
                save_addresses(addresses)
                st.success("Address removed!")
                time.sleep(1)  # Give user time to see the success message
                st.rerun()

def show_owner_management():
    st.title("👤 Owner Management")
    
    # Initialize database connection
    conn = init_db()
    
    # Add new owner section
    with st.expander("➕ Add New Owner", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            new_owner_name = st.text_input("Owner Name", key="new_owner_name")
            new_owner_discord = st.text_input("Discord Webhook URL", type="password", key="new_owner_discord")
        with col2:
            new_owner_email = st.text_input("Email Address", key="new_owner_email")
            new_owner_phone = st.text_input("Phone Number", key="new_owner_phone")
        
        # Schedule settings for new owner
        st.write("Notification Schedule (24-hour format):")
        schedule_cols = st.columns(3)
        default_schedule = [8, 12, 20]
        new_schedule = []
        for i, time in enumerate(default_schedule):
            with schedule_cols[i]:
                new_time = st.number_input(f"Time {i+1}", min_value=0, max_value=23, value=time, step=1, key=f"new_time_{i}")
                new_schedule.append(new_time)
        
        if st.button("Add Owner", use_container_width=True):
            if new_owner_name:
                owner_id = add_owner(
                    conn,
                    new_owner_name,
                    new_owner_discord if new_owner_discord else None,
                    new_owner_email if new_owner_email else None,
                    new_owner_phone if new_owner_phone else None
                )
                st.success(f"Added owner: {new_owner_name}")
                st.rerun()
            else:
                st.error("Owner name is required")
    
    # List owners and their properties
    owners = get_all_owners(conn)
    addresses = load_addresses()
    all_addresses = [addr['address'] for addr in addresses]
    
    # Create tabs for each owner
    owner_tabs = st.tabs([owner['name'] for owner in owners])
    
    for i, (owner, tab) in enumerate(zip(owners, owner_tabs)):
        with tab:
            # Owner details and preferences
            col1, col2 = st.columns([2, 1])
            
            with col1:
                st.subheader("Notification Preferences")
                new_discord = st.text_input(
                    "Discord Webhook",
                    value=owner['discord_webhook'] or "",
                    type="password",
                    key=f"discord_{owner['id']}"
                )
                new_email = st.text_input(
                    "Email",
                    value=owner['email'] or "",
                    key=f"email_{owner['id']}"
                )
                new_phone = st.text_input(
                    "Phone",
                    value=owner['phone'] or "",
                    key=f"phone_{owner['id']}"
                )
                
                # Schedule settings
                st.write("Notification Schedule (24-hour format):")
                schedule_cols = st.columns(3)
                current_schedule = json.loads(owner.get('schedule', '[8, 12, 20]'))
                new_schedule = []
                for j, time in enumerate(current_schedule):
                    with schedule_cols[j]:
                        new_time = st.number_input(
                            f"Time {j+1}",
                            min_value=0,
                            max_value=23,
                            value=time,
                            step=1,
                            key=f"time_{owner['id']}_{j}"
                        )
                        new_schedule.append(new_time)
                
                if st.button("Update Preferences", key=f"update_{owner['id']}", use_container_width=True):
                    update_owner_preferences(
                        conn,
                        owner['id'],
                        new_discord if new_discord else None,
                        new_email if new_email else None,
                        new_phone if new_phone else None,
                        json.dumps(new_schedule)
                    )
                    st.success("Preferences updated!")
            
            with col2:
                st.subheader("Address Management")
                owner_addrs = get_owner_addresses(conn, owner['id'])
                
                # Show assigned addresses with quick remove buttons
                if owner_addrs:
                    st.write("**Assigned Addresses:**")
                    for addr in owner_addrs:
                        col_a, col_b = st.columns([3, 1])
                        with col_a:
                            st.write(f"📍 {addr}")
                        with col_b:
                            if st.button("Remove", key=f"remove_{owner['id']}_{addr}", use_container_width=True):
                                remove_address_from_owner(conn, addr, owner['id'])
                                st.success(f"Removed {addr}")
                                st.rerun()
                
                # Assign new addresses
                st.write("**Assign New Addresses:**")
                unassigned = [addr for addr in all_addresses if addr not in owner_addrs]
                if unassigned:
                    selected_addrs = st.multiselect(
                        "Select Addresses",
                        unassigned,
                        key=f"select_{owner['id']}"
                    )
                    if selected_addrs and st.button("Assign Selected", key=f"assign_{owner['id']}", use_container_width=True):
                        for addr in selected_addrs:
                            assign_address_to_owner(conn, addr, owner['id'])
                        st.success(f"Assigned {len(selected_addrs)} address(es)")
                        st.rerun()
                else:
                    st.info("No unassigned addresses available")
    
    conn.close()

def show_settings():
    st.title("⚙️ Settings")
    
    # Proxy settings
    st.subheader("Proxy Settings")
    proxy_url = load_proxy()
    
    # Single toggle button that changes color and text based on state
    if st.button(
        "Proxy: " + ("ON" if proxy_url else "OFF"),
        type="primary" if proxy_url else "secondary",
        key="proxy_toggle"
    ):
        if proxy_url:
            save_proxy("")  # Turn off
        else:
            save_proxy("http://customer-kappy_nrNdL-cc-US:3tGCOHQaFsfv1pzlrDAm+@pr.oxylabs.io:7777")  # Turn on
        st.rerun()

def main():
    st.set_page_config(
        page_title="Building Monitor",
        page_icon="🏢",
        layout="wide"
    )
    
    # Use tabs for navigation
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🏢 Dashboard", 
        "📊 Insights", 
        "📍 Address Management", 
        "👤 Owner Management", 
        "⚙️ Settings"
    ])
    
    with tab1:
        show_dashboard()
    with tab2:
        show_insights()
    with tab3:
        show_address_management()
    with tab4:
        show_owner_management()
    with tab5:
        show_settings()

if __name__ == "__main__":
    main() 