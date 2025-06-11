from fastapi import FastAPI, Request, Depends, status, Query, File, UploadFile
from sqlalchemy.orm import Session
from fastapi.responses import HTMLResponse, RedirectResponse,JSONResponse
from fastapi.templating import Jinja2Templates
from database import get_db, engine
from models import User, Resume,JobPosting, Application
from fastapi import HTTPException
from utils import match_score
from fastapi.staticfiles import StaticFiles
from jose.exceptions import ExpiredSignatureError
from auth import routers
from auth.dependencies import get_current_user
import admin,models,employer,applicant,json,jobs, applications
import os
from resume_parser import ResumeParser
import asyncio
from datetime import datetime, timedelta
from auth.email_sender import send_feedback_email

models.Base.metadata.create_all(bind=engine)
THRESHOLD = 0.3
PAGE_SIZE = 5

app = FastAPI()

# Create Jinja2Templates instance
templates = Jinja2Templates(directory="templates")

app.include_router(routers.router)
app.include_router(admin.router)
app.include_router(employer.router, prefix="/employer")
app.include_router(applicant.router, prefix="/applicant")
app.include_router(applications.router, prefix="/applicant")
app.include_router(jobs.router)

# Create static and media directories if they don't exist
os.makedirs("static", exist_ok=True)
os.makedirs("media", exist_ok=True)

# Mount static files
app.mount(
    "/static",
    StaticFiles(directory="static"),
    name="static"
)

# Mount media files
app.mount(
    "/media",
    StaticFiles(directory="media"),
    name="media"
)

# Add cache control middleware
@app.middleware("http")
async def add_cache_control_headers(request: Request, call_next):
    response = await call_next(request)
    # Add cache control headers to all responses
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.get("/",tags=['Home page'], response_class=HTMLResponse)
def root(user=Depends(get_current_user)):
    # if you get here, they're authenticated
    if user.role == "employer":
        return RedirectResponse("/employer/emp-home")
    elif user.role == "job_seeker":
        return RedirectResponse("/home")
    elif user.is_admin:
        return RedirectResponse("/admin")
    # fallback—shouldn't happen if your roles are right
    return RedirectResponse("/login")

@app.get("/home", response_class=HTMLResponse,tags=['Home page'])
def show_home(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role != "job_seeker":
        raise HTTPException(status_code=403, detail="Only job seekers can access this page.")
    
    # Get all active jobs
    active_jobs = db.query(JobPosting).filter(JobPosting.is_active == True).all()

    # Calculate skills in demand
    skills_count = {}
    total_skills = 0
    
    for job in active_jobs:
        if isinstance(job.skills_required, str):
            skills = json.loads(job.skills_required)
        else:
            skills = job.skills_required
            
        for skill in skills:
            skill = skill.strip()
            if skill:
                skills_count[skill] = skills_count.get(skill, 0) + 1
                total_skills += 1

    # Calculate percentages and sort by count
    skills_in_demand = []
    for skill, count in skills_count.items():
        percentage = (count / total_skills * 100) if total_skills > 0 else 0
        skills_in_demand.append({
            'name': skill,
            'count': count,
            'percentage': round(percentage, 1)
        })

    # Sort by count in descending order
    skills_in_demand.sort(key=lambda x: x['count'], reverse=True)

    html = templates.TemplateResponse(
        "home.html", 
        {
            "request": request, 
            "user": user,
            "skills_in_demand": skills_in_demand[:5]  # Show top 5 skills
        }
    )
    html.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    html.headers["Pragma"] = "no-cache"
    html.headers["Expires"] = "0"
    return html

@app.get("/resume", response_class=HTMLResponse,tags=['Home page'])
def resume_form(request: Request, user: User = Depends(get_current_user)):
    html =  templates.TemplateResponse("applicant/resume.html", {"request": request, "user": user})
    html.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    html.headers["Pragma"] = "no-cache"
    html.headers["Expires"] = "0"
    return html

@app.get("/matches", response_class=HTMLResponse)
def job_matches(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    page: int = Query(1, ge=1)
):
    # Get all user's resumes
    user_resumes = (
        db.query(Resume)
          .filter(Resume.user_id == user.id)
          .order_by(Resume.uploaded_at.desc())
          .all()
    )
    
    # Initialize total
    total = 0
    
    if not user_resumes:
        matched_jobs, match_scores = [], {}
    else:
        # Get all active jobs
        all_jobs_q = db.query(JobPosting).filter(JobPosting.is_active == True)
        total = all_jobs_q.count()

        # Apply offset/limit
        all_jobs = (
            all_jobs_q
              .order_by(JobPosting.created_at.desc())
              .offset((page-1)*PAGE_SIZE)
              .limit(PAGE_SIZE)
              .all()
        )

        match_scores = {}
        for job in all_jobs:
            # Ensure job skills is a list
            job_skills = job.skills_required
            if isinstance(job_skills, str):
                try:
                    job_skills = json.loads(job_skills)
                except json.JSONDecodeError:
                    job_skills = []
            elif not isinstance(job_skills, list):
                job_skills = []
            
            # Set skill_list for each job
            job.skill_list = job_skills
            
            # Calculate match scores for each resume
            resume_matches = []
            for resume in user_resumes:
                resume_skills = resume.skills if isinstance(resume.skills, list) else []
                score = match_score(job_skills, resume_skills)
                resume_matches.append({
                    'filename': resume.filename,
                    'score': score
                })
            
            # Sort resume matches by score
            resume_matches.sort(key=lambda x: x['score'], reverse=True)
            
            # Store the best match score and resume matches
            match_scores[job.id] = {
                'score': resume_matches[0]['score'] if resume_matches else 0,
                'resume_matches': resume_matches
            }

        # Filter by threshold and sort by match score
        matched_jobs = [job for job in all_jobs if match_scores[job.id]['score'] >= THRESHOLD]
        matched_jobs.sort(key=lambda job: match_scores[job.id]['score'], reverse=True)

    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE

    html = templates.TemplateResponse(
        "applicant/matches.html",
        {
            "request": request,
            "user": user,
            "matched_jobs": matched_jobs,
            "match_scores": match_scores,
            "threshold_pct": int(THRESHOLD*100),
            "page": page,
            "total_pages": total_pages,
        }
    )
    html.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    html.headers["Pragma"] = "no-cache"
    html.headers["Expires"] = "0"
    return html

@app.get("/verify",tags=['Home page'])
def verify_email(token: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.verification_token == token).first()
    if not user:
        raise HTTPException(status_code=404, detail="Invalid or expired verification link")

    user.is_verified = True
    user.verification_token = None
    db.commit()

    return RedirectResponse("/login?msg=Email+verified+successfully!", status_code=303)

@app.exception_handler(HTTPException)
async def auth_redirect(request: Request, exc: HTTPException):
    # only hijack 401 Unauthorized
    if exc.status_code == status.HTTP_401_UNAUTHORIZED:
        # you can pass along the detail as a query param if you like
        return RedirectResponse("/login?msg=Session+expired", status_code=302)
    # everything else stays JSON
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
@app.exception_handler(ExpiredSignatureError)
async def expired_jwt(request: Request, exc: ExpiredSignatureError):
    # Redirect back to login whenever a JOSE token is expired
    return RedirectResponse("/login?msg=Session+expired", status_code=302)

@app.post("/resume/upload")
async def upload_resume(
    resume: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        # Create uploads directory if it doesn't exist
        os.makedirs("uploads", exist_ok=True)
        
        # Save the file
        file_path = f"uploads/{current_user.id}_{resume.filename}"
        with open(file_path, "wb") as buffer:
            content = await resume.read()
            buffer.write(content)
        
        # Parse the resume using ResumeParser class
        parser = ResumeParser()
        parsed_data = parser.parse(file_path)
        
        # Calculate completeness based on available sections
        completeness = 0
        if parsed_data:
            # Check for essential sections
            if parsed_data.skills:
                completeness += 25
            if parsed_data.experience:
                completeness += 25
            if parsed_data.education:
                completeness += 25
            if parsed_data.raw_text:  # Using raw_text as a proxy for contact info
                completeness += 25
        
        # Create new resume record
        new_resume = Resume(
            user_id=current_user.id,
            file_path=file_path,
            parsed_data=parsed_data.to_dict(),
            completeness=completeness,
            skills=parsed_data.skills,
            experience=[exp.to_dict() for exp in parsed_data.experience],
            education=[edu.to_dict() for edu in parsed_data.education]
        )
        
        # Delete old resume if exists
        old_resume = db.query(Resume).filter(Resume.user_id == current_user.id).first()
        if old_resume:
            if os.path.exists(old_resume.file_path):
                os.remove(old_resume.file_path)
            db.delete(old_resume)
        
        db.add(new_resume)
        db.commit()
        
        return {"success": True, "message": "Resume uploaded and parsed successfully"}
    except Exception as e:
        return {"success": False, "message": str(e)}

async def cleanup_rejected_applications():
    while True:
        await asyncio.sleep(600)  # Run every 10 minutes
        with next(get_db()) as db:
            now = datetime.utcnow()
            cutoff = now - timedelta(hours=2)
            rejected_apps = db.query(Application).filter(
                Application.status == 'rejected',
                Application.status_updated_at < cutoff
            ).all()
            for app in rejected_apps:
                # Send notification email before deleting
                send_feedback_email(
                    app.applicant.email,
                    app.job.title,
                    "Your application was deleted because it was rejected and the status did not change for over 2 hours."
                )
                db.delete(app)
            db.commit()

@app.on_event("startup")
async def start_cleanup_task():
    asyncio.create_task(cleanup_rejected_applications())