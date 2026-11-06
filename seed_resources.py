from database import SessionLocal
import models
import datetime

def seed():
    db = SessionLocal()
    # Clear existing resources to avoid duplicates during testing
    db.query(models.Resource).delete()
    
    resources = [
        models.Resource(
            title="Mindfulness Meditation for Focus",
            category="Mindfulness",
            type="Video",
            description="A guided 5-minute meditation to help you regain focus and stay calm during busy study sessions.",
            duration="5 min",
            image_url="https://images.unsplash.com/photo-1506126613408-eca07ce68773?w=800&q=80",
            content_url="https://www.youtube.com/watch?v=inpok4MKVLM"
        ),
        models.Resource(
            title="Deep Sleep Guided Meditation",
            category="Sleep",
            type="Video",
            description="A scientifically designed audio experience to help your mind settle and prepare for restorative sleep.",
            duration="15 min",
            image_url="https://images.unsplash.com/photo-1511295742364-917e70351634?w=800&q=80",
            content_url="https://www.youtube.com/watch?v=18SreazW59s"
        ),
        models.Resource(
            title="Overcoming Academic Burnout",
            category="Academic",
            type="Article",
            description="Learn the signs of burnout and practical strategies to manage your workload effectively.",
            duration="10 min read",
            image_url="https://images.unsplash.com/photo-1434031211128-095490e7e783?w=800&q=80",
            content_url="https://www.healthline.com/health/academic-burnout"
        ),
        models.Resource(
            title="Healthy Sleep Habits for Students",
            category="Sleep",
            type="Article",
            description="Discover how quality sleep impacts your cognitive performance and emotional well-being.",
            duration="7 min read",
            image_url="https://images.unsplash.com/photo-1541781774459-bb2af2f05b55?w=800&q=80",
            content_url="https://www.sleepfoundation.org/school-and-sleep"
        ),
        models.Resource(
            title="Effective Time Management",
            category="Education",
            type="Article",
            description="Master the art of prioritizing your tasks with these proven student-focused strategies.",
            duration="12 min read",
            image_url="https://images.unsplash.com/photo-1484480974693-6ca0a78fb36b?w=800&q=80",
            content_url="https://www.goconqr.com/en/examtime/blog/time-management-tips-for-students/"
        ),
        models.Resource(
            title="Quick Stress Relief Breathing",
            category="Mindfulness",
            type="Video",
            description="Simple box breathing exercises you can do anywhere to lower your heart rate and anxiety.",
            duration="3 min",
            image_url="https://images.unsplash.com/photo-1518241353349-9b5ed3e35ab0?w=800&q=80",
            content_url="https://www.youtube.com/watch?v=tEmt1Znux58"
        ),
        models.Resource(
            title="Daily Wellness Stretching",
            category="Lifestyle",
            type="Video",
            description="A low-impact stretching routine to release neck and shoulder tension from prolonged sitting.",
            duration="8 min",
            image_url="https://images.unsplash.com/photo-1518611012118-296072bb5604?w=800&q=80",
            content_url="https://www.youtube.com/watch?v=g_tea8ZNk5A"
        ),
        models.Resource(
            title="The Library of Silence",
            category="Education",
            type="Resource",
            description="Access our internal digital archive of calming soundscapes for deep concentration.",
            duration="Continuous",
            image_url="https://images.unsplash.com/photo-1507842217343-583bb7270b66?w=800&q=80",
            content_url="#"
        )
    ]
    
    db.add_all(resources)
    db.commit()
    print("Resources seeded successfully!")
    db.close()

if __name__ == "__main__":
    seed()
