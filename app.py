import logging
import os
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort, current_app
from werkzeug.security import generate_password_hash, check_password_hash
import logging
import os
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort, current_app
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from config import Config
from database.db import get_db, close_db, init_db
from ai.priority_prediction import predict_priority
from ai.duplicate_detection import find_duplicate
from utils.image_processing import allowed_file, validate_image_exif
from notifications.notification_service import notify_new_grievance, notify_status_change

class StaticRequestLogFilter(logging.Filter):
    """Keep browser asset-cache requests out of the development console."""

    def filter(self, record):
        return "/static/" not in record.getMessage()


DEPARTMENTS = ["Public Works", "Municipal", "Water Supply", "Electricity", "Drainage"]
STAFF_ACCOUNTS = [
    ("Staff 1", "staff1@gmail.com", "staff1", "+91 90000 00001"),
    ("Staff 2", "staff2@gmail.com", "staff2", "+91 90000 00002"),
    ("Staff 3", "staff3@gmail.com", "staff3", "+91 90000 00003"),
    ("Staff 4", "staff4@gmail.com", "staff4", "+91 90000 00004"),
    ("Staff 5", "staff5@gmail.com", "staff5", "+91 90000 00005"),
]
DEPARTMENT_STAFF_MAP = {
    "Public Works": "staff1@gmail.com",
    "Municipal": "staff2@gmail.com",
    "Water Supply": "staff3@gmail.com",
    "Electricity": "staff4@gmail.com",
    "Drainage": "staff5@gmail.com",
}
CATEGORY_DEPARTMENT = {
    "Roads & Streetlights": "Public Works",
    "Waste & Sanitation": "Municipal",
    "Water Supply": "Water Supply",
    "Electricity": "Electricity",
    "Drainage & Sewage": "Drainage",
}


def create_app():
    app = Flask(__name__)
    logging.getLogger("werkzeug").addFilter(StaticRequestLogFilter())
    app.config.from_object(Config)
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db()
        bootstrap_admin()
        bootstrap_staff()

    @app.context_processor
    def inject_user():
        user = current_user()
        return dict(
            current_user=user,
            unread_notifications_count=unread_notification_count(user) if user else 0,
        )

    @app.route("/")
    def index():
        # Show the rich public home page
        return render_template("index.html")

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            name = request.form["name"].strip()
            email = request.form["email"].lower().strip()
            password = request.form["password"]
            if not name or not email or len(password) < 6:
                flash("Enter your name, email, and a password of at least 6 characters.", "error")
            else:
                try:
                    db = get_db()
                    with db.cursor() as cur:
                        cur.execute(
                            "INSERT INTO users(name,email,phone,password_hash) VALUES(%s,%s,%s,%s)",
                            (name, email, request.form.get("phone"), generate_password_hash(password)),
                        )
                    db.commit()
                    flash("Account created. Please sign in.", "success")
                    return redirect(url_for("login"))
                except Exception:
                    flash("This email is already registered.", "error")
        return render_template("register.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            email = request.form.get("email", "").lower().strip()
            password = request.form.get("password", "")
            db = get_db()
            with db.cursor() as cur:
                cur.execute("SELECT * FROM users WHERE email=%s", (email,))
                user = cur.fetchone()
            if user and check_password_hash(user["password_hash"], password):
                session.clear()
                session["user_id"] = user["id"]
                flash(f"Welcome back, {user['name']}!", "success")
                return redirect(dashboard_url(user))
            flash("Incorrect email or password.", "error")
        return render_template("login.html")

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("index"))

    # ── Citizen ─────────────────────────────────────────────────────────────
    @app.route("/citizen/dashboard")
    @role_required("citizen")
    def citizen_dashboard():
        db = get_db()
        with db.cursor() as cur:
            cur.execute("SELECT * FROM complaints WHERE citizen_id=%s ORDER BY created_at DESC", (session["user_id"],))
            rows = cur.fetchall()
        return render_template("citizen/dashboard.html", complaints=rows, stats=status_stats(rows))

    @app.route("/citizen/complaints/new", methods=["GET", "POST"])
    @role_required("citizen")
    def new_complaint():
        if request.method == "POST":
            title = request.form["title"].strip()
            description = request.form["description"].strip()
            category = request.form["category"]

            if not title or not description or category not in CATEGORY_DEPARTMENT:
                flash("Complete the required complaint details.", "error")
                return render_template("citizen/register_complaint.html")

            # ── Image / EXIF validation (STRICT) ────────────────────────
            # Image MUST contain BOTH GPS location AND date/time in EXIF.
            # Photos without these are rejected — no exceptions.
            image = request.files.get("image")
            image_path = None
            lat = to_float(request.form.get("latitude"))
            lng = to_float(request.form.get("longitude"))

            if image and image.filename:
                if not allowed_file(image.filename):
                    flash("Only JPG/JPEG photos are accepted. PNG and WEBP are not supported.", "error")
                    return render_template("citizen/register_complaint.html")

                # Strict EXIF check: must have GPS + Date
                valid, reason, exif_lat, exif_lng = validate_image_exif(image)
                if not valid:
                    flash(f"Photo rejected: {reason}", "error")
                    return render_template("citizen/register_complaint.html")

                # Use EXIF GPS if user hasn't manually entered coordinates
                if lat is None or lng is None:
                    lat, lng = exif_lat, exif_lng

                filename = f"{uuid4().hex}_{secure_filename(image.filename)}"
                image.save(Path(app.config["UPLOAD_FOLDER"]) / filename)
                image_path = f"uploads/complaints/{filename}"


            # ── AI prediction + duplicate check ──────────────────────────
            db = get_db()
            with db.cursor() as cur:
                cur.execute("SELECT * FROM complaints WHERE status != 'Resolved'")
                existing = cur.fetchall()
            priority = predict_priority(description, category)
            department = CATEGORY_DEPARTMENT[category]
            # Duplicates are only meaningful within the department that owns
            # the issue. This gives the admin view a reliable duplicate link.
            duplicate = find_duplicate(description, lat, lng, existing, department)

            with db.cursor() as cur:
                assigned_officer = next_staff_for_department(department)
                cur.execute(
                    "INSERT INTO complaints"
                    "(reference,citizen_id,title,description,category,department,priority,"
                    "address,latitude,longitude,image_path,duplicate_of,assigned_officer_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        "PENDING", session["user_id"], title, description, category,
                        department, priority, request.form.get("address"), lat, lng,
                        image_path, duplicate, assigned_officer["id"],
                    ),
                )
                complaint_id = cur.lastrowid
            reference = f"SGRS-{complaint_id:06d}"
            with db.cursor() as cur:
                cur.execute("UPDATE complaints SET reference=%s WHERE id=%s", (reference, complaint_id))
                cur.execute(
                    "INSERT INTO complaint_updates(complaint_id,message,status) VALUES(%s,%s,%s)",
                    (complaint_id, f"Complaint registered and assigned to {assigned_officer['name']}.", "Submitted"),
                )
                staff_phone = assigned_officer.get("phone") or "Not provided"
                cur.execute(
                    "INSERT INTO user_notifications(user_id,complaint_id,title,message) VALUES(%s,%s,%s,%s)",
                    (
                        session["user_id"],
                        complaint_id,
                        "Staff member assigned",
                        f"{reference} has been assigned to {assigned_officer['name']}. "
                        f"Staff mobile: {staff_phone}.",
                    ),
                )
            db.commit()

            # ── Immediate WhatsApp notification ──────────────────────────
            try:
                print(f"[WHATSAPP] Triggering new-complaint alert for {reference}")
                notify_new_grievance({
                    "reference": reference,
                    "title": title,
                    "category": category,
                    "department": department,
                    "priority": priority,
                    "description": description,
                })
            except Exception as exc:
                current_app.logger.error("WhatsApp notification failed: %s", exc)
                print(f"[WHATSAPP] ERROR in notify_new_grievance: {exc}")
                import traceback; traceback.print_exc()

            flash(f"Complaint {reference} registered successfully.", "success")
            return redirect(url_for("complaint_status", complaint_id=complaint_id))

        return render_template("citizen/register_complaint.html")

    @app.route("/citizen/complaints")
    @role_required("citizen")
    def complaint_history():
        db = get_db()
        with db.cursor() as cur:
            cur.execute("SELECT * FROM complaints WHERE citizen_id=%s ORDER BY created_at DESC", (session["user_id"],))
            rows = cur.fetchall()
        return render_template("citizen/complaint_history.html", complaints=rows)

    @app.route("/citizen/notifications")
    @role_required("citizen")
    def citizen_notifications():
        db = get_db()
        with db.cursor() as cur:
            cur.execute("SELECT * FROM user_notifications WHERE user_id=%s ORDER BY created_at DESC", (session["user_id"],))
            notifications = cur.fetchall()
            cur.execute("UPDATE user_notifications SET is_read=1 WHERE user_id=%s AND is_read=0", (session["user_id"],))
        db.commit()
        return render_template("citizen/notifications.html", notifications=notifications)

    @app.route("/complaint/<int:complaint_id>")
    @login_required
    def complaint_status(complaint_id):
        db = get_db()
        with db.cursor() as cur:
            cur.execute("SELECT c.*,u.name citizen_name FROM complaints c JOIN users u ON c.citizen_id=u.id WHERE c.id=%s", (complaint_id,))
            c = cur.fetchone()
        if not c:
            abort(404)
        user = current_user()
        if user["role"] == "citizen" and c["citizen_id"] != user["id"]:
            abort(403)
        with db.cursor() as cur:
            cur.execute("SELECT * FROM complaint_updates WHERE complaint_id=%s ORDER BY created_at DESC", (complaint_id,))
            updates = cur.fetchall()
        return render_template("citizen/complaint_status.html", complaint=c, updates=updates)

    @app.route("/citizen/notifications/preference", methods=["POST"])
    @role_required("citizen")
    def notification_preference():
        data = request.get_json(silent=True) or {}
        enabled = 1 if data.get("enabled") is True else 0
        db = get_db()
        with db.cursor() as cur:
            cur.execute(
                "UPDATE users SET status_notifications_enabled=%s WHERE id=%s",
                (enabled, session["user_id"]),
            )
        db.commit()
        return {"enabled": bool(enabled)}

    @app.route("/citizen/profile", methods=["GET", "POST"])
    @role_required("citizen")
    def profile():
        user = current_user()
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            phone = request.form.get("phone", "").strip()
            notifications_enabled = 1 if request.form.get("status_notifications_enabled") == "1" else 0
            current_password = request.form.get("current_password", "")
            new_password = request.form.get("new_password", "")

            db = get_db()

            if new_password:
                if not current_password or not check_password_hash(user["password_hash"], current_password):
                    flash("Current password is required and must be correct to set a new password.", "error")
                    return redirect(url_for("profile"))
                if len(new_password) < 6:
                    flash("New password must be at least 6 characters long.", "error")
                    return redirect(url_for("profile"))

                with db.cursor() as cur:
                    cur.execute(
                        "UPDATE users SET name=%s, phone=%s, status_notifications_enabled=%s, password_hash=%s WHERE id=%s",
                        (name, phone, notifications_enabled, generate_password_hash(new_password), user["id"]),
                    )
                db.commit()
                flash("Profile and password updated successfully.", "success")
            else:
                with db.cursor() as cur:
                    cur.execute(
                        "UPDATE users SET name=%s, phone=%s, status_notifications_enabled=%s WHERE id=%s",
                        (name, phone, notifications_enabled, user["id"]),
                    )
                db.commit()
                flash("Profile updated successfully.", "success")

            return redirect(url_for("profile"))
        return render_template("citizen/profile.html", user=user)

    # ── Admin ────────────────────────────────────────────────────────────────
    @app.route("/admin/dashboard")
    @role_required("admin")
    def admin_dashboard():
        return render_template("admin/dashboard.html", stats=global_stats(), complaints=recent_complaints(), department_data=department_stats())

    @app.route("/admin/complaints")
    @role_required("admin")
    def admin_complaints():
        return render_template("admin/complaints.html", complaints=admin_complaints_grouped())

    @app.route("/admin/departments")
    @role_required("admin")
    def admin_departments():
        return render_template("admin/departments.html", department_data=department_stats())

    @app.route("/admin/officers")
    @role_required("admin")
    def admin_officers():
        db = get_db()
        with db.cursor() as cur:
            cur.execute(
                "SELECT u.id, u.name, u.email, u.phone, u.department, u.created_at, "
                "COUNT(c.id) AS pending_complaints "
                "FROM users u "
                "LEFT JOIN complaints c ON c.assigned_officer_id=u.id "
                "AND c.status NOT IN ('Resolved', 'Closed') "
                "WHERE u.role='officer' "
                "GROUP BY u.id, u.name, u.email, u.phone, u.department, u.created_at "
                "ORDER BY u.name"
            )
            officers = cur.fetchall()
        return render_template("admin/officers.html", users=officers)

    @app.route("/admin/citizens")
    @role_required("admin")
    def admin_citizens():
        db = get_db()
        with db.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE role='citizen'")
            citizens = cur.fetchall()
        return render_template("admin/citizens.html", users=citizens)

    @app.route("/admin/reports")
    @role_required("admin")
    def admin_reports():
        return render_template(
            "admin/reports.html",
            department_data=department_stats(),
            stats=global_stats(),
        )

    # ── Department / Officer ─────────────────────────────────────────────────
    @app.route("/department/<department>")
    @role_required("officer")
    def department_dashboard(department):
        name = normalize_department(department)
        db = get_db()
        user = current_user()
        with db.cursor() as cur:
            if user["role"] == "officer":
                cur.execute("UPDATE complaints SET is_read=1 WHERE assigned_officer_id=%s AND is_read=0", (user["id"],))
                cur.execute("SELECT * FROM complaints WHERE assigned_officer_id=%s ORDER BY created_at DESC", (user["id"],))
                name = "My assigned complaints"
            else:
                cur.execute("UPDATE complaints SET is_read=1 WHERE department=%s AND is_read=0", (name,))
                cur.execute("SELECT * FROM complaints WHERE department=%s ORDER BY created_at DESC", (name,))
            rows = cur.fetchall()
        db.commit()
        return render_template("departments/dashboard.html", department=name, complaints=rows, stats=status_stats(rows))

    @app.route("/department/<department>/complaint/<int:complaint_id>", methods=["GET", "POST"])
    @role_required("officer")
    def update_complaint(department, complaint_id):
        name = normalize_department(department)
        db = get_db()
        user = current_user()
        with db.cursor() as cur:
            cur.execute(
                "SELECT * FROM complaints WHERE id=%s AND department=%s AND assigned_officer_id=%s",
                (complaint_id, name, user["id"]),
            )
            c = cur.fetchone()
            if not c:
                cur.execute("SELECT * FROM complaints WHERE id=%s", (complaint_id,))
                c = cur.fetchone()
        if not c:
            abort(404)

        with db.cursor() as cur:
            cur.execute("SELECT * FROM complaint_updates WHERE complaint_id=%s ORDER BY created_at DESC", (complaint_id,))
            updates = cur.fetchall()

        if request.method == "POST":
            status = request.form.get("status", "").strip()
            if status not in {"Acknowledged", "In Progress", "Resolved"}:
                abort(400)
            officer_message = request.form.get("message", "").strip()
            message = officer_message or f"Status updated to {status}."

            update_image_path = None
            image = request.files.get("image")
            if image and image.filename:
                if allowed_file(image.filename):
                    filename = f"resolution_{uuid4().hex}_{secure_filename(image.filename)}"
                    image.save(Path(app.config["UPLOAD_FOLDER"]) / filename)
                    update_image_path = f"uploads/complaints/{filename}"

            with db.cursor() as cur:
                cur.execute(
                    "UPDATE complaints SET status=%s, updated_at=CURRENT_TIMESTAMP WHERE id=%s",
                    (status, complaint_id),
                )
                cur.execute(
                    "INSERT INTO complaint_updates(complaint_id,message,status,image_path) VALUES(%s,%s,%s,%s)",
                    (complaint_id, message, status, update_image_path),
                )
            db.commit()

            # ── Notify citizen via WhatsApp + e-mail ─────────────────────
            citizen = None
            try:
                with db.cursor() as cur:
                    cur.execute("SELECT id, name, email, phone, status_notifications_enabled FROM users WHERE id=%s", (c["citizen_id"],))
                    citizen = cur.fetchone()
                if citizen and citizen.get("status_notifications_enabled"):
                    notification_title = f"Complaint {status}"
                    notification_message = f"{c['reference']}: {c['title']} is now {status}."
                    if officer_message:
                        notification_message += f" {officer_message}"
                    with db.cursor() as cur:
                        cur.execute("INSERT INTO user_notifications(user_id, complaint_id, title, message) VALUES(%s,%s,%s,%s)", (citizen["id"], complaint_id, notification_title, notification_message))
                    db.commit()
                    notify_status_change(
                        dict(citizen),
                        {"reference": c["reference"], "title": c["title"], "department": c["department"]},
                        status,
                        message,
                    )
            except Exception as exc:
                current_app.logger.error("Status-change notification failed: %s", exc)

            if citizen and citizen.get("status_notifications_enabled"):
                flash(f"Complaint updated to '{status}' and citizen notified.", "success")
            else:
                flash(f"Complaint updated to '{status}'.", "success")
            return redirect(url_for("department_dashboard", department=department))
        return render_template("departments/update_status.html", complaint=c, updates=updates, department=name)

    @app.route("/.well-known/appspecific/com.chrome.devtools.json")
    def chrome_devtools_config():
        """Silence Chrome DevTools'' optional configuration probe."""
        return "", 204

    return app


# ── Helpers ──────────────────────────────────────────────────────────────────
def current_user():
    if "user_id" not in session:
        return None
    db = get_db()
    with db.cursor() as cur:
        cur.execute("SELECT * FROM users WHERE id=%s", (session["user_id"],))
        return cur.fetchone()


def unread_notification_count(user):
    """Return the signed-in citizen's unread website notification count."""
    if not user or user.get("role") != "citizen":
        return 0
    try:
        db = get_db()
        with db.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS count FROM user_notifications WHERE user_id=%s AND is_read=0", (user["id"],))
            return cur.fetchone()["count"]
    except Exception:
        return 0


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            flash("Please sign in to continue.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            u = current_user()
            if not u:
                return redirect(url_for("login"))
            if u["role"] not in roles:
                abort(403)
            return redirect(url_for("department_dashboard", department=department))
        return render_template("departments/update_status.html", complaint=c, updates=updates, department=name)

    @app.route("/.well-known/appspecific/com.chrome.devtools.json")
    def chrome_devtools_config():
        """Silence Chrome DevTools'' optional configuration probe."""
        return "", 204

    return app


# ── Helpers ──────────────────────────────────────────────────────────────────
def current_user():
    if "user_id" not in session:
        return None
    db = get_db()
    with db.cursor() as cur:
        cur.execute("SELECT * FROM users WHERE id=%s", (session["user_id"],))
        return cur.fetchone()


def unread_notification_count(user):
    """Return the signed-in citizen's unread website notification count."""
    if not user or user.get("role") != "citizen":
        return 0
    try:
        db = get_db()
        with db.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS count FROM user_notifications WHERE user_id=%s AND is_read=0", (user["id"],))
            return cur.fetchone()["count"]
    except Exception:
        return 0


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            flash("Please sign in to continue.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            u = current_user()
            if not u:
                return redirect(url_for("login"))
            if u["role"] not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def dashboard_url(user):
    if user["role"] == "citizen":
        return url_for("citizen_dashboard")
    if user["role"] == "admin":
        return url_for("admin_dashboard")
    dept = user.get("department") or "Public Works"
    dept_slug = dept.lower().replace(" ", "-")
    return url_for("department_dashboard", department=dept_slug)


def normalize_department(value):
    value = value.replace("-", " ").title()
    if value not in DEPARTMENTS:
        abort(404)
    return value


def to_float(value):
    try:
        return float(value) if value else None
    except ValueError:
        return None


def status_stats(rows):
    return {
        "total": len(rows),
        "open": sum(r["status"] not in ("Resolved", "Closed") for r in rows),
        "resolved": sum(r["status"] == "Resolved" for r in rows),
    }


def all_complaints():
    db = get_db()
    with db.cursor() as cur:
        cur.execute("SELECT c.*,u.name citizen_name FROM complaints c JOIN users u ON u.id=c.citizen_id ORDER BY c.created_at DESC")
        return cur.fetchall()


def recent_complaints():
    return admin_complaints_grouped()[:6]


def admin_complaints_grouped():
    """Return one admin-table row per department/location issue."""
    return group_complaints_for_admin(all_complaints())


def group_complaints_for_admin(rows):
    """Collapse admin rows and add the number of submitted complaints."""
    groups = {}
    for row in rows:
        groups.setdefault(complaint_location_key(row), []).append(row)

    grouped = []
    for members in groups.values():
        # Keep the newest submission as the row that represents the issue.
        representative = max(members, key=lambda complaint: complaint["created_at"])
        display_row = dict(representative)
        display_row["complaint_count"] = len(members)
        grouped.append(display_row)
    return sorted(grouped, key=lambda complaint: complaint["created_at"], reverse=True)


def complaint_location_key(complaint):
    """Create a stable department + location key for admin duplicate groups."""
    department = (complaint.get("department") or "").strip().casefold()
    latitude = complaint.get("latitude")
    longitude = complaint.get("longitude")
    if latitude is not None and longitude is not None:
        # GPS readings differ slightly for the same incident. Three decimal
        # places covers approximately 100 metres.
        return (department, "gps", round(float(latitude), 3), round(float(longitude), 3))

    address = " ".join((complaint.get("address") or "").casefold().split())
    if address:
        return (department, "address", address)

    # Reports without a captured location must remain separate.
    return (department, "complaint", complaint["id"])

def global_stats():
    return status_stats(all_complaints())


def department_stats():
    db = get_db()
    result = []
    for d in DEPARTMENTS:
        with db.cursor() as cur:
            cur.execute("SELECT COUNT(*) as cnt FROM complaints WHERE department=%s", (d,))
            total = cur.fetchone()["cnt"]
            cur.execute("SELECT COUNT(*) as cnt FROM complaints WHERE department=%s AND status='Resolved'", (d,))
            resolved = cur.fetchone()["cnt"]
            cur.execute("SELECT COUNT(*) as cnt FROM complaints WHERE department=%s AND is_read=0", (d,))
            unread = cur.fetchone()["cnt"]
        result.append({"name": d, "total": total, "resolved": resolved, "unread": unread})
    return result


def next_staff_for_department(department):
    """Return the designated staff member assigned to the specified department."""
    db = get_db()
    target_email = DEPARTMENT_STAFF_MAP.get(department, "staff1@gmail.com")
    with db.cursor() as cur:
        cur.execute(
            "SELECT id, name, email, phone, department FROM users WHERE role='officer' AND email=%s",
            (target_email,),
        )
        officer = cur.fetchone()
        if not officer:
            cur.execute(
                "SELECT id, name, email, phone, department FROM users WHERE role='officer' AND department=%s",
                (department,),
            )
            officer = cur.fetchone()
        if not officer:
            cur.execute("SELECT id, name, email, phone, department FROM users WHERE role='officer' LIMIT 1")
            officer = cur.fetchone()
    return officer


def bootstrap_admin():
    """Create one administrator only when secure environment variables are supplied."""
    name = current_app.config.get("ADMIN_BOOTSTRAP_NAME")
    email = current_app.config.get("ADMIN_BOOTSTRAP_EMAIL")
    password = current_app.config.get("ADMIN_BOOTSTRAP_PASSWORD")
    if not all((name, email, password)):
        return
    db = get_db()
    with db.cursor() as cur:
        cur.execute("SELECT 1 FROM users WHERE email=%s", (email.lower(),))
        exists = cur.fetchone()
    if not exists:
        with db.cursor() as cur:
            cur.execute(
                "INSERT INTO users(name,email,password_hash,role) VALUES(%s,%s,%s,%s)",
                (name, email.lower(), generate_password_hash(password), "admin"),
            )
        db.commit()


def bootstrap_staff():
    """Create the five shared staff accounts and set their specific department."""
    db = get_db()
    staff_dept_mapping = [
        ("Staff 1", "staff1@gmail.com", "staff1", "+91 90000 00001", "Public Works"),
        ("Staff 2", "staff2@gmail.com", "staff2", "+91 90000 00002", "Municipal"),
        ("Staff 3", "staff3@gmail.com", "staff3", "+91 90000 00003", "Water Supply"),
        ("Staff 4", "staff4@gmail.com", "staff4", "+91 90000 00004", "Electricity"),
        ("Staff 5", "staff5@gmail.com", "staff5", "+91 90000 00005", "Drainage"),
    ]
    with db.cursor() as cur:
        for name, email, password, phone, dept in staff_dept_mapping:
            cur.execute("SELECT id FROM users WHERE email=%s", (email,))
            existing = cur.fetchone()
            if existing:
                cur.execute(
                    "UPDATE users SET name=%s, phone=%s, password_hash=%s, role='officer', department=%s WHERE id=%s",
                    (name, phone, generate_password_hash(password), dept, existing["id"]),
                )
            else:
                cur.execute(
                    "INSERT INTO users(name,email,phone,password_hash,role,department) VALUES(%s,%s,%s,%s,'officer',%s)",
                    (name, email, phone, generate_password_hash(password), dept),
                )
    db.commit()


if __name__ == "__main__":
    create_app().run(debug=True)
