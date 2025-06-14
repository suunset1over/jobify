from extensions import db
from sqlalchemy.dialects.sqlite import JSON


class JobSeekerProfile(db.Model):
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True, nullable=False)
    cv_path = db.Column(db.String(300), nullable=False)
    skills = db.Column(db.String(500), nullable=True)
