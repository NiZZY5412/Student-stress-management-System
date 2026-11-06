import database
import models
db = next(database.get_db())
try:
    # Get all student IDs who have at least one High Stress (2) result
    high_stress_ids = {r.user_id for r in db.query(models.SurveyResult).filter(models.SurveyResult.predicted_stress == 2).all()}
    
    # Update those students to 'flagged' status if they aren't already resolved
    updated = db.query(models.User).filter(
        models.User.id.in_(high_stress_ids),
        models.User.role == 'student',
        models.User.status != 'resolved' # Don't re-flag someone who was already cleared
    ).update({models.User.status: 'flagged'}, synchronize_session=False)
    
    db.commit()
    print(f"Stats Synced: {updated} students are now correctly counted as 'High Risk'.")
except Exception as e:
    print(f"Error syncing stats: {e}")
finally:
    db.close()
