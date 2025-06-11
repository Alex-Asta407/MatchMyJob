from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional
from datetime import datetime

# ----- USER -----
class UserBase(BaseModel):
    email: EmailStr
    role: str = "job_seeker"  # Default role

class UserCreate(UserBase):
    password: str

class User(UserBase):
    id: int
    is_active: bool = True
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserOut(BaseModel):
    id: int
    name: str
    email: EmailStr
    is_verified: bool

    class Config:
        from_attributes = True

# ----- TOKEN -----
class Token(BaseModel):
    access_token: str
    token_type: str

# ----- RESUME -----
class ResumeBase(BaseModel):
    filename: str
    skills: List[str] = []
    experience: Optional[str] = None
    education: List[str] = []  # Added education field
    raw_text: Optional[str] = None
    parsed_at: Optional[datetime] = None

class ResumeCreate(ResumeBase):
    pass

class Resume(ResumeBase):
    id: int
    user_id: int
    uploaded_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class ResumeOut(BaseModel):
    id: int
    filename: str
    skills: List[str]
    experience: str
    uploaded_at: datetime

    class Config:
        from_attributes = True

# ----- JOB POSTING -----
class JobPostingBase(BaseModel):
    title: str
    company: str
    location: str
    description: str
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    employment_type: str
    skills_required: List[str] = []
    application_deadline: Optional[datetime] = None

class JobPostingCreate(JobPostingBase):
    pass

class JobPosting(JobPostingBase):
    id: int
    employer_id: int
    created_at: datetime
    updated_at: datetime
    is_active: bool = True

    class Config:
        from_attributes = True

class JobOut(BaseModel):
    """
    You already have something like this, but just to be sure:
      id, title, description, skills_required, created_at, employer_id
    """
    id: int
    title: str
    description: Optional[str]
    skills_required: List[str]
    created_at: datetime
    employer_id: int

    class Config:
        orm_mode = True

# ───────────────────────────────────────────────────────────────────
# 1.2. Application‐related schemas
# ───────────────────────────────────────────────────────────────────

class ApplicationBase(BaseModel):
    job_posting_id: int
    resume_id: int
    cover_letter: Optional[str] = None
    status: str = "pending"

class ApplicationCreate(ApplicationBase):
    pass

class Application(ApplicationBase):
    id: int
    user_id: int
    submission_timestamp: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class ApplicationOut(BaseModel):
    """
    Whenever you return an application (e.g. via JSON),
    you can show all these fields. Setting orm_mode allows
    FastAPI to read from a SQLAlchemy model directly.
    """
    id: int
    job_id: int
    resume_id: int
    user_id: int
    status: str
    feedback: Optional[str] = None
    submission_timestamp: datetime

    class Config:
        orm_mode = True

class JobSeekerBase(BaseModel):
    first_name: str
    last_name: str
    phone: Optional[str] = None
    location: Optional[str] = None
    bio: Optional[str] = None
    skills: List[str] = []
    experience: Optional[str] = None
    education: List[str] = []  # Added education field

class JobSeekerCreate(JobSeekerBase):
    pass

class JobSeeker(JobSeekerBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class EmployerBase(BaseModel):
    company_name: str
    industry: Optional[str] = None
    company_size: Optional[str] = None
    company_description: Optional[str] = None
    website: Optional[str] = None
    location: Optional[str] = None

class EmployerCreate(EmployerBase):
    pass

class Employer(EmployerBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
