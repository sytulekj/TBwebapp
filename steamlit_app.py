import streamlit as st
import pandas as pd
from datetime import datetime, date, time as dtime
import time as pytime
import gspread
from google.oauth2.service_account import Credentials

# -----------------------------
# App Config
# -----------------------------
st.set_page_config(page_title="Golf Tracker", layout="centered")

from streamlit_autorefresh import st_autorefresh

# refresh the page every 10 seconds without interrupting rendering
st_autorefresh(interval=10_000, key="live_refresh")

# Read creds & sheet URL from Streamlit secrets (Settings → Secrets)
SERVICE_INFO = dict(st.secrets["gcp_service_account"])
# normalize private_key in case it was saved with \n escapes
if "private_key" in SERVICE_INFO:
    SERVICE_INFO["private_key"] = SERVICE_INFO["private_key"].replace("\\n", "\n")

SHEET_URL = st.secrets["sheets"]["url"]
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

creds = Credentials.from_service_account_info(SERVICE_INFO, scopes=SCOPES)
client = gspread.authorize(creds)
ss = client.open_by_url(SHEET_URL)

# Columns (Date is stored in sheets, but not shown in Active UI)
ACTIVE_COLS  = ["Date", "Name", "Group Size", "Transport", "Start Time"]
RECORD_COLS  = ["Date", "Name", "Group Size", "Transport", "Start Time", "End Time", "Total Elapsed"]

def col_range(cols: int) -> str:
    # A..Z is plenty for our columns (<= 7)
    return f"A1:{chr(64 + cols)}1"

def get_or_create_ws(name: str, columns: list[str]):
    try:
        ws = ss.worksheet(name)
    except gspread.WorksheetNotFound:
        ws = ss.add_worksheet(title=name, rows=2000, cols=len(columns))
        ws.update(col_range(len(columns)), [columns])
        return ws
    header = ws.row_values(1)
    if header != columns:
        ws.update(col_range(len(columns)), [columns])
    return ws

ws_active  = get_or_create_ws("Active", ACTIVE_COLS)
ws_records = get_or_create_ws("Records", RECORD_COLS)

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
    if total_seconds < 0: total_seconds = 0
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

def read_active_df() -> pd.DataFrame:
    recs = ws_active.get_all_records()
    # backfill Date for old rows (if needed)
    if recs and "Date" not in recs[0]:
        for r in recs:
            st_dt = parse_iso(r.get("Start Time", "")) or datetime.now()
            r["Date"] = st_dt.date().isoformat()
    df = pd.DataFrame(recs, columns=ACTIVE_COLS) if recs else pd.DataFrame(columns=ACTIVE_COLS)
    if not df.empty:
        df["Group Size"] = pd.to_numeric(df["Group Size"], errors="coerce").fillna(1).astype(int)
        df["Start Time (dt)"] = df["Start Time"].apply(parse_iso)
    else:
        df["Start Time (dt)"] = pd.Series(dtype="datetime64[ns]")
    return df

def append_active(name: str, group_size: int, transport: str, start_dt: datetime):
    ws_active.append_row([
        start_dt.date().isoformat(),   # Date
        name,
        int(group_size),
        transport,
        isoformat(start_dt)            # Start Time
    ])

def append_record(date_str: str, name: str, group_size: int, transport: str, start_dt: datetime, end_dt: datetime):
    total = fmt_hms(int((end_dt - start_dt).total_seconds()))
    ws_records.append_row([
        date_str,
        name,
        int(group_size),
        transport,
        isoformat(start_dt),
        isoformat(end_dt),
        total
    ])

def delete_active_row(sheet_row: int):
    ws_active.delete_rows(sheet_row)

def combine_today(hour: int, minute: int) -> datetime:
    today = date.today()
    return datetime(today.year, today.month, today.day, hour, minute, 0)

def round_now_to_5min() -> dtime:
    now = datetime.now()
    minute = (now.minute // 5) * 5
    return dtime(now.hour, minute, 0)

# Records (today only) for History
def read_records_today_df() -> pd.DataFrame:
    recs = ws_records.get_all_records()
    df = pd.DataFrame(recs, columns=RECORD_COLS) if recs else pd.DataFrame(columns=RECORD_COLS)
    if df.empty:
        return df
    df["Group Size"] = pd.to_numeric(df["Group Size"], errors="coerce").fillna(1).astype(int)
    df["Start Time (dt)"] = df["Start Time"].apply(parse_iso)
    df["End Time (dt)"] = df["End Time"].apply(parse_iso)
    today_str = date.today().isoformat()
    df = df[df["Date"].astype(str) == today_str].copy()

    # compute Total Elapsed if missing
    def _compute(row):
        if pd.notna(row["Start Time (dt)"]) and pd.notna(row["End Time (dt)"]):
            secs = int((row["End Time (dt)"] - row["Start Time (dt)"]).total_seconds())
            return fmt_hms(secs)
        return row.get("Total Elapsed", "")
    df["Total Elapsed"] = df.apply(_compute, axis=1)
    return df

# persistent toggle for history panel
if "show_history" not in st.session_state:
    st.session_state.show_history = False

# -----------------------------
# UI
# -----------------------------
st.title("⛳ Golf Course Tracker (Shared)")
st.markdown(
    "Default is **Now**. Enable **Custom time** to pick hour & minute (5-minute steps). "
    "**Date** is saved in the sheet but hidden in the Active list. Records are saved when a round ends."
)

df_active = read_active_df()

# -----------------------------
# Add Golfer (Now or custom time)
# -----------------------------
st.subheader("Add Golfer")
with st.form("add_form"):
    col1, col2 = st.columns([2,1])
    with col1:
        name = st.text_input("Golfer Name")
    with col2:
        group_size = st.number_input("Group Size", min_value=1, max_value=6, value=1, step=1)

    transport = st.radio("Transport", ["Walking", "Cart"], horizontal=True)

    use_custom_start = st.checkbox("Use custom start time (HH:MM)")
    if use_custom_start:
        st_time_default = round_now_to_5min()
        c1, c2 = st.columns(2)
        hours = c1.selectbox("Hour", list(range(0,24)), index=st_time_default.hour, key="start_hr")
        minutes = c2.selectbox("Minute (5-step)", list(range(0,60,5)),
                               index=list(range(0,60,5)).index((st_time_default.minute//5)*5),
                               key="start_min")

    submitted = st.form_submit_button("Start Round")

    if submitted and name.strip():
        if use_custom_start:
            start_dt = combine_today(hours, minutes)
        else:
            start_dt = datetime.now()
        append_active(name.strip(), int(group_size), transport, start_dt)
        st.success(f"Started {name} at {start_dt.strftime('%H:%M')} ({transport}).")
        st.rerun()

# -----------------------------
# Current Golfers (live; Date hidden)
# -----------------------------
st.subheader("Current Golfers on Course")
if not df_active.empty:
    now = datetime.now()
    rows = []
    for _, r in df_active.iterrows():
        st_dt = r["Start Time (dt)"]
        elapsed = fmt_hms(int((now - st_dt).total_seconds())) if isinstance(st_dt, datetime) else ""
        rows.append({
            "Name": r["Name"],
            "Group Size": r["Group Size"],
            "Transport": r["Transport"],
            "Start Time": st_dt.strftime("%H:%M") if isinstance(st_dt, datetime) else r["Start Time"],
            "Time Elapsed (live)": elapsed
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True)

else:
    st.info("No golfers are currently on the course.")

# -----------------------------
# End Round (Now or custom time)
# -----------------------------
st.subheader("End Round")
if not df_active.empty:
    # Build choices that map to exact Active sheet row (header = row 1)
    options = []
    for idx, r in df_active.iterrows():
        sheet_row = idx + 2
        st_label = r["Start Time (dt)"].strftime("%H:%M") if isinstance(r["Start Time (dt)"], datetime) else r["Start Time"]
        label = f"{r['Name']} · {r['Transport']} · started {st_label} (row {sheet_row})"
        options.append((label, sheet_row))

    choice = st.selectbox("Select golfer to end", options, format_func=lambda x: x[0])

    use_custom_end = st.checkbox("Use custom end time (HH:MM)")
    if use_custom_end:
        et_default = round_now_to_5min()
        e1, e2 = st.columns(2)
        end_hr = e1.selectbox("Hour", list(range(0,24)), index=et_default.hour, key="end_hr")
        end_min = e2.selectbox("Minute (5-step)", list(range(0,60,5)),
                               index=list(range(0,60,5)).index((et_default.minute//5)*5),
                               key="end_min")

    if st.button("End Round"):
        _, sheet_row = choice
        # Read exact Active row (with Date)
        row_vals = ws_active.row_values(sheet_row)
        # Expected: [Date, Name, Group Size, Transport, Start Time]
        date_str, name, group_size, transport, start_str = (
            row_vals[0], row_vals[1], row_vals[2], row_vals[3], row_vals[4]
        )
        start_dt = parse_iso(start_str) or datetime.now()
        end_dt = combine_today(end_hr, end_min) if use_custom_end else datetime.now()

        # 1) Append to Records (with Total Elapsed)
        append_record(date_str, name, int(group_size or 1), transport, start_dt, end_dt)
        # 2) Remove from Active
        delete_active_row(sheet_row)

        st.success(f"Ended {name} at {end_dt.strftime('%H:%M')} · saved to Records.")
        st.rerun()
else:
    st.caption("No active golfers to end.")

# -----------------------------
# Today's History (button at bottom)
# -----------------------------
st.markdown("---")
colA, _ = st.columns([1,3])
with colA:
    if st.button("📜 Today’s History" + (" (hide)" if st.session_state.show_history else "")):
        st.session_state.show_history = not st.session_state.show_history

if st.session_state.show_history:
    st.subheader(f"History — {date.today().isoformat()}")
    today_df = read_records_today_df()

    if today_df.empty:
        st.info("No finished rounds for today yet.")
    else:
        show_cols = ["Date", "Name", "Group Size", "Transport", "Start Time", "End Time", "Total Elapsed"]
        st.dataframe(today_df[show_cols], use_container_width=True)

        # Quick stats
        total_rounds = len(today_df)
        total_players = int(today_df["Group Size"].sum())
        st.caption(f"Rounds: {total_rounds} • Players: {total_players}")

        # Download today's CSV
        csv_bytes = today_df[show_cols].to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Download Today’s CSV",
            csv_bytes,
            file_name=f"golf_records_{date.today().isoformat()}.csv",
            mime="text/csv"
        )

# -----------------------------
# Footer
# -----------------------------
st.markdown("---")
st.caption("Golf Tracker · Google Sheets (Active & Records) · Date stored (hidden in Active UI) · Custom HH:MM (5-min) · Live timers")

