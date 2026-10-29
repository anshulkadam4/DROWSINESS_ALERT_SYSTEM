import os
import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox

try:
    import oracledb
except ImportError:
    oracledb = None

# ============================================================
# DATABASE CONNECTION
# ============================================================

def connect_db():
    """Attempts Oracle connection first via unified db module; falls back to local SQLite demo database."""
    try:
        from db import get_connection
        return get_connection()
    except Exception:
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "local_demo.db")
        conn = sqlite3.connect(db_path)
        return conn, "sqlite"



# ============================================================
# VALIDATION
# ============================================================

VALID_ALERT_TYPES = ("Drowsiness", "Negligence")
VALID_SEVERITIES = ("Low", "Medium", "High")


def validate_inputs(alert_id, student_id, session_id, device_id,
                    alert_type, severity):

    if not alert_id.strip().isdigit():
        return "Alert ID must be a number."

    if not student_id.strip():
        return "Student ID cannot be empty."

    if not session_id.strip().isdigit():
        return "Session ID must be a number."

    if not device_id.strip().isdigit():
        return "Device ID must be a number."

    if alert_type not in VALID_ALERT_TYPES:
        return "Select a valid alert type."

    if severity not in VALID_SEVERITIES:
        return "Select a valid severity."

    return None


# ============================================================
# GET FORM DATA
# ============================================================

def get_form_data():
    return (
        entry_alert_id.get().strip(),
        entry_student_id.get().strip(),
        entry_session_id.get().strip(),
        entry_device_id.get().strip(),
        combo_alert_type.get(),
        combo_severity.get()
    )


# ============================================================
# CRUD OPERATIONS
# ============================================================

def add_record():

    alert_id, student_id, session_id, device_id, alert_type, severity = get_form_data()

    error = validate_inputs(
        alert_id, student_id, session_id,
        device_id, alert_type, severity
    )

    if error:
        messagebox.showerror("Validation Error", error)
        return

    conn = None
    cur = None
    try:
        conn, db_type = connect_db()
        cur = conn.cursor()

        if db_type == "oracle":
            cur.execute(
                """INSERT INTO Alert
                   (alert_id, student_id, session_id, device_id,
                    alert_type, alert_time, severity)
                   VALUES (:1, :2, :3, :4, :5, SYSDATE, :6)""",
                [
                    int(alert_id),
                    student_id,
                    int(session_id),
                    int(device_id),
                    alert_type,
                    severity
                ]
            )
        else:
            cur.execute(
                """INSERT INTO Alert
                   (alert_id, student_id, session_id, device_id,
                    alert_type, alert_time, severity)
                   VALUES (?, ?, ?, ?, ?, datetime('now', 'localtime'), ?)""",
                [
                    int(alert_id),
                    student_id,
                    int(session_id),
                    int(device_id),
                    alert_type,
                    severity
                ]
            )

        conn.commit()

        messagebox.showinfo(
            "Success",
            f"Alert {alert_id} added successfully."
        )

        fetch_all()
        clear_fields()

    except Exception as e:
        msg = str(e)
        if "UNIQUE" in msg.upper() or "INTEGRITY" in msg.upper() or "ORA-00001" in msg:
            messagebox.showerror(
                "Database Error",
                "Alert ID already exists or violates a database constraint."
            )
        else:
            messagebox.showerror("Database Error", msg)
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def fetch_all(show_error=True):
    conn = None
    cur = None
    try:
        conn, db_type = connect_db()
        cur = conn.cursor()

        if db_type == "oracle":
            cur.execute(
                """SELECT alert_id, student_id, session_id, device_id,
                          alert_type, severity,
                          TO_CHAR(alert_time, 'YYYY-MM-DD HH24:MI')
                   FROM Alert
                   ORDER BY alert_id"""
            )
        else:
            cur.execute(
                """SELECT alert_id, student_id, session_id, device_id,
                          alert_type, severity,
                          alert_time
                   FROM Alert
                   ORDER BY alert_id"""
            )

        rows = cur.fetchall()

        populate_tree(rows)
        update_record_count(len(rows))
        status_var.set("Oracle Connected" if db_type == "oracle" else "Demo Mode (Local DB)")

    except Exception as e:
        if show_error:
            messagebox.showerror("Database Error", str(e))
        else:
            status_var.set("DB Offline / Disconnected")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def search_record():

    alert_id = entry_alert_id.get().strip()

    if not alert_id.isdigit():
        messagebox.showerror(
            "Validation Error",
            "Enter a numeric Alert ID to search."
        )
        return

    conn = None
    cur = None
    try:
        conn, db_type = connect_db()
        cur = conn.cursor()

        if db_type == "oracle":
            cur.execute(
                """SELECT alert_id, student_id, session_id, device_id,
                          alert_type, severity,
                          TO_CHAR(alert_time, 'YYYY-MM-DD HH24:MI')
                   FROM Alert
                   WHERE alert_id = :1""",
                [int(alert_id)]
            )
        else:
            cur.execute(
                """SELECT alert_id, student_id, session_id, device_id,
                          alert_type, severity,
                          alert_time
                   FROM Alert
                   WHERE alert_id = ?""",
                [int(alert_id)]
            )

        row = cur.fetchone()

        if row:
            populate_tree([row])
            update_record_count(1)

            entry_student_id.delete(0, tk.END)
            entry_student_id.insert(0, row[1])

            entry_session_id.delete(0, tk.END)
            entry_session_id.insert(0, row[2])

            entry_device_id.delete(0, tk.END)
            entry_device_id.insert(0, row[3])

            combo_alert_type.set(row[4])
            combo_severity.set(row[5])

            status_var.set(f"Found Alert #{alert_id}")

        else:
            messagebox.showinfo(
                "Not Found",
                f"No alert with ID {alert_id}."
            )

    except Exception as e:
        messagebox.showerror("Database Error", str(e))
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def update_record():

    alert_id, student_id, session_id, device_id, alert_type, severity = get_form_data()

    error = validate_inputs(
        alert_id, student_id, session_id,
        device_id, alert_type, severity
    )

    if error:
        messagebox.showerror("Validation Error", error)
        return

    conn = None
    cur = None
    try:
        conn, db_type = connect_db()
        cur = conn.cursor()

        if db_type == "oracle":
            cur.execute(
                """UPDATE Alert
                   SET student_id = :1,
                       session_id = :2,
                       device_id = :3,
                       alert_type = :4,
                       severity = :5
                   WHERE alert_id = :6""",
                [
                    student_id,
                    int(session_id),
                    int(device_id),
                    alert_type,
                    severity,
                    int(alert_id)
                ]
            )
        else:
            cur.execute(
                """UPDATE Alert
                   SET student_id = ?,
                       session_id = ?,
                       device_id = ?,
                       alert_type = ?,
                       severity = ?
                   WHERE alert_id = ?""",
                [
                    student_id,
                    int(session_id),
                    int(device_id),
                    alert_type,
                    severity,
                    int(alert_id)
                ]
            )

        if cur.rowcount == 0:
            messagebox.showinfo(
                "Not Found",
                f"No alert with ID {alert_id} to update."
            )
            return

        conn.commit()

        messagebox.showinfo(
            "Success",
            f"Alert {alert_id} updated successfully."
        )

        fetch_all()

    except Exception as e:
        messagebox.showerror("Database Error", str(e))
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def delete_record():

    alert_id = entry_alert_id.get().strip()

    if not alert_id.isdigit():
        messagebox.showerror(
            "Validation Error",
            "Enter a numeric Alert ID to delete."
        )
        return

    confirm = messagebox.askyesno(
        "Confirm Delete",
        f"Delete Alert #{alert_id}?\n\nThis action cannot be undone."
    )

    if not confirm:
        return

    conn = None
    cur = None
    try:
        conn, db_type = connect_db()
        cur = conn.cursor()

        if db_type == "oracle":
            cur.execute(
                "DELETE FROM Alert WHERE alert_id = :1",
                [int(alert_id)]
            )
        else:
            cur.execute(
                "DELETE FROM Alert WHERE alert_id = ?",
                [int(alert_id)]
            )

        if cur.rowcount == 0:
            messagebox.showinfo(
                "Not Found",
                f"No alert with ID {alert_id}."
            )
            return

        conn.commit()

        messagebox.showinfo(
            "Deleted",
            f"Alert {alert_id} deleted successfully."
        )

        clear_fields()
        fetch_all()

    except Exception as e:
        messagebox.showerror("Database Error", str(e))
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


# ============================================================
# TABLE FUNCTIONS
# ============================================================

def populate_tree(rows):

    for item in tree.get_children():
        tree.delete(item)

    for row in rows:
        tree.insert("", tk.END, values=row)


def select_record(event):

    selected = tree.selection()

    if not selected:
        return

    values = tree.item(selected[0], "values")

    if not values:
        return

    entry_alert_id.delete(0, tk.END)
    entry_alert_id.insert(0, values[0])

    entry_student_id.delete(0, tk.END)
    entry_student_id.insert(0, values[1])

    entry_session_id.delete(0, tk.END)
    entry_session_id.insert(0, values[2])

    entry_device_id.delete(0, tk.END)
    entry_device_id.insert(0, values[3])

    combo_alert_type.set(values[4])
    combo_severity.set(values[5])

    status_var.set(f"Selected Alert #{values[0]}")


def update_record_count(count):

    record_count_var.set(f"{count} record{'s' if count != 1 else ''}")


def clear_fields():

    entry_alert_id.delete(0, tk.END)
    entry_student_id.delete(0, tk.END)
    entry_session_id.delete(0, tk.END)
    entry_device_id.delete(0, tk.END)

    combo_alert_type.set("")
    combo_severity.set("")

    status_var.set("Ready")


# ============================================================
# MODERN THEME
# ============================================================

BG = "#F5F7FA"
CARD = "#FFFFFF"
TEXT = "#172033"
MUTED = "#667085"
BORDER = "#D9DEE7"
PRIMARY = "#2563EB"
PRIMARY_DARK = "#1D4ED8"
DANGER = "#DC2626"
SUCCESS = "#16A34A"
INPUT_BG = "#F9FAFB"


root = tk.Tk()

root.title("Drowsiness & Negligence Alert System")
root.geometry("1100x700")
root.minsize(950, 620)
root.configure(bg=BG)


# ============================================================
# STYLE
# ============================================================

style = ttk.Style()
style.theme_use("clam")

style.configure(
    "Modern.Treeview",
    background=CARD,
    fieldbackground=CARD,
    foreground=TEXT,
    rowheight=38,
    font=("Arial", 10),
    borderwidth=0
)

style.configure(
    "Modern.Treeview.Heading",
    background="#EEF2F7",
    foreground=TEXT,
    font=("Arial", 10, "bold"),
    padding=10,
    relief="flat"
)

style.map(
    "Modern.Treeview",
    background=[("selected", "#DBEAFE")],
    foreground=[("selected", TEXT)]
)

style.configure(
    "Modern.TCombobox",
    fieldbackground=INPUT_BG,
    background=INPUT_BG,
    foreground=TEXT,
    borderwidth=1
)


# ============================================================
# HEADER
# ============================================================

header = tk.Frame(
    root,
    bg=TEXT,
    height=95
)

header.pack(fill=tk.X)
header.pack_propagate(False)


title_frame = tk.Frame(header, bg=TEXT)
title_frame.pack(side=tk.LEFT, padx=30, pady=18)

tk.Label(
    title_frame,
    text="DROWSINESS & NEGLIGENCE",
    font=("Arial", 20, "bold"),
    fg="white",
    bg=TEXT
).pack(anchor="w")

tk.Label(
    title_frame,
    text="Alert Management System",
    font=("Arial", 10),
    fg="#B8C1D1",
    bg=TEXT
).pack(anchor="w", pady=(3, 0))


status_var = tk.StringVar(value="Ready")

status_box = tk.Frame(
    header,
    bg="#243047",
    padx=14,
    pady=8
)
status_box.pack(side=tk.RIGHT, padx=30, pady=27)

tk.Label(
    status_box,
    text="●",
    font=("Arial", 10),
    fg="#4ADE80",
    bg="#243047"
).pack(side=tk.LEFT, padx=(0, 6))

tk.Label(
    status_box,
    textvariable=status_var,
    font=("Arial", 9, "bold"),
    fg="white",
    bg="#243047"
).pack(side=tk.LEFT)


# ============================================================
# MAIN CONTAINER
# ============================================================

main = tk.Frame(root, bg=BG)
main.pack(fill=tk.BOTH, expand=True, padx=25, pady=22)


# ============================================================
# FORM CARD
# ============================================================

form_card = tk.Frame(
    main,
    bg=CARD,
    highlightbackground=BORDER,
    highlightthickness=1
)

form_card.pack(fill=tk.X)


tk.Label(
    form_card,
    text="Alert Details",
    font=("Arial", 15, "bold"),
    fg=TEXT,
    bg=CARD
).grid(
    row=0,
    column=0,
    columnspan=4,
    sticky="w",
    padx=22,
    pady=(18, 2)
)

tk.Label(
    form_card,
    text="Enter alert information or select a record from the table.",
    font=("Arial", 9),
    fg=MUTED,
    bg=CARD
).grid(
    row=1,
    column=0,
    columnspan=4,
    sticky="w",
    padx=22,
    pady=(0, 15)
)


def create_label(text, row, column):

    tk.Label(
        form_card,
        text=text,
        font=("Arial", 9, "bold"),
        fg=TEXT,
        bg=CARD
    ).grid(
        row=row,
        column=column,
        sticky="w",
        padx=(22 if column == 0 else 12, 5),
        pady=(5, 4)
    )


def create_entry(row, column):

    entry = tk.Entry(
        form_card,
        font=("Arial", 10),
        bg=INPUT_BG,
        fg=TEXT,
        insertbackground=TEXT,
        relief="solid",
        bd=1
    )

    entry.grid(
        row=row,
        column=column,
        sticky="ew",
        padx=(0, 12),
        pady=(5, 10),
        ipady=7
    )

    return entry


create_label("Alert ID", 2, 0)
entry_alert_id = create_entry(3, 0)

create_label("Student ID", 2, 1)
entry_student_id = create_entry(3, 1)

create_label("Session ID", 2, 2)
entry_session_id = create_entry(3, 2)

create_label("Device ID", 2, 3)
entry_device_id = create_entry(3, 3)


create_label("Alert Type", 4, 0)

combo_alert_type = ttk.Combobox(
    form_card,
    values=VALID_ALERT_TYPES,
    state="readonly",
    style="Modern.TCombobox",
    font=("Arial", 10)
)

combo_alert_type.grid(
    row=5,
    column=0,
    sticky="ew",
    padx=(22, 12),
    pady=(5, 18),
    ipady=5
)


create_label("Severity", 4, 1)

combo_severity = ttk.Combobox(
    form_card,
    values=VALID_SEVERITIES,
    state="readonly",
    style="Modern.TCombobox",
    font=("Arial", 10)
)

combo_severity.grid(
    row=5,
    column=1,
    sticky="ew",
    padx=(0, 12),
    pady=(5, 18),
    ipady=5
)


for i in range(4):
    form_card.columnconfigure(i, weight=1)


# ============================================================
# BUTTON BAR
# ============================================================

button_bar = tk.Frame(main, bg=BG)
button_bar.pack(fill=tk.X, pady=15)


def modern_button(parent, text, command, bg_color, width=13):

    return tk.Button(
        parent,
        text=text,
        command=command,
        font=("Arial", 9, "bold"),
        bg=bg_color,
        fg="white",
        activebackground=bg_color,
        activeforeground="white",
        relief="flat",
        bd=0,
        cursor="hand2",
        width=width,
        pady=9
    )


modern_button(
    button_bar,
    "＋  Add New",
    add_record,
    PRIMARY
).pack(side=tk.LEFT, padx=(0, 8))

modern_button(
    button_bar,
    "↻  Fetch All",
    fetch_all,
    TEXT
).pack(side=tk.LEFT, padx=8)

modern_button(
    button_bar,
    "⌕  Search",
    search_record,
    SUCCESS
).pack(side=tk.LEFT, padx=8)

modern_button(
    button_bar,
    "✎  Update",
    update_record,
    "#7C3AED"
).pack(side=tk.LEFT, padx=8)

modern_button(
    button_bar,
    "Delete",
    delete_record,
    DANGER
).pack(side=tk.LEFT, padx=8)

tk.Button(
    button_bar,
    text="Clear",
    command=clear_fields,
    font=("Arial", 9, "bold"),
    bg=BG,
    fg=MUTED,
    activebackground=BG,
    relief="flat",
    bd=0,
    cursor="hand2",
    padx=15,
    pady=9
).pack(side=tk.RIGHT)


# ============================================================
# RECORD LIST HEADER
# ============================================================

list_header = tk.Frame(main, bg=BG)
list_header.pack(fill=tk.X, pady=(2, 8))

tk.Label(
    list_header,
    text="Alert Records",
    font=("Arial", 14, "bold"),
    fg=TEXT,
    bg=BG
).pack(side=tk.LEFT)

record_count_var = tk.StringVar(value="0 records")

tk.Label(
    list_header,
    textvariable=record_count_var,
    font=("Arial", 9),
    fg=MUTED,
    bg=BG
).pack(side=tk.RIGHT)


# ============================================================
# TABLE CARD
# ============================================================

table_card = tk.Frame(
    main,
    bg=CARD,
    highlightbackground=BORDER,
    highlightthickness=1
)

table_card.pack(fill=tk.BOTH, expand=True)


columns = (
    "Alert ID",
    "Student ID",
    "Session ID",
    "Device ID",
    "Type",
    "Severity",
    "Time"
)

tree = ttk.Treeview(
    table_card,
    columns=columns,
    show="headings",
    style="Modern.Treeview"
)

widths = {
    "Alert ID": 85,
    "Student ID": 110,
    "Session ID": 105,
    "Device ID": 105,
    "Type": 130,
    "Severity": 100,
    "Time": 160
}

for col in columns:

    tree.heading(
        col,
        text=col
    )

    tree.column(
        col,
        width=widths[col],
        anchor="center"
    )


scrollbar = ttk.Scrollbar(
    table_card,
    orient="vertical",
    command=tree.yview
)

tree.configure(
    yscrollcommand=scrollbar.set
)

tree.pack(
    side=tk.LEFT,
    fill=tk.BOTH,
    expand=True,
    padx=(10, 0),
    pady=10
)

scrollbar.pack(
    side=tk.RIGHT,
    fill=tk.Y,
    padx=(0, 8),
    pady=10
)


tree.bind(
    "<<TreeviewSelect>>",
    select_record
)


# ============================================================
# FOOTER
# ============================================================

footer = tk.Frame(
    root,
    bg=BG
)

footer.pack(
    fill=tk.X,
    padx=25,
    pady=(0, 12)
)

tk.Label(
    footer,
    text="Select a record from the table to load it into the form.",
    font=("Arial", 8),
    fg=MUTED,
    bg=BG
).pack(side=tk.LEFT)

tk.Label(
    footer,
    text="Oracle Database • CRUD Interface",
    font=("Arial", 8),
    fg=MUTED,
    bg=BG
).pack(side=tk.RIGHT)


# ============================================================
# START APPLICATION
# ============================================================

if __name__ == "__main__":
    root.after(100, lambda: fetch_all(show_error=False))
    root.mainloop()
