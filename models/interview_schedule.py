from datetime import datetime
from extensions import db


class InterviewSchedule(db.Model):
    __tablename__ = "interview_schedule"

    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey("application.id"), nullable=False)
    recruiter_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    jobseeker_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    scheduled_at = db.Column(db.DateTime, nullable=False)
    location = db.Column(db.String(200))
    note = db.Column(db.Text)
    status = db.Column(db.String(20), default="Proposed")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    responded_at = db.Column(db.DateTime)

    application = db.relationship(
        "Application",
        backref=db.backref("interview_schedules", lazy=True)
    )
