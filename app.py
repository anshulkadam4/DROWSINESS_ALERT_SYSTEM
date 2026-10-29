"""
AegisAlert — Students Drowsiness & Negligence Monitoring System
Main Flask Web Application Backend
Academic DBMS Project (DBMS Assessment-4 & Extended ER Architecture)
Author: Anshul Suhas Kadam (25BCE2117)
"""

import os
import secrets
from datetime import datetime
from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, jsonify, session, Response, abort
)

from db import get_connection, diagnose_connection, get_oracle_config, DatabaseError
from auth import (
    authenticate_user, get_current_user, login_required, admin_required,
    generate_csrf_token, validate_csrf_token, hash_password
)
import services

app = Flask(__name__, template_folder="template", static_folder="static")
app.config["DEMO_MODE"] = os.environ.get("DEMO_MODE", "false").lower() in ("true", "1", "yes")
secret_key = os.environ.get("SECRET_KEY")
if not secret_key:
    if not app.config["DEMO_MODE"]:
        raise RuntimeError("Set SECRET_KEY before starting AegisAlert outside DEMO_MODE.")
    secret_key = secrets.token_hex(32)
app.secret_key = secret_key
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=not app.config["DEMO_MODE"],
)


@app.before_request
def protect_state_changing_requests():
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
        if not validate_csrf_token(token):
            abort(400, description="Invalid or missing CSRF token.")


# ============================================================================
# JINJA TEMPLATE FILTERS & CONTEXT PROCESSORS
# ============================================================================

@app.template_filter("avatar_color")
def avatar_color_filter(val):
    """Generates a consistent, attractive HSL color from a string ID."""
    hue = abs(hash(str(val))) % 360
    return f"hsl({hue}, 65%, 48%)"


@app.template_filter("initials")
def initials_filter(val):
    """Extracts first letter or initials."""
    if not val:
        return "AA"
    parts = str(val).split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    return parts[0][:2].upper()


@app.context_processor
def inject_global_data():
    """Injects user, active engine, and CSRF token into all templates."""
    diag = diagnose_connection()
    user = get_current_user()
    db_mode = diag["active_engine"]

    if db_mode == "oracle":
        db_label = f"Oracle DB ({diag['oracle_dsn'].split('/')[-1]})"
    else:
        db_label = "Demo Mode (Local SQLite)"

    return {
        "current_user": user,
        "active_engine": db_mode,
        "db_label": db_label,
        "is_oracle": (db_mode == "oracle"),
        "demo_mode": app.config["DEMO_MODE"],
        "csrf_token": generate_csrf_token(),
        "now_year": datetime.now().year
    }


# ============================================================================
# AUTHENTICATION ROUTES
# ============================================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        user = authenticate_user(username, password)
        if user:
            session.clear()
            session["user"] = user
            services.log_audit("LOGIN", "Users", str(user["user_id"]), user["username"], "User logged in.")
            flash(f"Welcome back, {user['full_name']}!", "success")
            return redirect(url_for("index"))
        else:
            message = "Invalid username or password."
            if app.config["DEMO_MODE"]:
                message += " Demo accounts: admin / admin123 or faculty / faculty123."
            flash(message, "error")

    return render_template("login.html")


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    user = get_current_user()
    services.log_audit("LOGOUT", "Users", str(user.get("user_id", "0")), user.get("username", "Guest"), "User logged out.")
    session.pop("user", None)
    flash("You have been signed out.", "info")
    return redirect(url_for("login"))


@app.route("/switch-role", methods=["POST"])
@login_required
def switch_role():
    """Convenience feature for academic evaluation: quickly toggle between Administrator and Faculty."""
    if not app.config["DEMO_MODE"]:
        abort(404)
    target_role = request.form.get("role")
    if target_role == "Administrator":
        session["user"] = {
            "user_id": 1,
            "username": "admin",
            "full_name": "Chief Invigilator (Admin)",
            "role": "Administrator",
            "email": "admin@example.com"
        }
    elif target_role == "Faculty":
        session["user"] = {
            "user_id": 2,
            "username": "faculty",
            "full_name": "Faculty Demo",
            "role": "Faculty",
            "email": "faculty@example.com"
        }
    else:
        abort(400, description="Role must be Administrator or Faculty.")
    flash(f"Switched role to {target_role} for demonstration.", "info")
    return redirect(request.referrer or url_for("index"))


# ============================================================================
# DASHBOARD
# ============================================================================

@app.route("/")
@login_required
def index():
    try:
        analytics = services.get_dashboard_analytics()
        recent_alerts = services.fetch_alerts(limit=8)
        students = services.fetch_students()
        sessions_list = services.fetch_sessions()
        devices_list = services.fetch_devices()
        next_id = services.get_next_alert_id()

        return render_template(
            "dashboard.html",
            stats=analytics,
            alerts=recent_alerts,
            students=students,
            sessions=sessions_list,
            devices=devices_list,
            next_alert_id=next_id,
            active_tab="dashboard"
        )
    except Exception as e:
        flash(f"Dashboard error: {e}", "error")
        return render_template(
            "dashboard.html",
            stats={
                "total_alerts": 0, "high": 0, "medium": 0, "low": 0,
                "pending": 0, "resolved": 0, "drowsiness": 0, "negligence": 0,
                "distraction": 0, "active_devices": 0, "total_devices": 0,
                "total_students": 0, "trend_days": [], "trend_counts": [],
                "trend_highs": [], "hour_labels": [], "hour_data": [],
                "frequent_students": [], "timeline": []
            },
            alerts=[],
            students=[],
            sessions=[],
            devices=[],
            next_alert_id=101,
            active_tab="dashboard",
            error=str(e)
        )


# ============================================================================
# SMART ALERTS MANAGEMENT
# ============================================================================

@app.route("/alerts")
@login_required
def alerts_list():
    filter_type = request.args.get("type", "all")
    filter_severity = request.args.get("severity", "all")
    filter_status = request.args.get("status", "all")
    query = request.args.get("q", "").strip()

    alerts = services.fetch_alerts(
        filter_type=filter_type,
        filter_severity=filter_severity,
        filter_status=filter_status,
        query=query,
        limit=200
    )
    students = services.fetch_students()
    sessions_list = services.fetch_sessions()
    devices_list = services.fetch_devices()
    next_id = services.get_next_alert_id()

    return render_template(
        "alerts.html",
        alerts=alerts,
        students=students,
        sessions=sessions_list,
        devices=devices_list,
        next_alert_id=next_id,
        current_type=filter_type,
        current_severity=filter_severity,
        current_status=filter_status,
        search_query=query,
        active_tab="alerts"
    )


@app.route("/alerts/create", methods=["POST"])
@app.route("/add", methods=["POST"])  # Preserves legacy route for backward compatibility
@login_required
def create_alert_route():
    try:
        user = get_current_user()
        alert_id = int(request.form["alert_id"])
        student_id = request.form["student_id"].strip()
        session_id = int(request.form["session_id"])
        device_id = int(request.form["device_id"])
        alert_type = request.form["alert_type"].strip()
        severity = request.form["severity"].strip()
        eye_sec = float(request.form.get("eye_closure_sec", 0.0) or 0.0)

        ok, msg = services.create_alert(
            alert_id=alert_id,
            student_id=student_id,
            session_id=session_id,
            device_id=device_id,
            alert_type=alert_type,
            severity=severity,
            eye_closure_sec=eye_sec,
            performed_by=user["full_name"]
        )
        if ok:
            flash(msg, "success")
        else:
            flash(msg, "error")
    except Exception as e:
        flash(f"Failed to record alert: {e}", "error")

    return redirect(request.referrer or url_for("alerts_list"))


@app.route("/alerts/update", methods=["POST"])
@app.route("/update", methods=["POST"])  # Preserves legacy route
@login_required
def update_alert_route():
    try:
        user = get_current_user()
        alert_id = int(request.form["alert_id"])
        student_id = request.form["student_id"].strip()
        session_id = int(request.form["session_id"])
        device_id = int(request.form["device_id"])
        alert_type = request.form["alert_type"].strip()
        severity = request.form["severity"].strip()
        status = request.form.get("status", "Pending")
        eye_sec = float(request.form.get("eye_closure_sec", 0.0) or 0.0)
        notes = request.form.get("resolution_notes", "")

        ok, msg = services.update_alert(
            alert_id=alert_id,
            student_id=student_id,
            session_id=session_id,
            device_id=device_id,
            alert_type=alert_type,
            severity=severity,
            status=status,
            eye_closure_sec=eye_sec,
            notes=notes,
            performed_by=user["full_name"]
        )
        if ok:
            flash(msg, "success")
        else:
            flash(msg, "error")
    except Exception as e:
        flash(f"Update error: {e}", "error")

    return redirect(request.referrer or url_for("alerts_list"))


@app.route("/alerts/acknowledge", methods=["POST"])
@login_required
def acknowledge_alert_route():
    try:
        user = get_current_user()
        alert_id = int(request.form["alert_id"])
        ok, msg = services.acknowledge_alert(alert_id, performed_by=user["full_name"])
        flash(msg, "success" if ok else "error")
    except Exception as e:
        flash(f"Acknowledge failed: {e}", "error")
    return redirect(request.referrer or url_for("alerts_list"))


@app.route("/alerts/resolve", methods=["POST"])
@login_required
def resolve_alert_route():
    try:
        user = get_current_user()
        alert_id = int(request.form["alert_id"])
        notes = request.form.get("resolution_notes", "")
        ok, msg = services.resolve_alert(alert_id, resolution_notes=notes, performed_by=user["full_name"])
        flash(msg, "success" if ok else "error")
    except Exception as e:
        flash(f"Resolution failed: {e}", "error")
    return redirect(request.referrer or url_for("alerts_list"))


@app.route("/alerts/delete", methods=["POST"])
@app.route("/delete", methods=["POST"])  # Preserves legacy route
@admin_required
def delete_alert_route():
    try:
        user = get_current_user()
        alert_id = int(request.form["alert_id"])
        ok, msg = services.delete_alert(alert_id, performed_by=user["full_name"])
        flash(msg, "success" if ok else "error")
    except Exception as e:
        flash(f"Delete failed: {e}", "error")
    return redirect(request.referrer or url_for("alerts_list"))


@app.route("/simulate", methods=["POST"])
@login_required
def simulate_event():
    """Triggers an instantaneous edge-camera detection telemetry event."""
    try:
        user = get_current_user()
        ok, msg = services.simulate_telemetry_event(performed_by=user["full_name"])
        flash(msg, "success" if ok else "error")
    except Exception as e:
        flash(f"Simulation failed: {e}", "error")
    return redirect(request.referrer or url_for("index"))


# ============================================================================
# STUDENT MANAGEMENT
# ============================================================================

@app.route("/students")
@login_required
def students_list():
    query = request.args.get("q", "").strip()
    section = request.args.get("section", "all")
    department = request.args.get("dept", "all")

    students = services.fetch_students(query=query, section=section, department=department)
    return render_template(
        "students.html",
        students=students,
        search_query=query,
        current_section=section,
        current_dept=department,
        active_tab="students"
    )


@app.route("/students/<student_id>")
@login_required
def student_profile(student_id):
    profile = services.get_student_profile(student_id)
    if not profile:
        flash(f"Student '{student_id}' not found.", "error")
        return redirect(url_for("students_list"))

    return render_template("student_profile.html", student=profile, active_tab="students")


@app.route("/students/create", methods=["POST"])
@login_required
def create_student_route():
    try:
        user = get_current_user()
        sid = request.form["student_id"].strip().upper()
        sname = request.form["student_name"].strip()
        sec = request.form["class_section"].strip().upper()
        mail = request.form["email"].strip().lower()
        dept = request.form.get("department", "CSE").strip()
        year = int(request.form.get("enrollment_year", 2025))
        c_name = request.form.get("contact_name")
        c_phone = request.form.get("contact_phone")
        c_rel = request.form.get("contact_rel")

        ok, msg = services.create_student(
            student_id=sid,
            student_name=sname,
            class_section=sec,
            email=mail,
            enrollment_year=year,
            department=dept,
            contact_name=c_name,
            contact_phone=c_phone,
            contact_rel=c_rel,
            performed_by=user["full_name"]
        )
        flash(msg, "success" if ok else "error")
    except Exception as e:
        flash(f"Failed to add student: {e}", "error")
    return redirect(url_for("students_list"))


@app.route("/students/update", methods=["POST"])
@login_required
def update_student_route():
    try:
        user = get_current_user()
        sid = request.form["student_id"].strip().upper()
        sname = request.form["student_name"].strip()
        sec = request.form["class_section"].strip().upper()
        mail = request.form["email"].strip().lower()
        dept = request.form.get("department", "CSE").strip()
        year = int(request.form.get("enrollment_year", 2025))

        ok, msg = services.update_student(
            student_id=sid,
            student_name=sname,
            class_section=sec,
            email=mail,
            enrollment_year=year,
            department=dept,
            performed_by=user["full_name"]
        )
        flash(msg, "success" if ok else "error")
    except Exception as e:
        flash(f"Update failed: {e}", "error")
    return redirect(request.referrer or url_for("students_list"))


@app.route("/students/delete", methods=["POST"])
@admin_required
def delete_student_route():
    try:
        user = get_current_user()
        sid = request.form["student_id"].strip()
        ok, msg = services.delete_student(sid, performed_by=user["full_name"])
        flash(msg, "success" if ok else "error")
    except Exception as e:
        flash(f"Delete failed: {e}", "error")
    return redirect(url_for("students_list"))


@app.route("/students/import-csv", methods=["POST"])
@login_required
def import_students_csv_route():
    try:
        user = get_current_user()
        file = request.files.get("csv_file")
        if not file or not file.filename:
            flash("Please choose a CSV file to upload.", "error")
            return redirect(url_for("students_list"))

        csv_text = file.read().decode("utf-8-sig", errors="replace")
        res = services.import_students_csv(csv_text, performed_by=user["full_name"])

        flash(f"CSV Import Summary: {res['added']} students added, {res['skipped']} skipped.", "success" if res["added"] > 0 else "warning")
        if res["errors"]:
            flash(f"Notices ({len(res['errors'])}): " + " | ".join(res["errors"][:3]), "info")
    except Exception as e:
        flash(f"CSV import error: {e}", "error")
    return redirect(url_for("students_list"))


# ============================================================================
# SESSION MANAGEMENT
# ============================================================================

@app.route("/sessions")
@login_required
def sessions_list():
    sessions = services.fetch_sessions()
    return render_template("sessions.html", sessions=sessions, active_tab="sessions")


@app.route("/sessions/create", methods=["POST"])
@login_required
def create_session_route():
    try:
        user = get_current_user()
        sid = int(request.form["session_id"])
        sdate = request.form["session_date"].strip()
        subj = request.form["subject"].strip()
        fac = request.form["faculty_name"].strip()
        dur = int(request.form["duration_minutes"])
        sec = request.form["class_section"].strip().upper()

        ok, msg = services.create_session(
            session_id=sid,
            session_date=sdate,
            subject=subj,
            faculty_name=fac,
            duration_minutes=dur,
            class_section=sec,
            performed_by=user["full_name"]
        )
        flash(msg, "success" if ok else "error")
    except Exception as e:
        flash(f"Create session error: {e}", "error")
    return redirect(url_for("sessions_list"))


@app.route("/sessions/update", methods=["POST"])
@login_required
def update_session_route():
    try:
        user = get_current_user()
        sid = int(request.form["session_id"])
        sdate = request.form["session_date"].strip()
        subj = request.form["subject"].strip()
        fac = request.form["faculty_name"].strip()
        dur = int(request.form["duration_minutes"])
        sec = request.form["class_section"].strip().upper()

        ok, msg = services.update_session(
            session_id=sid,
            session_date=sdate,
            subject=subj,
            faculty_name=fac,
            duration_minutes=dur,
            class_section=sec,
            performed_by=user["full_name"]
        )
        flash(msg, "success" if ok else "error")
    except Exception as e:
        flash(f"Update session error: {e}", "error")
    return redirect(url_for("sessions_list"))


@app.route("/sessions/delete", methods=["POST"])
@admin_required
def delete_session_route():
    try:
        user = get_current_user()
        sid = int(request.form["session_id"])
        ok, msg = services.delete_session(sid, performed_by=user["full_name"])
        flash(msg, "success" if ok else "error")
    except Exception as e:
        flash(f"Delete session error: {e}", "error")
    return redirect(url_for("sessions_list"))


# ============================================================================
# DEVICE & CAMERA NODES MANAGEMENT
# ============================================================================

@app.route("/devices")
@login_required
def devices_list():
    devices = services.fetch_devices()
    camera_nodes = services.fetch_camera_nodes()
    return render_template("devices.html", devices=devices, camera_nodes=camera_nodes, active_tab="devices")


@app.route("/devices/create", methods=["POST"])
@login_required
def create_device_route():
    try:
        user = get_current_user()
        did = int(request.form["device_id"])
        dtype = request.form["device_type"]
        loc = request.form["location"].strip()
        status = request.form.get("status", "Active")
        health = int(request.form.get("health_score", 98))

        ok, msg = services.create_device(
            device_id=did,
            device_type=dtype,
            location=loc,
            status=status,
            health_score=health,
            performed_by=user["full_name"]
        )
        flash(msg, "success" if ok else "error")
    except Exception as e:
        flash(f"Device registration error: {e}", "error")
    return redirect(url_for("devices_list"))


@app.route("/devices/toggle", methods=["POST"])
@login_required
def toggle_device_route():
    try:
        user = get_current_user()
        did = int(request.form["device_id"])
        ok, msg = services.toggle_device_status(did, performed_by=user["full_name"])
        flash(msg, "info" if ok else "error")
    except Exception as e:
        flash(f"Toggle error: {e}", "error")
    return redirect(url_for("devices_list"))


@app.route("/devices/delete", methods=["POST"])
@admin_required
def delete_device_route():
    try:
        user = get_current_user()
        did = int(request.form["device_id"])
        ok, msg = services.delete_device(did, performed_by=user["full_name"])
        flash(msg, "success" if ok else "error")
    except Exception as e:
        flash(f"Delete device error: {e}", "error")
    return redirect(url_for("devices_list"))


# ============================================================================
# ANALYTICS & REPORTS
# ============================================================================

@app.route("/analytics")
@login_required
def analytics_view():
    analytics = services.get_dashboard_analytics()
    sessions = services.fetch_sessions()
    devices = services.fetch_devices()
    return render_template(
        "analytics.html",
        stats=analytics,
        sessions=sessions,
        devices=devices,
        active_tab="analytics"
    )


@app.route("/reports")
@login_required
def reports_view():
    alerts = services.fetch_alerts(limit=50)
    sessions = services.fetch_sessions()
    devices = services.fetch_devices()
    students = services.fetch_students()
    return render_template(
        "reports.html",
        alerts=alerts,
        sessions=sessions,
        devices=devices,
        students=students,
        active_tab="reports"
    )


@app.route("/export/<entity>")
@login_required
def export_csv(entity):
    """Exports clean CSV report for selected entity."""
    filter_status = request.args.get("status")
    filter_severity = request.args.get("severity")
    csv_data = services.export_to_csv(entity, filter_status=filter_status, filter_severity=filter_severity)
    filename = f"AegisAlert_{entity}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename={filename}"}
    )


# ============================================================================
# NOTIFICATION CENTER & AUDIT TRAIL
# ============================================================================

@app.route("/notifications")
@login_required
def notifications_view():
    notifs = services.fetch_notifications(limit=100)
    return render_template("notifications.html", notifications=notifs, active_tab="notifications")


@app.route("/audit")
@login_required
def audit_view():
    action_filter = request.args.get("action", "all")
    logs = services.fetch_audit_logs(limit=200, action_filter=action_filter)
    return render_template(
        "audit.html",
        logs=logs,
        current_action=action_filter,
        active_tab="audit"
    )


# ============================================================================
# DATABASE DIAGNOSTICS & ENGINE SWITCHER
# ============================================================================

@app.route("/diagnostics")
@login_required
def diagnostics_view():
    diag = diagnose_connection()
    return render_template("diagnostics.html", diag=diag, active_tab="diagnostics")


@app.route("/diagnostics/set-engine", methods=["POST"])
@admin_required
def set_database_engine():
    target_engine = request.form.get("engine", "auto")
    if target_engine not in {"auto", "oracle", "sqlite"}:
        abort(400, description="Engine must be auto, oracle, or sqlite.")
    os.environ["DB_FORCE_ENGINE"] = target_engine
    if target_engine == "oracle":
        os.environ["ORACLE_STRICT_MODE"] = "true"
    else:
        os.environ["ORACLE_STRICT_MODE"] = "false"

    flash(f"Database engine mode switched to '{target_engine}'.", "info")
    return redirect(url_for("diagnostics_view"))


# ============================================================================
# APP ENTRYPOINT
# ============================================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST", "127.0.0.1")
    print(f"🚀 AegisAlert Operations Dashboard online at http://{host}:{port}")
    app.run(host=host, port=port, debug=False)
