from extensions import db
from sqlalchemy.dialects.sqlite import JSON

class JobOffer(db.Model):

    __tablename__ = "job_offer"

    id          = db.Column(db.Integer, primary_key=True)
    recruiter_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    title       = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text,        nullable=False)

    required_skills    = db.Column(db.Text)          # comma-separated list
    min_experience     = db.Column(db.Integer)       # years
    education_required = db.Column(db.String(120))

    country  = db.Column(db.String(80),  nullable=False, default="Unknown")
    city     = db.Column(db.String(80),  nullable=False, default="Unknown")
    category = db.Column(db.String(40),  nullable=False, default="Other")


