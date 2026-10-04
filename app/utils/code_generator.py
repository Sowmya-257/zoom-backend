import random
import re


def generate_meeting_code() -> str:
    """Generate a clean 9-digit meeting code formatted as XXX-XXX-XXX."""
    digits = "".join([str(random.randint(0, 9)) for _ in range(9)])
    return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"


def normalize_meeting_code(input_str: str) -> str:
    """
    Extract and normalize meeting code from either:
    - Pure code: '123-456-789' or '123 456 789' or '123456789'
    - URL: 'http://localhost:3000/meeting/123-456-789' or 'https://zoom.us/j/123456789'
    Returns normalized form '123-456-789' or alphanumeric identifier.
    """
    if not input_str:
        return ""
    
    cleaned = input_str.strip()
    
    # Check if URL was passed
    if "/" in cleaned:
        cleaned = cleaned.rstrip("/").split("/")[-1]
        # Handle query params if any
        if "?" in cleaned:
            cleaned = cleaned.split("?")[0]
            
    # Remove whitespace and hyphens to see if it's 9-11 digits
    digits_only = re.sub(r"[^\d]", "", cleaned)
    if len(digits_only) == 9:
        return f"{digits_only[:3]}-{digits_only[3:6]}-{digits_only[6:]}"
    elif len(digits_only) == 10:
        return f"{digits_only[:3]}-{digits_only[3:6]}-{digits_only[6:]}"
    elif len(digits_only) == 11:
        return f"{digits_only[:3]}-{digits_only[3:7]}-{digits_only[7:]}"
    
    # Return cleaned fallback (could be a custom room name or meeting code)
    return cleaned.replace(" ", "-")
