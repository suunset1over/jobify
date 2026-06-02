from datetime import datetime
from extensions import db


class JobInvitation(db.Model):
    __tablename__ = "job_invitation"

    id = db.Column(db.Integer, primary_key=True)
    recruiter_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    jobseeker_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    joboffer_id = db.Column(db.Integer, db.ForeignKey("job_offer.id"), nullable=False)
    message = db.Column(db.Text)
    status = db.Column(db.String(20), default="Sent")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    job_offer = db.relationship("JobOffer")
