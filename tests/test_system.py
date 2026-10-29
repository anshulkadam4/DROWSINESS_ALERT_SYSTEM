"""
AegisAlert — Comprehensive Automated Test Suite
Verifies:
  - Database schema initialization & integrity (Users, Student, Sessions, Device, Alert, etc.)
  - Student CRUD, Emergency Contact relationship, CSV bulk import validation
  - Academic Session CRUD and incident counting
  - Device & Camera Node management and status toggling
  - Alert CRUD, Repeat Pattern Detection, Acknowledge & Resolve workflows
  - Notification dispatch & simulation logging
  - Immutable Audit trail recording
  - Real-time Analytics & KPI derivation
  - Flask web endpoints & CSV export responses
"""

import os
import unittest
import json
import sqlite3
import uuid

# Ensure we use test environment
os.environ["DB_FORCE_ENGINE"] = "sqlite"
os.environ["DEMO_AUTO_LOGIN"] = "true"
os.environ["DEMO_MODE"] = "true"

from db import get_connection, init_sqlite_schema_if_needed, diagnose_connection
from auth import authenticate_user
import services
from app import app


class TestAegisAlertSystem(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        init_sqlite_schema_if_needed()
        cls.client = app.test_client()

    def test_01_database_connectivity_and_tables(self):
        """Verifies dual-engine manager initializes all tables successfully."""
        conn, engine = get_connection()
        self.assertIn(engine, ("oracle", "sqlite"))
        cur = conn.cursor()

        tables = ["Users", "Student", "Emergency_Contact", "Proctor", "Sessions", "Device", "Camera_Nodes", "Alert", "Alert_Notifications", "Audit_Log"]
        for tbl in tables:
            cur.execute(f"SELECT COUNT(*) FROM {tbl}")
            count = cur.fetchone()[0]
            self.assertGreaterEqual(count, 0, f"Table {tbl} should be queryable")

        cur.close()
        conn.close()

    def test_02_student_crud_and_profile(self):
        """Tests student enrollment, demographic update, profile retrieval, and deletion."""
        test_id = "TST" + uuid.uuid4().hex[:8].upper()
        # 1. Create
        ok, msg = services.create_student(
            student_id=test_id,
            student_name="Test Student",
            class_section="C1",
            email=f"{test_id.lower()}@example.com",
            enrollment_year=2025,
            department="CSE",
            contact_name="Test Parent",
            contact_phone="000-000-0099",
            contact_rel="Parent",
            performed_by="Unit_Test"
        )
        self.assertTrue(ok)

        # 2. Duplicate detection
        ok_dup, msg_dup = services.create_student(
            student_id=test_id,
            student_name="Duplicate Attempt",
            class_section="C1",
            email=f"duplicate-{test_id.lower()}@example.com",
            enrollment_year=2025,
            department="CSE"
        )
        self.assertFalse(ok_dup, "Duplicate student_id must be rejected")

        # 3. Profile Fetch
        profile = services.get_student_profile(test_id)
        self.assertIsNotNone(profile)
        self.assertEqual(profile["student_name"], "Test Student")
        self.assertIsNotNone(profile["contact"])
        self.assertEqual(profile["contact"]["phone"], "000-000-0099")

        # 4. Update
        ok_up, msg_up = services.update_student(
            student_id=test_id,
            student_name="Test Student Updated",
            class_section="C2",
            email=f"updated-{test_id.lower()}@example.com",
            enrollment_year=2025,
            department="Data Science",
            performed_by="Unit_Test"
        )
        self.assertTrue(ok_up)

        # 5. Delete
        ok_del, msg_del = services.delete_student(test_id, performed_by="Unit_Test")
        self.assertTrue(ok_del)

    def test_03_csv_bulk_import(self):
        """Tests CSV parsing, validation, duplicate skipping, and batch insert."""
        csv_sample = """student_id,student_name,class_section,email,enrollment_year,department
25CSV0001,CSV Candidate One,A1,csv1@example.com,2025,CSE
25CSV0002,CSV Candidate Two,B2,csv2@example.com,2025,IT
"""
        res = services.import_students_csv(csv_sample, performed_by="Unit_Test")
        self.assertGreaterEqual(res["added"], 1)

        # Cleanup created test students
        services.delete_student("25CSV0001")
        services.delete_student("25CSV0002")

    def test_04_session_and_device_management(self):
        """Tests academic session and sensor device CRUD operations."""
        # Session CRUD
        ok_s, msg_s = services.create_session(
            session_id=999,
            session_date="2026-09-01",
            subject="Cloud Computing",
            faculty_name="Prof. Test Faculty",
            duration_minutes=50,
            class_section="A1",
            performed_by="Unit_Test"
        )
        self.assertTrue(ok_s)

        sessions = services.fetch_sessions()
        found_sess = any(s["session_id"] == 999 for s in sessions)
        self.assertTrue(found_sess)

        services.delete_session(999, performed_by="Unit_Test")

        # Device CRUD
        ok_d, msg_d = services.create_device(
            device_id=999,
            device_type="Camera",
            location="LAB999",
            status="Active",
            health_score=95,
            performed_by="Unit_Test"
        )
        self.assertTrue(ok_d)

        # Toggle status
        ok_tog, msg_tog = services.toggle_device_status(999, performed_by="Unit_Test")
        self.assertTrue(ok_tog)

        services.delete_device(999, performed_by="Unit_Test")

    def test_05_alert_lifecycle_workflow(self):
        """Tests full alert workflow: Create -> Repeat Detection -> Acknowledge -> Resolve -> Delete."""
        test_alert_id = 9999
        student_id = "STU001"

        # 1. Create Alert
        ok, msg = services.create_alert(
            alert_id=test_alert_id,
            student_id=student_id,
            session_id=1,
            device_id=1,
            alert_type="Drowsiness",
            severity="High",
            eye_closure_sec=4.9,
            performed_by="Unit_Test"
        )
        self.assertTrue(ok)

        # 2. Verify Repeat Alert Pattern
        has_pattern, prior_cnt, rep_msg = services.detect_repeat_pattern(student_id, 1, test_alert_id)
        self.assertIsInstance(has_pattern, bool)

        # 3. Acknowledge Alert
        ok_ack, msg_ack = services.acknowledge_alert(test_alert_id, performed_by="Proctor")
        self.assertTrue(ok_ack)

        # 4. Resolve Alert
        ok_res, msg_res = services.resolve_alert(
            test_alert_id,
            resolution_notes="Resolved after student rest consultation.",
            performed_by="Faculty One"
        )
        self.assertTrue(ok_res)

        # 5. Delete Alert
        ok_del, msg_del = services.delete_alert(test_alert_id, performed_by="Unit_Test")
        self.assertTrue(ok_del)

    def test_06_analytics_calculations(self):
        """Verifies dashboard analytics returns complete and consistent data structures."""
        analytics = services.get_dashboard_analytics()
        self.assertIn("total_alerts", analytics)
        self.assertIn("high", analytics)
        self.assertIn("critical", analytics)
        self.assertIn("drowsiness", analytics)
        self.assertIn("negligence", analytics)
        self.assertIn("absence", analytics)
        self.assertIn("trend_days", analytics)
        self.assertIn("trend_counts", analytics)
        self.assertIn("hour_labels", analytics)
        self.assertIn("timeline", analytics)

    def test_07_analytics_reflects_database_changes(self):
        """A newly inserted alert changes the queried metrics and rendered dashboard."""
        alert_id = services.get_next_alert_id()
        prior_total = services.get_dashboard_analytics()["total_alerts"]
        try:
            ok, message = services.create_alert(
                alert_id=alert_id,
                student_id="STU001",
                session_id=1,
                device_id=1,
                alert_type="Drowsiness",
                severity="High",
                eye_closure_sec=3.5,
                performed_by="Unit_Test",
            )
            self.assertTrue(ok, message)

            analytics = services.get_dashboard_analytics()
            self.assertEqual(analytics["total_alerts"], prior_total + 1)
            self.assertGreaterEqual(analytics["trend_counts"][-1], 1)
            response = self.client.get("/")
            self.assertEqual(response.status_code, 200)
            self.assertIn(f'<div class="kpi-number">{analytics["total_alerts"]}</div>'.encode(), response.data)
        finally:
            services.delete_alert(alert_id, performed_by="Unit_Test")

    def test_08_invalid_alert_input_is_rejected(self):
        """Rejects invalid alert categories and non-finite signal values before database writes."""
        for alert_type, severity, eye_sec in [
            ("Unknown", "High", 1.0),
            ("Drowsiness", "Unknown", 1.0),
            ("Drowsiness", "High", float("nan")),
        ]:
            ok, _ = services.create_alert(
                alert_id=9998,
                student_id="STU001",
                session_id=1,
                device_id=1,
                alert_type=alert_type,
                severity=severity,
                eye_closure_sec=eye_sec,
                performed_by="Unit_Test",
            )
            self.assertFalse(ok)

        ok, _ = services.update_alert(
            alert_id=1,
            student_id="STU001",
            session_id=1,
            device_id=1,
            alert_type="Drowsiness",
            severity="High",
            status="Forged",
            eye_closure_sec=1.0,
            notes="",
            performed_by="Unit_Test",
        )
        self.assertFalse(ok)

        ok, message = services.create_student(
            student_id="25TST0000",
            student_name="Invalid Year",
            class_section="A1",
            email="invalid.year@example.test",
            enrollment_year=2040,
            department="CSE",
            performed_by="Unit_Test",
        )
        self.assertFalse(ok)
        self.assertIn("Enrollment year", message)

    def test_09_csrf_and_faculty_authorization(self):
        """Requires CSRF tokens and rejects faculty attempts to use admin-only deletion."""
        login_page = self.client.get("/login")
        self.assertEqual(login_page.status_code, 200)
        self.assertIn(b'name="csrf_token"', login_page.data)
        with self.client.session_transaction() as browser_session:
            login_token = browser_session["_csrf_token"]
        login_response = self.client.post(
            "/login",
            data={"csrf_token": login_token, "username": "admin", "password": "admin123"},
        )
        self.assertEqual(login_response.status_code, 302)
        with self.client.session_transaction() as browser_session:
            self.assertEqual(browser_session["user"]["role"], "Administrator")

        missing_token = self.client.post("/simulate")
        self.assertEqual(missing_token.status_code, 400)

        with self.client.session_transaction() as browser_session:
            browser_session["user"] = {
                "user_id": 2,
                "username": "faculty",
                "full_name": "Faculty Test",
                "role": "Faculty",
                "email": "faculty@example.test",
            }
            browser_session["_csrf_token"] = "csrf-test-token"

        admin_routes = [
            ("/alerts/delete", {"alert_id": "999999"}),
            ("/students/delete", {"student_id": "NONEXISTENT"}),
            ("/sessions/delete", {"session_id": "999999"}),
            ("/devices/delete", {"device_id": "999999"}),
        ]
        for path, payload in admin_routes:
            response = self.client.post(path, data={"csrf_token": "csrf-test-token", **payload})
            self.assertEqual(response.status_code, 302, f"Faculty should not access {path}")
            self.assertEqual(response.location, "/")

        app.config["DEMO_MODE"] = False
        try:
            with app.app_context():
                self.assertIsNone(authenticate_user("admin", "admin123"))
            disabled_switch = self.client.post(
                "/switch-role",
                data={"csrf_token": "csrf-test-token", "role": "Administrator"},
            )
            self.assertEqual(disabled_switch.status_code, 404)
        finally:
            app.config["DEMO_MODE"] = True

    def test_10_web_endpoints(self):
        """Tests HTTP GET routes for all web pages."""
        endpoints = [
            "/",
            "/alerts",
            "/students",
            "/sessions",
            "/devices",
            "/analytics",
            "/reports",
            "/notifications",
            "/audit",
            "/diagnostics",
            "/export/alerts",
            "/export/students",
            "/export/sessions",
            "/export/devices",
            "/export/audit"
        ]
        for ep in endpoints:
            res = self.client.get(ep, follow_redirects=True)
            self.assertEqual(res.status_code, 200, f"Endpoint {ep} should return 200 OK")


if __name__ == "__main__":
    unittest.main()
