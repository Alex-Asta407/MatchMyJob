from fastapi import APIRouter, Request, Depends, HTTPException, status, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db
from models import SecurityLog, User, JobPosting, Resume
from auth.dependencies import get_current_admin, log_event
import os, smtplib
from email.message import EmailMessage

router = APIRouter(tags=["Admin"])
templates = Jinja2Templates(directory="templates")


@router.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, admin: User = Depends(get_current_admin)):
    """
    Show the main admin dashboard. Requires a valid admin session.
    """
    html = templates.TemplateResponse(
        "admin/admin.html",
        {"request": request, "user": admin}
    )
    # Add no-cache headers
    html.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    html.headers["Pragma"]        = "no-cache"
    html.headers["Expires"]       = "0"
    return html


@router.get("/admin/logs", response_class=HTMLResponse)
def view_logs(
    request: Request,
    page: int = 1,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    """
    Show security logs to the admin. Protected route.
    """
    # Calculate pagination
    logs_per_page = 20
    total_logs = db.query(SecurityLog).count()
    total_pages = (total_logs + logs_per_page - 1) // logs_per_page
    
    # Ensure page is within valid range
    page = max(1, min(page, total_pages)) if total_pages > 0 else 1
    
    # Get logs for current page
    logs = (
        db.query(SecurityLog)
        .order_by(SecurityLog.timestamp.desc())
        .offset((page - 1) * logs_per_page)
        .limit(logs_per_page)
        .all()
    )
    
    html = templates.TemplateResponse(
        "admin/admin_logs.html",
        {
            "request": request,
            "logs": logs,
            "user": admin,
            "current_page": page,
            "total_pages": total_pages,
            "has_previous": page > 1,
            "has_next": page < total_pages
        }
    )
    # Prevent caching
    html.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    html.headers["Pragma"]        = "no-cache"
    html.headers["Expires"]       = "0"
    return html


@router.get("/admin/users", response_class=HTMLResponse)
def admin_users(
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    """
    List all users for the admin. Protected route.
    """
    users = db.query(User).all()
    html = templates.TemplateResponse(
        "admin/admin_users.html",
        {"request": request, "users": users, "user": admin}
    )
    # Prevent caching
    html.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    html.headers["Pragma"]        = "no-cache"
    html.headers["Expires"]       = "0"
    return html


@router.get("/admin/jobs", response_class=HTMLResponse)
def admin_jobs(
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    """
    List all job postings for the admin. Protected route.
    """
    jobs = db.query(JobPosting).all()
    html = templates.TemplateResponse(
        "admin/admin_jobs.html",
        {"request": request, "jobs": jobs, "user": admin}
    )
    # Prevent caching
    html.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    html.headers["Pragma"]        = "no-cache"
    html.headers["Expires"]       = "0"
    return html


@router.get("/admin/resumes", response_class=HTMLResponse)
def admin_resumes(
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    """
    List all resumes for the admin. Protected route.
    """
    resumes = db.query(Resume).order_by(Resume.uploaded_at.desc()).all()
    html = templates.TemplateResponse(
        "admin/admin_resumes.html",
        {"request": request, "resumes": resumes, "user": admin}
    )
    # Prevent caching
    html.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    html.headers["Pragma"]        = "no-cache"
    html.headers["Expires"]       = "0"
    return html


@router.post("/admin/delete-user/{user_id}")
def admin_delete_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
    reason: str = Form("")
):
    """
    Delete a user. Protected action.
    """
    user_to_delete = db.query(User).filter(User.id == user_id).first()
    if not user_to_delete:
        raise HTTPException(status_code=404, detail="User not found")
    if user_to_delete.id == admin.id:
        log_event(db, "Blocked Action", "Admin tried to delete themselves", email=admin.email)
        return RedirectResponse("/admin/users?msg=You+cannot+delete+yourself", status_code=303)

    db.delete(user_to_delete)
    db.commit()
    log_event(db, "Admin Action", f"Admin deleted user {user_to_delete.email}", email=admin.email)

    # Send email to user with reason
    send_violation_email_user(user_to_delete.email, reason)
    return RedirectResponse("/admin/users?msg=User+deleted", status_code=303)


@router.post("/admin/delete-resume/{resume_id}")
def admin_delete_resume(
    resume_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
    reason: str = Form("")
):
    """
    Delete a resume and notify the user via email. Protected action.
    """
    resume = db.query(Resume).filter(Resume.id == resume_id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    user = db.query(User).filter(User.id == resume.user_id).first()
    log_event(
        db,
        "Admin Action",
        f"Admin {admin.email} deleted resume “{resume.filename}” owned by {user.email}",
        email=admin.email
    )

    # Delete the resume from database
    db.delete(resume)
    db.commit()

    # Notify the user via email
    send_violation_email_resume(user.email, resume.filename, reason)
    return RedirectResponse("/admin/resumes?msg=Resume+deleted+and+user+notified", status_code=303)


@router.post("/admin/delete-job/{job_id}")
def admin_delete_job(
    job_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
    reason: str = Form("")
):
    """
    Delete a job posting and notify the employer. Protected action.
    """
    job = db.query(JobPosting).filter(JobPosting.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    owner = db.query(User).filter(User.id == job.employer_id).first()

    log_event(db, "Admin Action",
              f"Admin {admin.email} deleted job '{job.title}'", email=admin.email)

    db.delete(job)
    db.commit()

    send_notification_email_jobpost(
        owner.email,
        "MatchMyJob Job Removal Notification",
        f"Hi {owner.name},\n\n"
        f"Your job posting “{job.title}” was removed because it violated our guidelines."
        + (f"\nReason: {reason}" if reason else "")
        + "\n\nIf you believe this was a mistake, please contact support."
    )
    return RedirectResponse("/admin/jobs?msg=Job+deleted+and+user+notified", status_code=303)


@router.get("/admin/edit-job/{job_id}", response_class=HTMLResponse)
async def admin_edit_job_form(job_id: int, request: Request, db: Session = Depends(get_db)):
    job = db.query(JobPosting).filter(JobPosting.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return templates.TemplateResponse("admin/edit-job.html", {"request": request, "job": job})


@router.post("/admin/edit-job/{job_id}")
async def admin_edit_job_submit(
    job_id: int,
    request: Request,
    title: str = Form(...),
    company: str = Form(...),
    location: str = Form(...),
    employment_type: str = Form(...),
    salary_range: str = Form(...),
    description: str = Form(...),
    db: Session = Depends(get_db)
):
    job = db.query(JobPosting).filter(JobPosting.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    job.title = title
    job.company = company
    job.location = location
    job.employment_type = employment_type
    job.salary_range = salary_range
    job.description = description
    db.commit()
    return RedirectResponse("/admin/jobs", status_code=303)


def send_violation_email_resume(user_email: str, resume_filename: str, reason: str = ""):
    """
    Send an email notifying the user that their resume was removed.
    """
    msg = EmailMessage()
    msg.set_content(
        f"Your resume “{resume_filename}” was removed because it violated our guidelines."
        + (f"\nReason: {reason}" if reason else "")
    )
    msg["Subject"] = "MatchMyJob Resume Removal Notification"
    msg["From"] = os.getenv("ADMIN_EMAIL")           # e.g. admin@matchmyjob.com
    msg["To"] = user_email

    try:
        with smtplib.SMTP(os.getenv("SMTP_HOST"), int(os.getenv("SMTP_PORT"))) as smtp:
            smtp.starttls()
            smtp.login(os.getenv("SENDER_EMAIL"), os.getenv("APP_PASSWORD"))
            smtp.send_message(msg)
    except Exception as e:
        print("Failed to send violation email:", e)


def send_notification_email_jobpost(to_address: str, subject: str, body: str):
    """
    Send an email notifying the employer that their job was removed.
    """
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = os.getenv("ADMIN_EMAIL")
    msg["To"] = to_address
    msg.set_content(body)
    with smtplib.SMTP(os.getenv("SMTP_HOST"), int(os.getenv("SMTP_PORT"))) as smtp:
        smtp.starttls()
        smtp.login(os.getenv("SENDER_EMAIL"), os.getenv("APP_PASSWORD"))
        smtp.send_message(msg)


def send_violation_email_user(user_email: str, reason: str):
    """
    Send an email notifying the user that their account was removed, with a reason.
    """
    msg = EmailMessage()
    msg.set_content(
        f"Your account was removed by the admin. Reason: {reason if reason else 'No reason provided.'}"
    )
    msg["Subject"] = "MatchMyJob Account Removal Notification"
    msg["From"] = os.getenv("ADMIN_EMAIL")
    msg["To"] = user_email

    try:
        with smtplib.SMTP(os.getenv("SMTP_HOST"), int(os.getenv("SMTP_PORT"))) as smtp:
            smtp.starttls()
            smtp.login(os.getenv("SENDER_EMAIL"), os.getenv("APP_PASSWORD"))
            smtp.send_message(msg)
    except Exception as e:
        print("Failed to send violation email to user:", e)
