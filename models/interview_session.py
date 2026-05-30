from datetime import datetime
from extensions import db


class InterviewSession(db.Model):
    __tablename__ = "interview_session"

    id = db.Column(db.Integer, primary_key=True)
    joboffer_id = db.Column(db.Integer, db.ForeignKey("job_offer.id"), nullable=False)
    jobseeker_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    questions_json = db.Column(db.Text, nullable=False)
    answers_json = db.Column(db.Text)
    feedback_json = db.Column(db.Text)
    ai_used = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(20), default="In progress")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)

    job_offer = db.relationship(
        "JobOffer",
        backref=db.backref("interview_sessions", lazy=True)
    )
