import streamlit as st
import pandas as pd
from datetime import datetime, date, time as dtime
import time as pytime
import gspread
from google.oauth2.service_account import Credentials

# -----------------------------
# Config
# -----------------------------
st.set_page_config(page_title="Golf Tracker", layout="centered")

# Read creds & sheet URL from Streamlit secrets (Settings → Secrets)
SERVICE_INFO = st.secrets["gcp_service_account"]
SHEET_URL = st.secrets["sheets"]["url"]

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

creds = Credentials.from_service_account_info(dict(SERVICE_INFO), scopes=SCOPES)
client = gspread.authorize(creds)
worksheet = client.open_by_url(SHEET_URL).sheet1

# Expected columns
COLUMNS = ["Name", "Group Size", "Transport", "Start Time", "End Time", "Total Elapsed"]

def ensure_headers():
    values = worksheet.get_all_values()
    if not values:
        worksheet.append_row(COLUMNS)
    else:
        header = values[0]
        if header != COLUMNS:
            worksheet.update("A1:F1", [COLUMNS])

ensure_headers()

# -----------------------------
# Utilities
# -----------------------------
def parse_iso(dt_str: str):
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str)
    except Exception:
        try:
            return pd.to_datetime(dt_str).to_pydatetime()
        except Exception:
            return None

def isoformat(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()

def fmt_hms(total_seconds: int) -> str:
    if total_seconds < 0:
        total_seconds = 0
    hrs = total_seconds // 3600
    rem = total_seconds % 3600
    mins = rem // 60
    secs = rem % 60
    return f"{hrs:02d}:{mins:02d}:{secs:02d}"

def read_golfers_df() -> pd.DataFrame:
    records = worksheet.get_all_records()
    df = pd.DataFrame(records, columns=COLUMNS) if records else pd.DataFrame(columns=COLUMNS)
    if not df.empty:
        df["Group Size"] = pd.to_numeric(df["Group Size"], errors="coerce").fillna(1).astype(int)
        df["Start Time (dt)"] = df["Start Time"].apply(parse_iso)
        df["End Time (dt)"] = df["End Time"].apply(parse_iso)
    else:
        df["Start Time (dt)"] = pd.Series(dtype="datetime64[ns]")
        df["End Time (dt)"] = pd.Series(dtype="datetime64[ns]")
    return df

def append_golfer_row(name: str, group_size: int, transport: str, start_dt: datetime):
    worksheet.append_row([
        name,
        int(group_size),
        transport,
        isoformat(start_dt),
        "",
        ""  # Total Elapsed to be filled when ended
    ])

def find_active_rows(df: pd.DataFrame):
    return df[df["End Time"].astype(str).str.len() == 0].copy()

def end_round_by_row(row_index_1_based: int, end_dt: datetime, start_str: str):
    start_dt = parse_iso(start_str)
    total = ""
    if isinstance(start_dt, datetime):
        total_seconds = int((end_dt - start_dt).total_seconds())
        total = fmt_hms(total_seconds)
    worksheet.update_cell(row_index_1_based, 5, isoformat(end_dt))  # End Time (E)
    worksheet.update_cell(row_index_1_based, 6, total)              # Total Elapsed (F)

def combine_today_with_time(t: dtime) -> datetime:
    today = date.today()
    return datetime(today.year, today.month, today.day, t.hour, t.minute, t.second)

# -----------------------------
# UI
# -----------------------------
st.title("⛳ Golf Course Tracker (Shared)")
st.markdown("Track golfers across devices. Default is **now**; optionally set a **custom time** (no date).")

df = read_golfers_df()
active_df = find_active_rows(df)

# -----------------------------
# Add Golfer (now or custom time)
# -----------------------------
st.subheader("Add Golfer")
with st.form("add_form"):
    col1, col2 = st.columns([2,1])
    with col1:
        name = st.text_input("Golfer Name")
    with col2:
        group_size = st.number_input("Group Size", min_value=1, max_value=6, value=1, step=1)
    transport = st.radio("Transport Type", ["Walking", "Cart"], horizontal=True)

    custom_start = st.checkbox("Use custom start time (HH:MM)")
    if custom_start:
        default_t = datetime.now().time().replace(second=0, microsecond=0)
        start_time_only = st.time_input("Start Time", value=default_t, step=60)
    submitted = st.form_submit_button("Start Round")

    if submitted and name.strip():
        if custom_start:
            start_dt = combine_today_with_time(start_time_only)
        else:
            start_dt = datetime.now()
        append_golfer_row(name.strip(), int(group_size), transport, start_dt)
        st.success(f"{name} started at {start_dt.strftime('%H:%M:%S')} ({transport}).")
        st.rerun()

# -----------------------------
# Active Golfers (Live)
# -----------------------------
st.subheader("Current Golfers on Course")
if not active_df.empty:
    now = datetime.now()
    display_rows = []
    for idx, r in active_df.iterrows():
        start_dt = r["Start Time (dt)"]
        elapsed = ""
        if isinstance(start_dt, datetime):
            elapsed = fmt_hms(int((now - start_dt).total_seconds()))
        display_rows.append({
            "Name": r["Name"],
            "Group Size": r["Group Size"],
            "Transport": r["Transport"],
            "Start Time": start_dt.strftime("%H:%M:%S") if isinstance(start_dt, datetime) else r["Start Time"],
            "Time Elapsed (live)": elapsed
        })
    st.dataframe(pd.DataFrame(display_rows), use_container_width=True)

    # auto-refresh ~10s for live timers
    pytime.sleep(10)
    st.rerun()
else:
    st.info("No golfers are currently on the course.")

# -----------------------------
# End Round (now or custom time)
# -----------------------------
st.subheader("End Round")
if not active_df.empty:
    # Build selection options with sheet row index (header is row 1)
    options = []
    for idx, r in active_df.iterrows():
        sheet_row = idx + 2
        start_label = r["Start Time (dt)"].strftime("%H:%M:%S") if isinstance(r["Start Time (dt)"], datetime) else r["Start Time"]
        options.append((f"{r['Name']} · {r['Transport']} · started {start_label} (row {sheet_row})",
                        sheet_row, r["Start Time"]))
    selection = st.selectbox("Select Golfer to End", options, format_func=lambda x: x[0])

    custom_end = st.checkbox("Use custom end time (HH:MM)")
    if custom_end:
        default_et = datetime.now().time().replace(second=0, microsecond=0)
        end_time_only = st.time_input("End Time", value=default_et, step=60, key="end_time_only")

    if st.button("End Round"):
        _, sheet_row, start_str = selection
        if custom_end:
            end_dt = combine_today_with_time(end_time_only)
        else:
            end_dt = datetime.now()
        end_round_by_row(sheet_row, end_dt, start_str)
        st.success(f"Ended round at {end_dt.strftime('%H:%M:%S')} and saved Total Elapsed.")
        st.rerun()
else:
    st.caption("No active golfers to end.")

# -----------------------------
# Footer
# -----------------------------
st.markdown("---")
st.caption("Golf Tracker · Google Sheets Sync · Total Elapsed · Custom Time · Live Timer")
