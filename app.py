import os
import re
import io
import base64
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, abort, session
)
from flask_login import (
    login_user, logout_user, login_required, current_user
)
from flask_migrate import Migrate
from itsdangerous import URLSafeSerializer
import pyotp
import qrcode
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader

from extensions        import db

from models.article import Article
from models.news import News
from config import Config
from extensions import db, login_manager
from models.user import User
from models.job_offer import JobOffer
from models.job_seeker import JobSeekerProfile
from models.application import Application
from models.message import Message
from ai.cv_parser import extract_skills_from_cv

# ───────── Fixed 20 job categories ─────────
CATEGORIES = [
    "Software", "Data Science", "DevOps", "UI/UX", "Project Management",
    "Marketing", "Sales", "HR", "Finance", "Customer Support",
    "Product", "QA / Testing", "Security", "AI/ML", "Business Analysis",
    "Content Writing", "Legal", "Operations", "Education", "Healthcare"
]

# ───────── Flask/DB setup ─────────
app = Flask(__name__)
app.config.from_object(Config)
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

db.init_app(app)
login_manager.init_app(app)
Migrate(app, db)

serializer = URLSafeSerializer(app.secret_key, salt="remember-device")

@login_manager.user_loader
def load_user(uid):
    return User.query.get(int(uid))

# ───────── Context globals ─────────
@app.context_processor
def inject_globals():
    msg_badge = apps_badge = dec_badge = 0
    brand = "#0d6efd"
    if current_user.is_authenticated:
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
        brand_color=brand
    )

# Public detail pages
@app.route("/article/<int:aid>")
def article_detail(aid):
    return render_template(
        "article_detail.html",
        article=Article.query.get_or_404(aid)
    )

@app.route("/news/<int:nid>")
def news_detail(nid):
    return render_template(
        "news_detail.html",
        news=News.query.get_or_404(nid)
    )

#  Lists (with pagination) 
@app.route("/articles")
def article_list():
    page = request.args.get("page", 1, int)
    pag = Article.query.order_by(
        Article.created_at.desc()
    ).paginate(page=page, per_page=6)
    return render_template("article_list.html", pagination=pag)

@app.route("/news")
@login_required
def news_list():
    page = request.args.get("page", 1, int)
    pag = News.query.order_by(
        News.created_at.desc()
    ).paginate(page=page, per_page=6)
    return render_template("news_list.html", pagination=pag)

#  Helpers 
def trusted_device(user):
    cookie = request.cookies.get("remember_device")
    if not cookie:
        return False
    try:
        return int(serializer.loads(cookie)) == user.id
    except Exception:
        return False

# ───────── Auth & 2-FA ─────────
@app.route("/")
def index():
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
        u = User(
            username=request.form["username"],
            password_hash=User.generate_password_hash(request.form["password"]),
            role=request.form["role"]
        )
        db.session.add(u)
        db.session.commit()
        flash("Registered! Log in.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/work-friendship-quiz")
def work_friendship_quiz():
    return render_template("quiz_friendship.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = User.query.filter_by(username=request.form["username"]).first()
        if u and u.check_password(request.form["password"]):
            if u.twofa_secret and not trusted_device(u):
                session["pre_2fa"] = u.id
                return redirect(url_for("twofa"))
            login_user(u)
            return redirect(url_for("index"))
        flash("Invalid credentials.", "danger")

    # data for public landing (mini-map + counts + banners)
    rows = db.session.query(
        JobOffer.city, db.func.count(JobOffer.id).label("cnt")
    ).group_by(JobOffer.city).all()
    public_counts = [(r[0], r[1]) for r in rows if r[0]]

    vacancies = JobOffer.query.count()
    latest_articles = Article.query.order_by(
        Article.created_at.desc()
    ).limit(3).all()
    latest_news = News.query.order_by(
        News.created_at.desc()
    ).limit(3).all()

    return render_template(
        "login.html",
        markers=public_counts,
        vacancies=vacancies,
        latest_articles=latest_articles,
        latest_news=latest_news
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
                    max_age=60*60*24*30,
                    httponly=True
                )
            return resp
        flash("Invalid token.", "danger")
    return render_template("twofa.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

#  Enable / disable 2-FA 
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

    uri = user.get_totp().provisioning_uri(
        user.username, issuer_name="JobMatcher"
    )
    buf = io.BytesIO()
    qrcode.make(uri).save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode()
    return render_template(
        "enable_2fa.html", qr_b64=qr_b64, secret=user.twofa_secret
    )

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

@app.route("/jobs/map")
@login_required
def job_map():
    # grab counts per city
    rows = (
        db.session
          .query(JobOffer.city, db.func.count(JobOffer.id).label("cnt"))
          .group_by(JobOffer.city)
          .all()
    )
    # turn Row objects into plain tuples
    markers = [(city, cnt) for city, cnt in rows if city]

    return render_template("job_map.html", markers=markers)

#  Brand-color for recruiters 
@app.route("/set_brand_color", methods=["POST"])
@login_required
def set_brand_color():
    if current_user.role != "recruiter":
        abort(403)
    color = request.form["brand_color"].strip()
    if re.fullmatch(r"#?[0-9A-Fa-f]{6}", color):
        if not color.startswith("#"):
            color = "#" + color
        current_user.brand_color = color
        db.session.commit()
        flash("Navbar color saved!", "success")
    else:
        flash("Invalid color.", "danger")
    return redirect(url_for("dashboard_recruiter"))

@app.route("/how-to-find-a-job")
def how_to_find_job():
    return render_template("how_to_find_job.html")

#  Recruiter CRUD 
@app.route("/dashboard/recruiter")
@login_required
def dashboard_recruiter():
    if current_user.role != "recruiter":
        abort(403)
    offers = JobOffer.query.filter_by(
        recruiter_id=current_user.id
    ).all()
    return render_template("dashboard_recruiter.html", offers=offers)

@app.route("/post_job", methods=["GET", "POST"])
@login_required
def post_job():
    if current_user.role != "recruiter":
        abort(403)
    if request.method == "POST":
        job = JobOffer(
            recruiter_id=current_user.id,
            title=request.form["title"],
            description=request.form["description"],
            required_skills=request.form["required_skills"],
            min_experience=int(request.form["min_experience"]),
            education_required=request.form["education_required"],
            country=request.form["country"],
            city=request.form["city"],
            category=request.form["category"]
        )
        db.session.add(job)
        db.session.commit()
        flash("Job posted!", "success")
        return redirect(url_for("dashboard_recruiter"))
    return render_template("post_job.html", offer=None, categories=CATEGORIES)

@app.route("/jobs/<int:offer_id>/edit", methods=["GET", "POST"])
@login_required
def edit_job(offer_id):
    if current_user.role != "recruiter":
        abort(403)
    off = JobOffer.query.get_or_404(offer_id)
    if off.recruiter_id != current_user.id:
        abort(403)
    if request.method == "POST":
        for field in (
            "title", "description", "required_skills",
            "min_experience", "education_required",
            "country", "city", "category"
        ):
            val = request.form[field]
            if field == "min_experience":
                val = int(val)
            setattr(off, field, val)
        db.session.commit()
        flash("Job updated.", "success")
        return redirect(url_for("dashboard_recruiter"))
    return render_template("post_job.html", offer=off, categories=CATEGORIES)

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

#  Recruiter view applications & candidates 
@app.route("/applications")
@login_required
def view_applications():
    if current_user.role != "recruiter":
        abort(403)
    apps = Application.query.join(JobOffer).filter(
        JobOffer.recruiter_id == current_user.id
    ).all()
    for a in apps:
        if a.status == "Pending" and not a.is_read_recruiter:
            a.is_read_recruiter = True
    db.session.commit()
    return render_template("applications.html", applications=apps)

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
    flash("Application accepted.", "success")
    return redirect(url_for("view_applications"))

@app.route("/applications/<int:app_id>/reject", methods=["POST"])
@recruiter_only
def reject_application(app):
    app.status = "Rejected"
    app.is_read_user = False
    db.session.commit()
    flash("Application rejected.", "warning")
    return redirect(url_for("view_applications"))

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
            flash("Message sent.", "info")
        return redirect(url_for("view_applications"))
    return render_template(
        "message_candidate.html", application=app
    )

@app.route("/candidates")
@login_required
def view_candidates():
    if current_user.role != "recruiter":
        abort(403)
    jobs = JobOffer.query.filter_by(
        recruiter_id=current_user.id
    ).all()
   

    rows = []
    for prof in JobSeekerProfile.query.all():
        seeker = {
            s.strip().lower()
            for s in (prof.skills or "").split(",") if s.strip()
        }
        scores = {}
        best = 0
        for j in jobs:
            req = {
                r.strip().lower()
                for r in j.required_skills.split(",") if r.strip()
            }
            sc = len(seeker & req) / (len(req) or 1)
            scores[j.id] = round(sc * 100)
            best = max(best, sc)
        rows.append((prof, scores, round(best * 100)))
    rows.sort(key=lambda r: r[2], reverse=True)
    return render_template("candidates.html", rows=rows, jobs=jobs)

#  Job-seeker dashboard & CV tools 
@app.route("/dashboard/jobseeker")
@login_required
def dashboard_jobseeker():
    if current_user.role != "jobseeker":
        abort(403)

    prof = JobSeekerProfile.query.filter_by(
        user_id=current_user.id
    ).first()

    decisions = Application.query.filter_by(
        jobseeker_id=current_user.id, is_read_user=False
    ).filter(Application.status != "Pending").all()
    for d in decisions:
        d.is_read_user = True
    db.session.commit()

    # skill-based recommendations
    recommendations = []
    if prof and prof.skills:
        have = {
            s.strip().lower()
            for s in prof.skills.split(",") if s.strip()
        }
        for j in JobOffer.query.all():
            req = {
                r.strip().lower()
                for r in j.required_skills.split(",") if r.strip()
            }
            pct = round((len(have & req) / (len(req) or 1)) * 100, 1)
            missing = sorted(req - have)
            recommendations.append((j, pct, missing))
        recommendations = sorted(
            recommendations, key=lambda x: x[1], reverse=True
        )[:3]

    return render_template(
        "dashboard_jobseeker.html",
        profile=prof,
        decisions=decisions,
        recommendations=recommendations
    )

@app.route("/upload_cv", methods=["POST"])
@login_required
def upload_cv():
    if current_user.role != "jobseeker":
        abort(403)
    f = request.files.get("cv_file")
    if not f or not f.filename:
        flash("No file.", "danger")
        return redirect(url_for("dashboard_jobseeker"))

    fn = f"{current_user.id}_{f.filename}"
    path = os.path.join(app.config["UPLOAD_FOLDER"], fn)
    f.save(path)

    skills = extract_skills_from_cv(path)
    prof = JobSeekerProfile.query.filter_by(
        user_id=current_user.id
    ).first()
    if prof:
        prof.cv_path = path
        prof.skills = ",".join(skills)
    else:
        prof = JobSeekerProfile(
            user_id=current_user.id,
            cv_path=path,
            skills=",".join(skills)
        )
        db.session.add(prof)

    db.session.commit()
    flash("CV uploaded.", "success")
    return redirect(url_for("dashboard_jobseeker"))

@app.route("/replace_cv", methods=["POST"])
@login_required
def replace_cv():
    if current_user.role != "jobseeker":
        abort(403)
    f = request.files.get("cv_file")
    if not f or not f.filename:
        flash("No file.", "danger")
        return redirect(url_for("dashboard_jobseeker"))

    fn = f"{current_user.id}_{f.filename}"
    path = os.path.join(app.config["UPLOAD_FOLDER"], fn)
    f.save(path)

    skills = extract_skills_from_cv(path)
    prof = JobSeekerProfile.query.filter_by(
        user_id=current_user.id
    ).first()
    prof.cv_path = path
    prof.skills = ",".join(skills)
    db.session.commit()

    flash("CV replaced.", "success")
    return redirect(url_for("dashboard_jobseeker"))

@app.route("/delete_cv", methods=["POST"])
@login_required
def delete_cv():
    if current_user.role != "jobseeker":
        abort(403)
    prof = JobSeekerProfile.query.filter_by(
        user_id=current_user.id
    ).first()
    if prof and prof.cv_path:
        try:
            os.remove(prof.cv_path)
        except FileNotFoundError:
            pass
        prof.cv_path = ""
        prof.skills = ""
        db.session.commit()
    flash("CV deleted.", "warning")
    return redirect(url_for("dashboard_jobseeker"))

#  CV Builder 
HEX_RE = re.compile(r"#?[0-9A-Fa-f]{6}")
def as_color(hex_str, fallback=colors.black):
    if not HEX_RE.fullmatch(hex_str or ""):
        return fallback
    if not hex_str.startswith("#"):
        hex_str = "#" + hex_str
    return colors.HexColor(hex_str)

@app.route("/build_cv", methods=["GET", "POST"])
@login_required
def build_cv():
    if current_user.role != "jobseeker":
        abort(403)
    if request.method == "POST":
        data = {k: request.form[k] for k in (
            "name", "email", "phone",
            "summary", "skills", "experience", "education"
        )}
        bg = as_color(request.form.get("bg_color", "#ffffff"), colors.white)
        fg = as_color(request.form.get("text_color", "#000000"), colors.black)

        photo = request.files.get("photo")
        photo_path = None
        if photo and photo.filename:
            photo_path = os.path.join(
                app.config["UPLOAD_FOLDER"],
                f"{current_user.id}_photo.jpg"
            )
            photo.save(photo_path)

        pdf_path = os.path.join(
            app.config["UPLOAD_FOLDER"],
            f"{current_user.id}_custom_cv.pdf"
        )
        c = canvas.Canvas(pdf_path, pagesize=letter)
        w, h = letter
        # draw background
        c.setFillColor(bg)
        c.rect(0, 0, w, h, stroke=0, fill=1)
        # header
        c.setFillColor(fg)
        c.setFont("Helvetica-Bold", 20)
        y = h - 60
        c.drawString(50, y, data["name"])
        y -= 22
        c.setFont("Helvetica", 12)
        c.drawString(50, y, data["email"])
        y -= 15
        c.drawString(50, y, data["phone"])
        y -= 25
        if photo_path:
            c.drawImage(
                ImageReader(photo_path),
                w - 150, h - 200, 100, 130,
                preserveAspectRatio=True
            )
        def heading(t):
            nonlocal y
            y -= 10
            c.setFont("Helvetica-Bold", 14)
            c.drawString(50, y, t)
            y -= 18
            c.setFont("Helvetica", 12)

        heading("PROFILE")
        c.drawString(50, y, data["summary"])
        y -= 30
        heading("SKILLS")
        for sk in data["skills"].split(","):
            sk = sk.strip()
            if sk:
                c.drawString(50, y, f"• {sk}")
                y -= 14
        y -= 10
        heading("EXPERIENCE")
        c.drawString(50, y, data["experience"])
        y -= 30
        heading("EDUCATION")
        c.drawString(50, y, data["education"])
        c.save()

        prof = JobSeekerProfile.query.filter_by(
            user_id=current_user.id
        ).first()
        if prof:
            prof.cv_path = pdf_path
            prof.skills  = data["skills"]
        else:
            db.session.add(
                JobSeekerProfile(
                    user_id=current_user.id,
                    cv_path=pdf_path,
                    skills=data["skills"]
                )
            )
        db.session.commit()
        flash("CV generated & saved.", "success")
        return redirect(url_for("dashboard_jobseeker"))

    return render_template("build_cv.html")

#  My applications 
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

@app.route('/account-settings', methods=['GET', 'POST'])
@login_required
def account_settings():
    # handle email/password/etc. updates here
    if request.method=='POST':
        # e.g. current_user.email = request.form['email']; db.session.commit()
        flash('Account settings saved.', 'success')
    return render_template('account_settings.html')

@app.route('/category-settings', methods=['GET', 'POST'])
@login_required
def category_settings():
    if request.method=='POST':
        # save their preferred categories
        flash('Category settings saved.', 'success')
    return render_template('category_settings.html', categories=CATEGORIES)


#  Job board & apply 
@app.route("/jobs")
@login_required
def job_list():
    q    = request.args.get("q", "")
    city = request.args.get("city", "")
    cat  = request.args.get("cat", "")

    jobs = JobOffer.query
    if q:
        jobs = jobs.filter(JobOffer.title.ilike(f"%{q}%"))
    if city:
        jobs = jobs.filter(JobOffer.city.ilike(f"%{city}%"))
    if cat:
        jobs = jobs.filter(JobOffer.category == cat)

    page = request.args.get("page", 1, int)
    pag  = jobs.order_by(JobOffer.id.desc()).paginate(page=page, per_page=5)

    rows = db.session.query(
        JobOffer.city, db.func.count(JobOffer.id).label("cnt")
    ).group_by(JobOffer.city).all()
    city_counts = [(r[0], r[1]) for r in rows if r[0]]

    return render_template(
        "job_list.html",
        pagination=pag,
        query=q,
        filter_city=city,
        filter_cat=cat,
        categories=CATEGORIES,
        city_counts=city_counts
    )

@app.route("/jobs/<int:job_id>/apply", methods=["GET","POST"])
@login_required
def apply_job(job_id):
    if current_user.role != "jobseeker":
        abort(403)
    job = JobOffer.query.get_or_404(job_id)
    prof = JobSeekerProfile.query.filter_by(
        user_id=current_user.id
    ).first()
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
        flash("Application submitted!", "success")
        return redirect(url_for("my_applications"))

    return render_template("apply_job.html", offer=job)

#  Inbox & chat 
@app.route("/inbox")
@login_required
def inbox():
    ids = {
        m.sender_id for m in current_user.received_messages
    } | {
        m.recipient_id for m in current_user.sent_messages
    }
    ids.discard(current_user.id)
    partners = User.query.filter(User.id.in_(ids)).all()
    return render_template("inbox.html", partners=partners)

@app.route("/chat/<int:uid>", methods=["GET","POST"])
@login_required
def chat(uid):
    other = User.query.get_or_404(uid)
    if other.role == current_user.role:
        abort(403)
    if request.method == "POST":
        txt = request.form["body"].strip()
        if txt:
            db.session.add(
                Message(
                    sender_id=current_user.id,
                    recipient_id=uid,
                    body=txt
                )
            )
            db.session.commit()
        return redirect(url_for("chat", uid=uid))

    msgs = Message.query.filter(
        ((Message.sender_id==current_user.id)&(Message.recipient_id==uid))|
        ((Message.sender_id==uid)&(Message.recipient_id==current_user.id))
    ).order_by(Message.timestamp).all()
    for m in msgs:
        if m.recipient_id==current_user.id and not m.is_read:
            m.is_read = True
    db.session.commit()
    return render_template("chat.html", other=other, messages=msgs)

if __name__ == "__main__":
    app.run(debug=True, port=5030)
