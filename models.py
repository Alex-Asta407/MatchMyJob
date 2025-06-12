from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, JSON, Text, DateTime, UniqueConstraint, Date
from datetime import datetime
from database import Base
from sqlalchemy.orm import relationship

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, index = True)
    name = Column(String)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    verification_token = Column(String, nullable=True)
    is_verified = Column(Boolean, default=False)
    is_admin = Column(Boolean, default=False)
    role = Column(String, default="job_seeker")
    reset_token = Column(String, nullable=True)
    reset_token_expires = Column(DateTime, nullable=True)
    
    # Job seeker specific fields
    current_job_title = Column(String, nullable=True)
    years_experience = Column(String, nullable=True)
    desired_job_title = Column(String, nullable=True)
    key_skills = Column(String, nullable=True)
    preferred_location = Column(String, nullable=True)
    salary_range = Column(String, nullable=True)
    company_description = Column(String, nullable=True)  # New field for company description
    
    resumes      = relationship(
        "Resume",
        back_populates="owner",
        cascade="all, delete-orphan"
    )
    job_postings = relationship(
        "JobPosting",
        back_populates="employer",
        cascade="all, delete-orphan",
        passive_deletes=True
    )
    applications = relationship(
        "Application",
        back_populates="applicant",
        cascade="all, delete-orphan"
    )

    def set_password(self, password):
        from auth.tokenhash import hash_password
        from auth.password_validation import password_validator
        
        # Validate password
        is_valid, errors = password_validator.validate_password(password)
        if not is_valid:
            raise ValueError("\n".join(errors))
            
        self.hashed_password = hash_password(password)

class Resume(Base):
    __tablename__ = 'resumes'

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String)
    skills = Column(JSON, default =[])  # Parsed skill list
    experience = Column(JSON, default =[])  # Changed from Text to JSON
    education = Column(JSON, default =[])  # Parsed education list
    raw_text = Column(Text)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    user_id = Column(Integer, ForeignKey("users.id"))
    owner = relationship("User", back_populates="resumes")
    __table_args__ = (
        UniqueConstraint("user_id", "filename", name="uq_user_filename"),
    )
    applications = relationship("Application", back_populates="resume")
    completeness = Column(Integer, default=0)  # Percentage of completeness (0-100)
    parsed_data = Column(JSON, nullable=True)

    def get_skills(self):
        """Get skills as a list, ensuring it's always a list even if None"""
        if self.skills is None:
            return []
        return self.skills if isinstance(self.skills, list) else []

    def get_experience(self):
        """Get experience as a list, ensuring it's always a list even if None"""
        if self.experience is None:
            return []
        return self.experience if isinstance(self.experience, list) else []

    def get_education(self):
        """Get education as a list, ensuring it's always a list even if None"""
        if self.education is None:
            return []
        return self.education if isinstance(self.education, list) else []

    def set_skills(self, skills_list):
        """Set skills, ensuring it's stored as a JSON-serializable list"""
        self.skills = skills_list if isinstance(skills_list, list) else []

    def set_experience(self, experience_list):
        """Set experience, ensuring it's stored as a JSON-serializable list"""
        self.experience = experience_list if isinstance(experience_list, list) else []

    def set_education(self, education_list):
        """Set education, ensuring it's stored as a JSON-serializable list"""
        self.education = education_list if isinstance(education_list, list) else []

class JobPosting(Base):
    __tablename__ = "job_postings"
    id             = Column(Integer, primary_key=True, index=True)
    title          = Column(String, nullable=False)
    description    = Column(Text, nullable=False)
    skills_required= Column(JSON, nullable=False)

    # ← new fields:
    company        = Column(String, nullable=False)
    location       = Column(String, nullable=True)
    salary_range   = Column(String, nullable=True)
    employment_type= Column(String, nullable=True)   # e.g. "Full-time"
    deadline       = Column(Date, nullable=True, index = True)     # date-only column

    created_at     = Column(DateTime, default=datetime.utcnow)
    employer_id    = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index = True)
    is_active      = Column(Boolean, default=True, nullable=False, index = True)

    employer       = relationship("User", back_populates="job_postings")
    applications   = relationship("Application", back_populates="job", cascade="all, delete-orphan")


class SecurityLog(Base):
    __tablename__ = 'security_logs'
    id = Column(Integer, primary_key=True)
    event_type = Column(String)
    description = Column(Text)
    user_email = Column(String, nullable=True)
    ip_address = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
class Application(Base):
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, index=True)
    resume_id            = Column(Integer, ForeignKey("resumes.id"))
    job_id = Column(Integer,ForeignKey("job_postings.id", ondelete="CASCADE"),nullable=False)
    user_id              = Column(Integer, ForeignKey("users.id"))      # ← add this
    status               = Column(String, default="pending")  # pending, accepted, rejected
    feedback             = Column(Text, nullable=True)
    submission_timestamp = Column(DateTime, default=datetime.utcnow)
    status_updated_at    = Column(DateTime, default=datetime.utcnow)

    job       = relationship("JobPosting", back_populates="applications")
    resume    = relationship("Resume", back_populates="applications")
    applicant = relationship("User", back_populates="applications")

class RevokedToken(Base):
    __tablename__ = "revoked_tokens"
    id = Column(Integer, primary_key=True, index=True)
    jti = Column(String, unique=True, index=True, nullable=False)
    revoked_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<RevokedToken jti={self.jti} revoked_at={self.revoked_at}>"