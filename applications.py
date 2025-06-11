from typing import Dict
from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from database import get_db
from models import Application, JobPosting, Resume, User
from auth.dependencies import get_current_user
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/applications", response_class=HTMLResponse)
def list_my_applications(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Show a job-seeker all of their applications, with job info and resume info.
    """
    if user.role != "job_seeker":
        raise HTTPException(status_code=403, detail="Only job‐seekers can view this page.")

    # Fetch all applications by this user, join with JobPosting and Resume
    apps = (
        db.query(Application)
          .filter(Application.user_id == user.id)
          .order_by(Application.submission_timestamp.desc())
          .all()
    )
    
    notice = pending_notifications.pop(user.id, "")

    # We'll pass them directly to the template; each app has .job and .resume relationships
    html = templates.TemplateResponse(
        "applicant/applicant-applications.html",
        {
            "request": request,
            "user": user,
            "applications": apps,
        }
    )
    html.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    html.headers["Pragma"]        = "no-cache"
    html.headers["Expires"]       = "0"
    return html
    
@router.post("/applications/{app_id}/delete")
def delete_my_application(
    app_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Allow a job‐seeker to delete their own application.
    """
    if user.role != "job_seeker":
        raise HTTPException(status_code=403, detail="Only job‐seekers can delete applications.")

    # Fetch the application and ensure it belongs to this user
    app_record = db.query(Application).filter(
        Application.id == app_id,
        Application.user_id == user.id
    ).first()

    if not app_record:
        # Either it doesn't exist, or does not belong to this user
        raise HTTPException(status_code=404, detail="Application not found or access denied.")

    db.delete(app_record)
    db.commit()

    # Redirect back to "My Applications"
    return RedirectResponse("/applications?msg=Application+deleted", status_code=303)

pending_notifications: Dict[int, str] = {}  # maps applicant_user_id -> message

@router.post("/applications/{app_id}/status")
def update_application_status(
    app_id: int,
    new_status: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    if user.role != "employer":
        raise HTTPException(status_code=403, detail="Only employers can update application status.")

    app_record = (
        db.query(Application)
          .join(JobPosting, Application.job_id == JobPosting.id)
          .filter(
            Application.id == app_id,
            JobPosting.employer_id == user.id
          )
          .first()
    )
    if not app_record:
        raise HTTPException(status_code=404, detail="Application not found or access denied.")

    # Update status
    app_record.status = new_status
    db.commit()

    # Queue a notification for the applicant
    applicant_id = app_record.user_id
    pending_notifications[applicant_id] = f"Status for job '{app_record.job.title}' updated to {new_status}."

    return RedirectResponse(
        f"/jobs/{app_record.job_id}/applications?msg=Status+updated",
        status_code=303
    )
