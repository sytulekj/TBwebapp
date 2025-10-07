import tkinter as tk
from tkinter import ttk
from datetime import datetime, timedelta
import os

# Store player data and create logs directory
player_data = {}
os.makedirs("logs", exist_ok=True)

# Update dropdown menu for ending a round
def update_active_dropdown():
    menu = end_dropdown['menu']
    menu.delete(0, 'end')
    for name in player_data:
        if player_data[name]["end"] is None:
            menu.add_command(label=name, command=lambda value=name: selected_golfer.set(value))

# Save round data to daily log file
def save_to_file(name):
    data = player_data[name]
    start_dt = datetime.strptime(data["start"], "%Y-%m-%d %I:%M %p")
    end_dt = datetime.strptime(data["end"], "%Y-%m-%d %I:%M %p")
    duration = end_dt - start_dt
    hours, remainder = divmod(duration.total_seconds(), 3600)
    minutes = remainder // 60
    time_on_course = f"{int(hours)}h {int(minutes)}m"

    today = datetime.now().strftime("%Y-%m-%d")
    filename = f"logs/golf_rounds_{today}.txt"

    log_line = (
        f"{name} | Players: {data['players']} | Holes: {data['holes']} | Busyness: {data['busy']} | "
        f"Start: {data['start']} | End: {data['end']} | Time on Course: {time_on_course} | "
        f"Transport: {data['transport']}\n"
    )

    with open(filename, "a") as f:
        f.write(log_line)

# Start round with current time
def start_round_auto():
    name = name_entry.get().strip()
    holes = holes_var.get()
    busy = busy_var.get()
    transport = transport_var.get()
    players = players_var.get()

    if name:
        start_time = datetime.now().strftime("%Y-%m-%d %I:%M %p")
        player_data[name] = {
            "holes": holes,
            "busy": busy,
            "transport": transport,
            "players": players,
            "start": start_time,
            "end": None
        }
        name_entry.delete(0, tk.END)
        update_active_dropdown()
        status_label.config(text=f"Auto started round for {name}")
    else:
        status_label.config(text="Enter a player name.")

# End round with current time
def end_round_auto():
    name = selected_golfer.get()
    if name in player_data and player_data[name]["end"] is None:
        end_time = datetime.now().strftime("%Y-%m-%d %I:%M %p")
        player_data[name]["end"] = end_time
        save_to_file(name)
        update_active_dropdown()
        status_label.config(text=f"Auto ended round for {name}")
    else:
        status_label.config(text="Invalid golfer selected.")

# Start round with manual time input
def start_round_manual():
    name = name_entry.get().strip()
    holes = holes_var.get()
    busy = busy_var.get()
    transport = transport_var.get()
    players = players_var.get()
    hour = start_hour.get().strip()
    minute = start_minute.get().strip()
    ampm = start_ampm.get()

    if name and hour.isdigit() and minute.isdigit():
        now = datetime.now()
        hour_12 = int(hour) % 12
        if ampm == "PM":
            hour_12 += 12
        start_time = now.replace(hour=hour_12, minute=int(minute), second=0)
        formatted = start_time.strftime("%Y-%m-%d %I:%M %p")
        player_data[name] = {
            "holes": holes,
            "busy": busy,
            "transport": transport,
            "players": players,
            "start": formatted,
            "end": None
        }
        name_entry.delete(0, tk.END)
        start_hour.delete(0, tk.END)
        start_minute.delete(0, tk.END)
        update_active_dropdown()
        status_label.config(text=f"Manual started round for {name}")
    else:
        status_label.config(text="Enter valid name and time.")

# End round with manual time input
def end_round_manual():
    name = selected_golfer.get()
    hour = end_hour.get().strip()
    minute = end_minute.get().strip()
    ampm = end_ampm.get()
    if name in player_data and player_data[name]["end"] is None and hour.isdigit() and minute.isdigit():
        now = datetime.now()
        hour_12 = int(hour) % 12
        if ampm == "PM":
            hour_12 += 12
        end_time = now.replace(hour=hour_12, minute=int(minute), second=0)
        formatted = end_time.strftime("%Y-%m-%d %I:%M %p")
        player_data[name]["end"] = formatted
        end_hour.delete(0, tk.END)
        end_minute.delete(0, tk.END)
        save_to_file(name)
        update_active_dropdown()
        status_label.config(text=f"Manual ended round for {name}")
    else:
        status_label.config(text="Enter valid time and golfer.")

# Refresh the list of currently playing golfers
def refresh_active_list():
    active_listbox.delete(0, tk.END)
    for i, name in enumerate(player_data):
        if player_data[name]["end"] is None:
            start_str = player_data[name]["start"]
            start = datetime.strptime(start_str, "%Y-%m-%d %I:%M %p")
            duration = datetime.now() - start
            minutes_on_course = int(duration.total_seconds() // 60)
            holes = player_data[name]["holes"]
            transport = player_data[name]["transport"]
            label = f"{name} | {holes} Holes | {transport} | {minutes_on_course} mins"
            active_listbox.insert(tk.END, label)
            if holes == "9" and duration > timedelta(hours=2):
                active_listbox.itemconfig(i, fg='red')
            elif holes == "18" and duration > timedelta(hours=4):
                active_listbox.itemconfig(i, fg='red')

# Periodic refresh every 5 seconds
def periodic_refresh():
    refresh_active_list()
    update_active_dropdown()
    root.after(5000, periodic_refresh)

# View today’s log in new window
def view_log():
    today = datetime.now().strftime("%Y-%m-%d")
    filename = f"logs/golf_rounds_{today}.txt"
    if os.path.exists(filename):
        with open(filename, "r") as f:
            content = f.read()
    else:
        content = "No records yet for today."
    log_window = tk.Toplevel(root)
    log_window.title("Golf Round Log")
    log_window.geometry("700x400")
    text_box = tk.Text(log_window, wrap="word")
    text_box.insert("1.0", content)
    text_box.config(state="disabled")
    text_box.pack(expand=True, fill="both")

# Tkinter UI setup
root = tk.Tk()
root.title("⛳ Golf Round Tracker")
root.geometry("950x650")

# Player Name
name_entry = tk.Entry(root, width=25)
tk.Label(root, text="Player Name:").grid(row=0, column=0, sticky="e")
name_entry.grid(row=0, column=1)

# Holes
holes_var = tk.StringVar(value="18")
tk.Label(root, text="Holes:").grid(row=1, column=0, sticky="e")
ttk.Combobox(root, textvariable=holes_var, values=["9", "18"], width=5).grid(row=1, column=1, sticky="w")

# Transport
transport_var = tk.StringVar(value="Cart")
tk.Label(root, text="Transport:").grid(row=2, column=0, sticky="e")
ttk.Combobox(root, textvariable=transport_var, values=["Cart", "Walking"], width=10).grid(row=2, column=1, sticky="w")

# Players
players_var = tk.StringVar(value="1")
tk.Label(root, text="Number of Players:").grid(row=3, column=0, sticky="e")
player_frame = tk.Frame(root)
player_frame.grid(row=3, column=1, sticky="w")
for i in range(1, 5):
    tk.Radiobutton(player_frame, text=str(i), variable=players_var, value=str(i)).pack(side="left", padx=2)

# Busyness
busy_var = tk.StringVar(value="Light")
tk.Label(root, text="Busyness:").grid(row=4, column=0, sticky="e")
ttk.Combobox(root, textvariable=busy_var, values=["Light", "Moderate", "Heavy"], width=10).grid(row=4, column=1, sticky="w")

# Auto Start
tk.Label(root, text="Auto Start:").grid(row=5, column=0, sticky="e")
tk.Button(root, text="Start Round (Now)", command=start_round_auto).grid(row=5, column=1, sticky="w")

# Manual Start
tk.Label(root, text="Manual Start:").grid(row=6, column=0, sticky="e")
start_hour = tk.Entry(root, width=4)
start_hour.grid(row=6, column=1, sticky="w")
tk.Label(root, text=":").grid(row=6, column=1, padx=(35, 0), sticky="w")
start_minute = tk.Entry(root, width=4)
start_minute.grid(row=6, column=1, padx=(50, 0), sticky="w")
start_ampm = ttk.Combobox(root, values=["AM", "PM"], width=5)
start_ampm.set("AM")
start_ampm.grid(row=6, column=2, sticky="w")
tk.Button(root, text="Start Round (Manual)", command=start_round_manual).grid(row=7, column=1, sticky="w", pady=4)

# Select Golfer
selected_golfer = tk.StringVar()
tk.Label(root, text="Select Golfer:").grid(row=8, column=0, sticky="e")
end_dropdown = ttk.OptionMenu(root, selected_golfer, "")
end_dropdown.grid(row=8, column=1, sticky="w")

# End Auto
tk.Button(root, text="End Round (Now)", command=end_round_auto).grid(row=9, column=1, sticky="w", pady=4)

# Manual End
tk.Label(root, text="Manual End:").grid(row=10, column=0, sticky="e")
end_hour = tk.Entry(root, width=4)
end_hour.grid(row=10, column=1, sticky="w")
tk.Label(root, text=":").grid(row=10, column=1, padx=(35, 0), sticky="w")
end_minute = tk.Entry(root, width=4)
end_minute.grid(row=10, column=1, padx=(50, 0), sticky="w")
end_ampm = ttk.Combobox(root, values=["AM", "PM"], width=5)
end_ampm.set("AM")
end_ampm.grid(row=10, column=2, sticky="w")
tk.Button(root, text="End Round (Manual)", command=end_round_manual).grid(row=11, column=1, sticky="w", pady=4)

# View Log
tk.Button(root, text="📄 View Today's Log", command=view_log).grid(row=12, column=1, sticky="w", pady=10)

# Active players list
tk.Label(root, text="Currently On Course:").grid(row=0, column=3, padx=15, sticky="w")
active_listbox = tk.Listbox(root, width=70, height=30)
active_listbox.grid(row=1, column=3, rowspan=12, padx=15, sticky="n")

# Status bar
status_label = tk.Label(root, text="", fg="blue")
status_label.grid(row=13, column=0, columnspan=3, pady=10)

# Start periodic refresh
periodic_refresh()
root.mainloop()