from extensions import db
from datetime import datetime

class Application(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    joboffer_id = db.Column(db.Integer, db.ForeignKey('job_offer.id'), nullable=False)
    jobseeker_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    cover_letter = db.Column(db.Text, nullable=False)
    applied_on = db.Column(db.DateTime, default=datetime.utcnow)

    job_offer = db.relationship('JobOffer', backref=db.backref('applications', lazy=True))
    job_seeker = db.relationship('JobSeekerProfile', backref=db.backref('applications', lazy=True))