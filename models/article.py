from extensions import db
from datetime import datetime

class Article(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    title      = db.Column(db.String(180), nullable=False)
    teaser     = db.Column(db.String(300))
    body       = db.Column(db.Text)
    image_url  = db.Column(db.String(250))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
