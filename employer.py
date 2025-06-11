from fastapi import APIRouter, Request, Depends, HTTPException,Form
from fastapi.responses import HTMLResponse,RedirectResponse
from sqlalchemy.orm import Session
from models import JobPosting, User, Application, Resume
from fastapi.templating import Jinja2Templates
from auth.dependencies import get_current_user
from datetime import datetime
import database,json
from typing import Optional
get_db = database.get_db
router = APIRouter(
    tags=["Employer"]
)
templates = Jinja2Templates(directory="templates")

@router.get("/emp-home", response_class=HTMLResponse)
def employer_home(
    request: Request, 
    user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if user.role != "employer":
        raise HTTPException(status_code=403, detail="Employer access only")
    
    # Get active jobs count
    active_jobs_count = db.query(JobPosting).filter(
        JobPosting.employer_id == user.id,
        JobPosting.is_active == True
    ).count()

    # Get total applications count
    total_applications = db.query(Application).join(
        JobPosting
    ).filter(
        JobPosting.employer_id == user.id
    ).count()

    # Calculate average applications per job
    avg_applications_per_job = float(total_applications) / float(active_jobs_count) if active_jobs_count > 0 else 0.0
    html = templates.TemplateResponse(
        "employer/emp-home.html", 
        {
            "request": request, 
            "user": user,
            "active_jobs_count": active_jobs_count,
            "total_applications": total_applications,
            "avg_applications_per_job": avg_applications_per_job
        }
    )
    html.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    html.headers["Pragma"]        = "no-cache"
    html.headers["Expires"]       = "0"
    return html
   
@router.get("/post-job", response_class=HTMLResponse)
def show_post_job_form(
    request: Request,
    user: User = Depends(get_current_user)
):
    if user.role != "employer":
        raise HTTPException(403, "Employer access only")
    html = templates.TemplateResponse(
        "employer/post-job.html",
        {"request": request, "user": user}
    )
    html.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    html.headers["Pragma"] = "no-cache"
    html.headers["Expires"] = "0"
    return html

@router.post("/post-job", response_class=HTMLResponse)
def create_job(
    request: Request,
    title: str | None = Form(None),
    description: str | None = Form(None),
    skills_required: str | None = Form(None),
    company: str | None = Form(None),
    location: str | None = Form(None),
    salary_range: str | None = Form(None),
    employment_type: str | None = Form(None),
    deadline: str | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role != "employer":
        raise HTTPException(403, "Employer access only")

    # Enforce description length
        # 1) Validate required fields and comma-separated skills
    errors = []
    if not title:
        errors.append("Job title is required.")
    if not description:
        errors.append("Description is required.")
    elif len(description) > 500:
        errors.append("Description cannot exceed 500 characters.")
    if not skills_required:
        errors.append("Required skills are required.")
    else:
        if "," not in skills_required:
            errors.append("Skills must be comma-separated, e.g. Python, JavaScript, React.")

    # If any validation errors, re-render form with all previous inputs
    if errors:
        return templates.TemplateResponse(
            "employer/post-job.html",
            {
                "request": request,
                "user":    user,
                "errors":  errors,
                "title":            title or "",
                "description":      description or "",
                "company":          company or "",
                "skills_required":  skills_required or "",
                "location":         location or "",
                "salary_range":     salary_range or "",
                "employment_type":  employment_type or "",
                "deadline":         deadline or "",
            }
        )

    # 2) Parse skills into a list
    skills_list = [s.strip() for s in skills_required.split(",") if s.strip()]

    # Convert deadline string to date object if provided
    deadline_date = None
    if deadline:
        try:
            deadline_date = datetime.strptime(deadline, "%Y-%m-%d").date()
        except ValueError:
            return templates.TemplateResponse(
                "employer/post-job.html",
                {"request": request, "user": user, "error": "Invalid deadline format. Use YYYY-MM-DD.",
                 "title": title, "description": description, "skills_required": skills_required, "company": company,
                 "location": location, "salary_range": salary_range, "employment_type": employment_type, "deadline": deadline}
            )

    # Create new job posting
    job = JobPosting(
        title=title,
        description=description,
        skills_required=skills_list,  # Direct list assignment
        company=company,
        location=location,
        salary_range=salary_range,
        employment_type=employment_type,
        deadline=deadline_date,  # Use the converted date object
        employer_id=user.id
    )

    db.add(job)
    db.commit()
    db.refresh(job)

    return RedirectResponse("/employer/employer-jobs?msg=Job+posted", status_code=303)

@router.get("/edit-job/{job_id}", response_class=HTMLResponse)
def edit_job_form(
    request: Request,
    job_id: int,
    db: Session = Depends(get_db),
    user = Depends(get_current_user)
):
    job = db.query(JobPosting).filter(JobPosting.id == job_id).first()
    if not job or job.employer_id != user.id:
        raise HTTPException(404, "Job not found or access denied")

    # job.skills_required may already be a Python list
    if isinstance(job.skills_required, str):
        skills_list = json.loads(job.skills_required)
    else:
        skills_list = job.skills_required

    skills_str  = ", ".join(skills_list)

    html = templates.TemplateResponse(
        "employer/edit-job.html",
        {
            "request": request,
            "user": user,
            "job": job,
            "skills_str": skills_str
        }
    )
    html.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    html.headers["Pragma"]        = "no-cache"
    html.headers["Expires"]       = "0"
    return html

@router.post("/edit-job/{job_id}")
def submit_job_edit(
    job_id: int,
    title: str = Form(...),
    company: str = Form(...),
    description: str = Form(...),
    skills_required: str = Form(...),
    location: str = Form(None),
    is_active: Optional[str] = Form(None),
    salary_range: str = Form(None),
    employment_type: str = Form(None),
    deadline: str = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    job = db.query(JobPosting).filter(JobPosting.id == job_id).first()
    if not job or job.employer_id != user.id:
        raise HTTPException(404, "Job not found or access denied")

    if len(description) > 500:
        return RedirectResponse(
            f"/employer/edit-job/{job_id}?msg=Description+cannot+exceed+500+characters",
            status_code=303
        )
    # Parse skills
    try:
        skills = json.loads(skills_required)
        if not isinstance(skills, list):
            raise ValueError()
        skills_list = [s.strip() for s in skills if s.strip()]
    except:
        if "," not in skills_required:
            return RedirectResponse(
                f"/employer/edit-job/{job_id}?msg=Skills+must+be+comma+separated",
                status_code=303
            )
        skills_list = [s.strip() for s in skills_required.split(",") if s.strip()]

    # Update job posting
    job.title = title
    job.description = description
    job.skills_required = skills_list  # Direct list assignment
    job.company = company
    job.location = location
    job.salary_range = salary_range
    job.employment_type = employment_type
    job.deadline = deadline
    job.is_active = True if is_active == "on" else False

    db.commit()
    return RedirectResponse("/employer/employer-jobs?msg=Job+updated+successfully", status_code=303)

@router.post("/delete-job/{job_id}")
def delete_job(
    job_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if user.role != "employer":
        raise HTTPException(status_code=403, detail="Only employers can access this page")
    
    job_posting = db.query(JobPosting).filter(
        JobPosting.id == job_id,
        JobPosting.employer_id == user.id
    ).first()
    
    if not job_posting:
        raise HTTPException(status_code=404, detail="Job posting not found")
    
    db.delete(job_posting)
    db.commit()
    
    return RedirectResponse("/employer/employer-jobs?msg=Job+deleted+successfully", status_code=303)

@router.get("/profile", response_class=HTMLResponse)
def employer_profile(
    request: Request,
    db: Session = Depends(get_db),
    user: User   = Depends(get_current_user)
):
    if user.role != "employer":
        raise HTTPException(403, "Access denied")

    # load & format this employer's jobs
    jobs = (
        db.query(JobPosting)
          .filter(JobPosting.employer_id == user.id)
          .order_by(JobPosting.created_at.desc())
          .all()
    )
    for j in jobs:
        # JSON-load skills into a list for the template
        j.skill_list = (
            json.loads(j.skills_required)
            if isinstance(j.skills_required, str)
            else j.skills_required
        )
        j.posted_at = j.created_at.strftime("%Y-%m-%d %H:%M")

    html = templates.TemplateResponse(
        "employer/emp-profile.html",
        {"request": request, "user": user, "jobs": jobs}
    )
    html.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    html.headers["Pragma"]        = "no-cache"
    html.headers["Expires"]       = "0"
    return html

@router.get("/jobs/{job_id}/applications", response_class=HTMLResponse)
def view_job_applications(
    request: Request,
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    List all applications for a given job. Only the employer who posted
    this job (i.e. job.posted_by_id == user.id) may view it.
    """
    if user.role != "employer":
        raise HTTPException(status_code=403, detail="Only employers can view job applications.")

    job = db.query(JobPosting).filter(JobPosting.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job.employer_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied for this job.")
    apps = (
        db.query(Application)
          .filter(Application.job_id == job_id)
          .order_by(Application.submission_timestamp.desc())
          .all()
    )

    html =  templates.TemplateResponse(
        "employer/employer-job-applications.html",
        {
            "request": request,
            "user": user,
            "job": job,
            "applications": apps,
            "msg": request.query_params.get("msg", "")
        }
    )
    html.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    html.headers["Pragma"]        = "no-cache"
    html.headers["Expires"]       = "0"
    return html

@router.get("/applications", response_class=HTMLResponse)
async def view_applications(
    request: Request,
    job_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    if user.role != "employer":
        raise HTTPException(status_code=403, detail="Not authorized")

    # Get employer's job postings
    employer_jobs = db.query(JobPosting).filter(JobPosting.employer_id == user.id).all()
    job_ids = [job.id for job in employer_jobs]

    # Base query for applications
    query = db.query(Application).filter(Application.job_id.in_(job_ids))

    # If viewing a specific job's applications
    if job_id:
        job = db.query(JobPosting).filter(JobPosting.id == job_id, JobPosting.employer_id == user.id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        query = query.filter(Application.job_id == job_id)
    else:
        # Get the first job posting to get the company name
        first_job = db.query(JobPosting).filter(JobPosting.employer_id == user.id).first()
        company_name = first_job.company if first_job else "Your Company"
        job = type('JobPosting', (), {'id': None, 'title': 'All Applications', 'company': company_name})()

    # Get applications with related data
    applications = query.order_by(Application.submission_timestamp.desc()).all()

    # Add job and applicant details to each application
    for app in applications:
        app.job = db.query(JobPosting).filter(JobPosting.id == app.job_id).first()
        app.applicant = db.query(User).filter(User.id == app.user_id).first()
        if app.resume_id:
            app.resume = db.query(Resume).filter(Resume.id == app.resume_id).first()

    return templates.TemplateResponse(
        "employer/employer-job-applications.html",
        {
            "request": request,
            "user": user,
            "applications": applications,
            "job": job
        },
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"}
    )

@router.post("/applications/{application_id}/status")
async def update_application_status(
    application_id: int,
    new_status: str = Form(...),
    feedback: str = Form(None),
    request: Request = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    if user.role != "employer":
        raise HTTPException(status_code=403, detail="Not authorized")

    # Get the application
    application = db.query(Application).filter(Application.id == application_id).first()
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    # Verify the job belongs to the employer
    job = db.query(JobPosting).filter(JobPosting.id == application.job_id).first()
    if not job or job.employer_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Update the status and feedback
    application.status = new_status
    application.feedback = feedback
    application.status_updated_at = datetime.utcnow()
    db.commit()

    # Send feedback email to the user
    if feedback:
        from auth.email_sender import send_feedback_email
        send_feedback_email(application.applicant.email, job.title, feedback)

    # Redirect back to the main applications page
    return RedirectResponse(
        url="/employer/applications?msg=Status+updated+successfully",
        status_code=303
    )

@router.get("/profile/edit", response_class=HTMLResponse)
def edit_profile_form(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if user.role != "employer":
        raise HTTPException(403, "Access denied")
    
    html = templates.TemplateResponse(
        "employer/edit-profile.html",
        {"request": request, "user": user}
    )
    html.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    html.headers["Pragma"] = "no-cache"
    html.headers["Expires"] = "0"
    return html

@router.post("/profile/edit")
def update_profile(
    request: Request,
    company_name: str = Form(...),
    email: str = Form(...),
    company_address: str = Form(None),
    website: str = Form(None),
    company_description: str = Form(None),
    phone: str = Form(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if user.role != "employer":
        raise HTTPException(403, "Access denied")
    
    # Update user profile
    user.company_name = company_name
    user.email = email
    user.company_address = company_address
    user.website = website
    user.company_description = company_description
    user.phone = phone
    
    db.commit()
    
    return RedirectResponse("/employer/profile?msg=Profile+updated+successfully", status_code=303)

@router.get("/employer-jobs", response_class=HTMLResponse)
async def view_employer_jobs(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if user.role != "employer":
        raise HTTPException(status_code=403, detail="Only employers can access this page")
    
    # Get all jobs posted by this employer
    job_postings = db.query(JobPosting).filter(JobPosting.employer_id == user.id).order_by(JobPosting.created_at.desc()).all()
    
    return templates.TemplateResponse(
        "employer/employer-jobs.html",
        {
            "request": request,
            "user": user,
            "job_postings": job_postings,
            "msg": request.query_params.get("msg")
        }
    )

@router.get("/employer/onboarding", response_class=HTMLResponse)
def employer_onboarding_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if user.role != "employer":
        raise HTTPException(status_code=403, detail="Only employers can access this page")
    
    return templates.TemplateResponse(
        "employer/onboarding.html",
        {
            "request": request,
            "user": user
        }
    )

@router.post("/employer/onboarding", response_class=HTMLResponse)
def employer_onboarding(
    request: Request,
    company_name: str = Form(...),
    company_size: str = Form(...),
    industry: str = Form(...),
    location: str = Form(...),
    website: str = Form(...),
    description: str = Form(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if user.role != "employer":
        raise HTTPException(status_code=403, detail="Only employers can access this page")
    
    # Update user profile
    user.company_name = company_name
    user.company_size = company_size
    user.industry = industry
    user.location = location
    user.website = website
    user.description = description
    user.profile_completed = True
    
    db.commit()
    
    return RedirectResponse(url="/employer/home", status_code=303)