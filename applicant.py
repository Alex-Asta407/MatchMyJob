from fastapi import APIRouter, Request, Form, UploadFile, File, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from database import get_db
from pathlib import Path
from models import Resume, User, Application
from auth.dependencies import get_current_user
from resume_parser import ResumeParser
from datetime import datetime
import json, tempfile, os

router = APIRouter()
templates = Jinja2Templates(directory="templates")
parser = ResumeParser()

UPLOAD_DIR: Path = Path("media") / "uploads" / "resumes"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

@router.get("/profile", response_class=HTMLResponse)
def applicant_profile(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if user.role != "job_seeker":
        raise HTTPException(status_code=403, detail="Only job seekers can access this page")
    
    # Fetch user's resumes
    resumes = (
        db.query(Resume)
          .filter(Resume.user_id == user.id)
          .order_by(Resume.uploaded_at.desc())
          .all()
    )
    
    # Process each resume to deserialize JSON data
    for resume in resumes:
        resume.uploaded_at_str = resume.uploaded_at.strftime("%B %d, %Y")
        # Use helper methods to get the data
        resume.skills = resume.get_skills()
        resume.experience = resume.get_experience()
        resume.education = resume.get_education()
    
    html = templates.TemplateResponse(
        "applicant/applicant-profile.html",
        {
            "request": request,
            "user": user,
            "resumes": resumes
        }
    )
    html.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    html.headers["Pragma"] = "no-cache"
    html.headers["Expires"] = "0"
    return html

@router.get("/profile/edit", response_class=HTMLResponse)
def edit_profile(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if user.role != "job_seeker":
        raise HTTPException(status_code=403, detail="Only job seekers can access this page")
    
    html = templates.TemplateResponse(
        "applicant/edit-profile.html",
        {
            "request": request,
            "user": user
        }
    )
    html.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    html.headers["Pragma"] = "no-cache"
    html.headers["Expires"] = "0"
    return html

@router.post("/profile/edit")
async def update_profile(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if user.role != "job_seeker":
        raise HTTPException(status_code=403, detail="Only job seekers can access this page")
    
    form_data = await request.form()
    
    # Update user profile fields
    user.full_name = form_data.get("full_name", user.full_name)
    user.location = form_data.get("location", user.location)
    user.phone = form_data.get("phone", user.phone)
    user.preferred_job_types = form_data.get("preferred_job_types", user.preferred_job_types)
    user.preferred_locations = form_data.get("preferred_locations", user.preferred_locations)
    
    db.commit()
    
    return RedirectResponse("/applicant/profile?msg=Profile+updated+successfully", status_code=303)

@router.post("/resume")
async def upload_resume(
    resume: UploadFile = File(..., alias="resume"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    if user.role != "job_seeker":
        raise HTTPException(403, "Only job-seekers can upload resumes")

    # 1) Validate file type
    allowed_types = {
        "application/pdf": ".pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        "text/plain": ".txt"
    }
    if resume.content_type not in allowed_types:
        raise HTTPException(400, "PDF, DOCX or TXT only")

    existing = (
        db.query(Resume)
          .filter(Resume.user_id == user.id, Resume.filename == resume.filename)
          .first()
    )
    if existing:
        return RedirectResponse(
            f"/applicant/profile?msg=The+same+resume+isn't+allowed",
            status_code=303
        )

    # 3) Save the file to disk
    safe_name     = os.path.basename(resume.filename)
    file_location = UPLOAD_DIR / f"{user.id}_{safe_name}"
    with open(file_location, "wb") as f:
        f.write(await resume.read())

    parsed = parser.parse(str(file_location))

    # Convert skills to JSON string, ensuring it's a list
    skills_list = parsed.skills if isinstance(parsed.skills, list) else []
    
    # Convert education to list of dictionaries and ensure JSON serialization
    education_list = []
    if parsed.education:
        for edu in parsed.education:
            edu_dict = edu.to_dict()
            # Format education as a readable string
            edu_str = f"{edu_dict['degree']} at {edu_dict['institution']}"
            if edu_dict.get('start_date') and edu_dict.get('end_date'):
                edu_str += f" ({edu_dict['start_date']} - {edu_dict['end_date']})"
            elif edu_dict.get('start_date'):
                edu_str += f" (Started {edu_dict['start_date']})"
            education_list.append(edu_str)
    
    # Convert experience to list of dictionaries and ensure JSON serialization
    experience_list = []
    if parsed.experience:
        for exp in parsed.experience:
            exp_dict = exp.to_dict()
            # Format experience as a readable string
            exp_str = f"{exp_dict['title']} at {exp_dict['company']}"
            if exp_dict.get('start_date') and exp_dict.get('end_date'):
                exp_str += f" ({exp_dict['start_date']} - {exp_dict['end_date']})"
            elif exp_dict.get('start_date'):
                exp_str += f" (Started {exp_dict['start_date']})"
            if exp_dict.get('description'):
                exp_str += f"\n• " + "\n• ".join(exp_dict['description'])
            experience_list.append(exp_str)

    # Calculate completeness score
    completeness = 0
    
    # Skills section (25%)
    skills_score = 0
    if skills_list and len(skills_list) > 0:
        # Base score for having skills
        skills_score += 10
        # Additional points based on number of skills
        if len(skills_list) >= 5:
            skills_score += 10
        if len(skills_list) >= 10:
            skills_score += 5
    completeness += skills_score

    # Experience section (25%)
    experience_score = 0
    if experience_list and len(experience_list) > 0:
        # Base score for having experience
        experience_score += 10
        # Additional points based on number of experiences
        if len(experience_list) >= 2:
            experience_score += 10
        if len(experience_list) >= 3:
            experience_score += 5
        # Check for detailed descriptions
        detailed_experiences = sum(1 for exp in experience_list if len(exp.split('\n')) > 2)
        if detailed_experiences > 0:
            experience_score += 5
    completeness += experience_score

    # Education section (25%)
    education_score = 0
    if education_list and len(education_list) > 0:
        # Base score for having education
        education_score += 10
        # Additional points based on number of education entries
        if len(education_list) >= 2:
            education_score += 10
        if len(education_list) >= 3:
            education_score += 5
        # Check for detailed education entries
        detailed_education = sum(1 for edu in education_list if len(edu.split()) > 10)
        if detailed_education > 0:
            education_score += 5
    completeness += education_score

    # Contact & Additional Information (25%)
    contact_score = 0
    if parsed.raw_text:
        # Base score for having content
        contact_score += 5
        # Length-based scoring
        text_length = len(parsed.raw_text)
        if text_length > 100:
            contact_score += 5
        if text_length > 500:
            contact_score += 5
        if text_length > 1000:
            contact_score += 5
        # Check for common contact indicators
        contact_indicators = ['email', 'phone', 'address', 'linkedin', 'github', 'portfolio']
        found_indicators = sum(1 for indicator in contact_indicators if indicator.lower() in parsed.raw_text.lower())
        contact_score += min(found_indicators * 2, 10)  # Up to 10 points for contact information
    completeness += contact_score

    # Ensure score doesn't exceed 100
    completeness = min(completeness, 100)

    # Create the resume object with pre-serialized JSON strings
    db_resume = Resume(
        filename   = resume.filename,
        user_id    = user.id,
        raw_text   = parsed.raw_text,
        completeness = completeness  # Add completeness score
    )
    
    # Use helper methods to set the data
    db_resume.set_skills(skills_list)
    db_resume.set_experience(experience_list)
    db_resume.set_education(education_list)
    
    db.add(db_resume)
    db.commit()

    return RedirectResponse(
        "/applicant/profile?msg=Resume+uploaded+and+parsed",
        status_code=303
    )

@router.post("/resume/delete/{resume_id}")
def delete_resume(resume_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    resume = db.query(Resume).filter(Resume.id == resume_id, Resume.user_id == user.id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found or access denied.")
    file_on_disk = UPLOAD_DIR / f"{user.id}_{resume.filename}"
    if file_on_disk.exists():
        file_on_disk.unlink()

    db.delete(resume)
    db.commit()

    return RedirectResponse("/applicant/profile?msg=Resume+deleted", status_code=303)

@router.get("/resume/{resume_id}/edit", response_class=HTMLResponse)
def edit_resume_form(
    request: Request,
    resume_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    # 1) Fetch & permission-check
    resume = (
        db.query(Resume)
          .filter(Resume.id == resume_id, Resume.user_id == user.id)
          .first()
    )
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found.")
    if user.role != "job_seeker":
        raise HTTPException(status_code=403, detail="Access denied.")

    # 2) Pull out the parsed fields
    skills_list     = resume.skills       # e.g. ["Python", "SQL", "Docker"]
    experience_text = resume.experience   # e.g. "– Software Engineer at Acme…"
    raw_text        = resume.raw_text     # original raw text, read-only

    html = templates.TemplateResponse(
        "/applicant/applicant-resume-edit.html",    # put your file under templates/
        {
            "request": request,
            "user": user,
            "resume": resume,
            "skills_list": skills_list,
            "experience_text": experience_text,
            "raw_text": raw_text,
        }
    )
    html.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    html.headers["Pragma"] = "no-cache"
    html.headers["Expires"] = "0"
    return html


@router.post("/resume/{resume_id}/edit")
async def edit_resume_submit(
    resume_id: int,
    skills: list[str] = Form(...),       # ← MUST be "skills"
    education: list[str] = Form(...),    # ← Added education field
    experience: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    # 1) Fetch & permission-check again
    resume = (
        db.query(Resume)
          .filter(Resume.id == resume_id, Resume.user_id == user.id)
          .first()
    )
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found.")
    if user.role != "job_seeker":
        raise HTTPException(status_code=403, detail="Access denied.")

    # 2) Clean up the submitted arrays
    clean_skills = [s.strip() for s in skills if s.strip()]
    clean_education = [e.strip() for e in education if e.strip()]
    clean_experience = experience.strip()

    # 3) Overwrite the Resume fields
    resume.set_skills(clean_skills)
    resume.set_education(clean_education)
    resume.set_experience([clean_experience])

    # 4) Persist to database
    db.commit()

    # 5) Redirect back to the profile page
    return RedirectResponse(
        "/applicant/profile?msg=Resume+updated",
        status_code=303
    )

@router.post("/resume/reparse/{resume_id}")
async def reparse_resume(
    resume_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Re-run the parser on the previously saved file and overwrite
    skills/experience/education/raw_text in the database.
    """
    # 1) Fetch & permission-check
    resume = (
        db.query(Resume)
          .filter(Resume.id == resume_id, Resume.user_id == user.id)
          .first()
    )
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found.")
    if user.role != "job_seeker":
        raise HTTPException(status_code=403, detail="Access denied.")

    # 2) Locate the file on disk
    file_on_disk = UPLOAD_DIR / f"{user.id}_{resume.filename}"
    if not file_on_disk.exists():
        raise HTTPException(status_code=404, detail="Stored file not found.")

    # 3) Re-run the parser
    parser = ResumeParser()
    parsed = parser.parse(str(file_on_disk))

    # 4) Update the database record
    # Convert skills to JSON string, ensuring it's a list
    skills_list = parsed.skills if isinstance(parsed.skills, list) else []
    
    # Convert education to list of dictionaries and ensure JSON serialization
    education_list = []
    if parsed.education:
        for edu in parsed.education:
            edu_dict = edu.to_dict()
            # Format education as a readable string
            edu_str = f"{edu_dict['degree']} at {edu_dict['institution']}"
            if edu_dict.get('start_date') and edu_dict.get('end_date'):
                edu_str += f" ({edu_dict['start_date']} - {edu_dict['end_date']})"
            elif edu_dict.get('start_date'):
                edu_str += f" (Started {edu_dict['start_date']})"
            education_list.append(edu_str)
    
    # Convert experience to list of dictionaries and ensure JSON serialization
    experience_list = []
    if parsed.experience:
        for exp in parsed.experience:
            exp_dict = exp.to_dict()
            # Format experience as a readable string
            exp_str = f"{exp_dict['title']} at {exp_dict['company']}"
            if exp_dict.get('start_date') and exp_dict.get('end_date'):
                exp_str += f" ({exp_dict['start_date']} - {exp_dict['end_date']})"
            elif exp_dict.get('start_date'):
                exp_str += f" (Started {exp_dict['start_date']})"
            if exp_dict.get('description'):
                exp_str += f"\n• " + "\n• ".join(exp_dict['description'])
            experience_list.append(exp_str)

    # Calculate completeness score
    completeness = 0
    
    # Skills section (25%)
    skills_score = 0
    if skills_list and len(skills_list) > 0:
        # Base score for having skills
        skills_score += 10
        # Additional points based on number of skills
        if len(skills_list) >= 5:
            skills_score += 10
        if len(skills_list) >= 10:
            skills_score += 5
    completeness += skills_score

    # Experience section (25%)
    experience_score = 0
    if experience_list and len(experience_list) > 0:
        # Base score for having experience
        experience_score += 10
        # Additional points based on number of experiences
        if len(experience_list) >= 2:
            experience_score += 10
        if len(experience_list) >= 3:
            experience_score += 5
        # Check for detailed descriptions
        detailed_experiences = sum(1 for exp in experience_list if len(exp.split('\n')) > 2)
        if detailed_experiences > 0:
            experience_score += 5
    completeness += experience_score

    # Education section (25%)
    education_score = 0
    if education_list and len(education_list) > 0:
        # Base score for having education
        education_score += 10
        # Additional points based on number of education entries
        if len(education_list) >= 2:
            education_score += 10
        if len(education_list) >= 3:
            education_score += 5
        # Check for detailed education entries
        detailed_education = sum(1 for edu in education_list if len(edu.split()) > 10)
        if detailed_education > 0:
            education_score += 5
    completeness += education_score

    # Contact & Additional Information (25%)
    contact_score = 0
    if parsed.raw_text:
        # Base score for having content
        contact_score += 5
        # Length-based scoring
        text_length = len(parsed.raw_text)
        if text_length > 100:
            contact_score += 5
        if text_length > 500:
            contact_score += 5
        if text_length > 1000:
            contact_score += 5
        # Check for common contact indicators
        contact_indicators = ['email', 'phone', 'address', 'linkedin', 'github', 'portfolio']
        found_indicators = sum(1 for indicator in contact_indicators if indicator.lower() in parsed.raw_text.lower())
        contact_score += min(found_indicators * 2, 10)  # Up to 10 points for contact information
    completeness += contact_score

    # Ensure score doesn't exceed 100
    completeness = min(completeness, 100)

    # Update the resume record with properly serialized data
    resume.set_skills(skills_list)
    resume.set_experience(experience_list)
    resume.set_education(education_list)
    resume.raw_text = parsed.raw_text
    resume.completeness = completeness  # Update completeness score
    resume.parsed_at = datetime.utcnow()
    db.commit()

    return RedirectResponse(
        "/applicant/profile?msg=Resume+reparsed",
        status_code=303
    )

@router.get("/applications", response_class=HTMLResponse)
def view_applications(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if user.role != "job_seeker":
        raise HTTPException(status_code=403, detail="Only job seekers can access this page")
    
    # Get all applications for the user
    applications = (
        db.query(Application)
        .filter(Application.user_id == user.id)
        .order_by(Application.submission_timestamp.desc())
        .all()
    )
    
    return templates.TemplateResponse(
        "applicant/applicant-applications.html",
        {
            "request": request,
            "user": user,
            "applications": applications
        }
    )

@router.get("/applicant/onboarding", response_class=HTMLResponse)
def applicant_onboarding_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if user.role != "job_seeker":
        raise HTTPException(status_code=403, detail="Only job seekers can access this page")
    
    return templates.TemplateResponse(
        "applicant/onboarding.html",
        {
            "request": request,
            "user": user
        }
    )

@router.post("/applicant/onboarding", response_class=HTMLResponse)
def applicant_onboarding(
    request: Request,
    location: str = Form(...),
    employment_type: str = Form(...),
    experience_level: str = Form(...),
    skills: str = Form(...),
    bio: str = Form(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if user.role != "job_seeker":
        raise HTTPException(status_code=403, detail="Only job seekers can access this page")
    
    # Update user profile
    user.location = location
    user.employment_type = employment_type
    user.experience_level = experience_level
    user.skills = [skill.strip() for skill in skills.split(",")]
    user.bio = bio
    user.profile_completed = True
    
    db.commit()
    
    return RedirectResponse(url="/applicant/profile", status_code=303)

@router.get("/faq", response_class=HTMLResponse)
def applicant_faq(request: Request, user: User = Depends(get_current_user)):
    if user.role != "job_seeker":
        raise HTTPException(status_code=403, detail="Only job seekers can access this page")
    html = templates.TemplateResponse(
        "applicant/applicant-faq.html",
        {"request": request, "user": user}
    )
    html.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    html.headers["Pragma"] = "no-cache"
    html.headers["Expires"] = "0"
    return html