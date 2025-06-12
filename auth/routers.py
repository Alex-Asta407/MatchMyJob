from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session
from database import get_db
from models import User, RevokedToken, JobPosting, Application
from jose import jwt
from auth.tokenhash import SECRET_KEY, ALGORITHM
from .tokenhash import hash_password, verify_password, create_access_token
from fastapi.templating import Jinja2Templates
from .dependencies import get_current_user_optional, get_current_user, get_current_admin, log_event
import uuid
from datetime import datetime, timedelta
from .email_sender import send_verification_email, send_password_reset_email
import re

router = APIRouter(
    tags=['Authentication']
)
templates = Jinja2Templates(directory="templates")
@router.get("/login", response_class=HTMLResponse)
def login_get(request: Request, user = Depends(get_current_user_optional)):
    if user:
        return RedirectResponse("/home?msg=You+are+already+logged+in", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request})

@router.post("/login")
def login_post(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email).first()
    ip = request.client.host

    if not user:
        log_event(db, "Failed Login", "User not found", email=email, ip=ip)
        return RedirectResponse("/login?msg=User+is+not+found+in+the+system", status_code=303)

    if not verify_password(password, user.hashed_password):
        log_event(db, "Failed Login", "Invalid password", email=email, ip=ip)
        return RedirectResponse("/login?msg=Please+repeat+your+password.+It's+incorrect.", status_code=303)

    if not user.is_verified:
        log_event(db, "Blocked Login", "Account not verified", email=email, ip=ip)
        return RedirectResponse("/login?msg=Please+verify+your+account", status_code=303)
    token = create_access_token({"sub": user.email})

    redirect_url = "/home"
    if user.role == "employer":
        redirect_url = "/employer/emp-home"
    elif user.role == "admin":
        redirect_url = "/admin"
    response = RedirectResponse(f"{redirect_url}?msg=Login+successful", status_code=303)
    response.set_cookie(key="access_token", value=token, httponly=True)

    log_event(db, "Login Success", "User successfully logged in", email=user.email, ip=ip)
    return response

@router.get("/terms", response_class=HTMLResponse)
async def terms(request: Request):
    return templates.TemplateResponse("terms.html", {"request": request})

@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@router.post("/register", response_class=HTMLResponse)
async def register(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    role: str = Form(...),
    terms: bool = Form(False),
    # Job seeker fields
    current_job_title: str = Form(None),
    years_experience: str = Form(None),
    desired_job_title: str = Form(None),
    key_skills: str = Form(None),
    preferred_location: str = Form(None),
    salary_range: str = Form(None),
    # Employer fields
    company_name: str = Form(None),
    company_size: str = Form(None),
    industry: str = Form(None),
    location: str = Form(None),
    website: str = Form(None),
    db: Session = Depends(get_db)
):
    # Check if terms are agreed to
    if not terms:
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "error": "You must agree to the Terms and Conditions to register."
            }
        )

    # Check if passwords match
    if password != confirm_password:
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "error": "Passwords do not match."
            }
        )

    # Check if email already exists
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "error": "Email already registered."
            }
        )

    # Validate role
    if role not in ["job_seeker", "employer"]:
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "error": "Invalid role selected."
            }
        )

    # Password validation
    forbidden_chars = r'[\}\{":~,]'
    if len(password) < 8:
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "error": "Password must be at least 8 characters long."
            }
        )
    if re.search(forbidden_chars, password):
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "error": "Password cannot contain any of the following characters: } { \" : ~ ,"
            }
        )

    # Create new user
    verification_token = str(uuid.uuid4())
    new_user = User(
        name=name,
        email=email,
        role=role,
        verification_token=verification_token
    )
    try:
        new_user.set_password(password)
    except ValueError as e:
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "error": str(e)
            }
        )
    
    db.add(new_user)
    db.commit()

    # Send verification email
    send_verification_email(email, verification_token)

    # Redirect to appropriate dashboard
    return RedirectResponse(
        "/login?msg=Registration+successful!+Please+check+your+email+for+a+verification+link.",
        status_code=303
    )

@router.get("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db), user = Depends(get_current_user)):
    """
    1) Fetch the token out of the user's cookie
    2) Decode and extract the JTI
    3) Insert it into the revoked_tokens table
    4) Delete the cookie so the browser no longer sends it
    5) Redirect to /login
    """
    raw_token = request.cookies.get("access_token")
    if raw_token:
        try:
            # We only want to decode the payload to get jti, skip expiration check:
            payload = jwt.decode(raw_token, SECRET_KEY, algorithms=[ALGORITHM], options={"verify_exp": False})
            jti = payload.get("jti")
            if jti:
                # Add a new RevokedToken row if not already present
                existing = db.query(RevokedToken).filter(RevokedToken.jti == jti).first()
                if not existing:
                    db.add(RevokedToken(jti=jti))
                    db.commit()
        except jwt.PyJWTError:
            # If decode fails for some reason, we still proceed to delete the cookie
            pass

    # Now delete the cookie and redirect
    response = RedirectResponse("/login?msg=Logged+out+successfully", status_code=303)
    response.delete_cookie("access_token", path="/")
    return response

@router.post("/delete-account")
def delete_account(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    # 1) If this user is an employer, tear down their job_postings + any applications to those jobs
    if user.role == "employer":
        # collect all their job IDs
        job_ids = [j.id for j in db.query(JobPosting.id)
                               .filter(JobPosting.employer_id == user.id)]
        if job_ids:
            # delete all applications against those jobs
            db.query(Application) \
              .filter(Application.job_id.in_(job_ids)) \
              .delete(synchronize_session=False)
        # delete the job postings themselves
        db.query(JobPosting) \
          .filter(JobPosting.employer_id == user.id) \
          .delete(synchronize_session=False)

    # 2) Delete any applications they themselves submitted (if job_seeker role)
    if user.role == "job_seeker":
        db.query(Application) \
          .filter(Application.user_id == user.id) \
          .delete(synchronize_session=False)
        # optionally: delete their resumes, too
        # db.query(Resume).filter(Resume.user_id == user.id).delete(synchronize_session=False)

    # 3) Finally delete the user record
    db.delete(user)
    db.commit()

    response = RedirectResponse("/register?msg=Account+deleted+successfully", status_code=303)
    response.delete_cookie("access_token")
    return response

@router.get("/forgot-password", response_class=HTMLResponse)
def forgot_password_get(request: Request):
    return templates.TemplateResponse("forgot-password.html", {"request": request})

@router.post("/forgot-password")
def forgot_password_post(
    request: Request,
    email: str = Form(...),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == email).first()
    if not user:
        # Don't reveal that the email doesn't exist
        return RedirectResponse("/login?msg=If+your+email+is+registered,+you+will+receive+a+password+reset+link", status_code=303)

    # Generate reset token
    reset_token = str(uuid.uuid4())
    reset_token_expires = datetime.utcnow() + timedelta(hours=1)  # Token expires in 1 hour

    # Update user with reset token
    user.reset_token = reset_token
    user.reset_token_expires = reset_token_expires
    db.commit()

    # Send reset email
    send_password_reset_email(email, reset_token)

    log_event(db, "Password Reset Request", f"Password reset requested for {email}", email=email)
    return RedirectResponse("/login?msg=If+your+email+is+registered,+you+will+receive+a+password+reset+link", status_code=303)

@router.get("/reset-password", response_class=HTMLResponse)
def reset_password_get(request: Request, token: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(
        User.reset_token == token,
        User.reset_token_expires > datetime.utcnow()
    ).first()

    if not user:
        return RedirectResponse("/login?msg=Invalid+or+expired+reset+link", status_code=303)

    return templates.TemplateResponse("reset-password.html", {
        "request": request,
        "token": token
    })

@router.post("/reset-password")
def reset_password_post(
    request: Request,
    token: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db)
):
    if password != confirm_password:
        return RedirectResponse(f"/reset-password?token={token}&error=Passwords+do+not+match", status_code=303)

    user = db.query(User).filter(
        User.reset_token == token,
        User.reset_token_expires > datetime.utcnow()
    ).first()

    if not user:
        return RedirectResponse("/login?msg=Invalid+or+expired+reset+link", status_code=303)

    # Password validation
    try:
        user.set_password(password)
    except ValueError as e:
        return RedirectResponse(f"/reset-password?token={token}&error={str(e).replace(' ', '+')}", status_code=303)

    # Clear reset token
    user.reset_token = None
    user.reset_token_expires = None
    db.commit()

    log_event(db, "Password Reset", f"Password reset successful for {user.email}", email=user.email)
    return RedirectResponse("/login?msg=Password+reset+successful.+Please+login+with+your+new+password", status_code=303)
