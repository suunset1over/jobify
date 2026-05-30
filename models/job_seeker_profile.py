from extensions import db

class JobSeekerProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, unique=True)

    # Personal details
    name = db.Column(db.String(100))
    email = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    summary = db.Column(db.Text)
    skills = db.Column(db.Text)
    experience = db.Column(db.Text)
    education = db.Column(db.Text)
    languages = db.Column(db.Text)
    certificates = db.Column(db.Text)
    desired_salary_gross = db.Column(db.Integer)
    desired_salary_net = db.Column(db.Integer)

    # Design fields
    font_family = db.Column(db.String(50))
    photo_shape = db.Column(db.String(20))
    text_color = db.Column(db.String(20))
    background_color = db.Column(db.String(20))

    # Files
    photo_filename = db.Column(db.String(200))
    cv_path = db.Column(db.String(200))
