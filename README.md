# Student Drowsiness Alert System

> **Demo-ready student monitoring dashboard**
> **Student Author:** Anshul Suhas Kadam
> **Registration Number:** 25BCE2117
> **Section:** A1
> **Department:** Computer Science and Engineering, Vellore Institute of Technology

---

## 📌 Executive Project Overview

This project is a demo-ready student monitoring dashboard for classroom drowsiness and alert tracking. It shows how to record and review sample classroom attention events using a web app and database-backed workflow. It does not connect to live classroom cameras or perform automatic AI-based detection.

The system features a **web-based monitoring dashboard**:
1. **Operations Web Portal (`app.py`)**: A dashboard for monitoring student drowsiness alerts, reviewing incident timelines, charting trends, acknowleding and resolving alerts, viewing student profiles, and reviewing audit logs.
2. **Desktop Proctor Utility (`alert_form.py`)**: A Python `tkinter` helper for quick alert logging and local review.

Both clients share a **dual-engine relational database layer (`db.py`)**:
- **Primary Engine**: **Oracle Database 21c Express Edition (`XEPDB1`)** or **Oracle Database 23c Free (`FREEPDB1`)** using thin-mode connection pooling.
- **Offline Fallback Engine**: **SQLite 3 (`local_demo.db`)** with the schema and queries needed for offline demonstration without Oracle.

---

## 🎨 Theme & UI Redesign Highlights

Following the telemetry operations center aesthetic:
- **Dark Operations Center Theme (Default)**: Deep charcoal/navy background (`#0b0d13`), slate containers (`#12151e`), high-contrast metric cards, and glowing telemetry accents.
- **Instant Light Mode Switch**: Crisp, clean SaaS workspace mode (`#f8fafc`) for administrative report printing and daytime grading.
- **Interactive Chronological Incident Timeline**: Visual timeline with floating severity pins displaying active classroom incidents.
- **AI Suggested Actions / Rapid Review Card**: One-click **Acknowledge** and **Resolve** action buttons for immediate triage.
- **KPI Metrics Ribbon**: Total incidents, critical high risks, behavior breakdown (Drowsy vs. Negligent), and sensor uptime.
- **Responsive Navigation Sidebar**: Left-hand navigation covering Dashboard, Smart Alerts, Students, Sessions, Devices, Analytics, Reports, Notifications, Audit Trail, and DB Diagnostics.

---

## 🗄️ Relational Database Schema & ER Model

The relational design complies with **3rd Normal Form (3NF)** with primary keys, foreign keys, cascade rules, and check constraints:

```text
┌─────────────────┐       ┌─────────────────┐       ┌────────────────────────┐
│      Users      │       │     Proctor     │       │        Student         │
├─────────────────┤       ├─────────────────┤       ├────────────────────────┤
│ user_id (PK)    │       │ proctor_id (PK) │       │ student_id (PK)        │
│ username (UK)   │       │ proctor_name    │       │ student_name           │
│ password_hash   │       │ department      │       │ class_section          │
│ role            │       │ assigned_room   │       │ email (UK)             │
└────────┬────────┘       └────────┬────────┘       │ enrollment_year        │
         │                         │                │ department             │
         │ (audits)                │ (proctors)     └─────┬────────────┬─────┘
         ▼                         ▼                      │            │
┌─────────────────┐       ┌─────────────────┐             │ (has)      │ (triggers)
│    Audit_Log    │       │    Sessions     │             ▼            ▼
├─────────────────┤       ├─────────────────┤   ┌───────────────────┐ ┌──────────────┐
│ audit_id (PK)   │       │ session_id (PK) │   │ Emergency_Contact │ │    Alert     │
│ action_type     │       │ subject         │   ├───────────────────┤ ├──────────────┤
│ table_name      │       │ faculty_name    │   │ contact_id (PK)   │ │alert_id (PK) │
│ performed_by    │       │ duration_minutes│   │ student_id (FK)   │ │student_id(FK)│
│ action_time     │       │ proctor_id (FK) ◄───┤ contact_name      │ │session_id(FK)│
└─────────────────┘       └────────┬────────┘   │ phone_number      │ │device_id (FK)│
                                   │            └───────────────────┘ │alert_type    │
                                   │ (context for)                    │severity      │
                                   ▼                                  │status        │
┌─────────────────┐       ┌─────────────────┐                         │eye_closure_s │
│     Device      │       │  Camera_Nodes   │                         │resolved_by   │
├─────────────────┤       ├─────────────────┤                         └──────┬───────┘
│ device_id (PK)  │◄──────┤ node_id (PK)    │                                │
│ device_type     │       │ device_id (FK)  │                                │ (dispatches)
│ location        │       │ ip_address      │                                ▼
│ status          │       │ resolution      │                    ┌───────────────────┐
│ health_score    │       │ stream_status   │                    │Alert_Notifications│
└────────┬────────┘       └─────────────────┘                    ├───────────────────┤
         │                                                       │notification_id(PK)│
         └──────────────────────────────────────────────────────►│alert_id (FK)      │
                                (captures)                       │recipient, channel │
                                                                 │status, sent_time  │
                                                                 └───────────────────┘
```

### Table Definitions

| Table Name | Primary Key | Foreign Keys & Relationships | Key Attributes & Domain Constraints |
| :--- | :--- | :--- | :--- |
| **`Users`** | `user_id` | *None* | `username` (UK), `password_hash`, `role` (CHECK: 'Administrator', 'Faculty') |
| **`Student`** | `student_id` | *None* | `student_name`, `class_section`, `email` (UK), `enrollment_year` (2020-2030), `department` |
| **`Emergency_Contact`** | `contact_id` | `student_id` → `Student` (CASCADE) | `contact_name`, `relationship`, `phone_number`, `email` |
| **`Proctor`** | `proctor_id` | *None* | `proctor_name`, `department`, `email` (UK), `phone`, `assigned_room` |
| **`Sessions`** | `session_id` | `proctor_id` → `Proctor` | `session_date`, `subject`, `faculty_name`, `duration_minutes` (>0), `class_section` |
| **`Device`** | `device_id` | *None* | `device_type` (Camera, IR Sensor, Eye Tracker, Accelerometer), `location`, `status`, `health_score` |
| **`Camera_Nodes`** | `node_id` | `device_id` → `Device` (CASCADE) | `ip_address`, `resolution` (1080p, 4K), `frame_rate` (fps), `stream_status` |
| **`Alert`** | `alert_id` | `student_id`, `session_id`, `device_id` | `alert_type` (Drowsiness, Negligence, Distraction), `severity` (Low, Medium, High), `status` (Pending, Acknowledged, Resolved), `eye_closure_sec`, `resolution_notes`, `resolved_by` |
| **`Alert_Notifications`**| `notification_id` | `alert_id` → `Alert` (CASCADE) | `recipient`, `channel` (Email, SMS), `status` (Delivered, Simulated, Failed), `message_text` |
| **`Audit_Log`** | `audit_id` | *None* | `action_type` (CREATE, UPDATE, DELETE, RESOLVE), `table_name`, `record_id`, `performed_by`, `action_time`, `details` |

---

## ⚡ Quick Start for Testers (Local SQLite Demo)

The app uses the pre-seeded local SQLite database for an offline evaluation. Demo shortcuts are opt-in; regular login remains enabled so role permissions can be demonstrated.

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Launch the Web Application
```bash
DEMO_MODE=true DB_FORCE_ENGINE=sqlite python app.py
```
Open your browser at **[http://127.0.0.1:5000](http://127.0.0.1:5000)**.
- Default Login Credentials:
  - **Administrator**: `admin` / `admin123`
  - **Faculty / Proctor**: `faculty` / `faculty123`
  *(Quick evaluation sign-in and role-switch shortcuts are available only with `DEMO_MODE=true`.)*
- `DEMO_AUTO_LOGIN=true` can bypass login for a disposable local demo only. Leave it false to test authentication and role permissions.
- Outside demo mode, set a private random `SECRET_KEY` and keep `DEMO_AUTO_LOGIN=false`. The app refuses to start without a configured key.
- The documented demo usernames/passwords are rejected outside demo mode. Before any real deployment, provision individual accounts with non-demo credentials and restrict demo/student sample data.

### 3. Launch the Desktop GUI
```bash
python alert_form.py
```

---

## 🏢 Oracle Database 21c XE / Free Setup Instructions

### Step 1: Verify Oracle Listener and Pluggable Database Name
On Windows PowerShell or Command Prompt:
```powershell
lsnrctl status
```
Inspect the output under `Services Summary`:
- If you see `XEPDB1`, your service name is **`XEPDB1`** (Standard Oracle 21c XE).
- If you see `FREEPDB1`, your service name is **`FREEPDB1`** (Oracle 23c Free).

### Step 2: Initialize Database Objects in SQL*Plus
Run the full Oracle DDL and sample seed script:
```powershell
sqlplus system@localhost:1521/XEPDB1 @schema_oracle.sql
```
*(Replace `XEPDB1` with `FREEPDB1` if needed and enter your Oracle system password locally.)*

### Step 3: Configure Environment Variables
Copy `.env.example` to `.env`:
```powershell
Copy-Item .env.example .env
```
Edit `.env` to match your credentials:
```ini
DB_USER=system
DB_PASSWORD=<your-oracle-password>
DB_HOST=localhost
DB_PORT=1521
DB_SERVICE_NAME=XEPDB1

# Enforce strict Oracle connection for final evaluation:
ORACLE_STRICT_MODE=true
DB_FORCE_ENGINE=oracle
```

### Step 4: Verify Live Oracle Connectivity
Run the diagnostic test or start the application:
```powershell
python -c "from db import diagnose_connection; print(diagnose_connection())"
python app.py
```
The status chip in the top navbar will display **`Oracle DB (XEPDB1)`** with an active green pulse.

---

## ☁️ Deploy a Demo to Render

The Render Blueprint in `render.yaml` runs the app with its seeded SQLite demo database; a separate hosted Oracle database is not required.

1. In Render, open the Blueprint and choose **Manual sync** to apply the latest repository changes. If you have not created the service yet, create it from this repository's Blueprint.
2. Let Render deploy the web service. The Blueprint generates a private `SECRET_KEY`, enables demo mode, keeps auto-login disabled, and selects SQLite.
3. Open the service URL and sign in with the demo credentials shown in the Quick Start section.

The free Render filesystem is temporary: database edits may be lost when the service restarts, redeploys, or sleeps. Treat this as a disposable evaluation demo and do not enter real student data. Persistent database storage requires a hosting plan/storage setup that supports a persistent disk, or adapting the app to a hosted database.

For an Oracle deployment instead, configure a remotely reachable Oracle database and its private environment variables (`DB_USER`, `DB_PASSWORD`, and `DB_DSN`). A database installed only on your computer is not reachable by Render via `localhost`. Never use Oracle's `SYSTEM` account for the web app or expose an unsecured database listener publicly. This academic app has not had a production security or load review.

---

## 🚀 Key Implemented Features

### 1. Executive Dashboard (`/`)
- **Top Context Ribbon**: Active candidate, recorded event category, source room/node, and sample sensor measurement (no AI model is connected).
- **Chronological Incident Timeline**: Interactive horizontal pin bar with severity color coding.
- **KPI Cards**: Live counts for total incidents, high severity alerts, behavioral breakdown, and online sensors.
- **Rapid Review**: One-click Acknowledge / Resolve actions directly on the dashboard.
- **Chart.js Visualizations**: 7-day incident trend curve, hourly lecture density bar chart, and category doughnut.
- **⚡ Demo Telemetry Simulator**: Button generating random sample alerts; it does not ingest live sensor data.

### 2. Smart Alerts Management (`/alerts`)
- Full CRUD operations with foreign-key lookups for Student, Session, and Device.
- Quick filter tabs: *All Alerts*, *⚠️ Unresolved (Pending)*, *🚨 High Risk*, *😴 Drowsiness*, *📱 Negligence*.
- Workflow state machine: `Pending` ➔ `Acknowledged` ➔ `Resolved`.
- Resolution drawer with faculty consultation notes and timestamp tracking.
- Repeat alert detection: Automatically detects multiple incidents logged for the same student in a session.
- Configurable severity criteria (demonstration eye closure thresholds: <2.0s Low, 2.0-4.0s Medium, >4.0s High).

### 3. Student Roster & Detailed Profiles (`/students`)
- Student listing with section filters (A1, B2) and instant search.
- Student risk classification: *Stable*, *Moderate Pattern*, *Repeated Pattern*.
- **Individual Student Dossier (`/students/<id>`)**:
  - Full academic demographics and institutional email.
  - Linked Emergency Contact (Parent/Guardian name, phone, relationship).
  - Chronological incident history table specific to the student.
  - Summary metrics: high-risk count and average eye closure duration.
- **CSV Bulk Import**: Upload CSV files with validation and automatic duplicate prevention.

### 4. Academic Session Management (`/sessions`)
- Timetable tracking: subject, lead faculty, section, duration, and assigned proctor.
- Session-level incident aggregation: counts total incidents and high-risk alerts per lecture.

### 5. Sensor Devices & Camera Nodes (`/devices`)
- Registry for edge cameras, infrared gaze sensors, and eye trackers.
- Hardware health score metric and quick status toggle (Active vs. Inactive).
- **Camera Nodes Sub-Entity**: Telemetry IP, streaming resolution (1080p, 4K), frame rate (fps), and firmware tracking.

### 6. Deep Analytics Portal (`/analytics`)
- 7-day database-backed trend chart with a high-risk overlay; empty periods show zero rather than fabricated sample values.
- Behavioral classification distribution doughnut chart.
- Criticality distribution bar chart (Low, Medium, High, Critical).
- Recorded alert counts by hour (09:00–16:00).
- Repeated alert frequency ranking table.

### 7. Reports & CSV Exports (`/reports`)
- Executive printable report view optimized for printing or PDF export (`@media print`).
- One-click CSV downloads for:
  - Incident Alerts (`/export/alerts`)
  - Student Roster (`/export/students`)
  - Academic Sessions (`/export/sessions`)
  - Device Registry (`/export/devices`)
  - System Audit Trail (`/export/audit`)

### 8. Database-Backed Notification Center (`/notifications`)
- Dispatched notifications table for Email and SMS.
- Recipient email/phone, timestamp, channel, and delivery status.
- Distinctly labelled **Simulation Sandbox Mode** to prevent external API charges.

### 9. Immutable Audit Trail (`/audit`)
- Security log tracking `CREATE`, `UPDATE`, `DELETE`, `ACKNOWLEDGE`, `RESOLVE`, and `TOGGLE_STATUS` events.
- Stores record ID, executing user, timestamp, and action details.

### 10. Database Diagnostics & Switcher (`/diagnostics`)
- Real-time Oracle connection health check, latency (ms), and version banner.
- Active schema entity row counter.
- Live engine switcher: Auto-Detect, Strict Oracle Mode, or Offline SQLite Demo.

---

## 🔐 Privacy, Safety & Demo Limitations

- The included SQLite database is seeded evaluation data. Do not populate a demo or public presentation with identifiable real student records.
- The simulator creates random sample alerts; the app does not connect to a camera, infer behavior with an AI model, or verify sensor measurements. The displayed eye-closure value is stored sample telemetry, not a model confidence score.
- Email/SMS dispatch is a database-backed simulation only. It does not send messages to recipients.
- An alert is an indicator for a trained human to review, not a finding of misconduct or a basis for an automatic penalty. Account for sensor error, context, disability, and other explanations.
- A real deployment must define and enforce an institutional consent/notice process, least-privilege access, data minimization, a retention/deletion schedule, secure backups, and incident-response procedures. These governance policies are not implemented by this academic demo.
- Never expose the local demo server to a public network. For deployment, use HTTPS, a strong private `SECRET_KEY`, real authentication, protected secrets, and a production WSGI server; disable demo mode, role switching, and auto-login.

## 🧪 Feature-by-Feature Testing Checklist

| Test Item | Verification Procedure | Expected Outcome | Verified Status |
| :--- | :--- | :--- | :--- |
| **1. Database Init** | Run `python -m unittest tests/test_system.py` | Database schema and integrity tests pass | ✅ |
| **2. Oracle DDL** | Execute `@schema_oracle.sql` in SQL*Plus | Tables, views, sequences, procedures, triggers, seed created | ✅ Passed |
| **3. Dashboard UI** | Load `http://127.0.0.1:5000/` in browser | Operations center dark dashboard loads with timeline and KPIs | ✅ Passed |
| **4. Theme Switcher** | Click Sun/Moon icon in navbar | Toggles seamlessly between Dark Operations and Light Workspace | ✅ Passed |
| **5. Demo Simulator** | Click "Simulate Event (Demo)" button in navbar | Clearly marked sample alert created in the database | ✅ |
| **6. Alert CRUD** | Create alert, acknowledge, and resolve with notes | Alert transitions: Pending ➔ Acknowledged ➔ Resolved | ✅ Passed |
| **7. Student Profile** | Navigate to `/students/STU001` | Dossier shows student stats, emergency contact, and incident log | ✅ Passed |
| **8. CSV Import** | Click "Import CSV" on Students page | Parses CSV, skips duplicates, and enlists new candidates | ✅ Passed |
| **9. Device Toggle** | Click Deactivate/Activate button on Devices page | Toggles status between Active and Inactive, audited in log | ✅ Passed |
| **10. CSV Exports** | Click "Export Telemetry" / "Download Alerts CSV" | Browser downloads clean `.csv` file with filter respect | ✅ Passed |
| **11. Print Preview** | Click "Print / Save PDF" on Reports page | Opens clean browser print preview without sidebar or navigation | ✅ Passed |
| **12. RBAC Security** | Login as Faculty and attempt admin deletion | Displays permission notice; prevents unauthorized operations | ✅ Passed |

---

## 📁 Project Directory Structure

```text
├── app.py                  # Flask Web Application & Route Controller
├── alert_form.py           # Native Python Tkinter Desktop Proctoring GUI
├── db.py                   # Unified Dual-Engine Database Manager (Oracle & SQLite)
├── auth.py                 # RBAC Security, PBKDF2 Hashing, and Session Manager
├── services.py             # Business Logic, Workflows, Simulation & Analytics Services
├── schema_oracle.sql       # Full Oracle 21c/23c DDL, Views, Procedures & Seed Script
├── schema_migration.sql    # Non-destructive in-place Oracle migration script
├── drop_schema_safe.sql    # Safe cleanup script for project-owned database objects only
├── local_demo.db           # Pre-seeded SQLite database for zero-config offline demos
├── requirements.txt        # Python package dependencies
├── .env.example            # Environment configuration template
├── tests/
│   └── test_system.py      # Automated unittest suite (7 test suites, 100% pass)
├── template/
│   ├── base.html           # Master application layout with navy sidebar & theme toggle
│   ├── dashboard.html      # Operations center telemetry dashboard & incident timeline
│   ├── alerts.html         # Smart alert list, filters, and workflow modals
│   ├── students.html       # Student roster, section filters, and CSV import modal
│   ├── student_profile.html# Student dossier, emergency contact & incident history
│   ├── sessions.html       # Academic sessions timetable & proctor assignments
│   ├── devices.html        # Sensor hardware registry & camera nodes telemetry
│   ├── analytics.html      # Deep analytics, fatigue curve & frequency rankings
│   ├── reports.html        # Printable executive reports & CSV export hub
│   ├── notifications.html  # Database-backed email & SMS dispatch history
│   ├── audit.html          # Immutable system security audit trail
│   ├── diagnostics.html    # Oracle connection diagnostics & engine mode switcher
│   └── login.html          # Sleek authentication portal with evaluation shortcuts
├── static/
│   └── style.css           # Modern telemetry design system (Dark & Light themes)
└── README.md               # Complete Project Documentation & Evaluation Guide
```

---

## 🔒 Security & Medical Advisory Notice

1. **Demonstration Heuristics**: Eye closure durations (e.g. 2.0s, 4.5s) are configurable demonstration thresholds designed for university laboratory evaluation, not clinically validated diagnostic criteria.
2. **Neutral Academic Phrasing**: The system uses objective terms such as *"repeated alert pattern"* rather than pejorative labelling to allow faculty proctors to conduct compassionate inquiry.
3. **Telemetry Simulation**: Simulated hardware nodes and notifications are clearly distinguished from live external networks, ensuring zero external billing risk during presentations.
