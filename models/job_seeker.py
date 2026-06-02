from extensions import db

class JobSeeker(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(120), unique=True)
    phone = db.Column(db.String(20))
    profile = db.Column(db.Text)
    skills = db.Column(db.Text)
    experience = db.Column(db.Text)
    education = db.Column(db.Text)
    photo = db.Column(db.String(200))

    # New fields:
    text_color = db.Column(db.String(20))
    background_color = db.Column(db.String(20))
    font_family = db.Column(db.String(50))  
    languages = db.Column(db.Text)
    certificates = db.Column(db.Text)
    photo_shape = db.Column(db.String(20))
