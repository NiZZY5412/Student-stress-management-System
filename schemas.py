from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime

class ResponseBase(BaseModel):
    status: str
    message: str

# User Schemas
class UserBase(BaseModel):
    email: str
    full_name: str
    role: str
    phone: Optional[str] = None
    department: Optional[str] = None
    bio: Optional[str] = None

class UserCreate(UserBase):
    password: str

class UserResponse(UserBase):
    id: int
    created_at: Optional[datetime] = None
    registration_number: Optional[str] = None
    department: Optional[str] = None
    bio: Optional[str] = None
    
    class Config:
        from_attributes = True

class UserLogin(BaseModel):
    email: str
    password: str

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    registration_number: Optional[str] = None
    department: Optional[str] = None
    bio: Optional[str] = None

# Activity Schemas
class ActivityBase(BaseModel):
    activity_type: str
    duration_minutes: Optional[int] = None
    note: Optional[str] = None

class ActivityCreate(ActivityBase):
    pass

class ActivityResponse(ActivityBase):
    id: int
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True

# Counselor Schemas
class CounselorBase(BaseModel):
    specialization: Optional[str] = None
    department: Optional[str] = None
    is_admin: int = 0
    is_active: int = 1

class CounselorCreate(CounselorBase):
    user_id: int

class CounselorResponse(BaseModel):
    id: int
    user_id: int
    specialization: Optional[str] = None
    department: Optional[str] = None
    is_admin: int = 0
    is_active: int = 1
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    
    class Config:
        from_attributes = True

# Survey Schemas
class SurveyInput(BaseModel):
    user_id: int 
    full_name: str
    registration_number: str
    email: Optional[str] = None
    message: Optional[str] = None
    anxiety_level: int
    self_esteem: int
    extracurricular_activities: int
    bullying: int
    social_support: int
    
class SurveyResponse(BaseModel):
    stress_level: int
    score: float
    message: str
    factors: Optional[List[dict]] = []
    created_at: datetime
    
# Counselor Dashboard Schemas
class StudentUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    registration_number: Optional[str] = None
    phone: Optional[str] = None
    status: Optional[str] = None

class StudentListItem(BaseModel):
    id: int
    full_name: str
    registration_number: Optional[str]
    email: str
    predicted_stress: Optional[int]
    status: str
    last_assessment_date: Optional[datetime]

    class Config:
        from_attributes = True

class StudentDetail(BaseModel):
    id: int
    full_name: str
    registration_number: Optional[str]
    email: str
    phone: Optional[str]
    status: str
    role: str
    surveys: List[SurveyResponse]
    actions: List[CounselorActionResponse] = []

    class Config:
        from_attributes = True

class FlaggedStudent(BaseModel):
    full_name: str
    email: str
    predicted_stress: int
    last_assessment_date: datetime

    class Config:
        from_attributes = True

# Counselor Management Schemas
class CounselorProfileCreate(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    phone: Optional[str] = None
    specialization: Optional[str] = None
    department: Optional[str] = None
    is_admin: int = 0

class CounselorProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    specialization: Optional[str] = None
    department: Optional[str] = None
    is_active: Optional[int] = None
    is_admin: Optional[int] = None

# Appointments
class AppointmentBase(BaseModel):
    counselor_id: int
    date: datetime
    notes: Optional[str] = None
    reason: Optional[str] = None
    session_type: str = 'video'

class AppointmentCreate(AppointmentBase):
    pass

class AppointmentUpdate(BaseModel):
    status: Optional[str] = None
    counselor_reply: Optional[str] = None
    proposed_date: Optional[datetime] = None
    notes: Optional[str] = None

class AppointmentResponse(AppointmentBase):
    id: int
    student_id: int
    status: str
    counselor_reply: Optional[str] = None
    proposed_date: Optional[datetime] = None
    created_at: Optional[datetime] = None
    counselor_name: Optional[str] = None 
    student_name: Optional[str] = None

    class Config:
        from_attributes = True

# Peer Group Posts
class PeerGroupPostBase(BaseModel):
    content: str
    is_anonymous: Optional[int] = 0

class PeerGroupPostCreate(PeerGroupPostBase):
    pass

class PeerGroupPostResponse(PeerGroupPostBase):
    id: int
    user_id: int
    user_name: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

# Counselor Actions
class CounselorActionBase(BaseModel):
    action_type: str
    notes: str

class CounselorActionCreate(CounselorActionBase):
    pass

class CounselorActionResponse(CounselorActionBase):
    id: int
    student_id: int
    created_at: datetime

    class Config:
        from_attributes = True

# Notifications
class NotificationBase(BaseModel):
    message: str
    is_read: bool = False

class NotificationCreate(NotificationBase):
    user_id: int

class NotificationResponse(NotificationBase):
    id: int
    user_id: int
    created_at: datetime
    
    class Config:
        from_attributes = True

# Clinical Documentation
class SessionNoteBase(BaseModel):
    student_id: int
    notes_text: str
    is_red_flagged: bool = False

class SessionNoteCreate(SessionNoteBase):
    pass

class SessionNoteResponse(SessionNoteBase):
    id: int
    counselor_id: int
    created_at: datetime

    class Config:
        from_attributes = True

# Administrative Logs
class SystemLogBase(BaseModel):
    action: str
    description: str

class SystemLogResponse(SystemLogBase):
    id: int
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True

# Counselor Report
class CounselorReportResponse(BaseModel):
    generated_at: datetime
    counselor_name: str
    student_stats: dict
    appointment_stats: dict
    clinical_stats: dict
    recent_activity: List[SystemLogResponse]

    class Config:
        from_attributes = True

# Mood Journal Schemas
class MoodLogBase(BaseModel):
    mood: str
    note: Optional[str] = None
    activity: Optional[str] = None
    stress_level: Optional[int] = 5

class MoodLogCreate(MoodLogBase):
    pass

class MoodLogResponse(MoodLogBase):
    id: int
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True

# Activity Tracker Schemas
class ActivityLogBase(BaseModel):
    activity_type: str
    duration_minutes: Optional[int] = None
    note: Optional[str] = None

class ActivityLogCreate(ActivityLogBase):
    pass

class ActivityLogResponse(ActivityLogBase):
    id: int
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True

# Chat Schemas
class ChatMessageBase(BaseModel):
    content: str

class ChatMessageCreate(ChatMessageBase):
    receiver_id: int

class ChatMessageResponse(ChatMessageBase):
    id: int
    sender_id: int
    receiver_id: int
    is_read: int
    created_at: datetime

    class Config:
        from_attributes = True

# Resource Schemas
class ResourceBase(BaseModel):
    title: str
    category: str
    type: str
    description: str
    duration: str
    image_url: Optional[str] = None
    content_url: str

class ResourceCreate(ResourceBase):
    pass

class ResourceResponse(ResourceBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True
