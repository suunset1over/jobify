import os

# absolute path to this folder
BASEDIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "you-should-override-this")
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.join(BASEDIR, 'job_matcher.db')}"
    UPLOAD_FOLDER = os.path.join(BASEDIR, "uploads")
    SQLALCHEMY_DATABASE_URI = 'sqlite:///jobify.db'
