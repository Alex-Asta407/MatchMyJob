from fastapi import APIRouter, Request, Depends, HTTPException, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from database import get_db
from models import JobPosting, Application, Resume, User
from auth.dependencies import get_current_user
from fastapi.templating import Jinja2Templates
import json
from sqlalchemy import or_

router = APIRouter(tags=["jobs"])  
templates = Jinja2Templates(directory="templates")
PAGE_SIZE = 5

@router.get("/jobs", response_class=HTMLResponse)
def list_jobs(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    page: int = Query(1, ge=1),
    search: str = None,
    location: str = None
):
    # Base query
    query = db.query(JobPosting).filter(JobPosting.is_active == True)
    
    # Apply search filter if provided
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                JobPosting.title.ilike(search_term),
                JobPosting.skills_required.ilike(search_term),
                JobPosting.company.ilike(search_term)
            )
        )
    
    # Apply location filter if provided
    if location:
        location_term = f"%{location}%"
        query = query.filter(JobPosting.location.ilike(location_term))
    
    # Get total count for pagination
    total = query.count()
    
    # Apply pagination
    jobs = (
        query
        .order_by(JobPosting.created_at.desc())
        .offset((page - 1) * PAGE_SIZE)
        .limit(PAGE_SIZE)
        .all()
    )
    
    # Parse skills_required for each job
    for job in jobs:
        if isinstance(job.skills_required, str):
            try:
                job.skills_required = json.loads(job.skills_required)
            except:
                job.skills_required = []
    
    # Get unique locations for the filter dropdown
    locations = db.query(JobPosting.location).distinct().all()
    locations = [loc[0] for loc in locations if loc[0]]  # Remove None values
    
    # Get applied job IDs if user is a job seeker
    applied_jobs = []
    if user and user.role == "job_seeker":
        applied_jobs = [app.job_id for app in user.applications]
    
    # Calculate total pages
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    
    return templates.TemplateResponse(
        "jobs.html",
        {
            "request": request,
            "user": user,
            "jobs": jobs,
            "applied_jobs": applied_jobs,
            "page": page,
            "total_pages": total_pages,
            "locations": locations,
            "search": search,
            "location": location
        }
    )


@router.get("/jobs/{job_id}", response_class=HTMLResponse)
def view_job(
    request: Request,
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Show details for a single job. If user.role == 'job_seeker',
    show an 'Apply' form with a dropdown of the user's resumes.
    """
    job = db.query(JobPosting).filter(JobPosting.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    # If the current user is a job-seeker, gather their resumes for the dropdown:
    user_resumes = []
    if user.role == "job_seeker":
        user_resumes = (
            db.query(Resume)
              .filter(Resume.user_id == user.id)
              .order_by(Resume.uploaded_at.desc())
              .all()
        )

    # Check if this user already applied to this job (so we disable repeated applications)
    already_applied = False
    if user.role == "job_seeker":
        existing_app = (
            db.query(Application)
              .filter(
                  Application.job_id == job_id,
                  Application.user_id == user.id
              ).first()
        )
        if existing_app:
            already_applied = True

    html = templates.TemplateResponse(
        "applicant/job-detail.html",
        {
            "request": request,
            "user": user,
            "job": job,
            "user_resumes": user_resumes,
            "already_applied": already_applied,
            "msg": request.query_params.get("msg", "")
        }
    )
    html.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    html.headers["Pragma"]        = "no-cache"
    html.headers["Expires"]       = "0"
    return html



@router.post("/jobs/{job_id}/apply")
def apply_to_job(
    job_id: int,
    resume_id: int = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Accept a resume_id from the job-detail page and create an Application record.
    """
    if user.role != "job_seeker":
        raise HTTPException(status_code=403, detail="Only job‐seekers may apply.")

    # 1) Ensure job exists
    job = db.query(JobPosting).filter(JobPosting.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    # 2) Ensure resume belongs to this user
    resume = (
        db.query(Resume)
          .filter(Resume.id == resume_id, Resume.user_id == user.id)
          .first()
    )
    if not resume:
        raise HTTPException(status_code=400, detail="Invalid resume selection.")

    # 3) Prevent duplicate applications
    existing = (
        db.query(Application)
          .filter(Application.job_id == job_id, Application.user_id == user.id)
          .first()
    )
    if existing:
        return RedirectResponse(
            f"/jobs/{job_id}?msg=You+have+already+applied",
            status_code=303
        )

    # 4) Create the application
    new_app = Application(
        job_id=job_id,
        resume_id=resume_id,
        user_id=user.id,
        status="Applied"
    )
    db.add(new_app)
    db.commit()

    return RedirectResponse(
        f"/jobs/{job_id}?msg=Application+submitted",
        status_code=303
    )
    
@router.post("/employer/toggle-job/{job_id}")
def toggle_job_active(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Toggle the is_active flag on a job. Only the employer who owns the job may do this.
    """
    if user.role != "employer":
        raise HTTPException(status_code=403, detail="Employer access only")

    # Fetch the job, making sure this employer actually owns it
    job = (
        db.query(JobPosting)
          .filter(JobPosting.id == job_id)
          .filter(JobPosting.employer_id == user.id)
          .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or access denied")

    # Flip is_active
    job.is_active = not job.is_active
    db.commit()   # <-- Without this commit, the change never persists

    return {"success": True, "is_active": job.is_active}