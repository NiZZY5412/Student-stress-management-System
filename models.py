from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float
from sqlalchemy.orm import relationship
from database import Base
import datetime

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(100))
    email = Column(String(100), unique=True, index=True)
    hashed_password = Column(String(255))
    role = Column(String(20)) # 'student' or 'counselor'
    phone = Column(String(20), nullable=True)
    status = Column(String(20), default='pending') # 'active', 'pending', etc.
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    registration_number = Column(String(50), nullable=True) # Principally for students
    department = Column(String(100), nullable=True)
    bio = Column(String(1000), nullable=True)

    # Relationships
    counselor_profile = relationship("Counselor", back_populates="user", uselist=False, cascade="all, delete-orphan")
    surveys = relationship("SurveyResult", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")
    system_logs = relationship("SystemLog", back_populates="user", cascade="all, delete-orphan")
    posts = relationship("PeerGroupPost", back_populates="author", cascade="all, delete-orphan")
    actions = relationship("CounselorAction", foreign_keys="CounselorAction.student_id", cascade="all, delete-orphan")
    
    # Appointments
    appointments_student = relationship("Appointment", foreign_keys="Appointment.student_id", back_populates="student", cascade="all, delete-orphan")
    appointments_counselor = relationship("Appointment", foreign_keys="Appointment.counselor_id", back_populates="counselor", cascade="all, delete-orphan")
    
    # Clinical Notes
    session_notes_student = relationship("SessionNote", foreign_keys="SessionNote.student_id", back_populates="student", cascade="all, delete-orphan")
    session_notes_counselor = relationship("SessionNote", foreign_keys="SessionNote.counselor_id", back_populates="counselor", cascade="all, delete-orphan")
    
    # Activity and Mood
    activity_logs = relationship("ActivityLog", back_populates="user", cascade="all, delete-orphan")
    mood_logs = relationship("MoodLog", back_populates="user", cascade="all, delete-orphan")
    
    # Chat
    sent_messages = relationship("ChatMessage", foreign_keys="ChatMessage.sender_id", back_populates="sender", cascade="all, delete-orphan")
    received_messages = relationship("ChatMessage", foreign_keys="ChatMessage.receiver_id", back_populates="receiver", cascade="all, delete-orphan")


class Counselor(Base):
    __tablename__ = "counselors"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    specialization = Column(String(100), nullable=True)
    department = Column(String(100), nullable=True)
    is_admin = Column(Integer, default=0) # 0: Staff, 1: Admin, 2: Super Admin
    is_active = Column(Integer, default=1)
    
    user = relationship("User", back_populates="counselor_profile")
    availability = relationship("CounselorAvailability", back_populates="counselor", cascade="all, delete-orphan")

class CounselorAction(Base):
    __tablename__ = "counselor_actions"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("users.id"))
    action_type = Column(String(50)) # 'Meeting', 'Call', 'Referral', etc.
    notes = Column(String(500))
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class PeerGroupPost(Base):
    __tablename__ = "peer_group_posts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    content = Column(String(1000))
    is_anonymous = Column(Integer, default=0) # 0: Signed, 1: Anonymous
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    author = relationship("User", back_populates="posts")

class CounselorAvailability(Base):
    __tablename__ = "counselor_availability"

    id = Column(Integer, primary_key=True, index=True)
    counselor_id = Column(Integer, ForeignKey("counselors.id", ondelete="CASCADE"))
    day_of_week = Column(String(20)) # 'Monday', etc.
    start_time = Column(String(10)) # '09:00'
    end_time = Column(String(10))   # '17:00'
    is_available = Column(Integer, default=1)
    
    counselor = relationship("Counselor", back_populates="availability")

class SurveyResult(Base):
    __tablename__ = "survey_results"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    
    # ML Model Features
    anxiety = Column(Integer, default=0)
    bullying = Column(Integer, default=0)
    extracurriculars = Column(Integer, default=0)
    social_support = Column(Integer, default=0)
    self_esteem = Column(Integer, default=0)

    registration_number = Column(String(50), nullable=True)
    guest_full_name = Column(String(100), nullable=True)
    guest_email = Column(String(100), nullable=True)
    message = Column(String(500), nullable=True)
    
    predicted_stress = Column(Integer)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="surveys")

class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    counselor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    date = Column(DateTime)
    status = Column(String(20), default='pending')
    notes = Column(String(500), nullable=True) 
    reason = Column(String(500), nullable=True) 
    session_type = Column(String(20), default='video') # 'video', 'chat', 'in-person'
    counselor_reply = Column(String(1000), nullable=True)
    proposed_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    student = relationship("User", foreign_keys=[student_id], back_populates="appointments_student")
    counselor = relationship("User", foreign_keys=[counselor_id], back_populates="appointments_counselor")

class SessionNote(Base):
    __tablename__ = "session_notes"

    id = Column(Integer, primary_key=True, index=True)
    counselor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    student_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    notes_text = Column(String(2000))
    is_red_flagged = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    counselor = relationship("User", foreign_keys=[counselor_id], back_populates="session_notes_counselor")
    student = relationship("User", foreign_keys=[student_id], back_populates="session_notes_student")

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    message = Column(String(500))
    is_read = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="notifications")

class SystemLog(Base):
    __tablename__ = "system_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    action = Column(String(100))
    description = Column(String(500))
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="system_logs")

class MoodLog(Base):
    __tablename__ = "mood_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    mood = Column(String(50))
    note = Column(String(500), nullable=True)
    activity = Column(String(100), nullable=True)
    stress_level = Column(Integer, default=5)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", foreign_keys=[user_id], back_populates="mood_logs")

class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    activity_type = Column(String(100))
    duration_minutes = Column(Integer, nullable=True)
    note = Column(String(500), nullable=True)
    status = Column(String(20), default='pending')
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", foreign_keys=[user_id], back_populates="activity_logs")

class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    sender_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    receiver_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    content = Column(String(2000))
    is_read = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    sender = relationship("User", foreign_keys=[sender_id], back_populates="sent_messages")
    receiver = relationship("User", foreign_keys=[receiver_id], back_populates="received_messages")

class Resource(Base):
    __tablename__ = "resources"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200))
    category = Column(String(50)) # 'mindfulness', 'academic', etc.
    type = Column(String(20))     # 'article', 'video', etc.
    description = Column(String(1000))
    duration = Column(String(20)) # '5 min'
    image_url = Column(String(500), nullable=True)
    content_url = Column(String(500))
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
