import os
import pyotp
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db


class User(UserMixin, db.Model):
    __tablename__ = "user"

    #  Core fields 
    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role          = db.Column(db.String(20), nullable=False)       # recruiter | jobseeker

    #  New theming / 2-FA fields 
    brand_color  = db.Column(db.String(7), default="#0d6efd")      # hex color for navbar
    twofa_secret = db.Column(db.String(32))                        

    #  Password helpers 
    @staticmethod
    def generate_password_hash(password: str) -> str:
        return generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    #  Two-factor helpers 
    def init_2fa(self):
        """Create a new base-32 secret if user hasn’t enabled 2-FA yet."""
        if not self.twofa_secret:
            self.twofa_secret = pyotp.random_base32()

    def get_totp(self) -> pyotp.TOTP:
        """Return a TOTP object for this user (init if needed)."""
        if not self.twofa_secret:
            self.init_2fa()
        return pyotp.TOTP(self.twofa_secret)

    def verify_token(self, token: str) -> bool:
        """Check a 6-digit token from authenticator app."""
        if not self.twofa_secret:
            return False
        try:
            return self.get_totp().verify(token, valid_window=1)
        except Exception:
            return False
