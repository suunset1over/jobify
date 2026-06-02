from app import app
from extensions import db

print("⚠ Deleting all existing tables...")
with app.app_context():
    db.drop_all()
    db.create_all()
print("✅ Database fully reset & synced to models.")











