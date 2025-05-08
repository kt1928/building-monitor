import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd

def export_to_gsheets(data, credentials_file="googl-cred.json", sheet_name="RE Data Aggregation", sheet_tab="Sheet1"):
    if not isinstance(data, (list, pd.DataFrame)):
        raise ValueError("Data must be a list of dicts or a pandas DataFrame")

    scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(credentials_file, scope)
    client = gspread.authorize(creds)

    try:
        sheet = client.open(sheet_name).worksheet(sheet_tab) if sheet_tab in [ws.title for ws in client.open(sheet_name).worksheets()] else client.open(sheet_name).add_worksheet(title=sheet_tab, rows="1000", cols="26")
    except gspread.exceptions.SpreadsheetNotFound:
        raise ValueError(f"Spreadsheet named '{sheet_name}' not found.")

    sheet.clear()

    df = pd.DataFrame(data)
    if not df.empty:
        rows = [df.columns.tolist()] + df.fillna("").astype(str).values.tolist()
        sheet.update("A1", rows)
