"""
Student Drowsiness Alert System — Authentication & Role-Based Access Control
Manages user sessions, PBKDF2/SHA-256 password hashing, roles (Administrator vs. Faculty),
and lightweight CSRF token validation.
"""

import functools
import os
import secrets
from flask import current_app, session, redirect, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash
from db import get_connection


def hash_password(password: str) -> str:
    """Generates a secure PBKDF2:SHA256 hash."""
    return generate_password_hash(password, method="pbkdf2:sha256")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies plain password against stored hash."""
    return check_password_hash(hashed_password, plain_password)


def authenticate_user(username: str, password: str):
    """
    Validates username and password against Users table.
    Returns user dict on success, None on failure.
    """
    demo_credentials = {("admin", "admin123"), ("faculty", "faculty123")}
    if (
        not current_app.config.get("DEMO_MODE", False)
        and (username.strip().lower(), password) in demo_credentials
    ):
        return None

    conn, engine = get_connection()
    cur = conn.cursor()
    try:
        if engine == "oracle":
            cur.execute("""
                SELECT user_id, username, password_hash, full_name, role, email
                FROM Users
                WHERE LOWER(username) = LOWER(:1)
            """, [username.strip()])
        else:
            cur.execute("""
                SELECT user_id, username, password_hash, full_name, role, email
                FROM Users
                WHERE LOWER(username) = LOWER(?)
            """, [username.strip()])

        row = cur.fetchone()
        if not row:
            return None

        # row indices: 0:id, 1:username, 2:hash, 3:full_name, 4:role, 5:email
        stored_hash = row[2]
        if verify_password(password, stored_hash):
            return {
                "user_id": row[0],
                "username": row[1],
                "full_name": row[3],
                "role": row[4],
                "email": row[5]
            }
        return None
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass


def get_current_user():
    """Returns the currently logged-in user info, or a non-privileged guest."""
    if "user" in session:
        return {**session["user"], "is_authenticated": True}
    return {
        "user_id": None,
        "username": "guest",
        "full_name": "Guest",
        "role": "Guest",
        "email": "",
        "is_authenticated": False
    }


def login_required(view):
    """Decorator to require an active session user."""
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if "user" not in session:
            demo_bypass = (
                current_app.config.get("DEMO_MODE", False)
                and os.environ.get("DEMO_AUTO_LOGIN", "false").lower() in ("true", "1", "yes")
            )
            if demo_bypass:
                session["user"] = {
                    "user_id": 1,
                    "username": "admin",
                    "full_name": "Chief Invigilator (Admin)",
                    "role": "Administrator",
                    "email": "admin@example.com"
                }
            else:
                flash("Please log in to access this page.", "warning")
                return redirect(url_for("login"))
        return view(**kwargs)
    return wrapped_view


def admin_required(view):
    """Decorator to require Administrator role."""
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        user = get_current_user()
        if user.get("role") != "Administrator":
            flash("Administrator privileges required for this action.", "error")
            return redirect(url_for("index"))
        return view(**kwargs)
    return wrapped_view


def generate_csrf_token():
    """Generates or retrieves CSRF token stored in session."""
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(16)
    return session["_csrf_token"]


def validate_csrf_token(token):
    """Validates provided CSRF token against session."""
    stored = session.get("_csrf_token")
    return bool(stored and token and secrets.compare_digest(stored, token))
