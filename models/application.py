from datetime import datetime
from sqlalchemy.orm import foreign
from extensions import db
from models.job_seeker import JobSeekerProfile


class Application(db.Model):
    __tablename__ = "application"

    id           = db.Column(db.Integer, primary_key=True)
    joboffer_id  = db.Column(db.Integer, db.ForeignKey("job_offer.id"), nullable=False)
    jobseeker_id = db.Column(db.Integer, db.ForeignKey("user.id"),      nullable=False)
    cover_letter = db.Column(db.Text, nullable=False)
    applied_on   = db.Column(db.DateTime, default=datetime.utcnow)

    status            = db.Column(db.String(20), default="Pending")   # Pending / Accepted / Rejected
    is_read_recruiter = db.Column(db.Boolean, default=False)
    is_read_user      = db.Column(db.Boolean, default=True)

    # parent job
    job_offer = db.relationship("JobOffer",
                                backref=db.backref("applications", lazy=True))

    # candidate profile + CV (eager loaded)
    job_seeker_profile = db.relationship(
        "JobSeekerProfile",
        primaryjoin=foreign(jobseeker_id) == JobSeekerProfile.user_id,
        lazy="joined",
        viewonly=True,
        uselist=False,
    )
