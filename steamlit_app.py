import streamlit as st
import pandas as pd
from datetime import datetime
import time
import os

# --- Config ---
st.set_page_config(page_title="Golf Tracker", layout="centered")
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

# --- Session State ---
if "golfers" not in st.session_state:
    st.session_state.golfers = []


# --- Helper Functions ---
def format_time():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log_to_file(action, golfer):
    date_str = datetime.now().strftime("%Y-%m-%d")
    log_path = os.path.join(LOG_DIR, f"log_{date_str}.txt")
    with open(log_path, "a") as f:
        f.write(
            f"[{format_time()}] {action}: {golfer['name']} ({golfer['group_size']} players, {golfer['transport']})\n")


def add_golfer(name, group_size, transport):
    golfer = {
        "name": name,
        "group_size": group_size,
        "transport": transport,
        "start_time": datetime.now(),
        "end_time": None
    }
    st.session_state.golfers.append(golfer)
    log_to_file("Start", golfer)


def end_golfer(name):
    for golfer in st.session_state.golfers:
        if golfer["name"] == name and not golfer["end_time"]:
            golfer["end_time"] = datetime.now()
            log_to_file("End", golfer)
            break


def get_duration(start_time):
    now = datetime.now()
    return str(now - start_time).split(".")[0]  # format HH:MM:SS


# --- Title ---
st.title("⛳ Golf Course Tracker")
st.markdown("Track golfers on the course and see live durations.")

# --- Add Golfer ---
st.subheader("Add Golfer")
with st.form("add_form"):
    name = st.text_input("Golfer Name")
    group_size = st.number_input("Group Size", min_value=1, max_value=6, value=1)
    transport = st.radio("Transport Type", ["Walking", "Cart"], horizontal=True)
    submitted = st.form_submit_button("Start Round")
    if submitted and name:
        add_golfer(name, group_size, transport)
        st.success(f"{name} has started a round ({transport}).")

# --- Active Golfers ---
st.subheader("Current Golfers on Course")
active = [g for g in st.session_state.golfers if not g["end_time"]]

if active:
    data = []
    for g in active:
        duration = get_duration(g["start_time"])
        data.append({
            "Name": g["name"],
            "Group Size": g["group_size"],
            "Transport": g["transport"],
            "Start Time": g["start_time"].strftime("%H:%M:%S"),
            "Time Elapsed": duration
        })
    st.dataframe(pd.DataFrame(data))

    # --- Auto-refresh every 10 seconds ---
    time.sleep(10)
    st.experimental_rerun()
else:
    st.info("No golfers are currently on the course.")

# --- End Golfer ---
st.subheader("End Round")
golfer_names = [g["name"] for g in active]
if golfer_names:
    selected_name = st.selectbox("Select Golfer to End", golfer_names)
    if st.button("End Round"):
        end_golfer(selected_name)
        st.success(f"{selected_name}'s round has ended.")
else:
    st.caption("No active golfers to end.")

# --- Footer ---
st.markdown("---")
st.caption("Golf Tracker App · Live Timer · Walking vs Cart · Auto-Refresh Enabled")