import database
import models
from sqlalchemy import text
db = next(database.get_db())
try:
    db.execute(text("ALTER TABLE activity_logs ADD status NVARCHAR(20) DEFAULT 'pending'"))
    db.commit()
    print("Column added successfully.")
except Exception as e:
    print(f"Error or already exists: {e}")
finally:
    db.close()
