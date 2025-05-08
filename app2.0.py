import streamlit as st
from utils.zillow_api import get_zillow_data, get_property_comps, get_property_details
from utils.sheets_export import export_to_gsheets
from utils.snapshot_store import init_db, save_snapshot, load_snapshot
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import pandas as pd
import os
import logging
import pydeck as pdk

# -- Logging --
logging.basicConfig(filename="app.log", level=logging.INFO)

# -- Init DB --
init_db()

# -- Global Geolocator --
geolocator = Nominatim(user_agent="zillow-app")

st.set_page_config(page_title="Real Estate Market Snapshot", layout="wide")
st.title("🏠 Real Estate Market Snapshot")

# --- MODE SELECTION ---
mode = st.radio("Select Mode:", [
    "🔍 ZIP Code Search",
    "📍 Smart Address Lookup",
    "💸 Rent Market Analysis"
])

# --- COMMON FILTERS ---
# (Sidebar cleared, no export button)
with st.sidebar:
    st.header("🔧 Actions")
    st.info("Select a mode and run a search.")

# --- ZIP MODE ---
if mode == "🔍 ZIP Code Search":
    st.subheader("ZIP Code Search")
    zip_code = st.text_input("Enter ZIP Code")
    min_price = st.number_input("Min Price", 0, 10_000_000, 0, step=50000)
    max_price = st.number_input("Max Price", 0, 10_000_000, 1_000_000, step=50000)
    min_beds = st.number_input("Min Bedrooms", 0, 10, 0, step=1)
    home_types = st.multiselect("Home Types", [
        "HOUSES", "APARTMENTS", "TOWNHOMES", "CONDOS", "MULTI_FAMILY"
    ], default=["HOUSES", "MULTI_FAMILY"])
    if st.button("Search ZIP"):
        if not zip_code:
            st.warning("Please enter a ZIP code.")
        else:
            try:
                if zip_code.isdigit() and len(zip_code) == 5:
                    pass
                else:
                    location = geolocator.geocode(zip_code)
                    if not location:
                        raise ValueError("Could not geocode input.")
                    zip_code = location.raw.get("address", {}).get("postcode")
                    if not zip_code or not zip_code.isdigit():
                        raise ValueError("Could not determine a valid U.S. ZIP code.")

                st.info(f"📍 Using ZIP code: {zip_code}")

                home_type_param = ",".join(home_types)
                listings = get_zillow_data(
                    zip_code=zip_code,
                    min_price=min_price,
                    max_price=max_price,
                    status_type="ForSale",
                    min_beds=min_beds,
                    home_types=home_type_param
                )

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
        if st.button("Export to Google Sheets", key="export_zip"):
            try:
                df_export = st.session_state["df_display"]
                if not df_export.empty:
                    from datetime import datetime
                    timestamp = datetime.now().strftime("%H%M%S")
                    export_to_gsheets(df_export, sheet_tab=f"ZipSearch_{zip_code}_{timestamp}")
                    st.success("📄 Exported to Google Sheets successfully.")
                else:
                    st.warning("No data available to export.")
            except Exception as e:
                st.error(f"❌ Failed to export: {e}")

# --- ADDRESS MODE ---
elif mode == "📍 Smart Address Lookup":
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
            import time
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

                # --- Stats Graph ---
                st.markdown("### 📊 Median & Average Stats")
                stats = {}
                for col in ["Price Sold", "Living Area", "Bedrooms", "Bathrooms", "Distance (mi)"]:
                    if col in df_display.columns:
                        vals = pd.to_numeric(df_display[col], errors='coerce').dropna()
                        if not vals.empty:
                            stats[col] = {
                                "median": vals.median(),
                                "mean": vals.mean()
                            }
                if stats:
                    stat_cols = st.columns(len(stats))
                    for i, (col, vals) in enumerate(stats.items()):
                        if col == "Price Sold":
                            stat_cols[i].metric(f"{col} Median", f"${vals['median']:,.0f}")
                            stat_cols[i].metric(f"{col} Average", f"${vals['mean']:,.0f}")
                        elif col == "Living Area":
                            stat_cols[i].metric(f"{col} Median", f"{vals['median']:,.0f} sqft")
                            stat_cols[i].metric(f"{col} Average", f"{vals['mean']:,.0f} sqft")
                        else:
                            stat_cols[i].metric(f"{col} Median", f"{vals['median']:.2f}")
                            stat_cols[i].metric(f"{col} Average", f"{vals['mean']:.2f}")

                # --- Map Visualization ---
                st.markdown("### 🗺️ Comparable Properties Map")
                map_data = []
                # Add comparable properties (red pins)
                for idx, row in df_display.iterrows():
                    if pd.notnull(row.get("Address")) and pd.notnull(row.get("Distance (mi)")):
                        details = get_property_details(row["Address"])
                        lat, lon = details.get("latitude"), details.get("longitude")
                        if lat and lon:
                            map_data.append({
                                "lat": lat,
                                "lon": lon,
                                "color": [255, 0, 0],
                                "label": row["Address"]
                            })
                # Add input address (green pin)
                if base_coords:
                    map_data.append({
                        "lat": base_coords[0],
                        "lon": base_coords[1],
                        "color": [0, 200, 0],
                        "label": "Input Address"
                    })
                if map_data:
                    map_df = pd.DataFrame(map_data)
                    layer = pdk.Layer(
                        "ScatterplotLayer",
                        data=map_df,
                        get_position='[lon, lat]',
                        get_color='color',
                        get_radius=80,
                        pickable=True
                    )
                    view_state = pdk.ViewState(
                        latitude=map_df["lat"].mean(),
                        longitude=map_df["lon"].mean(),
                        zoom=13,
                        pitch=0
                    )
                    st.pydeck_chart(pdk.Deck(
                        layers=[layer],
                        initial_view_state=view_state,
                        tooltip={"text": "{label}"}
                    ))

    if "df_display" in st.session_state:
        if st.button("Export to Google Sheets", key="export_tab2"):
            try:
                df_export = st.session_state["df_display"]
                if not df_export.empty:
                    from datetime import datetime
                    timestamp = datetime.now().strftime("%H%M%S")
                    export_to_gsheets(df_export, sheet_tab=f"CompReport_{timestamp}")
                    st.success("📄 Exported to Google Sheets successfully.")
                else:
                    st.warning("No data available to export.")
            except Exception as e:
                st.error(f"❌ Failed to export: {e}")

# --- RENT MODE ---
elif mode == "💸 Rent Market Analysis":
    st.subheader("Rental Market Lookup")
    rent_zip = st.text_input("Enter ZIP for Rent Search")
    max_rent = st.number_input("Max Rent", 500, 20000, 5000, step=100)
    selected_property_types = st.multiselect("Filter by Property Type", ["APARTMENT", "CONDO", "HOUSE", "TOWNHOUSE"], default=["APARTMENT", "CONDO", "HOUSE", "TOWNHOUSE"])
    bedroom_filter = st.number_input("Minimum Bedrooms", min_value=0, value=0, step=1)
    if st.button("Analyze Rent"):
        if not rent_zip or not rent_zip.isdigit():
            st.warning("Please enter a valid ZIP code.")
        else:
            try:
                listings = get_zillow_data(
                    zip_code=rent_zip,
                    status_type="ForRent",
                    min_beds=bedroom_filter,
                    max_price=max_rent,
                    home_types=','.join(selected_property_types)
                )

                # Strictly filter by max_rent in case API returns extra
                if listings:
                    listings = [l for l in listings if l.get("price") is not None and l["price"] <= max_rent]

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

                    st.markdown("### 📈 Rent Market Summary")
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Average Rent", f"${df_display['price'].mean():,.0f}")
                    col2.metric("Avg Rent/SqFt", f"${df_display['Rent/SqFt'].mean():.2f}")
                    col3.metric("Median Bedrooms", f"{df_display['bedrooms'].median():.1f}")

                    st.markdown("#### 📊 Rent Distribution")
                    st.bar_chart(df_display[["price"]].rename(columns={"price": "Monthly Rent"}))

            except Exception as e:
                st.error(f"❌ Error: {e}")

    if "df_display" in st.session_state:
        if st.button("Export to Google Sheets", key="export_rent"):
            try:
                df_export = st.session_state["df_display"]
                if not df_export.empty:
                    from datetime import datetime
                    timestamp = datetime.now().strftime("%H%M%S")
                    export_to_gsheets(df_export, sheet_tab=f"RentAnalysis_{rent_zip}_{timestamp}")
                    st.success("📄 Exported to Google Sheets successfully.")
                else:
                    st.warning("No data available to export.")
            except Exception as e:
                st.error(f"❌ Failed to export: {e}")

# --- EXPORT + DASHBOARD ---
# st.markdown("---")
# st.markdown("#### 📍 Optional Map + Graphs Here")
# st.caption("Map and bar chart to be added with pydeck or matplotlib")
