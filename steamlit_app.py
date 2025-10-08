import streamlit as st
import pandas as pd
from datetime import datetime, date
from zoneinfo import ZoneInfo
import gspread
from google.oauth2.service_account import Credentials
import streamlit.components.v1 as components
import re

# =============================
# App Config / Timezone
# =============================
st.set_page_config(page_title="Golf Tracker", layout="centered")

# Set your local timezone here
LOCAL_TZ = ZoneInfo("America/New_York")

# =============================
# Google Sheets Setup
# =============================
SERVICE_INFO = dict(st.secrets["gcp_service_account"])
if "private_key" in SERVICE_INFO:
    SERVICE_INFO["private_key"] = SERVICE_INFO["private_key"].replace("\\n", "\n")

SHEET_URL = st.secrets["sheets"]["url"]
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

creds = Credentials.from_service_account_info(SERVICE_INFO, scopes=SCOPES)
client = gspread.authorize(creds)

def extract_sheet_id(url: str):
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", url)
    return m.group(1) if m else None

sheet_id = extract_sheet_id(SHEET_URL)
if not sheet_id:
    st.error("Invalid Google Sheet URL in secrets. Expected: https://docs.google.com/spreadsheets/d/<ID>/edit")
    st.stop()

ss = client.open_by_key(sheet_id)

ACTIVE_COLS  = ["Date", "Name", "Group Size", "Transport", "Start Time"]
RECORD_COLS  = ["Date", "Name", "Group Size", "Transport", "Start Time", "End Time", "Total Elapsed"]

def col_range(cols: int) -> str:
    return f"A1:{chr(64 + cols)}1"

def get_or_create_ws(name: str, columns: list[str]):
    try:
        ws = ss.worksheet(name)
    except gspread.WorksheetNotFound:
        ws = ss.add_worksheet(title=name, rows=2000, cols=max(26, len(columns)))
        ws.update("A1", [columns])
        return ws
    header = ws.row_values(1)
    if header != columns:
        ws.update("A1", [columns])
    return ws

ws_active  = get_or_create_ws("Active", ACTIVE_COLS)
ws_records = get_or_create_ws("Records", RECORD_COLS)

# =============================
# Helpers
# =============================
def now_local() -> datetime:
    return datetime.now(LOCAL_TZ)

def fmt_hms(total_seconds: int) -> str:
    if total_seconds < 0: total_seconds = 0
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

def parse_iso(dt_str: str):
    """Parse stored local ISO (no timezone) and attach LOCAL_TZ without shifting the clock."""
    if not dt_str:
        return None
    try:
        dt = datetime.fromisoformat(dt_str)
    except Exception:
        try:
            dt = pd.to_datetime(dt_str).to_pydatetime()
        except Exception:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LOCAL_TZ)
    else:
        dt = dt.astimezone(LOCAL_TZ)
    return dt

def to_24h(hour12: int, minute: int, ampm: str) -> tuple[int, int]:
    h = hour12 % 12
    if ampm.upper() == "PM":
        h += 12
    return h, minute

def default_12h_now():
    now = now_local()
    ampm = "PM" if now.hour >= 12 else "AM"
    hour12 = now.hour % 12
    if hour12 == 0:
        hour12 = 12
    minute = (now.minute // 5) * 5
    return hour12, minute, ampm

def combine_today_local(hour: int, minute: int) -> datetime:
    base = now_local()
    return base.replace(hour=hour, minute=minute, second=0, microsecond=0)

def read_active_df() -> pd.DataFrame:
    recs = ws_active.get_all_records()
    df = pd.DataFrame(recs, columns=ACTIVE_COLS) if recs else pd.DataFrame(columns=ACTIVE_COLS)
    if not df.empty:
        df["Group Size"] = pd.to_numeric(df["Group Size"], errors="coerce").fillna(1).astype(int)
        df["Start Time (dt)"] = df["Start Time"].apply(parse_iso)
    else:
        df["Start Time (dt)"] = pd.Series(dtype="datetime64[ns, UTC]").astype("object")
    return df

def append_active(name: str, group_size: int, transport: str, start_dt_local: datetime):
    ws_active.append_row([
        start_dt_local.date().isoformat(),   # Date (local)
        name,
        int(group_size),
        transport,
        start_dt_local.replace(microsecond=0).isoformat()  # local ISO (no tz suffix)
    ])

def append_record(date_str: str, name: str, group_size: int, transport: str,
                  start_dt_local: datetime, end_dt_local: datetime):
    total = fmt_hms(int((end_dt_local - start_dt_local).total_seconds()))
    ws_records.append_row([
        date_str,
        name,
        int(group_size),
        transport,
        start_dt_local.replace(microsecond=0).isoformat(),
        end_dt_local.replace(microsecond=0).isoformat(),
        total
    ])

def delete_active_row(sheet_row: int):
    ws_active.delete_rows(sheet_row)

def read_records_today_df() -> pd.DataFrame:
    recs = ws_records.get_all_records()
    df = pd.DataFrame(recs, columns=RECORD_COLS) if recs else pd.DataFrame(columns=RECORD_COLS)
    if df.empty:
        return df
    df["Group Size"] = pd.to_numeric(df["Group Size"], errors="coerce").fillna(1).astype(int)
    df["Start Time (dt)"] = df["Start Time"].apply(parse_iso)
    df["End Time (dt)"] = df["End Time"].apply(parse_iso)
    today_str = date.today().isoformat()
    df = df[df["Date"] == today_str].copy()
    def _elapsed(row):
        a, b = row["Start Time (dt)"], row["End Time (dt)"]
        if isinstance(a, datetime) and isinstance(b, datetime):
            return fmt_hms(int((b - a).total_seconds()))
        return row.get("Total Elapsed", "")
    df["Total Elapsed"] = df.apply(_elapsed, axis=1)
    return df

# Keep history toggle
if "show_history" not in st.session_state:
    st.session_state.show_history = False

# =============================
# UI
# =============================
st.title("⛳ Golf Course Tracker (Shared)")
st.caption(f"Times shown in {LOCAL_TZ.key}")

# -----------------------------
# Add Golfer (Now or Manual)
# -----------------------------
st.subheader("Add Golfer")

col_name, col_group = st.columns([2,1])
with col_name:
    name = st.text_input("Golfer Name")
with col_group:
    group_size = st.number_input("Group Size", min_value=1, max_value=6, value=1, step=1)

transport = st.radio("Transport", ["Walking", "Cart"], horizontal=True)

mode_add = st.radio("Start mode", ["Now", "Manual time"], horizontal=True)
h12_def, m_def, ampm_def = default_12h_now()
if mode_add == "Manual time":
    c1, c2, c3 = st.columns([1,1,1])
    with c1:
        start_hour12 = st.selectbox("Hour", list(range(1,13)), index=list(range(1,13)).index(h12_def), key="start_h12")
    with c2:
        start_minute = st.selectbox("Minute", list(range(0,60,5)), index=list(range(0,60,5)).index(m_def), key="start_min5")
    with c3:
        start_ampm = st.selectbox("AM / PM", ["AM","PM"], index=(0 if ampm_def=="AM" else 1), key="start_ampm")

b_now, b_manual = st.columns(2)
start_now_clicked = b_now.button("▶️ Start Round (Now)")
start_manual_clicked = b_manual.button("🕒 Start Round (Manual)")

if start_now_clicked and name.strip():
    start_dt_local = now_local()
    append_active(name.strip(), int(group_size), transport, start_dt_local)
    st.success(f"Started {name} at {start_dt_local.strftime('%I:%M %p')} ({transport}).")
    st.rerun()

if start_manual_clicked and name.strip():
    if mode_add != "Manual time":
        st.warning("Choose ‘Manual time’ to set hour/minute first.")
    else:
        hh24, mm = to_24h(int(start_hour12), int(start_minute), str(start_ampm))
        start_dt_local = combine_today_local(hh24, mm)
        append_active(name.strip(), int(group_size), transport, start_dt_local)
        st.success(f"Started {name} at {start_dt_local.strftime('%I:%M %p')} ({transport}).")
        st.rerun()

# -----------------------------
# Current Golfers (no-flash live timers; Date hidden; white text)
# -----------------------------
st.subheader("Current Golfers on Course")

df_active_display = read_active_df()
if df_active_display.empty:
    st.info("No golfers are currently on the course.")
else:
    # Build rows with data-startiso parsed by the browser as local time
    rows_html = []
    for _, r in df_active_display.iterrows():
        st_dt = r["Start Time (dt)"]
        start_label = (st_dt.strftime('%I:%M %p') if isinstance(st_dt, datetime) else r["Start Time"])
        start_iso = (st_dt.replace(microsecond=0).isoformat() if isinstance(st_dt, datetime) else r["Start Time"])
        rows_html.append(f"""
          <tr>
            <td>{r['Name']}</td>
            <td class="center">{r['Group Size']}</td>
            <td class="center">{r['Transport']}</td>
            <td class="center">{start_label}</td>
            <td class="elapsed" data-startiso="{start_iso}">--:--:--</td>
          </tr>
        """)
    rows_html_str = "\n".join(rows_html)

    html = """
<style>
  .golf-wrap{
    overflow:auto; border:1px solid #333; border-radius:12px; padding:8px;
    background:#111;
  }
  .golf-table{
    width:100%; border-collapse:collapse;
    font-family:system-ui, -apple-system, Segoe UI, Roboto; font-size:0.95rem;
    color:#fff;
  }
  .golf-table th, .golf-table td{
    color:#fff;
    border-bottom:1px solid #333;
    padding:8px 6px;
  }
  .golf-table th{ text-align:left; }
  .center { text-align:center; }
</style>

<div class="golf-wrap">
  <table class="golf-table">
    <thead>
      <tr>
        <th>Name</th>
        <th class="center">Group Size</th>
        <th class="center">Transport</th>
        <th class="center">Start Time</th>
        <th>Time Elapsed (live)</th>
      </tr>
    </thead>
    <tbody>
      {{ROWS}}
    </tbody>
  </table>
</div>

<script>
  function pad(n){ return n < 10 ? ('0' + n) : n; }
  function fmt(s){ var h=Math.floor(s/3600), m=Math.floor((s%3600)/60), x=s%60; return pad(h)+':'+pad(m)+':'+pad(x); }
  function tick(){
    document.querySelectorAll('.elapsed').forEach(function(td){
      var iso = td.dataset.startiso;
      var startMs = Date.parse(iso);   // parsed as local by the browser
      var nowMs = Date.now();
      if (!isNaN(startMs)) {
        var secs = Math.max(0, Math.floor((nowMs - startMs)/1000));
        td.textContent = fmt(secs);
      } else {
        td.textContent = "--:--:--";
      }
    });
  }
  tick();
  setInterval(tick, 1000);
</script>
"""
    html = html.replace("{{ROWS}}", rows_html_str)
    components.html(html, height=min(420, 140 + 40*len(rows_html)))

    if st.button("🔃 Refresh data"):
        st.rerun()

# -----------------------------
# End Round (Now or Manual)
# -----------------------------
st.subheader("End Round")
df_active_for_end = read_active_df()
if not df_active_for_end.empty:
    options = []
    for idx, r in df_active_for_end.iterrows():
        sheet_row = idx + 2
        st_label = r["Start Time (dt)"].strftime("%I:%M %p") if isinstance(r["Start Time (dt)"], datetime) else r["Start Time"]
        label = f"{r['Name']} · {r['Transport']} · started {st_label} (row {sheet_row})"
        options.append((label, sheet_row))
    choice = st.selectbox("Select golfer to end", options, format_func=lambda x: x[0])

    mode_end = st.radio("End mode", ["Now", "Manual time"], horizontal=True, key="end_mode")

    # Manual end pickers (defaults)
    eh12_def, em_def, eampm_def = default_12h_now()
    if mode_end == "Manual time":
        e1, e2, e3 = st.columns([1,1,1])
        with e1:
            end_hour12 = st.selectbox("Hour", list(range(1,13)), index=list(range(1,13)).index(eh12_def), key="end_h12")
        with e2:
            end_minute = st.selectbox("Minute", list(range(0,60,5)), index=list(range(0,60,5)).index(em_def), key="end_min5")
        with e3:
            end_ampm = st.selectbox("AM / PM", ["AM","PM"], index=(0 if eampm_def=="AM" else 1), key="end_ampm")

    end_now_clicked = st.button("⏹ End Round (Now)")
    end_manual_clicked = st.button("🕒 End Round (Manual)")

    if end_now_clicked or end_manual_clicked:
        _, sheet_row = choice
        row_vals = ws_active.row_values(sheet_row)
        # Expected: [Date, Name, Group Size, Transport, Start Time]
        date_str, name_val, group_sz, transport_val, start_str = row_vals
        start_dt_local = parse_iso(start_str) or now_local()

        if end_manual_clicked:
            if mode_end != "Manual time":
                st.warning("Choose ‘Manual time’ to set hour/minute first.")
                st.stop()
            h24, mm = to_24h(int(end_hour12), int(end_minute), str(end_ampm))
            end_dt_local = combine_today_local(h24, mm)
        else:
            end_dt_local = now_local()

        append_record(date_str, name_val, int(group_sz or 1), transport_val, start_dt_local, end_dt_local)
        delete_active_row(sheet_row)

        st.success(f"Ended {name_val} at {end_dt_local.strftime('%I:%M %p')} · saved to Records.")
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

        total_rounds = len(today_df)
        total_players = int(today_df["Group Size"].sum())
        st.caption(f"Rounds: {total_rounds} • Players: {total_players}")

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
st.caption("Golf Tracker · Google Sheets (Active & Records) · Local timezone · No-flash timers · 12-hour Manual time (5-min steps)")
