import yagmail
import os
from dotenv import load_dotenv,find_dotenv
load_dotenv(find_dotenv())
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
APP_PASSWORD = os.getenv("APP_PASSWORD")
yag = yagmail.SMTP(user=SENDER_EMAIL, password=APP_PASSWORD)

def send_verification_email(to_email: str, token: str):
    link = f"http://localhost:8000/verify?token={token}"
    subject = "Verify your MatchMyJob account"
    content = f"Click the link to verify your account:\n\n{link}"
    yag.send(to=to_email, subject=subject, contents=content)

def send_password_reset_email(to_email: str, token: str):
    link = f"http://localhost:8000/reset-password?token={token}"
    subject = "Reset your MatchMyJob password"
    content = f"""Hello,

You have requested to reset your password for your MatchMyJob account.

Click the link below to reset your password:
{link}

This link will expire in 1 hour.

If you did not request this password reset, please ignore this email.

Best regards,
MatchMyJob Team"""
    yag.send(to=to_email, subject=subject, contents=content)

def send_feedback_email(to_email: str, job_title: str, feedback: str):
    subject = f"Feedback for your application to {job_title}"
    content = f"""Hello,

You have received feedback for your application to {job_title}:

{feedback}

Best regards,
MatchMyJob Team"""
    yag.send(to=to_email, subject=subject, contents=content)