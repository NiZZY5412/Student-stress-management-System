from typing import List, Optional
import csv
import io
import os
from fastapi import FastAPI, Depends, HTTPException, status, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from passlib.context import CryptContext
import models, schemas, database
import uvicorn
import joblib
import pandas as pd
import numpy as np
import datetime

# Database Setup handled in startup_event

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_event():
    print("Initializing Database Schema...")
    models.Base.metadata.create_all(bind=database.engine)
    print("Database Schema Ready.")

@app.get("/health")
def health_check():
    return {"status": "ok", "message": "FastAPI backend is running"}

# Auth Utils
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    # Truncate to 72 bytes to prevent bcrypt errors
    # Note: passlib usually handles this, but explicit is safer per user request
    plain_password_bytes = plain_password.encode("utf-8")[:72]
    return pwd_context.verify(plain_password_bytes, hashed_password)

def get_password_hash(password: str) -> str:
    # Truncate to 72 bytes
    password_bytes = password.encode("utf-8")[:72]
    return pwd_context.hash(password_bytes)

# Load Model
try:
    model = joblib.load("practical_stress_model.pkl")
    print("Model loaded successfully.")
except Exception as e:
    print(f"Error loading model: {e}")
    model = None

# --- Endpoints ---

@app.post("/signup", response_model=schemas.UserResponse)
def signup(user: schemas.UserCreate, db: Session = Depends(database.get_db)):
    try:
        db_user = db.query(models.User).filter(models.User.email == user.email).first()
        if db_user:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        hashed_password = get_password_hash(user.password)
        new_user = models.User(
            email=user.email,
            full_name=user.full_name,
            hashed_password=hashed_password,
            role=user.role,
            status='active' if user.role == 'student' else 'pending'
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        if user.role == 'counselor':
            counselor_prof = models.Counselor(
                user_id=new_user.id,
                is_active=0,
                is_admin=1 # Default to Admin (1), no more 'Staff' (0)
            )
            db.add(counselor_prof)
            db.commit()
            
        return new_user
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        print(f"CRITICAL ERROR during signup for {user.email}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/signin")
def signin(user: schemas.UserLogin, db: Session = Depends(database.get_db)):
    print(f"DEBUG: Login attempt for {user.email}")
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if not db_user:
        print(f"DEBUG: User {user.email} not found.")
        raise HTTPException(status_code=401, detail="Invalid credentials")
        
    if not verify_password(user.password, db_user.hashed_password):
        print(f"DEBUG: Invalid password for {user.email}")
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    print(f"DEBUG: Login successful for {user.email}")
    
    response_data = {
        "id": db_user.id,
        "email": db_user.email,
        "full_name": db_user.full_name,
        "role": db_user.role
    }
    
    if db_user.role == 'counselor':
        counselor_prof = db.query(models.Counselor).filter(models.Counselor.user_id == db_user.id).first()
        if not counselor_prof:
            # Auto-create profile if missing
            is_first = db.query(models.Counselor).count() == 0
            counselor_prof = models.Counselor(
                user_id=db_user.id,
                is_admin=2 if is_first else 1,
                is_active=1
            )
            db.add(counselor_prof)
            db.commit()
            db.refresh(counselor_prof)
        
        # Ensure first counselor is ALWAYS super admin even if record exists
        all_counselors = db.query(models.Counselor).all()
        if len(all_counselors) == 1 and all_counselors[0].is_admin != 2:
            all_counselors[0].is_admin = 2
            db.commit()

        response_data.update({
            "specialization": counselor_prof.specialization,
            "is_admin": counselor_prof.is_admin,
            "is_active": counselor_prof.is_active
        })
    else:
        # Student logic
        response_data.update({
            "department": db_user.department,
            "bio": db_user.bio,
            "phone": db_user.phone,
            "registration_number": db_user.registration_number
        })
            
    return response_data

@app.put("/users/{user_id}", response_model=schemas.UserResponse)
def update_user_profile(user_id: int, user_update: schemas.UserUpdate, db: Session = Depends(database.get_db)):
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
        
    if user_update.full_name is not None:
        db_user.full_name = user_update.full_name
    if user_update.phone is not None:
        db_user.phone = user_update.phone
    if user_update.registration_number is not None:
        db_user.registration_number = user_update.registration_number
    if user_update.department is not None:
        db_user.department = user_update.department
    if user_update.bio is not None:
        db_user.bio = user_update.bio
        
    db.commit()
    db.refresh(db_user)
    return db_user

@app.get("/users/{user_id}/latest-stress")
def get_latest_stress(user_id: int, db: Session = Depends(database.get_db)):
    latest = db.query(models.SurveyResult).filter(
        models.SurveyResult.user_id == user_id
    ).order_by(models.SurveyResult.created_at.desc()).first()
    if not latest:
        return {"stressLevel": 5}
    # Map predicted_stress (0=Low, 1=Medium, 2=High) to a 1-10 slider scale
    mapping = {0: 3, 1: 6, 2: 9}
    return {"stressLevel": mapping.get(latest.predicted_stress, 5)}

@app.post("/predict", response_model=schemas.SurveyResponse)
def predict_stress(data: schemas.SurveyInput, db: Session = Depends(database.get_db)):
    if not model:
        # Check if we should raise or fallback. For robustness per prompt, maybe fallback?
        # But raising error is correct for "Model not loaded" if true. 
        # However, user prompt says "Axios fix ... catch network vs server errors".
        # Let's keep it raising 500 but ensure we log it.
        print("ERROR: Model not loaded during prediction request.")
        raise HTTPException(status_code=500, detail="Model not loaded")

    # Prepare features
    # ... (skipping verbose comment block for brevity, logic remains same) ...
    
    try:
        # Assuming model expects list of lists or 2D array
        input_df = [[
            data.anxiety_level, 
            data.self_esteem, 
            data.extracurricular_activities, 
            data.bullying, 
            data.social_support
        ]]
        prediction = model.predict(input_df)[0]
    except Exception as e:
        print(f"Model prediction failed or mismatch: {e}. Using fallback logic.")
        # Fallback Logic
        score = (data.anxiety_level * 1.5) + (data.bullying * 2) - data.self_esteem - data.social_support
        if score < 5: prediction = 0
        elif score < 12: prediction = 1
        else: prediction = 2

    # Save to DB
    new_result = models.SurveyResult(
        user_id=data.user_id,
        anxiety=data.anxiety_level,
        self_esteem=data.self_esteem,
        extracurriculars=data.extracurricular_activities,
        bullying=data.bullying,
        social_support=data.social_support,
        registration_number=data.registration_number,
        guest_full_name=data.full_name,
        guest_email=data.email,
        message=data.message,
        predicted_stress=int(prediction)
    )
    db.add(new_result)
    
    # Dynamic Status Management based on Assessment Result
    student = db.query(models.User).filter(models.User.id == data.user_id).first()
    if student and (student.status or "active").lower() != 'resolved':
        if int(prediction) == 2:
            student.status = 'flagged'
            
            # Log critical activity
            new_alert = models.ActivityLog(
                user_id=student.id,
                activity_type="High Stress Assessment",
                note=f"CRITICAL: {student.full_name} completed an assessment indicating High Stress. Urgent attention recommended.",
                status="pending"
            )
            db.add(new_alert)
            
            # Notify counselors
            counselors = db.query(models.User).filter(models.User.role == 'counselor').all()
            for c in counselors:
                db.add(models.Notification(
                    user_id=c.id,
                    message=f"URGENT: {student.full_name} registered a high-stress assessment."
                ))
        elif int(prediction) < 2 and student.status == 'flagged':
            # Auto-unflag if they are now doing better
            student.status = 'active'
            
    db.commit()
    db.refresh(new_result)
    
    factors = []
    if data.anxiety_level > 6: factors.append({"name": "High Anxiety", "score": data.anxiety_level, "level": "High"})
    elif data.anxiety_level >= 4: factors.append({"name": "Moderate Anxiety", "score": data.anxiety_level, "level": "Moderate"})
    if data.bullying > 4: factors.append({"name": "Social Pressure", "score": data.bullying, "level": "High"})
    if data.self_esteem < 4: factors.append({"name": "Confidence Risk", "score": data.self_esteem, "level": "High"})
    if data.social_support < 5: factors.append({"name": "Isolation Pressure", "score": data.social_support, "level": "High"})
    if not factors: factors.append({"name": "Balanced Emotional Core", "score": 10, "level": "Low"})

    raw_stress = (data.anxiety_level * 1.5) + (data.bullying * 2) - data.self_esteem - data.social_support
    progress_score = min(100, max(0, ((raw_stress + 20) / 45.0) * 100))

    return {
        "stress_level": int(prediction),
        "score": float(progress_score),
        "factors": factors,
        "message": "Assessment complete.",
        "created_at": new_result.created_at
    }

@app.get("/flagged-students", response_model=list[schemas.FlaggedStudent])
def get_flagged_students(requester_id: int, db: Session = Depends(database.get_db)):
    # Role check
    requester = db.query(models.User).filter(models.User.id == requester_id).first()
    if not requester or requester.role != 'counselor':
        raise HTTPException(status_code=403, detail="Unauthorized")
    results = db.query(models.SurveyResult).filter(models.SurveyResult.predicted_stress == 2).all()
    flagged = []
    seen_users = set()
    for r in results:
        if r.user_id not in seen_users:
            user = db.query(models.User).filter(models.User.id == r.user_id).first()
            if user:
                flagged.append({
                    "full_name": user.full_name,
                    "email": user.email,
                    "predicted_stress": r.predicted_stress,
                    "last_assessment_date": r.created_at
                })
                seen_users.add(r.user_id)
    return flagged

# --- Counselor Dashboard Endpoints ---

@app.get("/students", response_model=List[schemas.StudentListItem])
def get_students(requester_id: int, db: Session = Depends(database.get_db)):
    # Role check
    requester = db.query(models.User).filter(models.User.id == requester_id).first()
    if not requester or requester.role != 'counselor':
        raise HTTPException(status_code=403, detail="Unauthorized")
        
    # Get all users with role 'student'
    students = db.query(models.User).filter(models.User.role == 'student').all()
    
    result = []
    for student in students:
        # Get latest survey
        latest_survey = db.query(models.SurveyResult).filter(models.SurveyResult.user_id == student.id).order_by(models.SurveyResult.created_at.desc()).first()
        
        result.append({
            "id": student.id,
            "full_name": student.full_name,
            "registration_number": student.registration_number or (latest_survey.registration_number if latest_survey else "N/A"),
            "email": student.email,
            "phone": student.phone or "N/A",
            "department": student.department or "N/A",
            "predicted_stress": latest_survey.predicted_stress if latest_survey else None,
            "status": student.status or "active",
            "last_assessment_date": latest_survey.created_at if latest_survey else None
        })
    return result

@app.get("/students/{student_id}", response_model=schemas.StudentDetail)
def get_student_detail(student_id: int, db: Session = Depends(database.get_db)):
    student = db.query(models.User).filter(models.User.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    
    # Transform surveys to match schema if necessary
    # The models.SurveyResult has predicted_stress, but SurveyResponse schema expects stress_level
    surveys = []
    for s in student.surveys:
        # Calculate score for detail view consistency
        calc_score = (s.anxiety * 1.5) + (s.bullying * 2) - s.self_esteem - s.social_support
        calc_score = max(0, calc_score)
        
        status_map = {0: "Low", 1: "Medium", 2: "High"}
        
        surveys.append({
            "stress_level": s.predicted_stress,
            "score": float(calc_score),
            "message": s.message or "",
            "created_at": s.created_at
        })

    return {
        "id": student.id,
        "full_name": student.full_name,
        "registration_number": student.registration_number or (student.surveys[0].registration_number if student.surveys else "N/A"),
        "email": student.email,
        "phone": student.phone,
        "status": student.status or "active",
        "role": student.role,
        "surveys": surveys,
        "actions": [
            {
                "id": a.id,
                "action_type": a.action_type,
                "notes": a.notes,
                "created_at": a.created_at
            } for a in (student.actions or [])
        ]
    }

@app.put("/students/{student_id}", response_model=schemas.UserResponse)
def update_student(student_id: int, student_update: schemas.StudentUpdate, counselor_id: int, db: Session = Depends(database.get_db)):
    # Role check
    counselor = db.query(models.User).filter(models.User.id == counselor_id, models.User.role == 'counselor').first()
    if not counselor:
        raise HTTPException(status_code=403, detail="Unauthorized. Only counselors can edit students.")

    db_student = db.query(models.User).filter(models.User.id == student_id).first()
    if not db_student:
        raise HTTPException(status_code=404, detail="Student not found")
    
    if student_update.full_name:
        db_student.full_name = student_update.full_name
    if student_update.email:
        db_student.email = student_update.email
    if student_update.phone:
        db_student.phone = student_update.phone
    if student_update.status:
        db_student.status = student_update.status
        if student_update.status == 'resolved':
            db.query(models.Notification).filter(
                models.Notification.is_read == 0,
                models.Notification.message.like(f"%{db_student.full_name}%")
            ).update({"is_read": 1}, synchronize_session=False)

    if student_update.registration_number:
        db_student.registration_number = student_update.registration_number
        
    db.commit()
    db.refresh(db_student)
    return db_student

@app.delete("/students/{student_id}")
def delete_student(student_id: int, counselor_id: int, db: Session = Depends(database.get_db)):
    # Role check — any clinical staff (Admin/Super Admin) can delete
    counselor_prof = db.query(models.Counselor).filter(models.Counselor.user_id == counselor_id).first()
    if not counselor_prof or (counselor_prof.is_admin or 0) < 1:
        raise HTTPException(status_code=403, detail="Unauthorized. Clinical admin privileges required.")

    db_student = db.query(models.User).filter(models.User.id == student_id).first()
    if not db_student:
        raise HTTPException(status_code=404, detail="Student not found")
    
    new_log = models.SystemLog(
        user_id=counselor_id,
        action="Student Hard Deleted",
        description=f"Deleted student ID {student_id} ({db_student.full_name})"
    )
    db.add(new_log)
    
    db.delete(db_student)
    db.commit()
    return {"message": "Student and all associated records deleted successfully"}

@app.post("/admin/students", response_model=schemas.UserResponse)
def counselor_create_student(student: schemas.UserCreate, counselor_id: int, db: Session = Depends(database.get_db)):
    # Role check
    counselor = db.query(models.User).filter(models.User.id == counselor_id, models.User.role == 'counselor').first()
    if not counselor:
        raise HTTPException(status_code=403, detail="Unauthorized. Only counselors can register students.")

    # Check if user exists
    existing = db.query(models.User).filter(models.User.email == student.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="User with this email already exists")

    hashed_password = pwd_context.hash(student.password)
    new_student = models.User(
        email=student.email,
        full_name=student.full_name,
        hashed_password=hashed_password,
        role='student',
        phone=student.phone,
        status="Active"
    )
    db.add(new_student)
    
    new_log = models.SystemLog(
        user_id=counselor_id,
        action="Student Created",
        description=f"Created student {student.full_name} ({student.email})"
    )
    db.add(new_log)
    
    db.commit()
    db.refresh(new_student)
    return new_student

@app.post("/students/{student_id}/action", response_model=schemas.CounselorActionResponse)
def log_action(student_id: int, action: schemas.CounselorActionCreate, db: Session = Depends(database.get_db)):
    db_student = db.query(models.User).filter(models.User.id == student_id).first()
    if not db_student:
        raise HTTPException(status_code=404, detail="Student not found")
    
    new_action = models.CounselorAction(
        student_id=student_id,
        action_type=action.action_type,
        notes=action.notes
    )
    
    # Optional: Send notification if it's a meeting
    if action.action_type == 'Meeting':
        print(f"--- NOTIFICATION: Email sent to {db_student.email} regarding a new meeting scheduling. ---")
        # In a real app, integrate with SMTP or SendGrid here
        
    db.add(new_action)
    db.commit()
    db.refresh(new_action)
    return new_action

@app.patch("/students/{student_id}/status")
def update_student_status(student_id: int, status_update: dict, db: Session = Depends(database.get_db)):
    student = db.query(models.User).filter(models.User.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    
    new_status = status_update.get("status")
    if new_status not in ["progress", "pending", "resolved"]:
        raise HTTPException(status_code=400, detail="Invalid status")
    
    student.status = new_status
    
    # Auto-clear all team notifications if the case is resolved
    if new_status == 'resolved':
        db.query(models.Notification).filter(
            models.Notification.is_read == 0,
            models.Notification.message.like(f"%{student.full_name}%")
        ).update({"is_read": 1}, synchronize_session=False)

    db.commit()
    return {"message": f"Status updated to {new_status}"}

# --- Wellness Resources Endpoints ---

@app.get("/counselors", response_model=List[schemas.CounselorResponse])
def get_counselors(db: Session = Depends(database.get_db)):
    results = db.query(models.User, models.Counselor).outerjoin(
        models.Counselor, models.User.id == models.Counselor.user_id
    ).filter(
        models.User.role == 'counselor'
    ).all()
    
    counselors = []
    for user, prof in results:
        if prof and prof.is_active == 1:
            counselors.append({
                "id": user.id,
                "user_id": user.id,
                "full_name": user.full_name,
                "email": user.email,
                "phone": user.phone,
                "status": user.status,
                "specialization": prof.specialization,
                "department": prof.department,
                "is_admin": prof.is_admin,
                "is_active": prof.is_active
            })
    return counselors

# --- Admin / Counselor Management Endpoints ---

@app.get("/admin/counselors", response_model=List[schemas.CounselorResponse])
def admin_get_counselors(db: Session = Depends(database.get_db)):
    results = db.query(models.User, models.Counselor).outerjoin(
        models.Counselor, models.User.id == models.Counselor.user_id
    ).filter(
        models.User.role == 'counselor'
    ).all()
    
    counselors = []
    for user, prof in results:
        counselors.append({
            "id": user.id,
            "user_id": user.id,
            "full_name": user.full_name,
            "email": user.email,
            "phone": user.phone,
            "status": user.status,
            "specialization": prof.specialization if prof else None,
            "department": prof.department if prof else None,
            "is_admin": prof.is_admin if prof else 0,
            "is_active": prof.is_active if prof else 0
        })
    return counselors

@app.post("/admin/counselors", response_model=schemas.CounselorResponse)
def admin_create_counselor(counselor: schemas.CounselorProfileCreate, requester_id: int, db: Session = Depends(database.get_db)):
    # Verify requester is Super Admin (level 2)
    requester = db.query(models.Counselor).filter(models.Counselor.user_id == requester_id).first()
    if not requester or requester.is_admin != 2:
        raise HTTPException(status_code=403, detail="Unauthorized. ONLY Super Admins can add other clinical staff.")

    # Check if email exists
    existing_user = db.query(models.User).filter(models.User.email == counselor.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
        
    db_user = models.User(
        email=counselor.email,
        full_name=counselor.full_name,
        hashed_password=get_password_hash(counselor.password),
        role='counselor',
        phone=counselor.phone
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    db_prof = models.Counselor(
        user_id=db_user.id,
        specialization=counselor.specialization,
        department=counselor.department,
        is_admin=max(1, counselor.is_admin), # Minimal level is 1 (Admin)
        is_active=1
    )
    db.add(db_prof)
    db.commit()
    db.refresh(db_prof)
    
    return {
        "id": db_user.id,
        "user_id": db_user.id,
        "full_name": db_user.full_name,
        "email": db_user.email,
        "phone": db_user.phone,
        "status": db_user.status,
        "specialization": db_prof.specialization,
        "department": db_prof.department,
        "is_admin": db_prof.is_admin,
        "is_active": db_prof.is_active
    }

@app.put("/admin/counselors/{counselor_id}", response_model=schemas.CounselorResponse)
def admin_update_counselor(counselor_id: int, updates: schemas.CounselorProfileUpdate, requester_id: int, db: Session = Depends(database.get_db)):
    # Verify requester is Super Admin (level 2)
    requester = db.query(models.Counselor).filter(models.Counselor.user_id == requester_id).first()
    if not requester or requester.is_admin != 2:
        raise HTTPException(status_code=403, detail="Unauthorized. ONLY Super Admins can update clinical staff.")

    user = db.query(models.User).filter(models.User.id == counselor_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Counselor not found")
        
    prof = db.query(models.Counselor).filter(models.Counselor.user_id == counselor_id).first()
    if not prof:
        prof = models.Counselor(user_id=counselor_id)
        db.add(prof)
        db.commit()
        db.refresh(prof)
        
    if updates.full_name is not None: user.full_name = updates.full_name
    if updates.phone is not None: user.phone = updates.phone
    
    if updates.specialization is not None: prof.specialization = updates.specialization
    if updates.department is not None: prof.department = updates.department
    if updates.is_active is not None: prof.is_active = updates.is_active
    if updates.is_admin is not None: 
        # Prevent downgrading to 0 (Staff). Minimal level is 1 (Admin).
        prof.is_admin = max(1, updates.is_admin)
        
    db.commit()
    db.refresh(user)
    db.refresh(prof)
    
    return {
        "id": user.id,
        "user_id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "phone": user.phone,
        "status": user.status,
        "specialization": prof.specialization,
        "department": prof.department,
        "is_admin": prof.is_admin,
        "is_active": prof.is_active
    }

@app.delete("/admin/counselors/{counselor_id}")
def admin_delete_counselor(counselor_id: int, db: Session = Depends(database.get_db)):
    prof = db.query(models.Counselor).filter(models.Counselor.user_id == counselor_id).first()
    if not prof:
        raise HTTPException(status_code=404, detail="Counselor profile not found")
    
    # Soft delete
    prof.is_active = 0
    db.commit()
    return {"message": "Counselor marked as inactive"}

@app.get("/admin/export-students")
def admin_export_students(admin_id: int, db: Session = Depends(database.get_db)):
    # Admin verification
    prof = db.query(models.Counselor).filter(models.Counselor.user_id == admin_id).first()
    if not prof or (prof.is_admin or 0) < 1:
        raise HTTPException(status_code=403, detail="Clinical Admin (Level 1+) privilege is required for CSV export.")
        
    students = db.query(models.User).filter(models.User.role == 'student').all()
    
    # Generate CSV with Excel BOM for compatibility
    output = io.StringIO()
    output.write('\ufeff') # UTF-8 BOM
    writer = csv.writer(output)
    writer.writerow(["UID", "Registration Number", "Full Name", "Email", "Phone", "Status", "Joined"])
    
    for s in students:
        writer.writerow([
            s.id, 
            s.registration_number or "N/A", 
            s.full_name or "Anonymous", 
            s.email, 
            s.phone or "", 
            s.status or "active", 
            s.created_at.strftime("%Y-%m-%d %H:%M:%S") if (s.created_at and hasattr(s.created_at, 'strftime')) else str(s.created_at)
        ])
        
    return PlainTextResponse(
        output.getvalue(), 
        media_type="text/csv", 
        headers={"Content-Disposition": "attachment; filename=registration_report_system.csv"}
    )

@app.post("/admin/import-counselors")
async def admin_import_counselors(admin_id: int, file: UploadFile = File(...), db: Session = Depends(database.get_db)):
    # Admin verification
    prof = db.query(models.Counselor).filter(models.Counselor.user_id == admin_id).first()
    if not prof or (prof.is_admin or 0) < 1:
        raise HTTPException(status_code=403, detail="Unauthorized. Admin level or higher required for import.")
        
    contents = await file.read()
    decoded = contents.decode("utf-8")
    reader = csv.DictReader(io.StringIO(decoded))
    
    count = 0
    for row in reader:
        email = row.get("Email")
        if not email: continue
        
        # Check if exists
        if db.query(models.User).filter(models.User.email == email).first():
            continue
            
        new_user = models.User(
            email=email,
            full_name=row.get("FullName", "Imported Counselor"),
            hashed_password=get_password_hash("changeme123!"),
            role=row.get("Role", "counselor"),
            phone=row.get("Phone", "")
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        new_prof = models.Counselor(
            user_id=new_user.id,
            specialization=row.get("Specialization", ""),
            department=row.get("Department", ""),
            is_admin=int(row.get("IsAdmin", 0))
        )
        db.add(new_prof)
        count += 1
        
    db.commit()
    return {"message": f"Successfully imported {count} counselors."}

@app.get("/admin/pending-counselors", response_model=List[schemas.CounselorResponse])
def admin_get_pending_counselors(admin_id: int, db: Session = Depends(database.get_db)):
    # Super Admin check usually (level 2)
    admin = db.query(models.Counselor).filter(models.Counselor.user_id == admin_id).first()
    if not admin or admin.is_admin < 1:
        raise HTTPException(status_code=403, detail="Unauthorized. Only admins can see pending roster.")
        
    results = db.query(models.User, models.Counselor).join(
        models.Counselor, models.User.id == models.Counselor.user_id
    ).filter(
        models.User.role == 'counselor',
        models.Counselor.is_active == 0
    ).all()
    
    pending = []
    for user, prof in results:
        pending.append({
            "id": user.id,
            "user_id": user.id,
            "full_name": user.full_name,
            "email": user.email,
            "phone": user.phone,
            "status": user.status,
            "specialization": prof.specialization,
            "department": prof.department,
            "is_admin": prof.is_admin,
            "is_active": prof.is_active
        })
    return pending

@app.post("/admin/approve-counselor/{counselor_id}")
def admin_approve_counselor(counselor_id: int, admin_id: int, db: Session = Depends(database.get_db)):
    admin = db.query(models.Counselor).filter(models.Counselor.user_id == admin_id).first()
    if not admin or admin.is_admin != 2:
        raise HTTPException(status_code=403, detail="Unauthorized. ONLY Super Admins can approve and activate new staff.")
        
    prof = db.query(models.Counselor).filter(models.Counselor.user_id == counselor_id).first()
    if not prof:
        raise HTTPException(status_code=404, detail="Counselor profile not found")
    
    prof.is_active = 1
    db.commit()
    return {"message": "Staff member approved and activated."}

@app.post("/admin/bulk-delete-counselors")
def bulk_delete_counselors(requester_id: int, db: Session = Depends(database.get_db)):
    # Super Admin only (level 2)
    admin = db.query(models.Counselor).filter(models.Counselor.user_id == requester_id).first()
    if not admin or admin.is_admin != 2:
        raise HTTPException(status_code=403, detail="Super Admin authorization required.")
    
    # Delete all counselors except self
    db.query(models.User).filter(
        models.User.role == 'counselor', 
        models.User.id != requester_id
    ).delete(synchronize_session=False)
    db.commit()
    return {"message": "All secondary counselor accounts purged."}

@app.post("/admin/bulk-delete-admins")
def bulk_delete_admins(requester_id: int, db: Session = Depends(database.get_db)):
    # Super Admin only
    admin = db.query(models.Counselor).filter(models.Counselor.user_id == requester_id).first()
    if not admin or (admin.is_admin or 0) < 2:
        raise HTTPException(status_code=403, detail="Super Admin authorization required.")
    
    # Delete all users whose counselor_profile has is_admin == 1
    admin_users = db.query(models.User).join(
        models.Counselor, models.User.id == models.Counselor.user_id
    ).filter(
        models.Counselor.is_admin == 1
    ).all()
    
    for au in admin_users:
        db.delete(au)
    
    db.commit()
    return {"message": "All operator-level administrative accounts removed."}

@app.post("/admin/bulk-delete-students")
def bulk_delete_students(requester_id: int, db: Session = Depends(database.get_db)):
    # Level 1 or 2
    admin = db.query(models.Counselor).filter(models.Counselor.user_id == requester_id).first()
    if not admin or (admin.is_admin or 0) < 1:
        raise HTTPException(status_code=403, detail="Clinical Admin privilege required.")
    
    db.query(models.User).filter(models.User.role == 'student').delete(synchronize_session=False)
    db.commit()
    return {"message": "All student registry data has been wiped."}

@app.post("/admin/bulk-resolve-students")
def bulk_resolve_students(requester_id: int, db: Session = Depends(database.get_db)):
    # Level 1 or 2
    admin = db.query(models.Counselor).filter(models.Counselor.user_id == requester_id).first()
    if not admin or (admin.is_admin or 0) < 1:
        raise HTTPException(status_code=403, detail="Clinical Admin privilege required.")
    
    # Set all students as resolved in User table
    db.query(models.User).filter(models.User.role == 'student').update({"status": "resolved"}, synchronize_session=False)
    
    # Bulk mark all stress/risk notifications as read
    db.query(models.Notification).filter(
        models.Notification.is_read == 0,
        (models.Notification.message.like("%stress%") | models.Notification.message.like("%Risk%"))
    ).update({"is_read": 1}, synchronize_session=False)

    db.commit()
    return {"message": "All active student cases have been officially resolved and alerts cleared."}

@app.get("/appointments/my", response_model=List[schemas.AppointmentResponse])
def get_my_appointments(user_id: int, db: Session = Depends(database.get_db)):
    # Verify user exists
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    if user.role == 'student':
        appointments = db.query(models.Appointment).filter(models.Appointment.student_id == user_id).all()
    else: # counselor
        appointments = db.query(models.Appointment).filter(models.Appointment.counselor_id == user_id).all()
        
    # Enrich with names (manual join for simplicity/schema match)
    results = []
    for app in appointments:
        resp = schemas.AppointmentResponse.from_orm(app)
        resp.counselor_name = app.counselor.full_name if app.counselor else "Unknown"
        resp.student_name = app.student.full_name if app.student else "Unknown"
        results.append(resp)
        
    return results

@app.post("/appointments", response_model=schemas.AppointmentResponse)
def create_appointment(
    appointment: schemas.AppointmentCreate, 
    user_id: int, # Pass user_id explicitly for now
    db: Session = Depends(database.get_db)
):
    # Verify student
    student = db.query(models.User).filter(models.User.id == user_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
        
    # Verify counselor
    counselor = db.query(models.User).filter(models.User.id == appointment.counselor_id).first()
    if not counselor or counselor.role != 'counselor':
        raise HTTPException(status_code=400, detail="Invalid counselor selection")

    new_appointment = models.Appointment(
        student_id=user_id,
        counselor_id=appointment.counselor_id,
        date=appointment.date,
        notes=appointment.notes, 
        reason=appointment.reason, # Student reason
        status="pending"
    )
    
    db.add(new_appointment)
    
    # Broadcast notification to all counselors/staff for team awareness
    staff = db.query(models.User).filter(models.User.role == 'counselor').all()
    date_str = appointment.date.strftime("%b %d, %H:%M") if hasattr(appointment.date, "strftime") else str(appointment.date)
    
    for member in staff:
        # Personalized message: if it's the specific counselor, emphasize "YOU are booked", others get "NEW booking"
        is_targeted = (member.id == appointment.counselor_id)
        msg = f"{'ALERT: You' if is_targeted else 'TEAM: [New] ' + counselor.full_name} booked by {student.full_name} for {appointment.session_type} on {date_str}."
        
        notification = models.Notification(
            user_id=member.id,
            message=msg
        )
        db.add(notification)
    
    db.commit()
    db.refresh(new_appointment)
    
    resp = schemas.AppointmentResponse.from_orm(new_appointment)
    resp.counselor_name = counselor.full_name
    resp.student_name = student.full_name
    return resp

@app.get("/appointments/counselor/{counselor_id}", response_model=List[schemas.AppointmentResponse])
def get_counselor_appointments(counselor_id: int, db: Session = Depends(database.get_db)):
    appointments = db.query(models.Appointment).filter(models.Appointment.counselor_id == counselor_id).all()
    results = []
    for appt in appointments:
        resp = schemas.AppointmentResponse.from_orm(appt)
        resp.counselor_name = appt.counselor.full_name if appt.counselor else "Unknown"
        resp.student_name = appt.student.full_name if appt.student else "Unknown"
        results.append(resp)
    return results

@app.put("/appointments/{appointment_id}", response_model=schemas.AppointmentResponse)
def update_appointment(
    appointment_id: int,
    update_data: schemas.AppointmentUpdate,
    db: Session = Depends(database.get_db)
):
    appointment = db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
        
    if update_data.status:
        appointment.status = update_data.status
    if update_data.counselor_reply:
        appointment.counselor_reply = update_data.counselor_reply
    if update_data.proposed_date:
        appointment.proposed_date = update_data.proposed_date
    if update_data.notes:
        appointment.notes = update_data.notes # Internal notes update
        
    db.commit()
    db.refresh(appointment)
    
    # Auto-clear team-wide notifications when handled
    if update_data.status in ['confirmed', 'completed', 'cancelled']:
        db.query(models.Notification).filter(
            models.Notification.is_read == 0,
            models.Notification.message.like(f"%{appointment.student.full_name}%")
        ).update({"is_read": 1}, synchronize_session=False)
        db.commit()
    
    resp = schemas.AppointmentResponse.from_orm(appointment)
    resp.counselor_name = appointment.counselor.full_name if appointment.counselor else "Unknown"
    resp.student_name = appointment.student.full_name if appointment.student else "Unknown"
    return resp

@app.get("/posts", response_model=List[schemas.PeerGroupPostResponse])
def get_posts(db: Session = Depends(database.get_db)):
    posts = db.query(models.PeerGroupPost).order_by(models.PeerGroupPost.created_at.desc()).limit(50).all()
    results = []
    for post in posts:
        resp = schemas.PeerGroupPostResponse.from_orm(post)
        resp.user_name = post.author.full_name if post.author else "Anonymous"
        results.append(resp)
    return results

@app.post("/posts", response_model=schemas.PeerGroupPostResponse)
def create_post(
    post: schemas.PeerGroupPostCreate,
    user_id: int,
    db: Session = Depends(database.get_db)
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    new_post = models.PeerGroupPost(
        user_id=user_id,
        content=post.content
    )
    
    db.add(new_post)
    db.commit()
    db.refresh(new_post)
    
    resp = schemas.PeerGroupPostResponse.from_orm(new_post)
    resp.user_name = user.full_name
    return resp

# --- Mood Journal Endpoints ---

@app.get("/moods/my", response_model=List[schemas.MoodLogResponse])
def get_my_moods(user_id: int, db: Session = Depends(database.get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    moods = db.query(models.MoodLog).filter(models.MoodLog.user_id == user_id).order_by(models.MoodLog.created_at.desc()).all()
    return moods

@app.post("/moods", response_model=schemas.MoodLogResponse)
def create_mood_log(mood: schemas.MoodLogCreate, user_id: int, db: Session = Depends(database.get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    new_mood = models.MoodLog(
        user_id=user_id,
        mood=mood.mood,
        note=mood.note,
        activity=mood.activity,
        stress_level=mood.stress_level
    )
    db.add(new_mood)
    db.commit()
    db.refresh(new_mood)
    return new_mood

# --- Analytics Endpoints ---

@app.get("/analytics/reports")
def get_global_analytics(requester_id: int, db: Session = Depends(database.get_db)):
    # Role check
    requester = db.query(models.User).filter(models.User.id == requester_id).first()
    if not requester or requester.role != 'counselor':
        raise HTTPException(status_code=403, detail="Unauthorized")

    from sqlalchemy.sql import func
    import datetime
    from dateutil.relativedelta import relativedelta

    # 1. Stress Levels over the last 6 months (Trend)
    # We'll group by month-year
    six_months_ago = datetime.datetime.now() - relativedelta(months=5)
    surveys = db.query(models.SurveyResult).filter(models.SurveyResult.created_at >= six_months_ago).all()
    
    monthly_data = {}
    for i in range(5, -1, -1):
        dt = datetime.datetime.now() - relativedelta(months=i)
        month_label = dt.strftime("%b %Y")
        monthly_data[month_label] = {"total_score": 0, "count": 0, "High": 0, "Medium": 0, "Low": 0}

    for s in surveys:
        month_label = s.created_at.strftime("%b %Y")
        if month_label in monthly_data:
            # Calculate dynamic score as it's not in the DB model
            current_score = (s.anxiety * 1.5) + (s.bullying * 2) - s.self_esteem - s.social_support
            current_score = max(0, current_score)
            
            monthly_data[month_label]["total_score"] += current_score
            monthly_data[month_label]["count"] += 1
            if s.predicted_stress == 2: monthly_data[month_label]["High"] += 1
            if s.predicted_stress == 1: monthly_data[month_label]["Medium"] += 1
            if s.predicted_stress == 0: monthly_data[month_label]["Low"] += 1

    trend_data = []
    for month, data in monthly_data.items():
        avg_score = round(data["total_score"] / data["count"], 1) if data["count"] > 0 else 0
        trend_data.append({
            "name": month,
            "Average_Stress": avg_score,
            "High_Risk": data["High"],
            "Medium_Risk": data["Medium"],
            "Low_Risk": data["Low"]
        })

    # 2. Risk Distribution
    # 2. Risk Distribution (Latest survey per student)
    latest_surveys_subquery = db.query(
        func.max(models.SurveyResult.id)
    ).group_by(models.SurveyResult.user_id).subquery()

    risk_dist = db.query(
        models.SurveyResult.predicted_stress, 
        func.count(models.SurveyResult.id).label('count')
    ).filter(models.SurveyResult.id.in_(latest_surveys_subquery)).group_by(models.SurveyResult.predicted_stress).all()
    
    risk_labels = {2: 'High Risk', 1: 'Medium Risk', 0: 'Low Risk', None: 'Unassessed'}
    risk_data = [{"name": risk_labels.get(r[0], 'Unassessed'), "value": r[1]} for r in risk_dist]

    # 3. Appointments Status
    appts_dist = db.query(
        models.Appointment.status,
        func.count(models.Appointment.id).label('count')
    ).group_by(models.Appointment.status).all()
    
    appts_data = [{"name": a.status.title(), "value": a.count} for a in appts_dist]

    return {
        "trend_data": trend_data,
        "risk_data": risk_data,
        "appts_data": appts_data
    }

@app.get("/analytics/sentiment-risk-heatmap")
def get_risk_heatmap(db: Session = Depends(database.get_db)):
    """ Returns matrix data of risk vs common factors (bullying, anxiety, etc) """
    from sqlalchemy.sql import func
    
    # Simple aggregation of averages per risk level
    results = db.query(
        models.SurveyResult.predicted_stress,
        func.avg(models.SurveyResult.anxiety).label('avg_anxiety'),
        func.avg(models.SurveyResult.bullying).label('avg_bullying'),
        func.avg(models.SurveyResult.self_esteem).label('avg_self_esteem'),
        func.avg(models.SurveyResult.social_support).label('avg_support')
    ).group_by(models.SurveyResult.predicted_stress).all()
    
    heatmap = []
    level_map = {0: 'Low Risk', 1: 'Medium Risk', 2: 'High Risk'}
    for r in results:
        heatmap.append({
            "Risk Level": level_map.get(r.predicted_stress, "Unknown"),
            "Anxiety": round(r.avg_anxiety, 1) if r.avg_anxiety else 0,
            "Bullying": round(r.avg_bullying, 1) if r.avg_bullying else 0,
            "Self Esteem": round(r.avg_self_esteem, 1) if r.avg_self_esteem else 0,
            "Social Support": round(r.avg_support, 1) if r.avg_support else 0
        })
    return heatmap

@app.get("/analytics/peak-hours")
def get_peak_hours(db: Session = Depends(database.get_db)):
    """ Group appointments by hour of the day """
    from sqlalchemy import func, text
    
    results = db.query(
        func.datepart(text('hour'), models.Appointment.created_at).label('hour'),
        func.count(models.Appointment.id).label('count')
    ).filter(models.Appointment.created_at != None).group_by(func.datepart(text('hour'), models.Appointment.created_at)).all()
    
    # Format to 24h timeline
    peak_data = [{"hour": f"{i}:00", "appointments": 0} for i in range(8, 19)] # 8 AM to 6 PM
    
    for r in results:
        hour_int = int(r.hour)
        if 8 <= hour_int <= 18:
            idx = hour_int - 8
            peak_data[idx]["appointments"] = r.count
            
    return peak_data

@app.get("/analytics/counselor/{counselor_id}")
def get_counselor_stats(counselor_id: int, db: Session = Depends(database.get_db)):
    # 1. Total Students
    total_students = db.query(models.User).filter(models.User.role == 'student').count()
    
    # 2. High Risk Students (Latest assessment is High Risk and NOT resolved)
    latest_surveys_subquery = db.query(
        models.SurveyResult.user_id,
        func.max(models.SurveyResult.id).label('latest_id')
    ).filter(models.SurveyResult.user_id.isnot(None)).group_by(models.SurveyResult.user_id).subquery()

    high_risk_count = db.query(models.User).join(
        latest_surveys_subquery, models.User.id == latest_surveys_subquery.c.user_id
    ).join(
        models.SurveyResult, models.SurveyResult.id == latest_surveys_subquery.c.latest_id
    ).filter(
        models.User.role == 'student',
        func.lower(models.User.status) != 'resolved',
        models.SurveyResult.predicted_stress == 2
    ).count()
    
    # 3. Pending Bookings for this counselor
    pending_bookings = db.query(models.Appointment).filter(
        models.Appointment.counselor_id == counselor_id,
        models.Appointment.status == 'pending'
    ).count()
    
    # 4. Campus Wellness Score (Using the same robust latest-survey logic)
    unresolved_students = db.query(models.User).filter(
        models.User.role == 'student',
        func.lower(models.User.status) != 'resolved'
    ).all()
    
    total_wellness_points = 0
    assessed_count = 0
    
    for student in unresolved_students:
        latest = db.query(models.SurveyResult).filter(
            models.SurveyResult.user_id == student.id
        ).order_by(models.SurveyResult.id.desc()).first()
        
        if latest:
            assessed_count += 1
            mapping = {0: 10, 1: 5, 2: 0}
            total_wellness_points += mapping.get(latest.predicted_stress, 5)
    
    if assessed_count == 0:
        wellness_streak = "100%"
    else:
        avg_wellness = (total_wellness_points / (assessed_count * 10)) * 100
        wellness_streak = f"{round(avg_wellness, 0)}%"

    return {
        "total_students": total_students,
        "high_risk": high_risk_count,
        "pending_bookings": pending_bookings,
        "wellness_streak": wellness_streak
    }

# --- Clinical Documentation ---

@app.post("/notes", response_model=schemas.SessionNoteResponse)
def create_session_note(note: schemas.SessionNoteCreate, counselor_id: int, db: Session = Depends(database.get_db)):
    counselor = db.query(models.User).filter(models.User.id == counselor_id, models.User.role == 'counselor').first()
    if not counselor:
        raise HTTPException(status_code=403, detail="Only counselors can create session notes")

    new_note = models.SessionNote(
        counselor_id=counselor_id,
        student_id=note.student_id,
        notes_text=note.notes_text,
        is_red_flagged=1 if note.is_red_flagged else 0
    )
    db.add(new_note)
    
    # Audit log
    new_log = models.SystemLog(
        user_id=counselor_id,
        action="Session Note Added",
        description=f"Added private clinical note for student ID {note.student_id}"
    )
    db.add(new_log)
    
    db.commit()
    db.refresh(new_note)
    return new_note

@app.get("/notes/student/{student_id}", response_model=List[schemas.SessionNoteResponse])
def get_session_notes(student_id: int, counselor_id: int, db: Session = Depends(database.get_db)):
    counselor = db.query(models.User).filter(models.User.id == counselor_id, models.User.role == 'counselor').first()
    if not counselor:
        raise HTTPException(status_code=403, detail="Unauthorized")
        
    notes = db.query(models.SessionNote).filter(models.SessionNote.student_id == student_id).order_by(models.SessionNote.created_at.desc()).all()
    return notes

@app.post("/students/{student_id}/escalate")
def escalate_student(student_id: int, counselor_id: int, reason: str, db: Session = Depends(database.get_db)):
    counselor = db.query(models.User).filter(models.User.id == counselor_id, models.User.role == 'counselor').first()
    if not counselor:
        raise HTTPException(status_code=403, detail="Unauthorized")

    new_log = models.SystemLog(
        user_id=counselor_id,
        action="Risk Escalation",
        description=f"Escalated student ID {student_id} to upper management/services. Reason: {reason}"
    )
    db.add(new_log)
    db.commit()
    return {"message": "Escalation logged successfully."}

@app.get("/logs", response_model=List[schemas.SystemLogResponse])
def get_system_logs(db: Session = Depends(database.get_db)):
    logs = db.query(models.SystemLog).order_by(models.SystemLog.created_at.desc()).limit(100).all()
    return logs

# --- Peer Group Posts ---

@app.post("/peergroups/posts", response_model=schemas.PeerGroupPostResponse)
def create_peer_post(post: schemas.PeerGroupPostCreate, user_id: int, db: Session = Depends(database.get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    new_post = models.PeerGroupPost(
        user_id=user_id,
        content=post.content,
        is_anonymous=post.is_anonymous
    )
    db.add(new_post)
    db.commit()
    db.refresh(new_post)
    
    # Prepare response with name
    res = schemas.PeerGroupPostResponse.from_orm(new_post)
    res.user_name = "Anonymous" if new_post.is_anonymous else user.full_name
    return res

@app.get("/peergroups/posts", response_model=List[schemas.PeerGroupPostResponse])
def get_peer_posts(db: Session = Depends(database.get_db)):
    posts = db.query(models.PeerGroupPost).order_by(models.PeerGroupPost.created_at.desc()).all()
    results = []
    for p in posts:
        res = schemas.PeerGroupPostResponse.from_orm(p)
        if p.is_anonymous:
            res.user_name = "Anonymous"
        else:
            user = db.query(models.User).filter(models.User.id == p.user_id).first()
            res.user_name = user.full_name if user else "Unknown"
        results.append(res)
    return results

@app.delete("/peergroups/posts/{post_id}")
def delete_peer_post(post_id: int, requester_id: int, db: Session = Depends(database.get_db)):
    post = db.query(models.PeerGroupPost).filter(models.PeerGroupPost.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
        
    requester = db.query(models.User).filter(models.User.id == requester_id).first()
    if not requester:
        raise HTTPException(status_code=404, detail="User not found")
        
    # Check if author or counselor
    if post.user_id == requester_id or requester.role == 'counselor':
        db.delete(post)
        db.commit()
        return {"message": "Post deleted successfully"}
    
    raise HTTPException(status_code=403, detail="Not authorized to delete this post")

# --- Emergency Alerts ---

@app.post("/emergency/log")
def log_emergency_action(user_id: int, action_type: str, contact_name: str, db: Session = Depends(database.get_db)):
    new_log = models.ActivityLog(
        user_id=user_id,
        activity_type="Emergency Call",
        note=f"Student initiated call to {contact_name} ({action_type})"
    )
    db.add(new_log)
    
    # Also add a system notification for counselors
    counselors = db.query(models.User).filter(models.User.role == 'counselor').all()
    student = db.query(models.User).filter(models.User.id == user_id).first()
    
    for c in counselors:
        notification = models.Notification(
            user_id=c.id,
            message=f"URGENT: {student.full_name if student else 'A student'} initiated an emergency call to {contact_name}."
        )
        db.add(notification)
        
    db.commit()
    return {"status": "Logged", "message": "Emergency action registered and counselors notified."}

@app.get("/counselor/emergency-alerts")
def get_emergency_alerts(db: Session = Depends(database.get_db)):
    # Fetch recent emergency logs and stress alerts from ActivityLog which are not resolved
    alerts = db.query(models.ActivityLog).filter(
        models.ActivityLog.activity_type.in_(["Emergency Call", "High Stress Assessment"]),
        models.ActivityLog.status != "resolved"
    ).order_by(models.ActivityLog.created_at.desc()).limit(20).all()
    
    results = []
    for a in alerts:
        user = db.query(models.User).filter(models.User.id == a.user_id).first()
        results.append({
            "id": a.id,
            "student_name": user.full_name if user else "Unknown Student",
            "student_id": a.user_id,
            "details": a.note,
            "timestamp": a.created_at,
            "status": a.status or "pending"
        })
    return results

@app.put("/counselor/emergency-alerts/{alert_id}/resolve")
def resolve_emergency_alert(alert_id: int, db: Session = Depends(database.get_db)):
    alert = db.query(models.ActivityLog).filter(models.ActivityLog.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert record not found")
        
    alert.status = "resolved"
    db.commit()
    return {"message": "Emergency alert marked as resolved."}

# --- Resource Management ---

@app.get("/resources", response_model=List[schemas.ResourceResponse])
def get_resources(db: Session = Depends(database.get_db)):
    return db.query(models.Resource).order_by(models.Resource.created_at.desc()).all()

@app.post("/resources", response_model=schemas.ResourceResponse)
def create_resource(resource: schemas.ResourceCreate, requester_id: int, db: Session = Depends(database.get_db)):
    user = db.query(models.User).filter(models.User.id == requester_id).first()
    if not user or user.role != 'counselor':
        raise HTTPException(status_code=403, detail="Only counselors can manage resources")
    
    db_resource = models.Resource(**resource.dict())
    db.add(db_resource)
    db.commit()
    db.refresh(db_resource)
    return db_resource

@app.delete("/resources/{resource_id}")
def delete_resource(resource_id: int, requester_id: int, db: Session = Depends(database.get_db)):
    user = db.query(models.User).filter(models.User.id == requester_id).first()
    if not user or user.role != 'counselor':
        raise HTTPException(status_code=403, detail="Only counselors can manage resources")
    
    db_resource = db.query(models.Resource).filter(models.Resource.id == resource_id).first()
    if not db_resource:
        raise HTTPException(status_code=404, detail="Resource not found")
    
    db.delete(db_resource)
    db.commit()
    return {"message": "Resource deleted successfully"}

@app.get("/counselor/reports/{report_type}")
def get_counselor_report_csv(report_type: str, counselor_id: int, db: Session = Depends(database.get_db)):
    # Counselor check
    counselor = db.query(models.User).filter(models.User.id == counselor_id, models.User.role == 'counselor').first()
    if not counselor:
        raise HTTPException(status_code=403, detail="Unauthorized")

    output = io.StringIO()
    writer = csv.writer(output)
    
    if report_type in ["stress", "students-stress"]:
        writer.writerow(["ID", "Student Name", "Anxiety", "Bullying", "Self Esteem", "Risk Level", "Date"])
        surveys = db.query(models.SurveyResult).all()
        for s in surveys:
            risk = {0: "Low", 1: "Medium", 2: "High"}.get(s.predicted_stress, "Unknown")
            writer.writerow([s.id, s.guest_full_name or s.user_id, s.anxiety, s.bullying, s.self_esteem, risk, s.created_at])
            
    elif report_type in ["high-risk", "high-risk-students"]:
        writer.writerow(["ID", "Student Name", "Email", "Critical Stress Score", "Last Seen"])
        high_risk = db.query(models.SurveyResult).filter(models.SurveyResult.predicted_stress == 2).all()
        for s in high_risk:
            score = (s.anxiety * 1.5) + (s.bullying * 2) - s.self_esteem - s.social_support
            writer.writerow([s.id, s.guest_full_name, s.guest_email, round(max(0, score), 1), s.created_at])
            
    elif report_type == "appointments":
        writer.writerow(["ID", "Student", "Counselor", "Date", "Status", "Clinical Reason"])
        appts = db.query(models.Appointment).all()
        for a in appts:
            writer.writerow([a.id, a.student.full_name if a.student else "N/A", a.counselor.full_name if a.counselor else "N/A", a.date, a.status, a.reason])
            
    elif report_type in ["activity", "activity-logs"]:
        writer.writerow(["ID", "Staff/Student", "Action", "Detail", "Timestamp"])
        logs = db.query(models.SystemLog).all()
        for l in logs:
            writer.writerow([l.id, l.user.full_name if l.user else "System", l.action, l.description, l.created_at])
            
    else:
        raise HTTPException(status_code=400, detail="Invalid report type")

    return PlainTextResponse(output.getvalue(), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={report_type}_report.csv"})

# --- Notifications ---

@app.get("/notifications/user/{user_id}", response_model=List[schemas.NotificationResponse])
def get_notifications(user_id: int, db: Session = Depends(database.get_db)):
    notifications = db.query(models.Notification).filter(
        models.Notification.user_id == user_id
    ).order_by(models.Notification.created_at.desc()).limit(50).all()
    return notifications

@app.put("/notifications/{notification_id}/read", response_model=schemas.NotificationResponse)
def mark_notification_read(notification_id: int, db: Session = Depends(database.get_db)):
    notification = db.query(models.Notification).filter(models.Notification.id == notification_id).first()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    notification.is_read = 1
    db.commit()
    db.refresh(notification)
    return notification

@app.delete("/notifications/user/{user_id}")
def clear_all_notifications(user_id: int, db: Session = Depends(database.get_db)):
    db.query(models.Notification).filter(models.Notification.user_id == user_id).delete(synchronize_session=False)
    db.commit()
    return {"message": "Notification history cleared"}

# --- AI Counseling ---

@app.post("/chat/ai")
async def chat_ai(payload: dict):
    # Verify we have messages
    messages = payload.get("messages", [])
    if not messages:
        raise HTTPException(status_code=400, detail="No messages provided")
        
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        # Fallback local response if key is missing
        last_user_msg = messages[-1].get("content", "").lower() if messages else ""
        if "stressed" in last_user_msg or "stress" in last_user_msg:
            reply = "I'm sorry you're feeling stressed. Take a deep breath. Would you like to try a 3-minute breathing exercise or check out our wellness resources?"
        elif "sleep" in last_user_msg:
            reply = "Sleep is crucial for your well-being. Have you tried avoiding screens an hour before bed?"
        else:
            reply = "I'm here to support you. Can you tell me more about how you're feeling?"
        return {"reply": reply}

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        
        # System prompt for wellness counseling
        system_msg = {
            "role": "system", 
            "content": "You are Dr. Aria, a supportive and empathetic AI Wellness Counselor for a university student stress management system. Your tone is warm, professional, and judgment-free. Help students manage stress, anxiety, and academic pressure. Mention university resources if appropriate. Important: You are an AI, not a replacement for professional clinical care. If a student mentions self-harm or severe crisis, gently but firmly urge them to use the 'Emergency' button or contact campus security/hotlines immediately."
        }
        
        # Add system message at the beginning
        full_history = [system_msg] + messages
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=full_history,
            temperature=0.7,
            max_tokens=500
        )
        
        return {"reply": response.choices[0].message.content}
    except Exception as e:
        print(f"OpenAI API Error: {e}")
        raise HTTPException(status_code=500, detail=f"AI Service Error: {str(e)}")


