import streamlit as st
from utils.zillow_api import get_zillow_data, get_property_comps, get_property_details
from utils.sheets_export import export_to_gsheets
from utils.snapshot_store import init_db, save_snapshot, load_snapshot
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import pandas as pd
import os
import logging

# -- Logging --
logging.basicConfig(filename="app.log", level=logging.INFO)

# -- Init DB --
init_db()

# -- Global Geolocator --
geolocator = Nominatim(user_agent="zillow-app")

# -- Streamlit UI --
st.set_page_config(page_title="Real Estate Snapshot", layout="wide")
st.title("🏠 Real Estate Snapshot")

tab1, tab2, tab3 = st.tabs(["🔍 Simple ZIP Search", "🧐 Smart Address Search", "💸 Neighborhood Rent Analysis"])

# --- Tab 1 ---
with tab1:
    st.subheader("🔎 Simple ZIP Search")
    user_input = st.text_input("Enter a ZIP code or full address")

    min_price = st.number_input("Minimum price", value=0, step=50000)
    max_price = st.number_input("Maximum price", value=1000000, step=50000)
    min_beds = st.number_input("Minimum bedrooms", value=0, step=1)

    status_label_map = {
        "For Sale": "ForSale",
        "For Rent": "ForRent",
        "Recently Sold": "RecentlySold"
    }
    status_label = st.selectbox("Listing status", list(status_label_map.keys()))
    status_type = status_label_map[status_label]

    home_type_options = {
        "Houses": "HOUSES",
        "Apartments": "APARTMENTS",
        "Townhomes": "TOWNHOMES",
        "Condos": "CONDOS",
        "Multi-family": "MULTI_FAMILY",
        "Manufactured": "MANUFACTURED",
        "Lots/Land": "LOT_LAND"
    }
    selected_home_types = st.multiselect("Home types", list(home_type_options.keys()), default=list(home_type_options.keys()))
    home_type_param = ",".join(home_type_options[ht] for ht in selected_home_types)

    force_refresh = st.checkbox("Force new snapshot", value=False)

    if st.button("Search", key="search_tab1"):
        if not user_input:
            st.warning("Please enter a ZIP or address.")
        else:
            try:
                if user_input.isdigit() and len(user_input) == 5:
                    zip_code = user_input
                else:
                    location = geolocator.geocode(user_input)
                    if not location:
                        raise ValueError("Could not geocode input.")
                    zip_code = location.raw.get("address", {}).get("postcode")
                    if not zip_code or not zip_code.isdigit():
                        raise ValueError("Could not determine a valid U.S. ZIP code.")

                st.info(f"📍 Using ZIP code: {zip_code} | Status: {status_type}")

                snapshot_key = f"{zip_code}_{status_type}_{min_beds}_{home_type_param}"
                df_snapshot = None if force_refresh else load_snapshot(snapshot_key)

                if df_snapshot is not None:
                    listings = df_snapshot.to_dict(orient="records")
                else:
                    listings = get_zillow_data(
                        zip_code=zip_code,
                        min_price=min_price,
                        max_price=max_price,
                        status_type=status_type,
                        min_beds=min_beds,
                        home_types=home_type_param
                    )
                    if listings:
                        df_temp = pd.DataFrame(listings)
                        save_snapshot(snapshot_key, df_temp)

                if not listings:
                    st.warning("No listings found.")
                else:
                    df = pd.DataFrame(listings)
                    display_cols = [
                        "bathrooms", "bedrooms", "propertyType", "address", "rentZestimate", 
                        "priceChange", "zestimate", "price", "lotAreaValue", "lotAreaUnit", 
                        "listingStatus", "daysOnZillow", "datePriceChanged", "unit"
                    ]
                    df_display = df[[col for col in display_cols if col in df.columns]].copy()
                    df_display = df_display.drop_duplicates(subset=["address", "price"], keep="first")

                    
                    st.session_state["df_display"] = df_display

                    st.success(f"✅ Found {len(df_display)} listings.")
                    st.dataframe(df_display)

            except Exception as e:
                st.error(f"❌ Error: {e}")

    if "df_display" in st.session_state:
        if st.button("Export to Google Sheets", key="export_tab1"):
            try:
                df_export = st.session_state["df_display"]
                if not df_export.empty:
                    from datetime import datetime
                    timestamp = datetime.now().strftime("%H%M%S")
                    sheet_suffix = zip_code if 'zip_code' in locals() else "data"
                    export_to_gsheets(df_export, sheet_tab=f"ZipSearch_{user_input}_{timestamp}")
                    st.success("📄 Exported to Google Sheets successfully.")
                else:
                    st.warning("No data available to export.")
            except Exception as e:
                st.error(f"❌ Failed to export: {e}")

# --- Tab 3: Rent Analysis ---
with tab3:
    st.subheader("💸 Neighborhood Rent Analysis")
    zip_input = st.text_input("Enter ZIP code for rent analysis")
    selected_property_types = st.multiselect("Filter by Property Type", ["APARTMENT", "CONDO", "HOUSE", "TOWNHOUSE"], default=["APARTMENT", "CONDO", "HOUSE", "TOWNHOUSE"])
    bedroom_filter = st.number_input("Minimum Bedrooms", min_value=0, value=0, step=1)
    max_rent = st.number_input("Maximum Rent", min_value=0, value=10000, step=100)

    if st.button("📊 Analyze Rent Market"):
        if not zip_input or not zip_input.isdigit():
            st.warning("Please enter a valid ZIP code.")
        else:
            try:
                listings = get_zillow_data(
                    zip_code=zip_input,
                    status_type="ForRent",
                    min_beds=bedroom_filter,
                    max_price=max_rent,
                    home_types=','.join(selected_property_types)
                )
                
                if not listings:
                    st.warning("No rental listings found.")
                else:
                    df = pd.DataFrame(listings)
                    display_cols = [
                        "address", "bedrooms", "bathrooms", "price", "livingArea", 
                        "propertyType", "listingStatus", "daysOnZillow"
                    ]
                    df_display = df[[col for col in display_cols if col in df.columns]].copy()
                    df_display = df_display.drop_duplicates(subset=["address", "price", "livingArea"], keep="first")

                    # Flatten nested address field if needed
                    if "address" in df_display.columns:
                        df_display["address"] = df_display["address"].apply(
                            lambda x: f"{x.get('streetAddress', '')}, {x.get('city', '')}, {x.get('state', '')} {x.get('zipcode', '')}" if isinstance(x, dict) else x
                        )

                    # Calculate Rent per SqFt
                    if "price" in df_display.columns and "livingArea" in df_display.columns:
                        df_display["Rent/SqFt"] = (df_display["price"] / df_display["livingArea"]).round(2)

                    st.session_state["df_display"] = df_display

                    st.success(f"✅ Found {len(df_display)} rental listings.")
                    st.dataframe(df_display)
                    st.markdown("#### 📊 Sale Price Distribution")
                    

                    st.markdown("### 📈 Rent Market Summary")
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Average Rent", f"${df_display['price'].mean():,.0f}")
                    col2.metric("Avg Rent/SqFt", f"${df_display['Rent/SqFt'].mean():.2f}")
                    col3.metric("Median Bedrooms", f"{df_display['bedrooms'].median():.1f}")

                    st.markdown("#### 📊 Rent Distribution")
                    st.bar_chart(df_display[["price"]].rename(columns={"price": "Monthly Rent"}))

            except Exception as e:
                st.error(f"❌ Error: {e}")

            except Exception as e:
                st.error(f"❌ Error: {e}")

    if "df_display" in st.session_state:
        if st.button("Export to Google Sheets", key="export_tab3"):
            try:
                df_export = st.session_state["df_display"]
                if not df_export.empty:
                    from datetime import datetime
                    timestamp = datetime.now().strftime("%H%M%S")
                    sheet_suffix = zip_code if 'zip_code' in locals() else "data"
                    export_to_gsheets(df_export, sheet_tab=f"RentAnalysis_{zip_input}_{timestamp}")
                    st.success("📄 Exported to Google Sheets successfully.")
                else:
                    st.warning("No data available to export.")
            except Exception as e:
                st.error(f"❌ Failed to export: {e}")

# --- Tab 2 ---
with tab2:
    st.subheader("📍 Search by Property Address (Using Property Comps + Details)")
    address_input = st.text_input("Enter a full address (e.g., 952A Greene Ave, Brooklyn, NY 11221)")

    if st.button("🔍 Step 1: Find Comparable Properties"):
        if not address_input:
            st.warning("Please enter a full address.")
        else:
            location = geolocator.geocode(address_input)
            if not location:
                st.error("Could not geocode the address.")
            else:
                base_coords = (location.latitude, location.longitude)
                st.session_state["base_coords"] = base_coords
                st.session_state["geo_address"] = address_input
                st.info(f"Coordinates: ({location.latitude:.5f}, {location.longitude:.5f})")

                try:
                    comps = get_property_comps(address_input, limit=20)
                    if not comps:
                        st.warning("No comparable properties found.")
                    else:
                        all_addresses = [
                            f"{addr.get('streetAddress', '')}, {addr.get('city', '')}, {addr.get('state', '')} {addr.get('zipcode', '')}"
                            for comp in comps
                            if isinstance((addr := comp.get('address')), dict)
                        ]
                        st.session_state["all_addresses"] = all_addresses
                        st.success(f"✅ Found {len(all_addresses)} comparable property addresses.")

                except Exception as e:
                    st.error(f"❌ Error during address search: {e}")

    if st.button("⚙️ Step 2: Enrich Property Details"):
        all_addresses = st.session_state.get("all_addresses", [])
        base_coords = st.session_state.get("base_coords")
        if not all_addresses or not base_coords:
            st.warning("No address list or coordinates found. Please run Step 1 first.")
        else:
            enriched_rows = []
            with st.spinner("🔄 Enriching comparable property data..."):
                for full_address in all_addresses:
                    retry_count = 0
                    while retry_count < 5:
                        details = get_property_details(full_address)
                        if details:
                            break
                        else:
                            wait = 2 ** retry_count
                            st.warning(f"⏳ Retrying in {wait} seconds due to rate limit...")
                            time.sleep(wait)
                            retry_count += 1

                    if not details:
                        continue

                    enriched = {
                        "Address": full_address,
                        "Price Sold": details.get("price", ""),
                        "Living Area": details.get("livingAreaValue", ""),
                        "Date Sold": details.get("dateSold", ""),
                        "Bedrooms": details.get("bedrooms", ""),
                        "Bathrooms": details.get("bathrooms", "")
                    }

                    prop_coords = (details.get("latitude"), details.get("longitude"))
                    if all(prop_coords):
                        enriched["Distance (mi)"] = round(geodesic(base_coords, prop_coords).miles, 2)
                    else:
                        enriched["Distance (mi)"] = "N/A"

                    enriched_rows.append(enriched)

            if not enriched_rows:
                st.warning("No detailed data retrieved from property details API.")
            else:
                df_display = pd.DataFrame(enriched_rows)
                st.session_state["df_display"] = df_display

                st.success(f"✅ Retrieved and enriched {len(df_display)} properties.")
                st.dataframe(df_display)

    if "df_display" in st.session_state:
        if st.button("Export to Google Sheets", key="export_tab2"):
            try:
                df_export = st.session_state["df_display"]
                if not df_export.empty:
                    from datetime import datetime
                    timestamp = datetime.now().strftime("%H%M%S")
                    sheet_suffix = zip_code if 'zip_code' in locals() else "data"
                    export_to_gsheets(df_export, sheet_tab=f"CompReport_{timestamp}")
                    st.success("📄 Exported to Google Sheets successfully.")
                else:
                    st.warning("No data available to export.")
            except Exception as e:
                st.error(f"❌ Failed to export: {e}")
