from extensions import db

class JobOffer(db.Model):
    __tablename__ = "job_offer"

    id               = db.Column(db.Integer, primary_key=True)
    recruiter_id     = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    title            = db.Column(db.String(120), nullable=False)
    description      = db.Column(db.Text,        nullable=False)
    required_skills  = db.Column(db.Text)
    min_experience   = db.Column(db.Integer)
    education_required = db.Column(db.String(120))

    country          = db.Column(db.String(80), nullable=False, default="Unknown")
    city             = db.Column(db.String(80), nullable=False, default="Unknown")
    category         = db.Column(db.String(40), nullable=False, default="Other")

    latitude         = db.Column(db.Float, nullable=True)
    longitude        = db.Column(db.Float, nullable=True)
