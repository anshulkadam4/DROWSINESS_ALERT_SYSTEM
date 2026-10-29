"""
AegisAlert — Unified Dual-Engine Database Manager
Supports:
  1. Oracle Database 21c XE / Free (XEPDB1, FREEPDB1, etc.) via python-oracledb (Thin Mode)
  2. SQLite 3 local fallback (local_demo.db) for offline demonstration and development

Provides automatic schema migration, connection pooling/handling, strict Oracle mode,
dialect-aware parameter translation, and comprehensive connection diagnostics.
"""

import os
import hashlib
import sqlite3
import time
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

# Safely import oracledb
try:
    import oracledb
    ORACLE_DRIVER_AVAILABLE = True
except ImportError:
    oracledb = None
    ORACLE_DRIVER_AVAILABLE = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SQLITE_DB_PATH = os.path.join(BASE_DIR, "local_demo.db")


def get_oracle_config():
    """Reads Oracle connection parameters from environment variables."""
    user = os.environ.get("DB_USER", "system")
    password = os.environ.get("DB_PASSWORD", "")
    dsn = os.environ.get("DB_DSN")

    if not dsn:
        host = os.environ.get("DB_HOST", "localhost")
        port = os.environ.get("DB_PORT", "1521")
        # Default to XEPDB1 (Oracle 21c XE), with fallback option for FREEPDB1 (Oracle 23c Free)
        service_name = os.environ.get("DB_SERVICE_NAME", "XEPDB1")
        dsn = f"{host}:{port}/{service_name}"

    strict_mode = os.environ.get("ORACLE_STRICT_MODE", "false").lower() in ("true", "1", "yes")
    force_engine = os.environ.get("DB_FORCE_ENGINE", "auto").lower()

    return {
        "user": user,
        "password": password,
        "dsn": dsn,
        "strict_mode": strict_mode,
        "force_engine": force_engine
    }


class DatabaseError(Exception):
    """Custom exception wrapper for AegisAlert database operations."""
    def __init__(self, message, code=None, engine=None, hint=None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.engine = engine
        self.hint = hint


def get_connection():
    """
    Returns (connection, engine_type).
    engine_type is either 'oracle' or 'sqlite'.

    If force_engine == 'oracle' or strict_mode is True:
      Attempts Oracle only; raises DatabaseError on failure.
    If force_engine == 'sqlite':
      Uses SQLite local database directly.
    Otherwise ('auto'):
      Attempts Oracle; on connection error falls back to SQLite.
    """
    cfg = get_oracle_config()

    if cfg["force_engine"] == "sqlite":
        init_sqlite_schema_if_needed()
        conn = sqlite3.connect(SQLITE_DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn, "sqlite"

    oracle_error_detail = None
    if ORACLE_DRIVER_AVAILABLE:
        try:
            # Connect using python-oracledb thin mode (no Oracle Client / Instant Client required)
            conn = oracledb.connect(
                user=cfg["user"],
                password=cfg["password"],
                dsn=cfg["dsn"]
            )
            return conn, "oracle"
        except Exception as e:
            oracle_error_detail = str(e)
    else:
        oracle_error_detail = "python-oracledb package is not installed."

    # If Oracle failed and strict mode is active:
    if cfg["strict_mode"] or cfg["force_engine"] == "oracle":
        hint = "Verify Oracle service (e.g., OracleServiceXE & OracleOraDB21Home1TNSListener) is running and DSN is correct."
        if "ORA-12541" in str(oracle_error_detail):
            hint = "TNS:no listener. Make sure the Oracle TNS Listener service is started on port 1521."
        elif "ORA-12514" in str(oracle_error_detail):
            hint = f"Listener cannot resolve service name '{cfg['dsn']}'. Check whether XEPDB1 or FREEPDB1 is registered with lsnrctl status."
        elif "ORA-01017" in str(oracle_error_detail):
            hint = "Invalid username/password. Check DB_USER and DB_PASSWORD in .env."

        raise DatabaseError(
            message=f"Strict Oracle connection failed: {oracle_error_detail}",
            code="ORACLE_CONN_FAIL",
            engine="oracle",
            hint=hint
        )

    # Fallback to local SQLite demo database
    init_sqlite_schema_if_needed()
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn, "sqlite"


def diagnose_connection():
    """
    Executes a comprehensive health check on both Oracle and SQLite engines.
    Returns a dictionary of diagnostic data for UI presentation.
    """
    cfg = get_oracle_config()
    diag = {
        "oracle_available": ORACLE_DRIVER_AVAILABLE,
        "oracle_user": cfg["user"],
        "oracle_dsn": cfg["dsn"],
        "oracle_strict": cfg["strict_mode"],
        "force_engine": cfg["force_engine"],
        "oracle_status": "Not Tested",
        "oracle_latency_ms": None,
        "oracle_version": None,
        "oracle_error": None,
        "sqlite_status": "Ready",
        "sqlite_path": SQLITE_DB_PATH,
        "active_engine": "unknown",
        "table_counts": {}
    }

    # Test Oracle
    if ORACLE_DRIVER_AVAILABLE:
        start_t = time.time()
        try:
            conn = oracledb.connect(user=cfg["user"], password=cfg["password"], dsn=cfg["dsn"])
            cur = conn.cursor()
            cur.execute("SELECT banner FROM v$version WHERE ROWNUM = 1")
            row = cur.fetchone()
            diag["oracle_version"] = row[0] if row else "Oracle Database"
            diag["oracle_status"] = "Connected"
            diag["oracle_latency_ms"] = round((time.time() - start_t) * 1000, 2)
            cur.close()
            conn.close()
        except Exception as e:
            diag["oracle_status"] = "Failed"
            diag["oracle_error"] = str(e)
    else:
        diag["oracle_status"] = "Driver Missing"
        diag["oracle_error"] = "oracledb python package not found"

    # Test Active Engine & Table Counts
    try:
        active_conn, active_engine = get_connection()
        diag["active_engine"] = active_engine
        cur = active_conn.cursor()

        tables = ["Student", "Sessions", "Device", "Alert", "Users", "Proctor", "Camera_Nodes", "Audit_Log"]
        counts = {}
        for tbl in tables:
            try:
                cur.execute(f"SELECT COUNT(*) FROM {tbl}")
                cnt = cur.fetchone()[0]
                counts[tbl] = cnt
            except Exception:
                counts[tbl] = "N/A"
        diag["table_counts"] = counts
        cur.close()
        active_conn.close()
    except Exception as e:
        diag["active_error"] = str(e)

    return diag


def execute_sql(sql_oracle, sql_sqlite, params=None, fetch=None, commit=False):
    """
    Executes a dialect-aware query.
    params can be a list or tuple.
    fetch: None, 'one', 'all', or 'val'.
    commit: True to commit transaction.
    Returns (result, rowcount, engine_used).
    """
    conn, engine = get_connection()
    cur = conn.cursor()
    params = params or []

    try:
        if engine == "oracle":
            sql = sql_oracle
        else:
            sql = sql_sqlite

        cur.execute(sql, params)

        res = None
        if fetch == "one":
            res = cur.fetchone()
        elif fetch == "all":
            res = cur.fetchall()
        elif fetch == "val":
            row = cur.fetchone()
            res = row[0] if row else None

        rowcount = cur.rowcount

        if commit:
            conn.commit()

        return res, rowcount, engine

    finally:
        try:
            cur.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass


def init_sqlite_schema_if_needed():
    """Initializes and seeds local SQLite demo database matching Assessment-4 & ER diagram."""
    conn = sqlite3.connect(SQLITE_DB_PATH)
    cur = conn.cursor()

    # Enable foreign keys
    cur.execute("PRAGMA foreign_keys = ON;")

    # Safe column migration helper for pre-existing tables
    def add_column_if_missing(table, column, col_def):
        try:
            cur.execute(f"PRAGMA table_info({table})")
            columns = [row[1] for row in cur.fetchall()]
            if columns and column not in columns:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")
        except Exception:
            pass

    add_column_if_missing("Student", "department", "TEXT DEFAULT 'CSE'")
    add_column_if_missing("Sessions", "proctor_id", "TEXT")
    add_column_if_missing("Device", "health_score", "INTEGER DEFAULT 98")
    add_column_if_missing("Alert", "status", "TEXT DEFAULT 'Pending'")
    add_column_if_missing("Alert", "eye_closure_sec", "REAL DEFAULT 0.0")
    add_column_if_missing("Alert", "resolution_notes", "TEXT")
    add_column_if_missing("Alert", "resolved_by", "TEXT")
    add_column_if_missing("Alert", "resolved_at", "TEXT")

    # 1. Users Table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS Users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT NOT NULL,
            role TEXT CHECK (role IN ('Administrator', 'Faculty')) NOT NULL,
            email TEXT UNIQUE,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)

    # 2. Student Table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS Student (
            student_id TEXT PRIMARY KEY,
            student_name TEXT NOT NULL,
            class_section TEXT NOT NULL,
            email TEXT UNIQUE,
            enrollment_year INTEGER CHECK (enrollment_year BETWEEN 2020 AND 2030),
            department TEXT DEFAULT 'CSE'
        )
    """)

    # 3. Emergency Contact Table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS Emergency_Contact (
            contact_id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            contact_name TEXT NOT NULL,
            relationship TEXT,
            phone_number TEXT NOT NULL,
            email TEXT,
            FOREIGN KEY (student_id) REFERENCES Student(student_id) ON DELETE CASCADE
        )
    """)

    # 4. Proctor Table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS Proctor (
            proctor_id TEXT PRIMARY KEY,
            proctor_name TEXT NOT NULL,
            department TEXT,
            email TEXT UNIQUE,
            phone TEXT,
            assigned_room TEXT
        )
    """)

    # 5. Sessions Table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS Sessions (
            session_id INTEGER PRIMARY KEY,
            session_date TEXT NOT NULL,
            subject TEXT NOT NULL,
            faculty_name TEXT NOT NULL,
            duration_minutes INTEGER CHECK (duration_minutes > 0),
            class_section TEXT NOT NULL,
            proctor_id TEXT,
            FOREIGN KEY (proctor_id) REFERENCES Proctor(proctor_id) ON DELETE SET NULL
        )
    """)

    # 6. Device Table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS Device (
            device_id INTEGER PRIMARY KEY,
            device_type TEXT NOT NULL,
            location TEXT NOT NULL,
            install_date TEXT DEFAULT (date('now')),
            status TEXT DEFAULT 'Active' CHECK (status IN ('Active', 'Inactive', 'Maintenance')),
            health_score INTEGER DEFAULT 98
        )
    """)

    # 7. Camera Nodes Table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS Camera_Nodes (
            node_id TEXT PRIMARY KEY,
            device_id INTEGER NOT NULL,
            ip_address TEXT,
            resolution TEXT DEFAULT '1080p',
            frame_rate INTEGER DEFAULT 30,
            firmware_version TEXT DEFAULT 'v2.4.1',
            stream_status TEXT DEFAULT 'Online' CHECK (stream_status IN ('Online', 'Degraded', 'Offline')),
            FOREIGN KEY (device_id) REFERENCES Device(device_id) ON DELETE CASCADE
        )
    """)

    # 8. Alert Table (Enhanced with resolution & IoT metrics)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS Alert (
            alert_id INTEGER PRIMARY KEY,
            student_id TEXT NOT NULL,
            session_id INTEGER NOT NULL,
            device_id INTEGER NOT NULL,
            alert_type TEXT NOT NULL,
            alert_time TEXT NOT NULL,
            severity TEXT NOT NULL,
            status TEXT DEFAULT 'Pending' CHECK (status IN ('Pending', 'Acknowledged', 'Resolved')),
            eye_closure_sec REAL DEFAULT 0.0,
            resolution_notes TEXT,
            resolved_by TEXT,
            resolved_at TEXT,
            FOREIGN KEY (student_id) REFERENCES Student(student_id) ON DELETE CASCADE,
            FOREIGN KEY (session_id) REFERENCES Sessions(session_id) ON DELETE CASCADE,
            FOREIGN KEY (device_id) REFERENCES Device(device_id) ON DELETE CASCADE
        )
    """)

    # 9. Alert Notifications Table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS Alert_Notifications (
            notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_id INTEGER NOT NULL,
            recipient TEXT NOT NULL,
            channel TEXT CHECK (channel IN ('Email', 'SMS')) NOT NULL,
            sent_time TEXT DEFAULT (datetime('now', 'localtime')),
            status TEXT DEFAULT 'Simulated' CHECK (status IN ('Delivered', 'Simulated', 'Failed')),
            message_text TEXT NOT NULL,
            FOREIGN KEY (alert_id) REFERENCES Alert(alert_id) ON DELETE CASCADE
        )
    """)

    # 10. Audit Log Table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS Audit_Log (
            audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_type TEXT NOT NULL,
            table_name TEXT NOT NULL,
            record_id TEXT NOT NULL,
            performed_by TEXT NOT NULL,
            action_time TEXT DEFAULT (datetime('now', 'localtime')),
            details TEXT
        )
    """)

    # Check if seed data exists
    cur.execute("SELECT COUNT(*) FROM Users")
    is_new_database = cur.fetchone()[0] == 0
    if is_new_database:
        # Seed Users: default passwords hashed (admin123, faculty123)
        # Using Werkzeug generate_password_hash format: pbkdf2:sha256
        from werkzeug.security import generate_password_hash
        admin_hash = generate_password_hash("admin123", method="pbkdf2:sha256")
        faculty_hash = generate_password_hash("faculty123", method="pbkdf2:sha256")

        cur.execute("""
            INSERT INTO Users (username, password_hash, full_name, role, email)
            VALUES (?, ?, ?, ?, ?)
        """, ('admin', admin_hash, 'Chief Proctor / Admin', 'Administrator', 'admin@example.com'))

        cur.execute("""
            INSERT INTO Users (username, password_hash, full_name, role, email)
            VALUES (?, ?, ?, ?, ?)
        """, ('faculty', faculty_hash, 'Faculty Demo', 'Faculty', 'faculty@example.com'))

    demo_mode = os.environ.get("DEMO_MODE", "false").lower() in ("true", "1", "yes")
    if demo_mode and (is_new_database or not hasattr(hashlib, "scrypt")):
        from werkzeug.security import generate_password_hash

        # Older demo databases may contain scrypt hashes unavailable in this Python build.
        demo_passwords = {"admin": "admin123", "faculty": "faculty123"}
        for username, password in demo_passwords.items():
            cur.execute("SELECT password_hash FROM Users WHERE username = ?", [username])
            row = cur.fetchone()
            if row and row[0].startswith("scrypt:"):
                cur.execute(
                    "UPDATE Users SET password_hash = ? WHERE username = ?",
                    [generate_password_hash(password, method="pbkdf2:sha256"), username],
                )

        # Seed Students (Preserves Assessment-4 records)
        students_data = [
            ('STU001', 'Alex Morgan', 'A1', 'student1@example.com', 2025, 'CSE'),
            ('STU002', 'Taylor Reed', 'A1', 'student2@example.com', 2025, 'CSE'),
            ('STU003', 'Jordan Lee', 'B2', 'student3@example.com', 2025, 'Data Science'),
            ('STU004', 'Casey Quinn', 'B2', 'student4@example.com', 2025, 'Cyber Security'),
            ('STU005', 'Riley Chen', 'A1', 'student5@example.com', 2025, 'CSE'),
            ('STU006', 'Sam Patel', 'B1', 'student6@example.com', 2025, 'CSE'),
            ('STU007', 'Morgan Shah', 'A2', 'student7@example.com', 2025, 'Information Tech')
        ]
        cur.executemany("INSERT OR IGNORE INTO Student (student_id, student_name, class_section, email, enrollment_year, department) VALUES (?, ?, ?, ?, ?, ?)", students_data)

        # Seed Emergency Contacts
        contacts_data = [
            (1, 'STU001', 'Guardian One', 'Parent', '000-000-0001', 'guardian1@example.com'),
            (2, 'STU002', 'Guardian Two', 'Parent', '000-000-0002', 'guardian2@example.com'),
            (3, 'STU003', 'Guardian Three', 'Guardian', '000-000-0003', 'guardian3@example.com'),
            (4, 'STU004', 'Guardian Four', 'Parent', '000-000-0004', 'guardian4@example.com')
        ]
        cur.executemany("INSERT OR IGNORE INTO Emergency_Contact (contact_id, student_id, contact_name, relationship, phone_number, email) VALUES (?, ?, ?, ?, ?, ?)", contacts_data)

        # Seed Proctors
        proctor_data = [
            ('PR-101', 'Faculty One', 'CSE Dept', 'faculty1@example.com', '000-000-0101', 'PRP353'),
            ('PR-102', 'Faculty Two', 'CSE Dept', 'faculty2@example.com', '000-000-0102', 'SJT101'),
            ('PR-103', 'Faculty Three', 'Data Science Dept', 'faculty3@example.com', '000-000-0103', 'TT205')
        ]
        cur.executemany("INSERT OR IGNORE INTO Proctor (proctor_id, proctor_name, department, email, phone, assigned_room) VALUES (?, ?, ?, ?, ?, ?)", proctor_data)

        # Seed Sessions
        sessions_data = [
            (1, '2026-08-10', 'DBMS Lab', 'Faculty One', 50, 'A1', 'PR-101'),
            (2, '2026-08-12', 'Data Structures', 'Faculty Two', 60, 'A1', 'PR-102'),
            (3, '2026-08-14', 'Networks', 'Faculty Three', 45, 'B2', 'PR-103'),
            (4, '2026-08-15', 'Operating Systems', 'Faculty One', 60, 'A1', 'PR-101'),
            (5, '2026-08-16', 'Software Engineering', 'Faculty Two', 50, 'B1', 'PR-102')
        ]
        cur.executemany("INSERT OR IGNORE INTO Sessions (session_id, session_date, subject, faculty_name, duration_minutes, class_section, proctor_id) VALUES (?, ?, ?, ?, ?, ?, ?)", sessions_data)

        # Seed Devices
        devices_data = [
            (1, 'Camera', 'PRP353', '2026-01-01', 'Active', 99),
            (2, 'IR Sensor', 'PRP353', '2026-01-01', 'Active', 96),
            (3, 'Accelerometer', 'SJT101', '2026-01-05', 'Inactive', 75),
            (4, 'Eye Tracker', 'TT205', '2026-02-10', 'Active', 100),
            (5, 'Camera', 'SJT101', '2026-02-15', 'Active', 92)
        ]
        cur.executemany("INSERT OR IGNORE INTO Device (device_id, device_type, location, install_date, status, health_score) VALUES (?, ?, ?, ?, ?, ?)", devices_data)

        # Seed Camera Nodes
        nodes_data = [
            ('NODE-CAM-01', 1, '192.168.10.101', '4K UltraHD', 60, 'v3.1.2', 'Online'),
            ('NODE-IR-01', 2, '192.168.10.102', 'N/A (IR Array)', 100, 'v1.8.0', 'Online'),
            ('NODE-ACC-01', 3, '192.168.10.103', 'N/A (MEMS)', 50, 'v1.4.1', 'Offline'),
            ('NODE-EYE-01', 4, '192.168.10.104', '1080p IR 120Hz', 120, 'v2.9.0', 'Online'),
            ('NODE-CAM-02', 5, '192.168.10.105', '1080p HD', 30, 'v2.4.0', 'Online')
        ]
        cur.executemany("INSERT OR IGNORE INTO Camera_Nodes (node_id, device_id, ip_address, resolution, frame_rate, firmware_version, stream_status) VALUES (?, ?, ?, ?, ?, ?, ?)", nodes_data)

        # Seed Alerts (Preserves original 5 rows + adds realistic status and telemetry)
        alerts_data = [
            (1, 'STU001', 1, 1, 'Drowsiness', '2026-08-10 09:15', 'High', 'Resolved', 4.8, 'Student informed after lab; advised rest before morning class.', 'Faculty One', '2026-08-10 11:30'),
            (2, 'STU002', 1, 2, 'Negligence', '2026-08-10 09:20', 'Medium', 'Acknowledged', 0.0, 'Observed secondary phone screen under desk.', 'Faculty One', '2026-08-10 09:35'),
            (3, 'STU003', 2, 1, 'Drowsiness', '2026-08-12 10:05', 'Low', 'Resolved', 2.3, 'Brief fatigue event during lecture; recovered quickly.', 'Faculty Two', '2026-08-12 10:45'),
            (4, 'STU001', 2, 2, 'Drowsiness', '2026-08-12 10:10', 'High', 'Pending', 5.1, None, None, None),
            (5, 'STU001', 2, 1, 'Negligence', '2026-08-12 10:15', 'Medium', 'Pending', 0.0, None, None, None),
            (6, 'STU004', 3, 4, 'Drowsiness', '2026-08-14 11:20', 'Medium', 'Acknowledged', 3.4, 'Proctor initiated alert check.', 'Faculty Three', '2026-08-14 11:25'),
            (7, 'STU005', 4, 1, 'Negligence', '2026-08-15 14:10', 'Low', 'Resolved', 0.0, 'Student requested a review.', 'Faculty One', '2026-08-15 14:30'),
            (8, 'STU001', 5, 5, 'Drowsiness', '2026-08-16 15:40', 'High', 'Pending', 6.2, None, None, None)
        ]
        cur.executemany("INSERT OR IGNORE INTO Alert (alert_id, student_id, session_id, device_id, alert_type, alert_time, severity, status, eye_closure_sec, resolution_notes, resolved_by, resolved_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", alerts_data)

        # Seed Notifications
        notifications_data = [
            (1, 1, 'student1@example.com', 'Email', '2026-08-10 09:16', 'Simulated', 'Alert #1: High Drowsiness sample detected in DBMS Lab (PRP353).'),
            (2, 4, 'student1@example.com', 'Email', '2026-08-12 10:11', 'Simulated', 'Alert #4: High Drowsiness sample detected in Data Structures (PRP353).'),
            (3, 4, '000-000-0001', 'SMS', '2026-08-12 10:12', 'Simulated', 'Sample notification for a repeated demo event.')
        ]
        cur.executemany("INSERT OR IGNORE INTO Alert_Notifications (notification_id, alert_id, recipient, channel, sent_time, status, message_text) VALUES (?, ?, ?, ?, ?, ?, ?)", notifications_data)

        # Seed Audit Log
        audit_data = [
            (1, 'SYSTEM_INIT', 'System', '0', 'SYSTEM', '2026-08-10 08:00', 'Initialized AegisAlert database schema with Assessment-4 foundation.'),
            (2, 'CREATE', 'Alert', '1', 'IoT_Camera_Daemon', '2026-08-10 09:15', 'Sample alert record created for demo data.'),
            (3, 'RESOLVE', 'Alert', '1', 'Faculty One', '2026-08-10 11:30', 'Resolved with student consultation note.'),
            (4, 'CREATE', 'Alert', '4', 'IoT_Camera_Daemon', '2026-08-12 10:10', 'Sample telemetry event: High Drowsiness for STU001.')
        ]
        cur.executemany("INSERT OR IGNORE INTO Audit_Log (audit_id, action_type, table_name, record_id, performed_by, action_time, details) VALUES (?, ?, ?, ?, ?, ?, ?)", audit_data)

    conn.commit()
    conn.close()
