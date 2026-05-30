from datetime import datetime
from extensions import db


class SavedJob(db.Model):
    __tablename__ = "saved_job"

    id = db.Column(db.Integer, primary_key=True)
    jobseeker_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    joboffer_id = db.Column(db.Integer, db.ForeignKey("job_offer.id"), nullable=False)
    saved_at = db.Column(db.DateTime, default=datetime.utcnow)

    job_offer = db.relationship(
        "JobOffer",
        backref=db.backref("saved_by", lazy=True)
    )

    __table_args__ = (
        db.UniqueConstraint("jobseeker_id", "joboffer_id", name="uq_saved_job_pair"),
    )
