"""
Student Drowsiness Alert System — Core Application Services & Business Logic Layer
Implements CRUD, foreign-key integrity, workflow state transitions,
repeat incident pattern detection, CSV bulk import/export, telemetry simulation,
database-backed notifications, and audit logging.
"""

import csv
import io
import math
import random
from datetime import datetime, timedelta
from db import get_connection, DatabaseError


# ============================================================================
# AUDIT LOGGING SERVICE
# ============================================================================

def log_audit(action_type: str, table_name: str, record_id: str, performed_by: str, details: str = None):
    """Writes an immutable record into the Audit_Log table."""
    conn, engine = get_connection()
    cur = conn.cursor()
    try:
        if engine == "oracle":
            cur.execute("""
                INSERT INTO Audit_Log (audit_id, action_type, table_name, record_id, performed_by, action_time, details)
                VALUES (SEQ_AUDIT_ID.NEXTVAL, :1, :2, :3, :4, SYSDATE, :5)
            """, [action_type, table_name, str(record_id), performed_by, details or ''])
        else:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cur.execute("""
                INSERT INTO Audit_Log (action_type, table_name, record_id, performed_by, action_time, details)
                VALUES (?, ?, ?, ?, ?, ?)
            """, [action_type, table_name, str(record_id), performed_by, now_str, details or ''])
        conn.commit()
    except Exception as e:
        print(f"[Warning] Failed to write audit log: {e}")
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass


def fetch_audit_logs(limit: int = 100, action_filter: str = None):
    """Retrieves recent audit log events."""
    conn, engine = get_connection()
    cur = conn.cursor()
    try:
        sql = """
            SELECT audit_id, action_type, table_name, record_id, performed_by, action_time, details
            FROM Audit_Log
        """
        params = []
        if action_filter and action_filter != 'all':
            sql += " WHERE action_type = :1" if engine == "oracle" else " WHERE action_type = ?"
            params.append(action_filter)

        sql += " ORDER BY audit_id DESC"
        if engine == "oracle":
            sql = f"SELECT * FROM ({sql}) WHERE ROWNUM <= {limit}"
        else:
            sql += f" LIMIT {limit}"

        cur.execute(sql, params)
        rows = cur.fetchall()
        logs = []
        for r in rows:
            time_val = r[5]
            if hasattr(time_val, "strftime"):
                time_val = time_val.strftime("%Y-%m-%d %H:%M:%S")
            logs.append({
                "audit_id": r[0],
                "action_type": r[1],
                "table_name": r[2],
                "record_id": r[3],
                "performed_by": r[4],
                "action_time": str(time_val),
                "details": r[6]
            })
        return logs
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass


# ============================================================================
# ALERT MANAGEMENT & WORKFLOW SERVICES
# ============================================================================

def fetch_alerts(filter_type=None, filter_severity=None, filter_status=None, query=None, limit=100):
    """Fetches alerts joined with Student, Sessions, and Device."""
    conn, engine = get_connection()
    cur = conn.cursor()
    try:
        if engine == "oracle":
            sql = """
                SELECT a.alert_id, a.student_id, NVL(s.student_name, 'Unknown'),
                       s.class_section, NVL(s.department, 'CSE'),
                       a.session_id, NVL(sess.subject, 'Unknown'), NVL(sess.faculty_name, 'Unknown'),
                       a.device_id, NVL(d.device_type, 'Camera'), NVL(d.location, 'PRP353'),
                       a.alert_type, a.severity, a.status,
                       NVL(a.eye_closure_sec, 0.0),
                       TO_CHAR(a.alert_time, 'YYYY-MM-DD HH24:MI:SS'),
                       a.resolution_notes, a.resolved_by,
                       TO_CHAR(a.resolved_at, 'YYYY-MM-DD HH24:MI')
                FROM Alert a
                LEFT JOIN Student s ON s.student_id = a.student_id
                LEFT JOIN Sessions sess ON sess.session_id = a.session_id
                LEFT JOIN Device d ON d.device_id = a.device_id
                WHERE 1=1
            """
        else:
            sql = """
                SELECT a.alert_id, a.student_id, COALESCE(s.student_name, 'Unknown'),
                       s.class_section, COALESCE(s.department, 'CSE'),
                       a.session_id, COALESCE(sess.subject, 'Unknown'), COALESCE(sess.faculty_name, 'Unknown'),
                       a.device_id, COALESCE(d.device_type, 'Camera'), COALESCE(d.location, 'PRP353'),
                       a.alert_type, a.severity, a.status,
                       COALESCE(a.eye_closure_sec, 0.0),
                       a.alert_time,
                       a.resolution_notes, a.resolved_by,
                       a.resolved_at
                FROM Alert a
                LEFT JOIN Student s ON s.student_id = a.student_id
                LEFT JOIN Sessions sess ON sess.session_id = a.session_id
                LEFT JOIN Device d ON d.device_id = a.device_id
                WHERE 1=1
            """

        params = []
        if filter_type and filter_type != 'all':
            sql += " AND a.alert_type = :1" if engine == "oracle" else " AND a.alert_type = ?"
            params.append(filter_type)
        if filter_severity and filter_severity != 'all':
            param_idx = len(params) + 1
            sql += f" AND a.severity = :{param_idx}" if engine == "oracle" else " AND a.severity = ?"
            params.append(filter_severity)
        if filter_status and filter_status != 'all':
            param_idx = len(params) + 1
            sql += f" AND a.status = :{param_idx}" if engine == "oracle" else " AND a.status = ?"
            params.append(filter_status)
        if query:
            param_idx = len(params) + 1
            q = f"%{query.lower()}%"
            if engine == "oracle":
                sql += f" AND (LOWER(s.student_name) LIKE :{param_idx} OR LOWER(a.student_id) LIKE :{param_idx} OR LOWER(sess.subject) LIKE :{param_idx} OR LOWER(d.location) LIKE :{param_idx})"
            else:
                sql += f" AND (LOWER(s.student_name) LIKE ? OR LOWER(a.student_id) LIKE ? OR LOWER(sess.subject) LIKE ? OR LOWER(d.location) LIKE ?)"
            params.append(q)

        sql += " ORDER BY a.alert_id DESC"
        if engine == "oracle":
            sql = f"SELECT * FROM ({sql}) WHERE ROWNUM <= {limit}"
        else:
            sql += f" LIMIT {limit}"

        cur.execute(sql, params)
        raw_rows = cur.fetchall()

        alerts = []
        for r in raw_rows:
            alerts.append({
                "alert_id": r[0],
                "student_id": r[1],
                "student_name": r[2],
                "section": r[3],
                "department": r[4],
                "session_id": r[5],
                "subject": r[6],
                "faculty": r[7],
                "device_id": r[8],
                "device_type": r[9],
                "location": r[10],
                "alert_type": r[11],
                "severity": r[12],
                "status": r[13] or "Pending",
                "eye_closure_sec": float(r[14] or 0.0),
                "alert_time": str(r[15]),
                "resolution_notes": r[16] or "",
                "resolved_by": r[17] or "",
                "resolved_at": str(r[18]) if r[18] else ""
            })
        return alerts
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass


def get_next_alert_id():
    """Calculates the next available alert ID."""
    conn, engine = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT MAX(alert_id) FROM Alert")
        row = cur.fetchone()
        max_id = row[0] if (row and row[0] is not None) else 100
        return max_id + 1
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass


def detect_repeat_pattern(student_id: str, session_id: int, current_alert_id: int = None):
    """
    Checks if student has previous alerts recorded in the same session.
    Returns (has_pattern, prior_count, message).
    """
    conn, engine = get_connection()
    cur = conn.cursor()
    try:
        if current_alert_id:
            sql = "SELECT COUNT(*) FROM Alert WHERE student_id = ? AND session_id = ? AND alert_id != ?" if engine == "sqlite" else "SELECT COUNT(*) FROM Alert WHERE student_id = :1 AND session_id = :2 AND alert_id != :3"
            cur.execute(sql, [student_id, session_id, current_alert_id])
        else:
            sql = "SELECT COUNT(*) FROM Alert WHERE student_id = ? AND session_id = ?" if engine == "sqlite" else "SELECT COUNT(*) FROM Alert WHERE student_id = :1 AND session_id = :2"
            cur.execute(sql, [student_id, session_id])

        row = cur.fetchone()
        count = row[0] if row else 0
        if count >= 2:
            return True, count, f"Repeated alert pattern: {count} prior alerts logged for this student in this session."
        elif count == 1:
            return False, count, "1 prior alert logged in this session."
        return False, 0, "Initial alert in this session."
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass


def create_alert(alert_id: int, student_id: str, session_id: int, device_id: int,
                 alert_type: str, severity: str, eye_closure_sec: float = 0.0,
                 performed_by: str = "System"):
    """Creates a new incident alert with validation and auto-dispatch simulation."""
    try:
        alert_id = int(alert_id)
        session_id = int(session_id)
        device_id = int(device_id)
        eye_closure_sec = float(eye_closure_sec)
    except (TypeError, ValueError):
        return False, "Alert, session, and device IDs must be integers; eye closure must be numeric."
    if min(alert_id, session_id, device_id) <= 0:
        return False, "Alert, session, and device IDs must be positive."
    if alert_type not in {"Drowsiness", "Negligence", "Distraction", "Absence"}:
        return False, "Alert type is invalid."
    if severity not in {"Low", "Medium", "High", "Critical"}:
        return False, "Alert severity is invalid."
    if not math.isfinite(eye_closure_sec) or not 0 <= eye_closure_sec <= 999.9:
        return False, "Eye closure must be between 0 and 999.9 seconds."
    student_id = str(student_id).strip()
    if not student_id:
        return False, "Student ID is required."

    conn, engine = get_connection()
    cur = conn.cursor()
    try:
        if engine == "oracle":
            cur.execute("""
                INSERT INTO Alert (alert_id, student_id, session_id, device_id, alert_type, alert_time, severity, status, eye_closure_sec)
                VALUES (:1, :2, :3, :4, :5, SYSDATE, :6, 'Pending', :7)
            """, [int(alert_id), student_id, int(session_id), int(device_id), alert_type, severity, float(eye_closure_sec)])
        else:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cur.execute("""
                INSERT INTO Alert (alert_id, student_id, session_id, device_id, alert_type, alert_time, severity, status, eye_closure_sec)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'Pending', ?)
            """, [int(alert_id), student_id, int(session_id), int(device_id), alert_type, now_str, severity, float(eye_closure_sec)])

        conn.commit()

        # Check for repeat patterns
        has_repeat, count, repeat_msg = detect_repeat_pattern(student_id, int(session_id), int(alert_id))

        # Log to Audit
        log_audit("CREATE", "Alert", str(alert_id), performed_by,
                  f"Created {alert_type} ({severity} risk) for {student_id}. {repeat_msg}")

        # Dispatch simulated notification
        dispatch_simulated_alert_notification(alert_id, student_id, alert_type, severity)

        return True, f"Alert #{alert_id} recorded successfully."
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass


def update_alert(alert_id: int, student_id: str, session_id: int, device_id: int,
                 alert_type: str, severity: str, status: str, eye_closure_sec: float,
                 notes: str, performed_by: str = "Faculty"):
    """Updates existing alert attributes."""
    try:
        alert_id = int(alert_id)
        session_id = int(session_id)
        device_id = int(device_id)
        eye_closure_sec = float(eye_closure_sec)
    except (TypeError, ValueError):
        return False, "Alert, session, and device IDs must be integers; eye closure must be numeric."
    if min(alert_id, session_id, device_id) <= 0:
        return False, "Alert, session, and device IDs must be positive."
    if not str(student_id).strip():
        return False, "Student ID is required."
    if alert_type not in {"Drowsiness", "Negligence", "Distraction", "Absence"}:
        return False, "Alert type is invalid."
    if severity not in {"Low", "Medium", "High", "Critical"}:
        return False, "Alert severity is invalid."
    if status not in {"Pending", "Acknowledged", "Resolved"}:
        return False, "Alert status is invalid."
    if not math.isfinite(eye_closure_sec) or not 0 <= eye_closure_sec <= 999.9:
        return False, "Eye closure must be between 0 and 999.9 seconds."
    student_id = str(student_id).strip()

    conn, engine = get_connection()
    cur = conn.cursor()
    try:
        if engine == "oracle":
            cur.execute("""
                UPDATE Alert
                SET student_id = :1,
                    session_id = :2,
                    device_id = :3,
                    alert_type = :4,
                    severity = :5,
                    status = :6,
                    eye_closure_sec = :7,
                    resolution_notes = :8
                WHERE alert_id = :9
            """, [student_id, int(session_id), int(device_id), alert_type, severity, status, float(eye_closure_sec), notes or '', int(alert_id)])
        else:
            cur.execute("""
                UPDATE Alert
                SET student_id = ?,
                    session_id = ?,
                    device_id = ?,
                    alert_type = ?,
                    severity = ?,
                    status = ?,
                    eye_closure_sec = ?,
                    resolution_notes = ?
                WHERE alert_id = ?
            """, [student_id, int(session_id), int(device_id), alert_type, severity, status, float(eye_closure_sec), notes or '', int(alert_id)])

        if cur.rowcount == 0:
            return False, f"Alert #{alert_id} not found."

        conn.commit()
        log_audit("UPDATE", "Alert", str(alert_id), performed_by,
                  f"Updated alert attributes. Status: {status}, Severity: {severity}")
        return True, f"Alert #{alert_id} updated successfully."
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass


def acknowledge_alert(alert_id: int, performed_by: str = "Faculty"):
    """Transitions alert status from Pending to Acknowledged."""
    conn, engine = get_connection()
    cur = conn.cursor()
    try:
        if engine == "oracle":
            cur.execute("UPDATE Alert SET status = 'Acknowledged' WHERE alert_id = :1", [int(alert_id)])
        else:
            cur.execute("UPDATE Alert SET status = 'Acknowledged' WHERE alert_id = ?", [int(alert_id)])

        conn.commit()
        log_audit("ACKNOWLEDGE", "Alert", str(alert_id), performed_by, "Alert acknowledged by invigilator.")
        return True, f"Alert #{alert_id} marked as Acknowledged."
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass


def resolve_alert(alert_id: int, resolution_notes: str, performed_by: str = "Faculty"):
    """Transitions alert status to Resolved with notes and timestamp."""
    conn, engine = get_connection()
    cur = conn.cursor()
    try:
        if engine == "oracle":
            cur.execute("""
                UPDATE Alert
                SET status = 'Resolved',
                    resolution_notes = :1,
                    resolved_by = :2,
                    resolved_at = SYSDATE
                WHERE alert_id = :3
            """, [resolution_notes.strip() if resolution_notes else "Resolved after faculty review.", performed_by, int(alert_id)])
        else:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cur.execute("""
                UPDATE Alert
                SET status = 'Resolved',
                    resolution_notes = ?,
                    resolved_by = ?,
                    resolved_at = ?
                WHERE alert_id = ?
            """, [resolution_notes.strip() if resolution_notes else "Resolved after faculty review.", performed_by, now_str, int(alert_id)])

        conn.commit()
        log_audit("RESOLVE", "Alert", str(alert_id), performed_by,
                  f"Resolved alert. Notes: {resolution_notes or 'No specific notes'}")
        return True, f"Alert #{alert_id} resolved successfully."
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass


def delete_alert(alert_id: int, performed_by: str = "Administrator"):
    """Deletes an alert record and cascades associated notifications."""
    conn, engine = get_connection()
    cur = conn.cursor()
    try:
        if engine == "oracle":
            cur.execute("DELETE FROM Alert WHERE alert_id = :1", [int(alert_id)])
        else:
            cur.execute("DELETE FROM Alert WHERE alert_id = ?", [int(alert_id)])

        if cur.rowcount == 0:
            return False, f"Alert #{alert_id} not found."

        conn.commit()
        log_audit("DELETE", "Alert", str(alert_id), performed_by, f"Deleted Alert #{alert_id}")
        return True, f"Alert #{alert_id} deleted."
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass


def simulate_telemetry_event(performed_by: str = "IoT_Daemon"):
    """Simulates an incoming edge-AI camera event with realistic telemetry."""
    conn, engine = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT student_id, student_name FROM Student")
        students = cur.fetchall()

        cur.execute("SELECT session_id, subject FROM Sessions")
        sessions = cur.fetchall()

        cur.execute("SELECT device_id, device_type, location FROM Device WHERE status = 'Active'")
        devices = cur.fetchall()

        if not students or not sessions or not devices:
            return False, "Cannot simulate: Need at least 1 student, 1 session, and 1 active device."

        st = random.choice(students)
        se = random.choice(sessions)
        dv = random.choice(devices)

        alert_type = random.choice(["Drowsiness", "Negligence", "Distraction"])
        if alert_type == "Drowsiness":
            eye_sec = round(random.uniform(2.2, 7.5), 1)
            severity = "High" if eye_sec > 4.5 else ("Medium" if eye_sec >= 3.0 else "Low")
        elif alert_type == "Negligence":
            eye_sec = 0.0
            severity = random.choice(["Medium", "High"])
        else:
            eye_sec = round(random.uniform(1.0, 3.0), 1)
            severity = "Low"

        next_id = get_next_alert_id()

        ok, msg = create_alert(
            alert_id=next_id,
            student_id=st[0],
            session_id=se[0],
            device_id=dv[0],
            alert_type=alert_type,
            severity=severity,
            eye_closure_sec=eye_sec,
            performed_by=performed_by
        )

        sim_detail = f"⚡ Simulated {alert_type} ({severity} Risk, {eye_sec}s eye closure) for {st[1]} via {dv[1]} in Room {dv[2]}."
        return True, sim_detail
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass


# ============================================================================
# NOTIFICATION SERVICE
# ============================================================================

def dispatch_simulated_alert_notification(alert_id: int, student_id: str, alert_type: str, severity: str):
    """Writes simulated notification records into Alert_Notifications."""
    conn, engine = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT email, student_name FROM Student WHERE student_id = ?" if engine == "sqlite" else "SELECT email, student_name FROM Student WHERE student_id = :1", [student_id])
        s_row = cur.fetchone()
        email = s_row[0] if s_row else "student@example.com"
        name = s_row[1] if s_row else "Student"

        msg_body = f"Student Drowsiness Alert System: {alert_type} ({severity} risk) detected during class lecture for {name} ({student_id}). Please consult faculty if rest or assistance is needed."

        if engine == "oracle":
            cur.execute("""
                INSERT INTO Alert_Notifications (notification_id, alert_id, recipient, channel, sent_time, status, message_text)
                VALUES (SEQ_NOTIF_ID.NEXTVAL, :1, :2, 'Email', SYSDATE, 'Simulated', :3)
            """, [int(alert_id), email, msg_body])
        else:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cur.execute("""
                INSERT INTO Alert_Notifications (alert_id, recipient, channel, sent_time, status, message_text)
                VALUES (?, ?, 'Email', ?, 'Simulated', ?)
            """, [int(alert_id), email, now_str, msg_body])

        conn.commit()
    except Exception as e:
        print(f"[Warning] Failed to write notification: {e}")
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass


def fetch_notifications(limit: int = 50):
    """Retrieves notification dispatch history."""
    conn, engine = get_connection()
    cur = conn.cursor()
    try:
        sql = """
            SELECT n.notification_id, n.alert_id, n.recipient, n.channel, n.sent_time, n.status, n.message_text,
                   a.student_id, a.alert_type, a.severity
            FROM Alert_Notifications n
            LEFT JOIN Alert a ON a.alert_id = n.alert_id
            ORDER BY n.notification_id DESC
        """
        if engine == "oracle":
            sql = f"SELECT * FROM ({sql}) WHERE ROWNUM <= {limit}"
        else:
            sql += f" LIMIT {limit}"

        cur.execute(sql)
        rows = cur.fetchall()
        notifs = []
        for r in rows:
            time_val = r[4]
            if hasattr(time_val, "strftime"):
                time_val = time_val.strftime("%Y-%m-%d %H:%M")
            notifs.append({
                "notification_id": r[0],
                "alert_id": r[1],
                "recipient": r[2],
                "channel": r[3],
                "sent_time": str(time_val),
                "status": r[5],
                "message_text": r[6],
                "student_id": r[7] or "N/A",
                "alert_type": r[8] or "Notice",
                "severity": r[9] or "Medium"
            })
        return notifs
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass


# ============================================================================
# STUDENT MANAGEMENT & PROFILES
# ============================================================================

def fetch_students(query=None, section=None, department=None):
    """Fetches list of students with summary statistics."""
    conn, engine = get_connection()
    cur = conn.cursor()
    try:
        sql = """
            SELECT s.student_id, s.student_name, s.class_section, s.email, s.enrollment_year,
                   COALESCE(s.department, 'CSE'),
                   COUNT(a.alert_id) AS alert_count,
                   SUM(CASE WHEN a.severity IN ('High', 'Critical') THEN 1 ELSE 0 END) AS high_count,
                   SUM(CASE WHEN a.status = 'Pending' THEN 1 ELSE 0 END) AS pending_count
            FROM Student s
            LEFT JOIN Alert a ON a.student_id = s.student_id
            WHERE 1=1
        """
        if engine == "oracle":
            sql = sql.replace("COALESCE", "NVL")

        params = []
        if section and section != 'all':
            sql += " AND s.class_section = :1" if engine == "oracle" else " AND s.class_section = ?"
            params.append(section)
        if department and department != 'all':
            param_idx = len(params) + 1
            sql += f" AND s.department = :{param_idx}" if engine == "oracle" else " AND s.department = ?"
            params.append(department)
        if query:
            param_idx = len(params) + 1
            q = f"%{query.lower()}%"
            sql += f" AND (LOWER(s.student_name) LIKE :{param_idx} OR LOWER(s.student_id) LIKE :{param_idx})" if engine == "oracle" else f" AND (LOWER(s.student_name) LIKE ? OR LOWER(s.student_id) LIKE ?)"
            params.append(q)

        sql += " GROUP BY s.student_id, s.student_name, s.class_section, s.email, s.enrollment_year, " + ("NVL(s.department, 'CSE')" if engine == "oracle" else "COALESCE(s.department, 'CSE')")
        sql += " ORDER BY s.student_name ASC"

        cur.execute(sql, params)
        rows = cur.fetchall()
        students = []
        for r in rows:
            tot = r[6] or 0
            high = r[7] or 0
            # Neutral risk badge: Normal (0-1), Moderate Pattern (2-3), Repeated Pattern (4+)
            if tot >= 4 or high >= 2:
                risk_tier = "Repeated Pattern"
                risk_class = "risk-high"
            elif tot >= 2:
                risk_tier = "Moderate Pattern"
                risk_class = "risk-medium"
            else:
                risk_tier = "Stable"
                risk_class = "risk-low"

            students.append({
                "student_id": r[0],
                "student_name": r[1],
                "class_section": r[2],
                "email": r[3],
                "enrollment_year": r[4],
                "department": r[5],
                "total_alerts": tot,
                "high_alerts": high,
                "pending_alerts": r[8] or 0,
                "risk_tier": risk_tier,
                "risk_class": risk_class
            })
        return students
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass


def get_student_profile(student_id: str):
    """Retrieves full student profile, emergency contacts, and complete incident history."""
    conn, engine = get_connection()
    cur = conn.cursor()
    try:
        # 1. Student Basic Info
        cur.execute("SELECT student_id, student_name, class_section, email, enrollment_year, department FROM Student WHERE student_id = ?" if engine == "sqlite" else "SELECT student_id, student_name, class_section, email, enrollment_year, NVL(department, 'CSE') FROM Student WHERE student_id = :1", [student_id])
        st_row = cur.fetchone()
        if not st_row:
            return None

        # 2. Emergency Contact
        cur.execute("SELECT contact_name, relationship, phone_number, email FROM Emergency_Contact WHERE student_id = ?" if engine == "sqlite" else "SELECT contact_name, relationship, phone_number, email FROM Emergency_Contact WHERE student_id = :1", [student_id])
        contact_row = cur.fetchone()
        contact = None
        if contact_row:
            contact = {
                "name": contact_row[0],
                "relationship": contact_row[1],
                "phone": contact_row[2],
                "email": contact_row[3]
            }

        # 3. Student Alert History
        if engine == "oracle":
            alerts_sql = """
                SELECT a.alert_id, sess.subject, d.location, a.alert_type, a.severity, a.status,
                       a.eye_closure_sec, TO_CHAR(a.alert_time, 'YYYY-MM-DD HH24:MI'),
                       a.resolution_notes, a.resolved_by
                FROM Alert a
                LEFT JOIN Sessions sess ON sess.session_id = a.session_id
                LEFT JOIN Device d ON d.device_id = a.device_id
                WHERE a.student_id = :1
                ORDER BY a.alert_id DESC
            """
        else:
            alerts_sql = """
                SELECT a.alert_id, sess.subject, d.location, a.alert_type, a.severity, a.status,
                       a.eye_closure_sec, a.alert_time,
                       a.resolution_notes, a.resolved_by
                FROM Alert a
                LEFT JOIN Sessions sess ON sess.session_id = a.session_id
                LEFT JOIN Device d ON d.device_id = a.device_id
                WHERE a.student_id = ?
                ORDER BY a.alert_id DESC
            """
        cur.execute(alerts_sql, [student_id])
        alert_rows = cur.fetchall()

        history = []
        for r in alert_rows:
            history.append({
                "alert_id": r[0],
                "subject": r[1] or "General",
                "location": r[2] or "PRP353",
                "alert_type": r[3],
                "severity": r[4],
                "status": r[5] or "Pending",
                "eye_closure_sec": float(r[6] or 0.0),
                "alert_time": str(r[7]),
                "notes": r[8] or "",
                "resolved_by": r[9] or ""
            })

        tot = len(history)
        high_cnt = sum(1 for h in history if h["severity"] in ("High", "Critical"))
        pending_cnt = sum(1 for h in history if h["status"] == "Pending")
        avg_eye = round(sum(h["eye_closure_sec"] for h in history) / tot, 1) if tot > 0 else 0.0

        return {
            "student_id": st_row[0],
            "student_name": st_row[1],
            "class_section": st_row[2],
            "email": st_row[3],
            "enrollment_year": st_row[4],
            "department": st_row[5] or "CSE",
            "contact": contact,
            "total_alerts": tot,
            "high_alerts": high_cnt,
            "pending_alerts": pending_cnt,
            "avg_eye_sec": avg_eye,
            "history": history
        }
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass


def create_student(student_id: str, student_name: str, class_section: str,
                   email: str, enrollment_year: int, department: str,
                   contact_name: str = None, contact_phone: str = None,
                   contact_rel: str = None, performed_by: str = "Administrator"):
    """Adds a new student and optional emergency contact."""
    student_id = student_id.strip().upper()
    student_name = student_name.strip()
    class_section = class_section.strip().upper()
    email = email.strip().lower()
    department = department.strip()
    try:
        enrollment_year = int(enrollment_year)
    except (TypeError, ValueError):
        return False, "Enrollment year must be an integer between 2020 and 2030."
    if not all((student_id, student_name, class_section, email, department)):
        return False, "Student ID, name, section, email, and department are required."
    if not 2020 <= enrollment_year <= 2030:
        return False, "Enrollment year must be between 2020 and 2030."
    conn, engine = get_connection()
    cur = conn.cursor()
    try:
        # Check duplicate
        cur.execute("SELECT student_id FROM Student WHERE student_id = ?" if engine == "sqlite" else "SELECT student_id FROM Student WHERE student_id = :1", [student_id])
        if cur.fetchone():
            return False, f"Student ID '{student_id}' already exists."

        if engine == "oracle":
            cur.execute("""
                INSERT INTO Student (student_id, student_name, class_section, email, enrollment_year, department)
                VALUES (:1, :2, :3, :4, :5, :6)
            """, [student_id, student_name.strip(), class_section.strip().upper(), email.strip().lower(), int(enrollment_year), department.strip()])
        else:
            cur.execute("""
                INSERT INTO Student (student_id, student_name, class_section, email, enrollment_year, department)
                VALUES (?, ?, ?, ?, ?, ?)
            """, [student_id, student_name.strip(), class_section.strip().upper(), email.strip().lower(), int(enrollment_year), department.strip()])

        # Emergency contact
        if contact_name and contact_phone:
            if engine == "oracle":
                cur.execute("""
                    INSERT INTO Emergency_Contact (contact_id, student_id, contact_name, relationship, phone_number)
                    VALUES (SEQ_CONTACT_ID.NEXTVAL, :1, :2, :3, :4)
                """, [student_id, contact_name.strip(), contact_rel or 'Parent', contact_phone.strip()])
            else:
                cur.execute("""
                    INSERT INTO Emergency_Contact (student_id, contact_name, relationship, phone_number)
                    VALUES (?, ?, ?, ?)
                """, [student_id, contact_name.strip(), contact_rel or 'Parent', contact_phone.strip()])

        conn.commit()
        log_audit("CREATE", "Student", student_id, performed_by, f"Added student {student_name} ({class_section})")
        return True, f"Student {student_name} ({student_id}) enrolled successfully."
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass


def update_student(student_id: str, student_name: str, class_section: str,
                   email: str, enrollment_year: int, department: str,
                   performed_by: str = "Administrator"):
    """Updates existing student record."""
    conn, engine = get_connection()
    cur = conn.cursor()
    try:
        if engine == "oracle":
            cur.execute("""
                UPDATE Student
                SET student_name = :1, class_section = :2, email = :3, enrollment_year = :4, department = :5
                WHERE student_id = :6
            """, [student_name.strip(), class_section.strip().upper(), email.strip().lower(), int(enrollment_year), department.strip(), student_id])
        else:
            cur.execute("""
                UPDATE Student
                SET student_name = ?, class_section = ?, email = ?, enrollment_year = ?, department = ?
                WHERE student_id = ?
            """, [student_name.strip(), class_section.strip().upper(), email.strip().lower(), int(enrollment_year), department.strip(), student_id])

        conn.commit()
        log_audit("UPDATE", "Student", student_id, performed_by, f"Updated profile for {student_name}")
        return True, f"Student record {student_id} updated."
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass


def delete_student(student_id: str, performed_by: str = "Administrator"):
    """Deletes student and cascaded contacts/alerts."""
    conn, engine = get_connection()
    cur = conn.cursor()
    try:
        if engine == "oracle":
            cur.execute("DELETE FROM Student WHERE student_id = :1", [student_id])
        else:
            cur.execute("DELETE FROM Student WHERE student_id = ?", [student_id])

        conn.commit()
        log_audit("DELETE", "Student", student_id, performed_by, f"Removed student record {student_id}")
        return True, f"Student {student_id} removed."
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass


def import_students_csv(csv_text: str, performed_by: str = "Administrator"):
    """
    Parses and bulk imports students from CSV data.
    Expected headers: student_id, student_name, class_section, email, enrollment_year, department
    """
    reader = csv.DictReader(io.StringIO(csv_text))
    added = 0
    skipped = 0
    errors = []

    for row_idx, row in enumerate(reader, start=2):
        sid = (row.get("student_id") or "").strip().upper()
        sname = (row.get("student_name") or "").strip()
        sec = (row.get("class_section") or "").strip().upper()
        mail = (row.get("email") or "").strip().lower()
        dept = (row.get("department") or "CSE").strip()
        year_str = (row.get("enrollment_year") or "2025").strip()

        if not sid or not sname or not sec:
            errors.append(f"Row {row_idx}: Missing required fields (student_id, student_name, class_section).")
            continue

        try:
            year = int(year_str)
        except ValueError:
            year = 2025

        ok, msg = create_student(
            student_id=sid,
            student_name=sname,
            class_section=sec,
            email=mail or f"{sid.lower()}@example.com",
            enrollment_year=year,
            department=dept,
            performed_by=performed_by
        )
        if ok:
            added += 1
        else:
            skipped += 1
            errors.append(f"Row {row_idx} ({sid}): {msg}")

    return {
        "added": added,
        "skipped": skipped,
        "errors": errors
    }


# ============================================================================
# SESSION MANAGEMENT
# ============================================================================

def fetch_sessions():
    """Fetches academic sessions with associated alert statistics."""
    conn, engine = get_connection()
    cur = conn.cursor()
    try:
        sql = """
            SELECT sess.session_id, sess.session_date, sess.subject, sess.faculty_name,
                   sess.duration_minutes, sess.class_section, sess.proctor_id,
                   COUNT(a.alert_id) AS incident_count,
                   SUM(CASE WHEN a.severity IN ('High', 'Critical') THEN 1 ELSE 0 END) AS high_severity_count
            FROM Sessions sess
            LEFT JOIN Alert a ON a.session_id = sess.session_id
            GROUP BY sess.session_id, sess.session_date, sess.subject, sess.faculty_name,
                     sess.duration_minutes, sess.class_section, sess.proctor_id
            ORDER BY sess.session_id ASC
        """
        cur.execute(sql)
        rows = cur.fetchall()
        sessions = []
        for r in rows:
            date_val = r[1]
            if hasattr(date_val, "strftime"):
                date_val = date_val.strftime("%Y-%m-%d")
            sessions.append({
                "session_id": r[0],
                "session_date": str(date_val),
                "subject": r[2],
                "faculty_name": r[3],
                "duration_minutes": r[4],
                "class_section": r[5],
                "proctor_id": r[6] or "PR-101",
                "incident_count": r[7] or 0,
                "high_count": r[8] or 0
            })
        return sessions
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass


def create_session(session_id: int, session_date: str, subject: str,
                   faculty_name: str, duration_minutes: int, class_section: str,
                   proctor_id: str = None, performed_by: str = "Administrator"):
    """Creates a new academic session."""
    conn, engine = get_connection()
    cur = conn.cursor()
    try:
        if engine == "oracle":
            cur.execute("""
                INSERT INTO Sessions (session_id, session_date, subject, faculty_name, duration_minutes, class_section, proctor_id)
                VALUES (:1, TO_DATE(:2, 'YYYY-MM-DD'), :3, :4, :5, :6, :7)
            """, [int(session_id), session_date, subject.strip(), faculty_name.strip(), int(duration_minutes), class_section.strip().upper(), proctor_id or 'PR-101'])
        else:
            cur.execute("""
                INSERT INTO Sessions (session_id, session_date, subject, faculty_name, duration_minutes, class_section, proctor_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, [int(session_id), session_date, subject.strip(), faculty_name.strip(), int(duration_minutes), class_section.strip().upper(), proctor_id or 'PR-101'])

        conn.commit()
        log_audit("CREATE", "Sessions", str(session_id), performed_by, f"Created session {subject} for {class_section}")
        return True, f"Session #{session_id} ({subject}) scheduled."
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass


def update_session(session_id: int, session_date: str, subject: str,
                   faculty_name: str, duration_minutes: int, class_section: str,
                   performed_by: str = "Administrator"):
    """Updates an existing session."""
    conn, engine = get_connection()
    cur = conn.cursor()
    try:
        if engine == "oracle":
            cur.execute("""
                UPDATE Sessions
                SET session_date = TO_DATE(:1, 'YYYY-MM-DD'),
                    subject = :2,
                    faculty_name = :3,
                    duration_minutes = :4,
                    class_section = :5
                WHERE session_id = :6
            """, [session_date, subject.strip(), faculty_name.strip(), int(duration_minutes), class_section.strip().upper(), int(session_id)])
        else:
            cur.execute("""
                UPDATE Sessions
                SET session_date = ?,
                    subject = ?,
                    faculty_name = ?,
                    duration_minutes = ?,
                    class_section = ?
                WHERE session_id = ?
            """, [session_date, subject.strip(), faculty_name.strip(), int(duration_minutes), class_section.strip().upper(), int(session_id)])

        conn.commit()
        log_audit("UPDATE", "Sessions", str(session_id), performed_by, f"Updated session #{session_id}")
        return True, f"Session #{session_id} updated."
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass


def delete_session(session_id: int, performed_by: str = "Administrator"):
    """Deletes an academic session and associated alerts."""
    conn, engine = get_connection()
    cur = conn.cursor()
    try:
        if engine == "oracle":
            cur.execute("DELETE FROM Sessions WHERE session_id = :1", [int(session_id)])
        else:
            cur.execute("DELETE FROM Sessions WHERE session_id = ?", [int(session_id)])

        conn.commit()
        log_audit("DELETE", "Sessions", str(session_id), performed_by, f"Deleted session #{session_id}")
        return True, f"Session #{session_id} deleted."
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass


# ============================================================================
# DEVICE & CAMERA NODE MANAGEMENT
# ============================================================================

def fetch_devices():
    """Fetches all hardware devices with associated camera nodes and alert counts."""
    conn, engine = get_connection()
    cur = conn.cursor()
    try:
        sql = """
            SELECT d.device_id, d.device_type, d.location, d.install_date, d.status,
                   COALESCE(d.health_score, 98),
                   COUNT(DISTINCT a.alert_id) AS alert_count,
                   COUNT(DISTINCT c.node_id) AS node_count
            FROM Device d
            LEFT JOIN Alert a ON a.device_id = d.device_id
            LEFT JOIN Camera_Nodes c ON c.device_id = d.device_id
            GROUP BY d.device_id, d.device_type, d.location, d.install_date, d.status,
        """
        if engine == "oracle":
            sql = sql.replace("COALESCE", "NVL")
            sql += " NVL(d.health_score, 98)"
        else:
            sql += " COALESCE(d.health_score, 98)"
        sql += " ORDER BY d.device_id ASC"

        cur.execute(sql)
        rows = cur.fetchall()
        devices = []
        for r in rows:
            date_val = r[3]
            if hasattr(date_val, "strftime"):
                date_val = date_val.strftime("%Y-%m-%d")
            devices.append({
                "device_id": r[0],
                "device_type": r[1],
                "location": r[2],
                "install_date": str(date_val),
                "status": r[4] or "Active",
                "health_score": r[5] or 98,
                "alert_count": r[6] or 0,
                "node_count": r[7] or 0
            })
        return devices
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass


def fetch_camera_nodes():
    """Retrieves detailed camera nodes endpoints."""
    conn, engine = get_connection()
    cur = conn.cursor()
    try:
        sql = """
            SELECT c.node_id, c.device_id, d.device_type, d.location,
                   c.ip_address, c.resolution, c.frame_rate, c.firmware_version, c.stream_status
            FROM Camera_Nodes c
            JOIN Device d ON d.device_id = c.device_id
            ORDER BY c.node_id ASC
        """
        cur.execute(sql)
        rows = cur.fetchall()
        nodes = []
        for r in rows:
            nodes.append({
                "node_id": r[0],
                "device_id": r[1],
                "device_type": r[2],
                "location": r[3],
                "ip_address": r[4],
                "resolution": r[5],
                "frame_rate": r[6],
                "firmware_version": r[7],
                "stream_status": r[8]
            })
        return nodes
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass


def create_device(device_id: int, device_type: str, location: str, status: str = "Active",
                  health_score: int = 98, performed_by: str = "Administrator"):
    """Registers a new monitoring sensor device."""
    conn, engine = get_connection()
    cur = conn.cursor()
    try:
        if engine == "oracle":
            cur.execute("""
                INSERT INTO Device (device_id, device_type, location, install_date, status, health_score)
                VALUES (:1, :2, :3, SYSDATE, :4, :5)
            """, [int(device_id), device_type, location.strip(), status, int(health_score)])
        else:
            now_str = datetime.now().strftime("%Y-%m-%d")
            cur.execute("""
                INSERT INTO Device (device_id, device_type, location, install_date, status, health_score)
                VALUES (?, ?, ?, ?, ?, ?)
            """, [int(device_id), device_type, location.strip(), now_str, status, int(health_score)])

        conn.commit()
        log_audit("CREATE", "Device", str(device_id), performed_by, f"Registered {device_type} in {location}")
        return True, f"Device #{device_id} ({device_type}) registered."
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass


def toggle_device_status(device_id: int, performed_by: str = "Administrator"):
    """Toggles device status between Active and Inactive."""
    conn, engine = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT status FROM Device WHERE device_id = ?" if engine == "sqlite" else "SELECT status FROM Device WHERE device_id = :1", [int(device_id)])
        row = cur.fetchone()
        if not row:
            return False, "Device not found."

        current = row[0]
        new_status = "Inactive" if current == "Active" else "Active"

        if engine == "oracle":
            cur.execute("UPDATE Device SET status = :1 WHERE device_id = :2", [new_status, int(device_id)])
        else:
            cur.execute("UPDATE Device SET status = ? WHERE device_id = ?", [new_status, int(device_id)])

        conn.commit()
        log_audit("TOGGLE_STATUS", "Device", str(device_id), performed_by, f"Toggled status to {new_status}")
        return True, f"Device #{device_id} is now {new_status}."
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass


def delete_device(device_id: int, performed_by: str = "Administrator"):
    """Deletes device and associated camera nodes."""
    conn, engine = get_connection()
    cur = conn.cursor()
    try:
        if engine == "oracle":
            cur.execute("DELETE FROM Device WHERE device_id = :1", [int(device_id)])
        else:
            cur.execute("DELETE FROM Device WHERE device_id = ?", [int(device_id)])

        conn.commit()
        log_audit("DELETE", "Device", str(device_id), performed_by, f"Deleted device #{device_id}")
        return True, f"Device #{device_id} deleted."
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass


# ============================================================================
# ANALYTICS & DASHBOARD METRICS
# ============================================================================

def get_dashboard_analytics():
    """Calculates all key statistics and chart datasets strictly from database queries."""
    conn, engine = get_connection()
    cur = conn.cursor()
    try:
        # 1. Total counts
        cur.execute("SELECT COUNT(*) FROM Student")
        total_students = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM Alert")
        total_alerts = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM Alert WHERE severity IN ('High', 'Critical')")
        high_alerts = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM Alert WHERE severity = 'Critical'")
        critical_alerts = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM Alert WHERE severity = 'Medium'")
        med_alerts = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM Alert WHERE severity = 'Low'")
        low_alerts = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM Alert WHERE status = 'Pending'")
        pending_alerts = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM Alert WHERE status = 'Resolved'")
        resolved_alerts = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM Alert WHERE alert_type = 'Drowsiness'")
        drowsiness_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM Alert WHERE alert_type = 'Negligence'")
        negligence_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM Alert WHERE alert_type = 'Distraction'")
        distraction_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM Alert WHERE alert_type = 'Absence'")
        absence_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM Device WHERE status = 'Active'")
        active_devices = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM Device")
        total_devices = cur.fetchone()[0]

        # 2. Daily trend (past 7 calendar days)
        trend_days = []
        trend_counts = []
        trend_highs = []
        base_date = datetime.now()
        for i in range(6, -1, -1):
            d = (base_date - timedelta(days=i)).strftime("%Y-%m-%d")
            trend_days.append((base_date - timedelta(days=i)).strftime("%b %d"))
            if engine == "oracle":
                cur.execute("SELECT COUNT(*), SUM(CASE WHEN severity IN ('High', 'Critical') THEN 1 ELSE 0 END) FROM Alert WHERE TO_CHAR(alert_time, 'YYYY-MM-DD') = :1", [d])
            else:
                cur.execute("SELECT COUNT(*), SUM(CASE WHEN severity IN ('High', 'Critical') THEN 1 ELSE 0 END) FROM Alert WHERE SUBSTR(alert_time, 1, 10) = ?", [d])
            row = cur.fetchone()
            c = row[0] if (row and row[0] is not None) else 0
            h = row[1] if (row and row[1] is not None) else 0
            trend_counts.append(c)
            trend_highs.append(h)

        # 3. Alerts by hour, aggregated from their stored timestamps.
        hour_labels = [f"{hour:02d}:00" for hour in range(9, 17)]
        hour_counts = {hour: 0 for hour in range(9, 17)}
        if engine == "oracle":
            cur.execute("""
                SELECT TO_NUMBER(TO_CHAR(alert_time, 'HH24')), COUNT(*)
                FROM Alert
                GROUP BY TO_NUMBER(TO_CHAR(alert_time, 'HH24'))
            """)
        else:
            cur.execute("""
                SELECT CAST(strftime('%H', alert_time) AS INTEGER), COUNT(*)
                FROM Alert
                GROUP BY strftime('%H', alert_time)
            """)
        for hour, count in cur.fetchall():
            if hour in hour_counts:
                hour_counts[hour] = count
        hour_data = [hour_counts[hour] for hour in range(9, 17)]

        # 4. Students with frequent alerts
        cur.execute("""
            SELECT s.student_id, s.student_name, COUNT(a.alert_id) AS cnt,
                   SUM(CASE WHEN a.severity IN ('High', 'Critical') THEN 1 ELSE 0 END) AS high_cnt
            FROM Student s
            JOIN Alert a ON a.student_id = s.student_id
            GROUP BY s.student_id, s.student_name
            HAVING COUNT(a.alert_id) >= 2
            ORDER BY cnt DESC
        """)
        repeat_rows = cur.fetchall()
        frequent_students = []
        for r in repeat_rows:
            frequent_students.append({
                "student_id": r[0],
                "student_name": r[1],
                "count": r[2],
                "high_count": r[3] or 0
            })

        # 5. Incident Timeline (Top 6 latest incidents for visual interactive timeline)
        alerts_timeline = fetch_alerts(limit=6)

        return {
            "total_students": total_students,
            "total_alerts": total_alerts,
            "high": high_alerts,
            "critical": critical_alerts,
            "medium": med_alerts,
            "low": low_alerts,
            "pending": pending_alerts,
            "resolved": resolved_alerts,
            "drowsiness": drowsiness_count,
            "negligence": negligence_count,
            "distraction": distraction_count,
            "absence": absence_count,
            "active_devices": active_devices,
            "total_devices": total_devices,
            "trend_days": trend_days,
            "trend_counts": trend_counts,
            "trend_highs": trend_highs,
            "hour_labels": hour_labels,
            "hour_data": hour_data,
            "frequent_students": frequent_students,
            "timeline": alerts_timeline
        }
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass


# ============================================================================
# CSV EXPORT SERVICE
# ============================================================================

def export_to_csv(entity: str, filter_status=None, filter_severity=None):
    """Generates formatted CSV string for downloadable reports."""
    output = io.StringIO()
    writer = csv.writer(output)

    if entity == "alerts":
        alerts = fetch_alerts(filter_status=filter_status, filter_severity=filter_severity, limit=1000)
        writer.writerow([
            "Incident_ID", "Student_ID", "Student_Name", "Section", "Department",
            "Subject", "Faculty", "Device_Type", "Room_Location",
            "Classification", "Severity", "Status", "Eye_Closure_Seconds",
            "Detected_Time", "Resolution_Notes", "Resolved_By"
        ])
        for a in alerts:
            writer.writerow([
                a["alert_id"], a["student_id"], a["student_name"], a["section"], a["department"],
                a["subject"], a["faculty"], a["device_type"], a["location"],
                a["alert_type"], a["severity"], a["status"], a["eye_closure_sec"],
                a["alert_time"], a["resolution_notes"], a["resolved_by"]
            ])

    elif entity == "students":
        students = fetch_students()
        writer.writerow(["Student_ID", "Student_Name", "Section", "Department", "Email", "Enrollment_Year", "Total_Incidents", "High_Risk_Incidents", "Status_Tier"])
        for s in students:
            writer.writerow([s["student_id"], s["student_name"], s["class_section"], s["department"], s["email"], s["enrollment_year"], s["total_alerts"], s["high_alerts"], s["risk_tier"]])

    elif entity == "sessions":
        sessions = fetch_sessions()
        writer.writerow(["Session_ID", "Date", "Subject", "Faculty_Name", "Duration_Min", "Section", "Proctor_ID", "Total_Incidents", "High_Severity_Incidents"])
        for sess in sessions:
            writer.writerow([sess["session_id"], sess["session_date"], sess["subject"], sess["faculty_name"], sess["duration_minutes"], sess["class_section"], sess["proctor_id"], sess["incident_count"], sess["high_count"]])

    elif entity == "devices":
        devices = fetch_devices()
        writer.writerow(["Device_ID", "Device_Type", "Location", "Install_Date", "Status", "Health_Score", "Total_Alerts", "Active_Nodes"])
        for d in devices:
            writer.writerow([d["device_id"], d["device_type"], d["location"], d["install_date"], d["status"], d["health_score"], d["alert_count"], d["node_count"]])

    elif entity == "audit":
        logs = fetch_audit_logs(limit=500)
        writer.writerow(["Audit_ID", "Action_Type", "Table_Name", "Record_ID", "Performed_By", "Action_Time", "Details"])
        for l in logs:
            writer.writerow([l["audit_id"], l["action_type"], l["table_name"], l["record_id"], l["performed_by"], l["action_time"], l["details"]])

    return output.getvalue()
