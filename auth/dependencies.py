from fastapi import Request, HTTPException, status, Depends
from jose import JWTError, jwt, ExpiredSignatureError
from auth.tokenhash import SECRET_KEY, ALGORITHM
from jwt import ExpiredSignatureError, PyJWTError
from database import get_db
from sqlalchemy.orm import Session
from models import User, SecurityLog, RevokedToken

def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    try:
        # Normal decode: this checks signature _and_ expiration.
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        jti: str = payload.get("jti")
        if email is None or jti is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed token")
    except ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired, please log in again")
    except PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    # Check revocation:
    revoked = db.query(RevokedToken).filter(RevokedToken.jti == jti).first()
    if revoked:
        # If you find this JTI in the revoked list, treat as unauthorized
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token was revoked. Please log in again")

    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return user

def get_current_user_optional(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if email is None:
            return None
    except JWTError:
        return None

    return db.query(User).filter(User.email == email).first()

def get_current_admin(request:Request,db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access only")
    return user
def log_event(db: Session, event_type: str, description: str, email: str = None, ip: str = None):
    log = SecurityLog(
        event_type=event_type,
        description=description,
        user_email=email,
        ip_address=ip
    )
    db.add(log)
    db.commit()
    
def get_current_employer(user: User = Depends(get_current_user)):
    if user.role != "employer":
        raise HTTPException(status_code=403, detail="Employer access only")
    return user

def get_current_job_seeker(user: User = Depends(get_current_user)):
    if user.role != "job_seeker":
        raise HTTPException(status_code=403, detail="Job Seeker access only")
    return user
