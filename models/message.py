from extensions import db
from datetime import datetime

class Message(db.Model):
    __tablename__ = 'message'

    id           = db.Column(db.Integer, primary_key=True)
    sender_id    = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    body         = db.Column(db.Text,    nullable=False)
    timestamp    = db.Column(db.DateTime, default=datetime.utcnow)
    is_read      = db.Column(db.Boolean, default=False)

    sender    = db.relationship(
        'User',
        foreign_keys=[sender_id],
        backref=db.backref('sent_messages', lazy='dynamic')
    )
    recipient = db.relationship(
        'User',
        foreign_keys=[recipient_id],
        backref=db.backref('received_messages', lazy='dynamic')
    )
