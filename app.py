import os
import re
import io
import sys
import json
import base64
import secrets
import smtplib
from email.message import EmailMessage
from datetime import datetime, timedelta
from functools import wraps
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash
from itsdangerous import URLSafeSerializer
import pyotp
import qrcode
import csv
from flask import session
from flask import Response
from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, abort, session, current_app,
    send_from_directory, send_file, make_response, jsonify
)
from flask_login import (
    login_user, logout_user, login_required, current_user
)
from flask_migrate import Migrate
from dotenv import load_dotenv

load_dotenv()

# ───────── Extensions ───────────────────────────────────────────────────────
from extensions import db, login_manager

# ───────── Models ────────────────────────────────────────────────────────────
from models.job_offer           import JobOffer
from models.user                import User
from models.job_seeker_profile  import JobSeekerProfile
from models.application         import Application
from models.interview_session   import InterviewSession
from models.interview_schedule  import InterviewSchedule
from models.job_invitation      import JobInvitation
from models.message             import Message
from models.news                import News
from models.article             import Article
from models.block               import Block
from models.saved_job           import SavedJob


def load_local_env():
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ[key.strip()] = value.strip().strip("\"'")


load_local_env()

from ai.cv_parser import extract_profile_locally_from_cv_text, extract_skills_from_cv, extract_text
from ai.gemini_service import (
    analyze_candidate_fit,
    basic_match_score,
    candidate_profile_dashboard,
    check_gemini_connection,
    evaluate_interview_answers,
    extract_profile_from_cv_text,
    generate_interview_questions,
    generate_cover_letter,
    gemini_available,
    improve_cv_content,
    job_market_insights,
    recruiter_shortlist_report,
    skill_gap_analysis,
)

# ───────── PDF / Image Imports ───────────────────────────────────────────────
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from weasyprint import HTML

# ───────── Config / Upload folder ───────────────────────────────────────────
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
CHAT_UPLOAD_FOLDER = os.path.join(UPLOAD_FOLDER, "chat")
os.makedirs(CHAT_UPLOAD_FOLDER, exist_ok=True)

HEX_RE = re.compile(r"#?[0-9A-Fa-f]{6}")

CATEGORIES = [
    "Software", "Data Science", "DevOps", "UI/UX", "Project Management",
    "Marketing", "Sales", "HR", "Finance", "Customer Support",
    "Product", "QA / Testing", "Security", "AI/ML", "Business Analysis",
    "Content Writing", "Legal", "Operations", "Education", "Healthcare"
]

CITY_COORDS = {
    "amsterdam": (52.3676, 4.9041),
    "athens": (37.9838, 23.7275),
    "barcelona": (41.3874, 2.1686),
    "belgrade": (44.7866, 20.4489),
    "berlin": (52.5200, 13.4050),
    "brasov": (45.6579, 25.6012),
    "bratislava": (48.1486, 17.1077),
    "brussels": (50.8503, 4.3517),
    "bucharest": (44.4268, 26.1025),
    "bucuresti": (44.4268, 26.1025),
    "budapest": (47.4979, 19.0402),
    "cluj": (46.7712, 23.6236),
    "cluj-napoca": (46.7712, 23.6236),
    "copenhagen": (55.6761, 12.5683),
    "constanta": (44.1598, 28.6348),
    "craiova": (44.3302, 23.7949),
    "dublin": (53.3498, -6.2603),
    "frankfurt": (50.1109, 8.6821),
    "galati": (45.4353, 28.0079),
    "hamburg": (53.5511, 9.9937),
    "helsinki": (60.1699, 24.9384),
    "iasi": (47.1585, 27.6014),
    "krakow": (50.0647, 19.9450),
    "lisbon": (38.7223, -9.1393),
    "london": (51.5072, -0.1276),
    "lyon": (45.7640, 4.8357),
    "madrid": (40.4168, -3.7038),
    "milan": (45.4642, 9.1900),
    "munich": (48.1351, 11.5820),
    "oradea": (47.0465, 21.9189),
    "oslo": (59.9139, 10.7522),
    "paris": (48.8566, 2.3522),
    "prague": (50.0755, 14.4378),
    "rome": (41.9028, 12.4964),
    "sibiu": (45.7983, 24.1256),
    "sofia": (42.6977, 23.3219),
    "stockholm": (59.3293, 18.0686),
    "timisoara": (45.7489, 21.2087),
    "vienna": (48.2082, 16.3738),
    "warsaw": (52.2297, 21.0122),
    "zurich": (47.3769, 8.5417),
}

CHAT_ATTACHMENT_EXTENSIONS = {
    "pdf", "doc", "docx", "txt", "png", "jpg", "jpeg", "gif", "webp", "zip"
}


def allowed_chat_attachment(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in CHAT_ATTACHMENT_EXTENSIONS


def normalize_city_name(value):
    return (value or "").strip().lower() \
        .replace("ș", "s").replace("ş", "s") \
        .replace("ț", "t").replace("ţ", "t") \
        .replace("ă", "a").replace("â", "a").replace("î", "i")


def city_coordinates(city):
    return CITY_COORDS.get(normalize_city_name(city))


def request_location_coordinates():
    lat = float(request.form.get("latitude") or 0) or None
    lng = float(request.form.get("longitude") or 0) or None
    if lat is not None and lng is not None:
        return lat, lng
    coords = city_coordinates(request.form.get("city"))
    return coords if coords else (None, None)


def marker_payload_from_jobs(jobs):
    grouped = {}
    for job in jobs:
        lat = job.latitude
        lng = job.longitude
        if lat is None or lng is None:
            coords = city_coordinates(job.city)
            if not coords:
                continue
            lat, lng = coords
        key = (round(float(lat), 6), round(float(lng), 6), job.city or "Unknown")
        if key not in grouped:
            grouped[key] = {
                "lat": key[0],
                "lng": key[1],
                "city": key[2],
                "count": 0,
                "job_ids": [],
                "titles": [],
            }
        grouped[key]["count"] += 1
        grouped[key]["job_ids"].append(job.id)
        grouped[key]["titles"].append(job.title)
    return list(grouped.values())


def mail_configured():
    return bool(os.environ.get("MAIL_USERNAME") and os.environ.get("MAIL_PASSWORD"))


def send_email(to_email, subject, body):
    if not to_email or not mail_configured():
        print(f"Email skipped: {subject}")
        return False
    host = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    port = int(os.environ.get("MAIL_PORT", "587"))
    username = os.environ.get("MAIL_USERNAME")
    password = os.environ.get("MAIL_PASSWORD")
    sender = os.environ.get("MAIL_DEFAULT_SENDER", username)

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = to_email
    message.set_content(body)

    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=12) as smtp:
                smtp.login(username, password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=12) as smtp:
                smtp.starttls()
                smtp.login(username, password)
                smtp.send_message(message)
        return True
    except Exception as exc:
        print(f"Email failed: {exc}")
        return False


def send_preferred_email(user, preference_name, subject, body):
    if not user:
        return False
    if not user.email_notifications_enabled or not user.email_verified:
        return False
    if not getattr(user, preference_name, False):
        return False
    return send_email(user.email, subject, body)


def ensure_runtime_columns():
    dialect = db.engine.dialect.name
    if dialect != "sqlite":
        return
    table_columns = {}
    for table_name in ("message", "user", "job_seeker_profile"):
        rows = db.session.execute(db.text(f"PRAGMA table_info({table_name})")).fetchall()
        table_columns[table_name] = {row[1] for row in rows}
    message_additions = {
        "read_at": "DATETIME",
        "edited_at": "DATETIME",
        "deleted_at": "DATETIME",
        "reaction": "VARCHAR(20)",
        "attachment_filename": "VARCHAR(200)",
        "attachment_original": "VARCHAR(200)",
        "scheduled_for": "DATETIME",
    }
    for column, column_type in message_additions.items():
        if column not in table_columns["message"]:
            db.session.execute(db.text(f"ALTER TABLE message ADD COLUMN {column} {column_type}"))
    if "last_seen" not in table_columns["user"]:
        db.session.execute(db.text("ALTER TABLE user ADD COLUMN last_seen DATETIME"))
    user_additions = {
        "email_verified": "BOOLEAN DEFAULT 0",
        "email_verification_code": "VARCHAR(12)",
        "email_verification_sent_at": "DATETIME",
        "email_notifications_enabled": "BOOLEAN DEFAULT 0",
        "notify_email_job_invitations": "BOOLEAN DEFAULT 1",
        "notify_email_application_decisions": "BOOLEAN DEFAULT 1",
        "notify_email_interview_updates": "BOOLEAN DEFAULT 1",
        "notify_email_new_applications": "BOOLEAN DEFAULT 1",
        "notify_email_messages": "BOOLEAN DEFAULT 0",
    }
    for column, column_type in user_additions.items():
        if column not in table_columns["user"]:
            db.session.execute(db.text(f"ALTER TABLE user ADD COLUMN {column} {column_type}"))
    profile_additions = {
        "desired_salary_gross": "INTEGER",
        "desired_salary_net": "INTEGER",
    }
    for column, column_type in profile_additions.items():
        if column not in table_columns["job_seeker_profile"]:
            db.session.execute(db.text(f"ALTER TABLE job_seeker_profile ADD COLUMN {column} {column_type}"))
    db.session.commit()

class SimplePagination:
    def __init__(self, items, page, per_page, total):
        self.items = items
        self.page = page
        self.per_page = per_page
        self.total = total
        self.pages = max(1, (total + per_page - 1) // per_page)
        self.has_prev = page > 1
        self.has_next = page < self.pages
        self.prev_num = page - 1
        self.next_num = page + 1

# ───────── App Factory ───────────────────────────────────────────────────────
def create_app():
    app = Flask(__name__)
    app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///jobify.db'
    app.secret_key = os.environ.get("SECRET_KEY", "my_super_secret_key")

    # initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    Migrate(app, db)

    return app

# ─── Instantiate app ─────────────────────────────────────────────────────────
app = create_app()

# ─── Create all tables on startup ─────────────────────────────────────────────
with app.app_context():
    db.create_all()
    ensure_runtime_columns()
    print("✅ All database tables created (or already existed).")

# ─── Serializer ──────────────────────────────────────────────────────────────
serializer = URLSafeSerializer(app.secret_key, salt="remember-device")

@login_manager.user_loader
def load_user(uid):
    return User.query.get(int(uid))

@app.before_request
def update_last_seen():
    admin_allowed_endpoints = {
        "admin_login",
        "admin_dashboard",
        "admin_logout",
        "export_users",
        "static",
    }
    if current_user.is_authenticated and current_user.username == ADMIN_USERNAME:
        session["admin_logged_in"] = True
        if request.endpoint not in admin_allowed_endpoints:
            return redirect(url_for("admin_dashboard"))
        return

    if current_user.is_authenticated:
        current_user.last_seen = datetime.utcnow()
        db.session.commit()

# ─── Context Processor ───────────────────────────────────────────────────────
@app.context_processor
def inject_globals():
    msg_badge = apps_badge = dec_badge = notifications_badge = 0
    brand = "#0d6efd"
    if current_user.is_authenticated:
        notifications_badge = notification_badge_count(current_user)
        msg_badge = Message.query.filter_by(
            recipient_id=current_user.id, is_read=False
        ).count()
        if current_user.role == "recruiter":
            brand = current_user.brand_color or brand
            apps_badge = Application.query.join(JobOffer).filter(
                JobOffer.recruiter_id == current_user.id,
                Application.status == "Pending",
                Application.is_read_recruiter.is_(False)
            ).count()
        else:
            dec_badge = Application.query.filter_by(
                jobseeker_id=current_user.id, is_read_user=False
            ).filter(Application.status != "Pending").count()
    return dict(
        unread_count=msg_badge,
        unread_apps=apps_badge,
        unread_decisions=dec_badge,
        notification_count=notifications_badge,
        brand_color=brand
    )

def trusted_device(user):
    cookie = request.cookies.get("remember_device")
    if not cookie:
        return False


def enrich_profile_from_cv(profile):
    if not profile or not profile.cv_path:
        return False
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], profile.cv_path)
    if not os.path.isfile(path):
        return False
    try:
        local_profile = extract_profile_locally_from_cv_text(extract_text(path))
    except Exception:
        return False
    changed = False
    for field in ("name", "email", "phone", "summary", "experience", "education"):
        value = local_profile.get(field)
        if value and not getattr(profile, field, None):
            setattr(profile, field, value)
            changed = True
    if local_profile.get("skills") and not profile.skills:
        profile.skills = ",".join(local_profile["skills"])
        changed = True
    return changed
    try:
        return int(serializer.loads(cookie)) == user.id
    except Exception:
        return False


def percent_of(value, total):
    return round((value / total * 100), 1) if total else 0


def safe_dt(value):
    return value or datetime.min


def build_notification_center(user, limit=25):
    notifications = []
    now = datetime.utcnow()

    unread_messages = Message.query.filter_by(
        recipient_id=user.id, is_read=False
    ).order_by(Message.timestamp.desc()).limit(6).all()
    for msg in unread_messages:
        notifications.append({
            "type": "Message",
            "title": f"New message from {msg.sender.name or msg.sender.username}",
            "body": (msg.body or msg.attachment_original or "Attachment")[:140],
            "time": msg.timestamp,
            "status": "Unread",
            "tone": "primary",
            "href": url_for("chat", uid=msg.sender_id),
        })

    if user.role == "recruiter":
        recruiter_jobs = JobOffer.query.filter_by(recruiter_id=user.id).all()
        job_ids = [job.id for job in recruiter_jobs]

        if job_ids:
            recent_apps = Application.query.filter(
                Application.joboffer_id.in_(job_ids)
            ).order_by(Application.applied_on.desc()).limit(8).all()
            for app_row in recent_apps:
                notifications.append({
                    "type": "Application",
                    "title": f"Candidate #{app_row.jobseeker_id} applied",
                    "body": f"Application for {app_row.job_offer.title} is {app_row.status}.",
                    "time": app_row.applied_on,
                    "status": "Unread" if not app_row.is_read_recruiter else app_row.status,
                    "tone": "warning" if not app_row.is_read_recruiter else "secondary",
                    "href": url_for("view_applications"),
                })

        interviews = InterviewSchedule.query.filter_by(
            recruiter_id=user.id
        ).order_by(InterviewSchedule.created_at.desc()).limit(8).all()
        for interview in interviews:
            needs_reply = interview.status == "Countered"
            notifications.append({
                "type": "Interview",
                "title": "Interview schedule update",
                "body": f"{interview.application.job_offer.title}: {interview.status} for {interview.scheduled_at.strftime('%Y-%m-%d %H:%M')}.",
                "time": interview.responded_at or interview.created_at,
                "status": "Action needed" if needs_reply else interview.status,
                "tone": "danger" if needs_reply else "info",
                "href": url_for("interview_calendar"),
            })

    else:
        decisions = Application.query.filter_by(
            jobseeker_id=user.id
        ).filter(Application.status != "Pending").order_by(Application.applied_on.desc()).limit(8).all()
        for app_row in decisions:
            notifications.append({
                "type": "Decision",
                "title": f"Application {app_row.status.lower()}",
                "body": f"Your application for {app_row.job_offer.title} was {app_row.status}.",
                "time": app_row.applied_on,
                "status": "New" if not app_row.is_read_user else app_row.status,
                "tone": "success" if app_row.status == "Accepted" else "danger",
                "href": url_for("my_applications"),
            })

        invitations = JobInvitation.query.filter_by(
            jobseeker_id=user.id
        ).order_by(JobInvitation.created_at.desc()).limit(8).all()
        for invite in invitations:
            notifications.append({
                "type": "Invitation",
                "title": "Recruiter invited you to apply",
                "body": f"{invite.job_offer.title}: {invite.message or 'You received a job invitation.'}",
                "time": invite.created_at,
                "status": invite.status,
                "tone": "primary",
                "href": url_for("apply_job", job_id=invite.joboffer_id),
            })

        interviews = InterviewSchedule.query.filter_by(
            jobseeker_id=user.id
        ).order_by(InterviewSchedule.created_at.desc()).limit(8).all()
        for interview in interviews:
            needs_reply = interview.status == "Proposed"
            notifications.append({
                "type": "Interview",
                "title": "Interview proposal",
                "body": f"{interview.application.job_offer.title}: {interview.status} for {interview.scheduled_at.strftime('%Y-%m-%d %H:%M')}.",
                "time": interview.responded_at or interview.created_at,
                "status": "Action needed" if needs_reply else interview.status,
                "tone": "danger" if needs_reply else "info",
                "href": url_for("interview_calendar"),
            })

        profile = JobSeekerProfile.query.filter_by(user_id=user.id).first()
        if profile and profile.skills:
            best_matches = []
            applied_ids = {
                app_row.joboffer_id
                for app_row in Application.query.filter_by(jobseeker_id=user.id).all()
            }
            for job in JobOffer.query.all():
                if job.id in applied_ids:
                    continue
                score = basic_match_score(profile, job)
                if score >= 60:
                    best_matches.append((job, score))
            for job, score in sorted(best_matches, key=lambda item: item[1], reverse=True)[:4]:
                notifications.append({
                    "type": "Job Match",
                    "title": f"{score}% match: {job.title}",
                    "body": f"This job matches your profile well. City: {job.city}.",
                    "time": now - timedelta(minutes=job.id),
                    "status": "Recommended",
                    "tone": "success",
                    "href": url_for("job_list"),
                })

    notifications.sort(key=lambda item: safe_dt(item["time"]), reverse=True)
    return notifications[:limit]


def notification_badge_count(user):
    if not user or not user.is_authenticated:
        return 0
    count = Message.query.filter_by(recipient_id=user.id, is_read=False).count()
    if user.role == "recruiter":
        count += Application.query.join(JobOffer).filter(
            JobOffer.recruiter_id == user.id,
            Application.status == "Pending",
            Application.is_read_recruiter.is_(False)
        ).count()
        count += InterviewSchedule.query.filter_by(
            recruiter_id=user.id, status="Countered"
        ).count()
    else:
        count += Application.query.filter_by(
            jobseeker_id=user.id, is_read_user=False
        ).filter(Application.status != "Pending").count()
        count += InterviewSchedule.query.filter_by(
            jobseeker_id=user.id, status="Proposed"
        ).count()
        count += JobInvitation.query.filter_by(
            jobseeker_id=user.id, status="Sent"
        ).count()
    return count

# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    if session.get("admin_logged_in"):
        return redirect(url_for("admin_dashboard"))
    if current_user.is_authenticated:
        dash = (
            "dashboard_recruiter"
            if current_user.role == "recruiter"
            else "dashboard_jobseeker"
        )
        return redirect(url_for(dash))
    return redirect(url_for("login"))

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash("Username already exists. Please choose another.", "danger")
            return redirect(url_for("register"))

        password_hash = generate_password_hash(request.form["password"])
        role = request.form["role"]
        brand_color = request.form.get("brand_color", "#0d6efd")

        user = User(
            username=username,
            password_hash=password_hash,
            role=role,
            brand_color=brand_color
        )
        db.session.add(user)
        db.session.commit()

        flash("Registration successful. Please login.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            logout_user()
            session["admin_logged_in"] = True
            return redirect(url_for("admin_dashboard"))

        u = User.query.filter_by(username=username).first()
        if u and u.check_password(password):
            if u.twofa_secret and not trusted_device(u):
                session["pre_2fa"] = u.id
                return redirect(url_for("twofa"))
            login_user(u)
            return redirect(url_for("index"))
        flash("Invalid credentials.", "danger")

    public_counts = marker_payload_from_jobs(JobOffer.query.all())
    vacancies = JobOffer.query.count()
    latest_articles = Article.query.order_by(Article.created_at.desc()).limit(3).all()
    latest_news = News.query.order_by(News.created_at.desc()).limit(3).all()

    return render_template(
        "login.html",
        markers=public_counts,
        vacancies=vacancies,
        latest_articles=latest_articles,
        latest_news=latest_news
    )

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

    #Block and ublock

@app.route("/block_user/<int:uid>", methods=["POST"])
@login_required
def block_user(uid):
    if uid == current_user.id:
        abort(400)
    # ensure user exists
    target = User.query.get_or_404(uid)
    # no duplicate
    if not Block.query.filter_by(blocker_id=current_user.id, blocked_id=uid).first():
        db.session.add(Block(blocker_id=current_user.id, blocked_id=uid))
        db.session.commit()
        flash(f"You’ve blocked {target.username}.", "info")
    return redirect(url_for("inbox"))

@app.route("/unblock_user/<int:uid>", methods=["POST"])
@login_required
def unblock_user(uid):
    blk = Block.query.filter_by(blocker_id=current_user.id, blocked_id=uid).first()
    if blk:
        db.session.delete(blk)
        db.session.commit()
        flash("User unblocked.", "success")
    return redirect(url_for("inbox"))

@app.route("/admin/export/users")
def export_users():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    si = []
    users = User.query.all()
    output = "id,username,email,role\n"
    for u in users:
        output += f"{u.id},{u.username},{u.email},{u.role}\n"

    return Response(output, mimetype="text/csv",
                    headers={"Content-Disposition": "attachment;filename=users.csv"})

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "4433"

@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if session.get("admin_logged_in"):
        return redirect(url_for("admin_dashboard"))
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            return redirect(url_for("admin_dashboard"))
        else:
            flash("Invalid credentials", "danger")
    return render_template("admin_login.html")


@app.route("/admin/dashboard")
def admin_dashboard():
    if not session.get('admin_logged_in'):
        return redirect(url_for("admin_login"))

    total_users = User.query.count()
    total_jobs = JobOffer.query.count()
    total_applications = Application.query.count()
    total_messages = Message.query.count()
    total_interviews = InterviewSchedule.query.count()
    total_saved_jobs = SavedJob.query.count()

    recruiters = User.query.filter_by(role="recruiter").count()
    jobseekers = User.query.filter_by(role="jobseeker").count()
    active_users = User.query.filter(
        User.last_seen >= datetime.utcnow() - timedelta(days=7)
    ).count()

    pending_apps = Application.query.filter_by(status="Pending").count()
    accepted_apps = Application.query.filter_by(status="Accepted").count()
    rejected_apps = Application.query.filter_by(status="Rejected").count()

    jobs_by_category = db.session.query(
        JobOffer.category,
        db.func.count(JobOffer.id).label("cnt")
    ).group_by(JobOffer.category).order_by(db.func.count(JobOffer.id).desc()).all()

    jobs_by_city = db.session.query(
        JobOffer.city,
        db.func.count(JobOffer.id).label("cnt")
    ).group_by(JobOffer.city).order_by(db.func.count(JobOffer.id).desc()).limit(8).all()

    top_recruiters = []
    recruiter_rows = db.session.query(
        JobOffer.recruiter_id,
        db.func.count(JobOffer.id).label("jobs_count")
    ).group_by(JobOffer.recruiter_id).order_by(db.func.count(JobOffer.id).desc()).limit(5).all()
    for row in recruiter_rows:
        recruiter = User.query.get(row.recruiter_id)
        top_recruiters.append({
            "name": recruiter.name or recruiter.username if recruiter else f"Recruiter #{row.recruiter_id}",
            "jobs": row.jobs_count,
        })

    days = []
    app_activity = []
    for offset in range(6, -1, -1):
        day = datetime.utcnow().date() - timedelta(days=offset)
        next_day = day + timedelta(days=1)
        count = Application.query.filter(
            Application.applied_on >= datetime.combine(day, datetime.min.time()),
            Application.applied_on < datetime.combine(next_day, datetime.min.time())
        ).count()
        days.append(day.strftime("%d %b"))
        app_activity.append(count)

    latest_users = User.query.order_by(User.id.desc()).limit(5).all()
    latest_jobs = JobOffer.query.order_by(JobOffer.id.desc()).limit(5).all()
    recent_applications = Application.query.order_by(Application.applied_on.desc()).limit(6).all()
    recent_interviews = InterviewSchedule.query.order_by(InterviewSchedule.created_at.desc()).limit(5).all()

    max_category = max(max([row.cnt for row in jobs_by_category], default=0), 1)
    max_city = max(max([row.cnt for row in jobs_by_city], default=0), 1)
    max_activity = max(max(app_activity or [0]), 1)

    return render_template(
        "admin_dashboard.html",
        total_users=total_users,
        total_jobs=total_jobs,
        total_applications=total_applications,
        total_messages=total_messages,
        total_interviews=total_interviews,
        total_saved_jobs=total_saved_jobs,
        recruiters=recruiters,
        jobseekers=jobseekers,
        active_users=active_users,
        pending_apps=pending_apps,
        accepted_apps=accepted_apps,
        rejected_apps=rejected_apps,
        jobs_by_category=jobs_by_category,
        jobs_by_city=jobs_by_city,
        top_recruiters=top_recruiters,
        days=days,
        app_activity=app_activity,
        max_category=max_category,
        max_city=max_city,
        max_activity=max_activity,
        user_role_jobseekers=percent_of(jobseekers, total_users),
        user_role_recruiters=percent_of(recruiters, total_users),
        application_acceptance=percent_of(accepted_apps, total_applications),
        application_pending=percent_of(pending_apps, total_applications),
        latest_users=latest_users,
        latest_jobs=latest_jobs,
        recent_applications=recent_applications,
        recent_interviews=recent_interviews,
    )

@app.route("/admin/logout")
def admin_logout():
    session.pop('admin_logged_in', None)
    logout_user()
    return redirect(url_for('admin_login'))


# ─── News Detail ─────────────────────────────────────────────────────────────
@app.route("/news/<int:nid>")
def news_detail(nid):
    n = News.query.get_or_404(nid)
    return render_template("news_detail.html", news=n)

# ─── Article Detail ──────────────────────────────────────────────────────────
@app.route("/articles/<int:aid>")
def article_detail(aid):
    a = Article.query.get_or_404(aid)
    return render_template("article_detail.html", article=a)

@app.route("/recruiter_stats")
@login_required
def recruiter_stats():
    if current_user.role != "recruiter":
        abort(403)

    # 1️⃣ Total Jobs
    total_jobs = JobOffer.query.filter_by(recruiter_id=current_user.id).count()

    # 2️⃣ Total Applications
    total_applications = Application.query.join(JobOffer).filter(JobOffer.recruiter_id == current_user.id).count()

    # 3️⃣ Acceptance Rate
    accepted = Application.query.join(JobOffer).filter(
        JobOffer.recruiter_id == current_user.id,
        Application.status == "Accepted"
    ).count()

    acceptance_rate = (accepted / total_applications * 100) if total_applications > 0 else 0

    # 4️⃣ Unread Applications
    unread_apps = Application.query.join(JobOffer).filter(
        JobOffer.recruiter_id == current_user.id,
        Application.status == "Pending",
        Application.is_read_recruiter == False
    ).count()

    # 5️⃣ Top Skills extraction (basic text parsing)
    from collections import Counter

    skills_counter = Counter()
    seeker_profiles = JobSeekerProfile.query.all()

    for prof in seeker_profiles:
        if prof.skills:
            skills = [s.strip().lower() for s in prof.skills.split(",") if s.strip()]
            skills_counter.update(skills)

    top_skills = skills_counter.most_common(5)

    return render_template(
        "recruiter_stats.html",
        total_jobs=total_jobs,
        total_applications=total_applications,
        acceptance_rate=acceptance_rate,
        unread_apps=unread_apps,
        top_skills=top_skills
    )


@app.route("/twofa", methods=["GET", "POST"])
def twofa():
    uid = session.get("pre_2fa")
    if not uid:
        return redirect(url_for("login"))
    user = User.query.get(uid)
    if request.method == "POST":
        code = request.form["token"]
        if user.verify_token(code):
            login_user(user)
            session.pop("pre_2fa", None)
            resp = redirect(url_for("index"))
            if "remember" in request.form:
                resp.set_cookie(
                    "remember_device",
                    serializer.dumps(user.id),
                    max_age=60 * 60 * 24 * 30,
                    httponly=True
                )
            return resp
        flash("Invalid token.", "danger")
    return render_template("twofa.html")

@app.route("/enable_2fa", methods=["GET", "POST"])
@login_required
def enable_2fa():
    user = current_user
    if not user.twofa_secret:
        user.twofa_secret = pyotp.random_base32()
        db.session.commit()
    if request.method == "POST":
        flash("Two-Factor enabled!", "success")
        return redirect(url_for("index"))

    uri = user.get_totp().provisioning_uri(user.username, issuer_name="JobMatcher")
    buf = io.BytesIO()
    qrcode.make(uri).save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode()
    return render_template("enable_2fa.html", qr_b64=qr_b64, secret=user.twofa_secret)

# ─── Edit Profile ─────────────────────────────────────────────────────────────
@app.route("/profile/edit", methods=["GET", "POST"])
@login_required
def edit_profile():
    # Only allow jobseekers AND recruiters
    prof = None
    if current_user.role == "jobseeker":
        prof = JobSeekerProfile.query.filter_by(user_id=current_user.id).first()
        if not prof:
            prof = JobSeekerProfile(user_id=current_user.id)
            db.session.add(prof)
    if request.method == "POST":
        # grab the form data
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        pic = request.files.get("picture")

        # update fields
        current_user.name = name or current_user.name
        current_user.email = email or current_user.email
        if prof:
            prof.name = name or prof.name
            prof.email = email or prof.email
            prof.phone = request.form.get("phone", "").strip() or prof.phone
            prof.summary = request.form.get("summary", "").strip() or prof.summary
            prof.desired_salary_gross = request.form.get("desired_salary_gross", type=int)
            prof.desired_salary_net = request.form.get("desired_salary_net", type=int)

        # handle picture upload
        if pic and pic.filename:
            filename = f"user_{current_user.id}_" + secure_filename(pic.filename)
            path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
            pic.save(path)
            current_user.picture_path = filename

        db.session.commit()
        flash("Profile updated.", "success")
        return redirect(url_for("dashboard_recruiter"
                        if current_user.role=="recruiter" else
                        "dashboard_jobseeker"))

    # GET: just show the form
    return render_template("edit_profile.html",
                           name=current_user.name,
                           email=current_user.email,
                           profile=prof)


# ─── Delete CV ───────────────────────────────────────────────────────────────
@app.route("/delete_cv", methods=["POST"])
@login_required
def delete_cv():
    prof = JobSeekerProfile.query.filter_by(user_id=current_user.id).first()
    if prof and prof.cv_path:
        path = os.path.join(current_app.config["UPLOAD_FOLDER"], prof.cv_path)
        if os.path.exists(path):
            os.remove(path)
        prof.cv_path = None
        prof.skills = ""
        db.session.commit()
        flash("CV deleted.", "warning")
    else:
        flash("No CV to delete.", "info")
    return redirect(url_for("dashboard_jobseeker"))

@app.route("/disable_2fa", methods=["POST"])
@login_required
def disable_2fa():
    current_user.twofa_secret = None
    db.session.commit()
    flash("Two-Factor disabled.", "warning")
    target = (
        "dashboard_jobseeker"
        if current_user.role == "jobseeker"
        else "dashboard_recruiter"
    )
    return redirect(url_for(target))

@app.route("/change_password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current = request.form["current_password"]
        new = request.form["new_password"]
        confirm = request.form["confirm_password"]
        if not current_user.check_password(current):
            flash("Current password is incorrect.", "danger")
        elif new != confirm:
            flash("New passwords do not match.", "warning")
        else:
            current_user.password_hash = generate_password_hash(new)
            db.session.commit()
            flash("Password successfully changed.", "success")
            return redirect(url_for("index"))
    return render_template("change_password.html")

@app.route("/dashboard/recruiter")
@login_required
def dashboard_recruiter():
    if current_user.role != "recruiter":
        abort(403)
    offers = JobOffer.query.filter_by(recruiter_id=current_user.id).all()
    return render_template("dashboard_recruiter.html", offers=offers)

@app.route("/post_job", methods=["GET", "POST"])
@login_required
def post_job():
    if current_user.role != "recruiter":
        abort(403)
    if request.method == "POST":
        lat, lng = request_location_coordinates()
        job = JobOffer(
            recruiter_id=current_user.id,
            title=request.form["title"],
            description=request.form["description"],
            required_skills=request.form["required_skills"],
            min_experience=int(request.form["min_experience"]),
            education_required=request.form["education_required"],
            country=request.form["country"],
            city=request.form["city"],
            category=request.form["category"],
            latitude=lat,
            longitude=lng
        )
        db.session.add(job)
        db.session.commit()
        flash("Job posted!", "success")
        return redirect(url_for("dashboard_recruiter"))
    return render_template("post_job.html", offer=None, categories=CATEGORIES, city_coords=CITY_COORDS)

@app.route("/jobs/<int:offer_id>/edit", methods=["GET", "POST"])
@login_required
def edit_job(offer_id):
    off = JobOffer.query.get_or_404(offer_id)
    if off.recruiter_id != current_user.id:
        abort(403)
    if request.method == "POST":
        off.title = request.form["title"]
        off.description = request.form["description"]
        off.required_skills = request.form["required_skills"]
        off.min_experience = int(request.form["min_experience"])
        off.education_required = request.form["education_required"]
        off.country = request.form["country"]
        off.city = request.form["city"]
        off.category = request.form["category"]
        off.latitude, off.longitude = request_location_coordinates()
        db.session.commit()
        flash("Job updated.", "success")
        return redirect(url_for("dashboard_recruiter"))
    return render_template("post_job.html", offer=off, categories=CATEGORIES, city_coords=CITY_COORDS)

@app.route("/jobs/<int:offer_id>/delete", methods=["POST"])
@login_required
def delete_job(offer_id):
    if current_user.role != "recruiter":
        abort(403)
    off = JobOffer.query.get_or_404(offer_id)
    if off.recruiter_id != current_user.id:
        abort(403)
    db.session.delete(off)
    db.session.commit()
    flash("Job deleted.", "success")
    return redirect(url_for("dashboard_recruiter"))

@app.route("/applications")
@login_required
def view_applications():
    if current_user.role != "recruiter":
        abort(403)
    apps = Application.query.join(JobOffer).filter(
        JobOffer.recruiter_id == current_user.id
    ).all()
    shortlist = {}
    for a in apps:
        if a.status == "Pending" and not a.is_read_recruiter:
            a.is_read_recruiter = True
        if a.job_seeker_profile:
            shortlist[a.id] = recruiter_shortlist_report(
                a.job_seeker_profile,
                a.job_offer,
                a.cover_letter
            )
    db.session.commit()
    apps.sort(key=lambda app: shortlist.get(app.id, {}).get("score", 0), reverse=True)
    return render_template("applications.html", applications=apps, shortlist=shortlist)

def recruiter_only(fn):
    @wraps(fn)
    def inner(app_id):
        if current_user.role != "recruiter":
            abort(403)
        appl = Application.query.get_or_404(app_id)
        if appl.job_offer.recruiter_id != current_user.id:
            abort(403)
        return fn(appl)
    return inner

@app.route("/applications/<int:app_id>/accept", methods=["POST"])
@recruiter_only
def accept_application(app):
    app.status = "Accepted"
    app.is_read_user = False
    db.session.commit()
    send_preferred_email(
        User.query.get(app.jobseeker_id),
        "notify_email_application_decisions",
        f"Application accepted: {app.job_offer.title}",
        (
            f"Good news! Your application for {app.job_offer.title} "
            "has been accepted on Jobify.ro.\n\n"
            "Open your account to see the latest decision and next steps."
        ),
    )
    flash("Application accepted.", "success")
    return redirect(url_for("view_applications"))

@app.route("/applications/<int:app_id>/reject", methods=["POST"])
@recruiter_only
def reject_application(app):
    app.status = "Rejected"
    app.is_read_user = False
    db.session.commit()
    send_preferred_email(
        User.query.get(app.jobseeker_id),
        "notify_email_application_decisions",
        f"Application update: {app.job_offer.title}",
        (
            f"Your application for {app.job_offer.title} was marked as rejected "
            "on Jobify.ro.\n\n"
            "You can continue exploring other matching jobs in your account."
        ),
    )
    flash("Application rejected.", "warning")
    return redirect(url_for("view_applications"))


@app.route("/applications/<int:app_id>/schedule-interview", methods=["POST"])
@recruiter_only
def schedule_interview(app):
    raw_time = request.form.get("scheduled_at", "").strip()
    try:
        scheduled_at = datetime.strptime(raw_time, "%Y-%m-%dT%H:%M")
    except ValueError:
        flash("Choose a valid interview date and time.", "warning")
        return redirect(url_for("view_applications"))
    location = request.form.get("location", "").strip()
    note = request.form.get("note", "").strip()
    schedule = InterviewSchedule(
        application_id=app.id,
        recruiter_id=current_user.id,
        jobseeker_id=app.jobseeker_id,
        scheduled_at=scheduled_at,
        location=location,
        note=note,
        status="Proposed",
    )
    db.session.add(schedule)
    db.session.add(Message(
        sender_id=current_user.id,
        recipient_id=app.jobseeker_id,
        body=(
            f"Interview proposed for {app.job_offer.title} on "
            f"{scheduled_at.strftime('%Y-%m-%d %H:%M')}."
            + (f" Location/link: {location}." if location else "")
            + (f" Note: {note}" if note else "")
        )
    ))
    db.session.commit()
    send_preferred_email(
        User.query.get(app.jobseeker_id),
        "notify_email_interview_updates",
        f"Interview proposed: {app.job_offer.title}",
        (
            f"A recruiter proposed an interview for {app.job_offer.title} on "
            f"{scheduled_at.strftime('%Y-%m-%d %H:%M')}."
            + (f"\nLocation/link: {location}" if location else "")
            + (f"\nNote: {note}" if note else "")
            + "\n\nOpen Jobify.ro to accept, decline, or propose another time."
        ),
    )
    flash("Interview proposal sent.", "success")
    return redirect(url_for("view_applications"))


@app.route("/interviews/<int:schedule_id>/respond", methods=["POST"])
@login_required
def respond_interview(schedule_id):
    if current_user.role != "jobseeker":
        abort(403)
    schedule = InterviewSchedule.query.get_or_404(schedule_id)
    if schedule.jobseeker_id != current_user.id:
        abort(403)
    decision = request.form.get("decision")
    if decision not in {"Accepted", "Declined", "Counter Proposed"}:
        abort(400)
    if decision == "Counter Proposed":
        raw_time = request.form.get("scheduled_at", "").strip()
        try:
            schedule.scheduled_at = datetime.strptime(raw_time, "%Y-%m-%dT%H:%M")
        except ValueError:
            flash("Choose a valid alternative date and time.", "warning")
            return redirect(url_for("my_applications"))
        schedule.location = request.form.get("location", "").strip() or schedule.location
        schedule.note = request.form.get("note", "").strip() or schedule.note
    schedule.status = decision
    schedule.responded_at = datetime.utcnow()
    if decision == "Counter Proposed":
        message_body = (
            f"I propose another interview time for {schedule.application.job_offer.title}: "
            f"{schedule.scheduled_at.strftime('%Y-%m-%d %H:%M')}."
            + (f" Location/link: {schedule.location}." if schedule.location else "")
            + (f" Note: {schedule.note}" if schedule.note else "")
        )
    else:
        message_body = (
            f"I have {decision.lower()} the interview for "
            f"{schedule.application.job_offer.title} on {schedule.scheduled_at.strftime('%Y-%m-%d %H:%M')}."
        )
    db.session.add(Message(
        sender_id=current_user.id,
        recipient_id=schedule.recruiter_id,
        body=message_body
    ))
    db.session.commit()
    send_preferred_email(
        User.query.get(schedule.recruiter_id),
        "notify_email_interview_updates",
        f"Interview response: {schedule.application.job_offer.title}",
        (
            f"{current_user.name or current_user.username} responded to the interview "
            f"for {schedule.application.job_offer.title}: {decision}.\n\n"
            f"Scheduled time: {schedule.scheduled_at.strftime('%Y-%m-%d %H:%M')}"
            + (f"\nLocation/link: {schedule.location}" if schedule.location else "")
        ),
    )
    flash("Interview response sent.", "success" if decision == "Accepted" else "info")
    return redirect(url_for("my_applications"))


@app.route("/interviews/<int:schedule_id>/recruiter-respond", methods=["POST"])
@login_required
def recruiter_respond_interview(schedule_id):
    if current_user.role != "recruiter":
        abort(403)
    schedule = InterviewSchedule.query.get_or_404(schedule_id)
    if schedule.recruiter_id != current_user.id:
        abort(403)
    decision = request.form.get("decision")
    if decision not in {"Accepted", "Declined"}:
        abort(400)
    schedule.status = decision
    schedule.responded_at = datetime.utcnow()
    db.session.add(Message(
        sender_id=current_user.id,
        recipient_id=schedule.jobseeker_id,
        body=(
            f"Your proposed interview time for {schedule.application.job_offer.title} "
            f"was {decision.lower()}: {schedule.scheduled_at.strftime('%Y-%m-%d %H:%M')}."
        )
    ))
    db.session.commit()
    send_preferred_email(
        User.query.get(schedule.jobseeker_id),
        "notify_email_interview_updates",
        f"Interview proposal {decision.lower()}: {schedule.application.job_offer.title}",
        (
            f"Your proposed interview time for {schedule.application.job_offer.title} "
            f"was {decision.lower()} by the recruiter.\n\n"
            f"Time: {schedule.scheduled_at.strftime('%Y-%m-%d %H:%M')}"
        ),
    )
    flash(f"Candidate proposal {decision.lower()}.", "success" if decision == "Accepted" else "info")
    return redirect(url_for("interview_calendar"))

@app.route("/applications/<int:app_id>/message", methods=["GET", "POST"])
@recruiter_only
def message_candidate(app):
    if request.method == "POST":
        txt = request.form["message"].strip()
        if txt:
            db.session.add(
                Message(
                    sender_id=current_user.id,
                    recipient_id=app.jobseeker_id,
                    body=txt
                )
            )
            db.session.commit()
            send_preferred_email(
                User.query.get(app.jobseeker_id),
                "notify_email_messages",
                f"New recruiter message about {app.job_offer.title}",
                (
                    f"You received a new message from {current_user.name or current_user.username} "
                    f"about {app.job_offer.title}.\n\n"
                    f"Message: {txt}"
                ),
            )
            flash("Message sent.", "info")
        return redirect(url_for("view_applications"))
    return render_template("message_candidate.html", application=app)

@app.route("/candidates")
@login_required
def view_candidates():
    if current_user.role != "recruiter":
        abort(403)
    jobs = JobOffer.query.filter_by(recruiter_id=current_user.id).all()
    rows = []
    for prof in JobSeekerProfile.query.all():
        scores = {}
        best = 0
        best_job = None
        for job in jobs:
            pct = basic_match_score(prof, job)
            scores[job.id] = pct
            if pct > best:
                best = pct
                best_job = job
        rows.append((prof, scores, best, best_job))
    rows.sort(key=lambda item: item[2], reverse=True)
    avg_best = round(sum(row[2] for row in rows) / (len(rows) or 1))
    strong_count = len([row for row in rows if row[2] >= 75])
    return render_template(
        "candidates.html",
        rows=rows,
        jobs=jobs,
        ai_enabled=gemini_available(),
        avg_best=avg_best,
        strong_count=strong_count
    )


@app.route("/candidates/<int:user_id>/invite", methods=["POST"])
@login_required
def invite_candidate(user_id):
    if current_user.role != "recruiter":
        abort(403)
    job = JobOffer.query.get_or_404(request.form.get("job_id", type=int))
    if job.recruiter_id != current_user.id:
        abort(403)
    JobSeekerProfile.query.filter_by(user_id=user_id).first_or_404()
    message = request.form.get("message", "").strip()
    existing = JobInvitation.query.filter_by(
        recruiter_id=current_user.id,
        jobseeker_id=user_id,
        joboffer_id=job.id,
        status="Sent",
    ).first()
    if existing:
        flash("You already invited this candidate to that job.", "info")
        return redirect(url_for("view_candidates"))
    db.session.add(JobInvitation(
        recruiter_id=current_user.id,
        jobseeker_id=user_id,
        joboffer_id=job.id,
        message=message,
    ))
    db.session.add(Message(
        sender_id=current_user.id,
        recipient_id=user_id,
        body=(
            f"You are invited to apply for {job.title}."
            + (f" {message}" if message else "")
        )
    ))
    db.session.commit()
    send_preferred_email(
        User.query.get(user_id),
        "notify_email_job_invitations",
        f"Job invitation: {job.title}",
        (
            f"{current_user.name or current_user.username} invited you to apply for "
            f"{job.title} on Jobify.ro."
            + (f"\n\nRecruiter message: {message}" if message else "")
        ),
    )
    flash("Job invitation sent.", "success")
    return redirect(url_for("view_candidates"))

@app.route("/ai/match/<int:job_id>/<int:user_id>")
@login_required
def ai_match_report(job_id, user_id):
    job = JobOffer.query.get_or_404(job_id)
    allowed_recruiter = current_user.role == "recruiter" and job.recruiter_id == current_user.id
    allowed_jobseeker = current_user.role == "jobseeker" and current_user.id == user_id
    if not (allowed_recruiter or allowed_jobseeker):
        abort(403)
    prof = JobSeekerProfile.query.filter_by(user_id=user_id).first_or_404()
    report = analyze_candidate_fit(prof, job)
    return render_template(
        "ai_match_report.html",
        job=job,
        profile=prof,
        report=report,
        ai_configured=gemini_available()
    )

@app.route("/ai/status")
@login_required
def ai_status():
    status = check_gemini_connection()
    if request.args.get("format") == "json":
        return jsonify(status)
    return render_template("ai_status.html", status=status)

@app.route("/dashboard/jobseeker")
@login_required
def dashboard_jobseeker():
    if current_user.role != "jobseeker":
        abort(403)
    prof = JobSeekerProfile.query.filter_by(user_id=current_user.id).first()
    if enrich_profile_from_cv(prof):
        db.session.commit()
    unread_decisions = Application.query.filter_by(
        jobseeker_id=current_user.id, is_read_user=False
    ).filter(Application.status != "Pending").all()
    for d in unread_decisions:
        d.is_read_user = True
    db.session.commit()
    decisions = Application.query.filter_by(
        jobseeker_id=current_user.id
    ).filter(Application.status != "Pending").order_by(Application.applied_on.desc()).limit(5).all()

    recommendations = []
    saved_job_ids = set()
    all_jobs = JobOffer.query.all()
    all_apps = Application.query.filter_by(jobseeker_id=current_user.id).all()
    saved_job_ids = {
        row.joboffer_id
        for row in SavedJob.query.filter_by(jobseeker_id=current_user.id).all()
    }
    profile_dashboard = candidate_profile_dashboard(prof, all_jobs, all_apps, current_user) if prof else None
    market_insights = job_market_insights(prof, all_jobs)
    invitations = JobInvitation.query.filter_by(
        jobseeker_id=current_user.id
    ).order_by(JobInvitation.created_at.desc()).limit(5).all()
    if prof and prof.skills:
        for j in all_jobs:
            pct = basic_match_score(prof, j)
            have = {
                s.strip().lower()
                for s in (prof.skills or "").split(",") if s.strip()
            }
            req = {
                r.strip().lower()
                for r in (j.required_skills or "").split(",") if r.strip()
            }
            missing = sorted(req - have)
            recommendations.append((j, pct, missing))
        recommendations = sorted(recommendations, key=lambda x: x[1], reverse=True)[:3]

    return render_template(
        "dashboard_jobseeker.html",
        profile=prof,
        profile_dashboard=profile_dashboard,
        market_insights=market_insights,
        decisions=decisions,
        invitations=invitations,
        recommendations=recommendations,
        saved_job_ids=saved_job_ids,
        ai_enabled=gemini_available()
    )

@app.route("/upload_cv", methods=["POST"])
@login_required
def upload_cv():
    if current_user.role != "jobseeker":
        abort(403)
    f = request.files.get("cv_file")
    if not f or not f.filename:
        flash("No file selected.", "danger")
        return redirect(url_for("dashboard_jobseeker"))

    fn = f"{current_user.id}_{secure_filename(f.filename)}"
    full_path = os.path.join(current_app.config["UPLOAD_FOLDER"], fn)
    f.save(full_path)

    ai_profile = None
    local_profile = None
    try:
        cv_text = extract_text(full_path)
        ai_profile = extract_profile_from_cv_text(cv_text)
        local_profile = extract_profile_locally_from_cv_text(cv_text)
    except Exception:
        ai_profile = None

    if ai_profile and ai_profile["skills"]:
        skills = ai_profile["skills"]
    elif local_profile and local_profile["skills"]:
        skills = local_profile["skills"]
    else:
        skills = extract_skills_from_cv(full_path)
    prof = JobSeekerProfile.query.filter_by(user_id=current_user.id).first()
    if not prof:
        prof = JobSeekerProfile(user_id=current_user.id)
        db.session.add(prof)
    prof.cv_path = fn
    prof.skills = ",".join(skills)
    parsed_profile = ai_profile or local_profile or {}
    if parsed_profile:
        prof.name = parsed_profile.get("name") or prof.name
        prof.email = parsed_profile.get("email") or prof.email
        prof.phone = parsed_profile.get("phone") or prof.phone
        prof.summary = parsed_profile.get("summary") or prof.summary
        prof.experience = parsed_profile.get("experience") or prof.experience
        prof.education = parsed_profile.get("education") or prof.education
    if ai_profile:
        prof.languages = ",".join(ai_profile["languages"]) or prof.languages
        prof.certificates = ",".join(ai_profile["certificates"]) or prof.certificates
    db.session.commit()

    if ai_profile:
        flash("CV uploaded and analyzed with AI.", "success")
    elif local_profile:
        flash("CV uploaded and analyzed locally.", "success")
    else:
        flash("CV uploaded. Add GEMINI_API_KEY to enable deeper AI analysis.", "success")
    return redirect(url_for("dashboard_jobseeker"))

@app.route("/uploads/<path:filename>")
def serve_upload(filename):
    uploads = current_app.config["UPLOAD_FOLDER"]
    safe_name = secure_filename(filename)
    full_path = os.path.join(uploads, safe_name)
    if not os.path.isfile(full_path):
        abort(404)
    return send_from_directory(uploads, safe_name, as_attachment=True)

@app.route("/download_cv/<int:user_id>")
@login_required
def download_cv(user_id):
    if current_user.role != "recruiter":
        abort(403)
    prof = JobSeekerProfile.query.filter_by(user_id=user_id).first_or_404()
    if not prof.cv_path:
        flash("This candidate hasn’t uploaded a CV yet.", "warning")
        return redirect(url_for("view_candidates"))
    return send_from_directory(
        app.config["UPLOAD_FOLDER"],
        prof.cv_path,
        as_attachment=True
    )

@app.route("/build_cv/improve", methods=["POST"])
@login_required
def improve_cv():
    if current_user.role != "jobseeker":
        abort(403)
    payload = request.get_json(silent=True) or {}
    cv_data = {
        "name": payload.get("name", "").strip(),
        "email": payload.get("email", "").strip(),
        "phone": payload.get("phone", "").strip(),
        "summary": payload.get("summary", "").strip(),
        "skills": payload.get("skills", "").strip(),
        "experience": payload.get("experience", "").strip(),
        "education": payload.get("education", "").strip(),
    }
    return jsonify(improve_cv_content(cv_data))

@app.route("/build_cv", methods=["GET", "POST"])
@login_required
def build_cv():
    if current_user.role != "jobseeker":
        abort(403)
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        phone = request.form["phone"]
        summary = request.form["summary"]
        skills_str = request.form["skills"]
        experience = request.form["experience"]
        education = request.form["education"]
        template_name = request.form.get("template", "modern")
        accent_color = request.form.get("accent_color", "#0d6efd")
        text_color = request.form.get("text_color", "#000000")
        bg_color = request.form.get("bg_color", "#ffffff")
        photo_file = request.files.get("photo")

        pdf_buffer = io.BytesIO()
        c = canvas.Canvas(pdf_buffer, pagesize=letter)
        w, h = letter

        if not HEX_RE.fullmatch(bg_color):
            bg_color = "#ffffff"
        if not HEX_RE.fullmatch(text_color):
            text_color = "#000000"
        if not HEX_RE.fullmatch(accent_color):
            accent_color = "#0d6efd"

        c.setFillColor(colors.HexColor(bg_color))
        c.rect(0, 0, w, h, fill=1, stroke=0)

        text = colors.HexColor(text_color)
        accent = colors.HexColor(accent_color)

        def draw_wrapped(value, x, y_pos, max_width, font="Helvetica", size=10, leading=13):
            c.setFont(font, size)
            c.setFillColor(text)
            words = (value or "").replace("\r", "").split()
            line = ""
            for word in words:
                candidate = f"{line} {word}".strip()
                if c.stringWidth(candidate, font, size) <= max_width:
                    line = candidate
                else:
                    c.drawString(x, y_pos, line)
                    y_pos -= leading
                    line = word
            if line:
                c.drawString(x, y_pos, line)
                y_pos -= leading
            return y_pos

        def section(title, value, x, y_pos, max_width):
            c.setFillColor(accent)
            c.setFont("Helvetica-Bold", 12)
            c.drawString(x, y_pos, title.upper())
            c.setStrokeColor(accent)
            c.setLineWidth(1)
            c.line(x, y_pos - 4, x + max_width, y_pos - 4)
            return draw_wrapped(value, x, y_pos - 18, max_width) - 8

        if template_name == "classic":
            margin = 54
            y = h - 58
            c.setFillColor(text)
            c.setFont("Times-Bold", 26)
            c.drawCentredString(w / 2, y, name)
            y -= 20
            c.setFont("Helvetica", 10)
            c.drawCentredString(w / 2, y, f"{email} | {phone}")
            y -= 34
            max_width = w - margin * 2
        elif template_name == "compact":
            margin = 42
            c.setFillColor(accent)
            c.rect(0, h - 92, w, 92, fill=1, stroke=0)
            c.setFillColor(colors.white)
            c.setFont("Helvetica-Bold", 24)
            compact_text_width = w - margin * 2
            if photo_file and photo_file.filename:
                compact_text_width -= 92
            c.drawString(margin, h - 44, name[:32])
            c.setFont("Helvetica", 10)
            contact = f"{email}  |  {phone}"
            while c.stringWidth(contact, "Helvetica", 10) > compact_text_width and len(contact) > 8:
                contact = contact[:-2]
            c.drawString(margin, h - 64, contact)
            y = h - 120
            max_width = w - margin * 2
        else:
            margin = 50
            c.setFillColor(accent)
            c.rect(0, 0, 170, h, fill=1, stroke=0)
            c.setFillColor(colors.white)
            c.setFont("Helvetica-Bold", 22)
            c.drawString(28, h - 60, name[:18])
            c.setFont("Helvetica", 9)
            c.drawString(28, h - 82, email[:28])
            c.drawString(28, h - 98, phone[:28])
            y = h - 58
            margin = 195
            max_width = w - margin - 45

        if photo_file and photo_file.filename:
            try:
                photo = ImageReader(photo_file)
                if template_name == "modern":
                    c.drawImage(photo, 48, h - 205, 72, 72, preserveAspectRatio=True)
                elif template_name == "compact":
                    c.drawImage(photo, w - 112, h - 82, 58, 58, preserveAspectRatio=True)
                else:
                    c.drawImage(photo, w - 126, h - 142, 72, 72, preserveAspectRatio=True)
                    y = min(y, h - 166)
            except Exception:
                pass

        y = section("Profile", summary, margin, y, max_width)
        skills = [s.strip() for s in skills_str.split(",") if s.strip()]
        c.setFillColor(accent)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(margin, y, "SKILLS")
        c.line(margin, y - 4, margin + max_width, y - 4)
        y -= 20
        c.setFont("Helvetica", 9)
        c.setFillColor(text)
        line = ""
        for skill in skills:
            candidate = f"{line}  |  {skill}".strip(" |")
            if c.stringWidth(candidate, "Helvetica", 9) <= max_width:
                line = candidate
            else:
                c.drawString(margin, y, line)
                y -= 13
                line = skill
        if line:
            c.drawString(margin, y, line)
            y -= 18
        y = section("Experience", experience, margin, y, max_width)
        y = section("Education", education, margin, y, max_width)

        c.showPage()
        c.save()
        pdf_buffer.seek(0)

        return send_file(
            pdf_buffer,
            as_attachment=True,
            download_name="cv.pdf",
            mimetype="application/pdf"
        )
    return render_template("build_cv.html")

@app.route("/how_to_find_job")
def how_to_find_job():
    """
    This backs the <a href="{{ url_for('how_to_find_job') }}"> link
    in your login.html. Make sure you have templates/how_to_find_job.html.
    """
    return render_template("how_to_find_job.html")

@app.route("/news")
def news_list():
    page = request.args.get("page", 1, type=int)
    pagination = (
        News.query
            .order_by(News.created_at.desc())
            .paginate(page=page, per_page=5)
    )
    return render_template("news_list.html", pagination=pagination)

@app.route("/articles")
def article_list():
    page = request.args.get("page", 1, type=int)
    pagination = (
        Article.query
            .order_by(Article.created_at.desc())
            .paginate(page=page, per_page=5)
    )
    return render_template("article_list.html", pagination=pagination)

@app.route("/my_applications")
@login_required
def my_applications():
    if current_user.role != "jobseeker":
        abort(403)
    apps = Application.query.join(JobOffer).filter(
        Application.jobseeker_id == current_user.id
    ).order_by(Application.applied_on.desc()).all()
    for a in apps:
        if a.status != "Pending" and not a.is_read_user:
            a.is_read_user = True
    db.session.commit()
    return render_template("my_applications.html", applications=apps)


@app.route("/notifications")
@login_required
def notifications():
    items = build_notification_center(current_user)
    action_count = sum(1 for item in items if item["status"] in {"Unread", "New", "Action needed"})
    message_count = sum(1 for item in items if item["type"] == "Message")
    interview_count = sum(1 for item in items if item["type"] == "Interview")
    return render_template(
        "notifications.html",
        notifications=items,
        action_count=action_count,
        message_count=message_count,
        interview_count=interview_count,
    )


@app.route("/notification-settings", methods=["GET", "POST"])
@login_required
def notification_settings():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "save_email":
            new_email = request.form.get("email", "").strip() or None
            if new_email != current_user.email:
                current_user.email = new_email
                current_user.email_verified = False
                current_user.email_notifications_enabled = False
                current_user.email_verification_code = None
                current_user.email_verification_sent_at = None
            db.session.commit()
            flash("Email saved. Please verify it before enabling email notifications.", "info")

        elif action == "send_code":
            if not current_user.email:
                flash("Add an email address first.", "warning")
            else:
                code = f"{secrets.randbelow(1000000):06d}"
                current_user.email_verification_code = code
                current_user.email_verification_sent_at = datetime.utcnow()
                current_user.email_verified = False
                db.session.commit()
                sent = send_email(
                    current_user.email,
                    "Your Jobify.ro email verification code",
                    f"Your Jobify.ro verification code is: {code}\n\nIf you did not request this, you can ignore this email."
                )
                flash(
                    "Verification code sent to your email." if sent else "Verification code created, but email sending is not configured. Check MAIL settings in .env.",
                    "success" if sent else "warning"
                )

        elif action == "verify_code":
            code = request.form.get("code", "").strip()
            is_fresh = bool(
                current_user.email_verification_sent_at and
                current_user.email_verification_sent_at >= datetime.utcnow() - timedelta(minutes=20)
            )
            if code and code == current_user.email_verification_code and is_fresh:
                current_user.email_verified = True
                current_user.email_verification_code = None
                current_user.email_verification_sent_at = None
                db.session.commit()
                flash("Email verified successfully.", "success")
            else:
                flash("Invalid or expired verification code.", "danger")

        elif action == "save_preferences":
            wants_email = "email_notifications_enabled" in request.form
            if wants_email and not current_user.email_verified:
                current_user.email_notifications_enabled = False
                flash("Verify your email before enabling email notifications.", "warning")
            else:
                current_user.email_notifications_enabled = wants_email
                current_user.notify_email_job_invitations = "job_invitations" in request.form
                current_user.notify_email_application_decisions = "application_decisions" in request.form
                current_user.notify_email_interview_updates = "interview_updates" in request.form
                current_user.notify_email_new_applications = "new_applications" in request.form
                current_user.notify_email_messages = "messages" in request.form
                db.session.commit()
                flash("Notification preferences updated.", "success")
        return redirect(url_for("notification_settings"))

    return render_template(
        "notification_settings.html",
        mail_configured=mail_configured(),
    )

@app.route("/jobs")
@login_required
def job_list():
    q = request.args.get("q", "")
    city = request.args.get("city", "")
    cat = request.args.get("cat", "")

    jobs_q = JobOffer.query
    if q:
        jobs_q = jobs_q.filter(JobOffer.title.ilike(f"%{q}%"))
    if city:
        jobs_q = jobs_q.filter(JobOffer.city.ilike(f"%{city}%"))
    if cat:
        jobs_q = jobs_q.filter(JobOffer.category == cat)

    page = request.args.get("page", 1, int)
    per_page = 5
    profile = None
    match_scores = {}
    missing_skills = {}
    gap_reports = {}
    sorted_by_match = False
    saved_job_ids = set()

    if current_user.role == "jobseeker":
        profile = JobSeekerProfile.query.filter_by(user_id=current_user.id).first()
        saved_job_ids = {
            row.joboffer_id
            for row in SavedJob.query.filter_by(jobseeker_id=current_user.id).all()
        }

    if profile and profile.skills:
        jobs = jobs_q.all()
        have = {
            s.strip().lower()
            for s in (profile.skills or "").split(",") if s.strip()
        }
        for job in jobs:
            report = skill_gap_analysis(profile, job)
            gap_reports[job.id] = report
            match_scores[job.id] = report["score"]
            missing_skills[job.id] = report["missing"]
        jobs.sort(key=lambda job: (match_scores.get(job.id, 0), job.id), reverse=True)
        total = len(jobs)
        start = (page - 1) * per_page
        pag = SimplePagination(jobs[start:start + per_page], page, per_page, total)
        sorted_by_match = True
    else:
        pag = jobs_q.order_by(JobOffer.id.desc()).paginate(page=page, per_page=per_page)

    rows = db.session.query(
        JobOffer.city, db.func.count(JobOffer.id).label("cnt")
    ).group_by(JobOffer.city).all()
    city_counts = [(r[0], r[1]) for r in rows if r[0]]

    markers = marker_payload_from_jobs(jobs_q.all())

    return render_template(
        "job_list.html",
        pagination=pag,
        query=q,
        filter_city=city,
        filter_cat=cat,
        categories=CATEGORIES,
        city_counts=city_counts,
        markers=markers,
        match_scores=match_scores,
        missing_skills=missing_skills,
        gap_reports=gap_reports,
        sorted_by_match=sorted_by_match,
        best_match=max(match_scores.values()) if match_scores else None,
        saved_job_ids=saved_job_ids,
    )


@app.route("/jobs/<int:job_id>/save", methods=["POST"])
@login_required
def toggle_save_job(job_id):
    if current_user.role != "jobseeker":
        abort(403)
    JobOffer.query.get_or_404(job_id)
    saved = SavedJob.query.filter_by(
        jobseeker_id=current_user.id,
        joboffer_id=job_id
    ).first()
    if saved:
        db.session.delete(saved)
        flash("Job removed from saved jobs.", "info")
    else:
        db.session.add(SavedJob(jobseeker_id=current_user.id, joboffer_id=job_id))
        flash("Job saved.", "success")
    db.session.commit()
    return redirect(request.referrer or url_for("job_list"))


@app.route("/saved-jobs")
@login_required
def saved_jobs():
    if current_user.role != "jobseeker":
        abort(403)
    rows = SavedJob.query.filter_by(
        jobseeker_id=current_user.id
    ).order_by(SavedJob.saved_at.desc()).all()
    profile = JobSeekerProfile.query.filter_by(user_id=current_user.id).first()
    match_scores = {}
    gap_reports = {}
    if profile:
        for row in rows:
            gap = skill_gap_analysis(profile, row.job_offer)
            match_scores[row.joboffer_id] = gap["score"]
            gap_reports[row.joboffer_id] = gap
    return render_template(
        "saved_jobs.html",
        saved_jobs=rows,
        match_scores=match_scores,
        gap_reports=gap_reports,
    )


@app.route("/interview-calendar")
@login_required
def interview_calendar():
    if current_user.role == "recruiter":
        interviews = InterviewSchedule.query.filter_by(recruiter_id=current_user.id).order_by(InterviewSchedule.scheduled_at.desc()).all()
    else:
        interviews = InterviewSchedule.query.filter_by(jobseeker_id=current_user.id).order_by(InterviewSchedule.scheduled_at.desc()).all()
    return render_template("interview_calendar.html", interviews=interviews)

@app.route("/jobs/<int:job_id>/apply", methods=["GET", "POST"])
@login_required
def apply_job(job_id):
    if current_user.role != "jobseeker":
        abort(403)
    job = JobOffer.query.get_or_404(job_id)
    prof = JobSeekerProfile.query.filter_by(user_id=current_user.id).first()
    if not prof or not prof.cv_path:
        flash("Upload or build a CV first.", "danger")
        return redirect(url_for("dashboard_jobseeker"))

    dup = Application.query.filter_by(
        joboffer_id=job_id,
        jobseeker_id=current_user.id,
        status="Pending"
    ).first()
    if dup:
        flash("Already applied—await feedback.", "info")
        return redirect(url_for("my_applications"))

    if request.method == "POST":
        a = Application(
            joboffer_id=job_id,
            jobseeker_id=current_user.id,
            cover_letter=request.form["cover_letter"],
            applied_on=datetime.utcnow()
        )
        db.session.add(a)
        db.session.commit()
        send_preferred_email(
            User.query.get(job.recruiter_id),
            "notify_email_new_applications",
            f"New application: {job.title}",
            (
                f"{current_user.name or current_user.username} applied for {job.title} "
                "on Jobify.ro.\n\n"
                f"Candidate email: {current_user.email or 'not provided'}"
            ),
        )
        flash("Application submitted!", "success")
        return redirect(url_for("my_applications"))

    gap_report = skill_gap_analysis(prof, job)
    return render_template("apply_job.html", offer=job, gap_report=gap_report)

@app.route("/jobs/<int:job_id>/cover-letter", methods=["POST"])
@login_required
def cover_letter_generator(job_id):
    if current_user.role != "jobseeker":
        abort(403)
    job = JobOffer.query.get_or_404(job_id)
    prof = JobSeekerProfile.query.filter_by(user_id=current_user.id).first()
    if not prof:
        return jsonify({
            "ai_used": False,
            "error": "Create or upload a CV profile before generating a cover letter.",
            "cover_letter": "",
            "tips": ["Upload a CV first so Jobify can tailor the letter to your profile."],
        }), 400
    return jsonify(generate_cover_letter(prof, job))

@app.route("/interview-simulator")
@login_required
def interview_simulator():
    if current_user.role != "jobseeker":
        abort(403)
    prof = JobSeekerProfile.query.filter_by(user_id=current_user.id).first()
    jobs = JobOffer.query.order_by(JobOffer.id.desc()).all()
    match_scores = {}
    if prof:
        match_scores = {job.id: basic_match_score(prof, job) for job in jobs}
        jobs.sort(key=lambda job: (match_scores.get(job.id, 0), job.id), reverse=True)
    sessions = InterviewSession.query.filter_by(
        jobseeker_id=current_user.id
    ).order_by(InterviewSession.created_at.desc()).limit(6).all()
    return render_template(
        "interview_simulator.html",
        profile=prof,
        jobs=jobs,
        match_scores=match_scores,
        sessions=sessions,
        ai_enabled=gemini_available(),
    )

@app.route("/interview-simulator/start", methods=["POST"])
@login_required
def start_interview():
    if current_user.role != "jobseeker":
        abort(403)
    job = JobOffer.query.get_or_404(request.form.get("job_id", type=int))
    prof = JobSeekerProfile.query.filter_by(user_id=current_user.id).first()
    if not prof:
        flash("Upload or build a CV first so the simulator can personalize questions.", "warning")
        return redirect(url_for("dashboard_jobseeker"))

    generated = generate_interview_questions(prof, job)
    session_obj = InterviewSession(
        joboffer_id=job.id,
        jobseeker_id=current_user.id,
        questions_json=json.dumps(generated["questions"], ensure_ascii=False),
        ai_used=generated.get("ai_used", False),
    )
    db.session.add(session_obj)
    db.session.commit()
    if generated.get("error"):
        flash(generated["error"], "info")
    return redirect(url_for("take_interview", session_id=session_obj.id))

@app.route("/interview-simulator/<int:session_id>", methods=["GET", "POST"])
@login_required
def take_interview(session_id):
    if current_user.role != "jobseeker":
        abort(403)
    session_obj = InterviewSession.query.get_or_404(session_id)
    if session_obj.jobseeker_id != current_user.id:
        abort(403)
    prof = JobSeekerProfile.query.filter_by(user_id=current_user.id).first()
    questions = json.loads(session_obj.questions_json or "[]")
    answers = json.loads(session_obj.answers_json or "[]") if session_obj.answers_json else []
    feedback = json.loads(session_obj.feedback_json or "{}") if session_obj.feedback_json else None

    if request.method == "POST":
        answers = [
            request.form.get(f"answer_{idx}", "").strip()
            for idx in range(len(questions))
        ]
        if any(not answer for answer in answers):
            flash("Answer all 5 questions before requesting feedback.", "warning")
        else:
            feedback = evaluate_interview_answers(prof, session_obj.job_offer, questions, answers)
            session_obj.answers_json = json.dumps(answers, ensure_ascii=False)
            session_obj.feedback_json = json.dumps(feedback, ensure_ascii=False)
            session_obj.ai_used = bool(session_obj.ai_used or feedback.get("ai_used"))
            session_obj.status = "Completed"
            session_obj.completed_at = datetime.utcnow()
            db.session.commit()
            if feedback.get("error"):
                flash(feedback["error"], "info")
            return redirect(url_for("take_interview", session_id=session_obj.id))

    return render_template(
        "interview_take.html",
        interview=session_obj,
        questions=questions,
        answers=answers,
        feedback=feedback,
    )

@app.route("/inbox")
@login_required
def inbox():
    now = datetime.utcnow()
    ids = {
        m.sender_id for m in Message.query.filter(
            Message.recipient_id == current_user.id,
            ((Message.scheduled_for.is_(None)) | (Message.scheduled_for <= now))
        )
    } | {
        m.recipient_id for m in Message.query.filter_by(sender_id=current_user.id)
    }
    ids.discard(current_user.id)

    partners = User.query.filter(User.id.in_(ids)).all()
    conversation_meta = {}
    for partner in partners:
        messages = conversation_messages(current_user.id, partner.id, include_future_sender=True)
        last = messages[-1] if messages else None
        unread = sum(1 for msg in messages if msg.recipient_id == current_user.id and not msg.is_read)
        conversation_meta[partner.id] = {
            "last": last,
            "unread": unread,
            "online": is_online(partner),
        }

    blocked = {b.blocked_id for b in Block.query.filter_by(blocker_id=current_user.id)}
    return render_template(
        "inbox.html",
        partners=partners,
        blocked_ids=blocked,
        conversation_meta=conversation_meta,
        now=now,
    )


def is_online(user):
    return bool(user.last_seen and user.last_seen >= datetime.utcnow() - timedelta(minutes=5))


def conversation_messages(user_id, partner_id, include_future_sender=False):
    now = datetime.utcnow()
    visible = (
        (Message.scheduled_for.is_(None)) |
        (Message.scheduled_for <= now)
    )
    if include_future_sender:
        visible = visible | ((Message.sender_id == user_id) & (Message.scheduled_for > now))
    return Message.query.filter(
        (
            ((Message.sender_id == user_id) & (Message.recipient_id == partner_id)) |
            ((Message.sender_id == partner_id) & (Message.recipient_id == user_id))
        ) & visible
    ).order_by(Message.timestamp).all()


def partner_profile_context(other):
    if other.role == "recruiter":
        return {
            "jobs": JobOffer.query.filter_by(recruiter_id=other.id).order_by(JobOffer.id.desc()).all(),
            "profile": None,
        }
    return {
        "jobs": [],
        "profile": JobSeekerProfile.query.filter_by(user_id=other.id).first(),
    }


@app.route("/chat/<int:uid>", methods=["GET", "POST"])
@login_required
def chat(uid):
    other = User.query.get_or_404(uid)
    if other.role == current_user.role:
        abort(403)

    # ─── Block check ──────────────────────────────────────────────
    already_blocked = Block.query.filter_by(
        blocker_id=current_user.id, blocked_id=uid
    ).first() or Block.query.filter_by(
        blocker_id=uid, blocked_id=current_user.id
    ).first()
    if already_blocked:
        flash("Cannot open chat: one of you has blocked the other.", "warning")
        return redirect(url_for("inbox"))
    # ────────────────────────────────────────────────────────────────

    if request.method == "POST":
        txt = request.form.get("body", "").strip()
        scheduled_for = None
        raw_schedule = request.form.get("scheduled_for", "").strip()
        if raw_schedule:
            try:
                scheduled_for = datetime.strptime(raw_schedule, "%Y-%m-%dT%H:%M")
                if scheduled_for <= datetime.utcnow():
                    scheduled_for = None
            except ValueError:
                scheduled_for = None

        attachment = request.files.get("attachment")
        attachment_filename = None
        attachment_original = None
        if attachment and attachment.filename:
            if allowed_chat_attachment(attachment.filename):
                attachment_original = secure_filename(attachment.filename)
                attachment_filename = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}_{current_user.id}_{attachment_original}"
                attachment.save(os.path.join(CHAT_UPLOAD_FOLDER, attachment_filename))
            else:
                flash("Unsupported attachment type.", "warning")
                return redirect(url_for("chat", uid=uid))

        if txt or attachment_filename:
            db.session.add(Message(
                sender_id=current_user.id,
                recipient_id=uid,
                body=txt,
                attachment_filename=attachment_filename,
                attachment_original=attachment_original,
                scheduled_for=scheduled_for,
            ))
            db.session.commit()
            if not scheduled_for:
                send_preferred_email(
                    other,
                    "notify_email_messages",
                    f"New message from {current_user.name or current_user.username}",
                    (
                        f"You received a new message on Jobify.ro from "
                        f"{current_user.name or current_user.username}."
                        + (f"\n\nMessage: {txt}" if txt else "\n\nThe message includes an attachment.")
                    ),
                )
        return redirect(url_for("chat", uid=uid))

    msgs = conversation_messages(current_user.id, uid, include_future_sender=True)

    for m in msgs:
        if m.recipient_id == current_user.id and not m.is_read:
            m.is_read = True
            m.read_at = datetime.utcnow()
    db.session.commit()

    return render_template(
        "chat.html",
        other=other,
        messages=msgs,
        other_online=is_online(other),
        profile_context=partner_profile_context(other),
        now=datetime.utcnow(),
    )


@app.route("/chat/message/<int:message_id>/edit", methods=["POST"])
@login_required
def edit_message(message_id):
    msg = Message.query.get_or_404(message_id)
    if msg.sender_id != current_user.id or msg.deleted_at:
        abort(403)
    msg.body = request.form.get("body", "").strip()
    msg.edited_at = datetime.utcnow()
    db.session.commit()
    return redirect(url_for("chat", uid=msg.recipient_id))


@app.route("/chat/message/<int:message_id>/delete", methods=["POST"])
@login_required
def delete_message(message_id):
    msg = Message.query.get_or_404(message_id)
    if msg.sender_id != current_user.id:
        abort(403)
    msg.deleted_at = datetime.utcnow()
    msg.body = ""
    db.session.commit()
    return redirect(url_for("chat", uid=msg.recipient_id))


@app.route("/chat/message/<int:message_id>/react", methods=["POST"])
@login_required
def react_message(message_id):
    msg = Message.query.get_or_404(message_id)
    if current_user.id not in (msg.sender_id, msg.recipient_id):
        abort(403)
    reaction = request.form.get("reaction", "").strip()[:12]
    msg.reaction = "" if msg.reaction == reaction else reaction
    db.session.commit()
    partner_id = msg.sender_id if msg.sender_id != current_user.id else msg.recipient_id
    return redirect(url_for("chat", uid=partner_id))


@app.route("/chat/attachment/<path:filename>")
@login_required
def chat_attachment(filename):
    safe_name = secure_filename(filename)
    msg = Message.query.filter_by(attachment_filename=safe_name).first_or_404()
    if current_user.id not in (msg.sender_id, msg.recipient_id):
        abort(403)
    return send_from_directory(
        CHAT_UPLOAD_FOLDER,
        safe_name,
        as_attachment=request.args.get("download") == "1"
    )

if __name__ == "__main__":
    app.run(debug=False, port=5049, use_reloader=False)
