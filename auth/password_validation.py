from typing import List, Tuple
import re

class PasswordValidator:
    def __init__(self):
        self.min_length = 8
        self.max_length = 64
        self.require_uppercase = True
        self.require_lowercase = True
        self.require_digit = True
        self.require_special = True
        self.forbidden_chars = r'[\}\{":~,]'
        self.common_passwords = {
            'password', '123456', '12345678', 'qwerty', 'abc123', 'monkey', 'letmein',
            'dragon', '111111', 'baseball', 'iloveyou', 'trustno1', 'sunshine',
            'master', 'welcome', 'shadow', 'ashley', 'football', 'jesus', 'michael',
            'ninja', 'mustang', 'password1'
        }

    def validate_password(self, password: str) -> Tuple[bool, List[str]]:
        """
        Validates a password against security rules.
        Returns a tuple of (is_valid, list_of_errors)
        """
        errors = []

        # Check length
        if len(password) < self.min_length:
            errors.append(f"Password must be at least {self.min_length} characters long")
        if len(password) > self.max_length:
            errors.append(f"Password must not exceed {self.max_length} characters")

        # Check character types
        if self.require_uppercase and not re.search(r'[A-Z]', password):
            errors.append("Password must contain at least one uppercase letter")
        if self.require_lowercase and not re.search(r'[a-z]', password):
            errors.append("Password must contain at least one lowercase letter")
        if self.require_digit and not re.search(r'\d', password):
            errors.append("Password must contain at least one number")
        if self.require_special and not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("Password must contain at least one special character (!@#$%^&*(),.?\":{}|<>)")

        # Check for forbidden characters
        if re.search(self.forbidden_chars, password):
            errors.append("Password cannot contain any of the following characters: } { \" : ~ ,")

        # Check for common passwords
        if password.lower() in self.common_passwords:
            errors.append("Password is too common and easily guessable")

        # Check for sequential characters
        if re.search(r'(.)\1{2,}', password):
            errors.append("Password cannot contain the same character repeated more than twice")

        # Check for sequential numbers
        if re.search(r'123|234|345|456|567|678|789|890|987|876|765|654|543|432|321|210', password):
            errors.append("Password cannot contain sequential numbers")

        return len(errors) == 0, errors

# Create a singleton instance
password_validator = PasswordValidator() 