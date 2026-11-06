import database
import models
db = next(database.get_db())
try:
    updated = db.query(models.Counselor).filter(models.Counselor.is_admin == 0).update({models.Counselor.is_admin: 1}, synchronize_session=False)
    db.commit()
    print(f"Successfully upgraded {updated} counselor(s) from 'Staff' to 'Admin'.")
except Exception as e:
    print(f"Error during upgrade: {e}")
finally:
    db.close()
