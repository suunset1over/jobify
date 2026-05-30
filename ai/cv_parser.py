import os
import re
from PyPDF2 import PdfReader

# Extract text from PDF or TXT
def extract_text(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == '.pdf':
        reader = PdfReader(path)
        text = ''
        for page in reader.pages:
            text += page.extract_text() or ''
        return text
    elif ext == '.txt':
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    else:
        raise ValueError(f"Unsupported file extension: {ext}")

# Identify skills from extracted text
def extract_skills_from_cv(path):
    text = extract_text(path).lower()
    skills_list = [
        'python', 'java', 'sql', 'machine learning', 'flask', 'django',
        'react', 'javascript', 'docker', 'linux'
    ]
    extracted = []
    for skill in skills_list:
        if re.search(rf"\b{re.escape(skill)}\b", text):
            extracted.append(skill)
    return extracted


def extract_profile_locally_from_cv_text(text):
    clean = re.sub(r"\r", "\n", text or "")
    lines = [line.strip() for line in clean.splitlines() if line.strip()]
    email_match = re.search(r"[\w.\-+]+@[\w.\-]+\.\w+", clean)
    phone = _guess_phone(clean)
    name = _guess_name(lines, email_match.group(0) if email_match else "")
    skills = _extract_skills_from_text(clean)
    return {
        "name": name,
        "email": email_match.group(0) if email_match else "",
        "phone": phone,
        "summary": _section(clean, ["profile", "summary", "objective", "about me"]),
        "skills": skills,
        "experience": _section(clean, ["experience", "work experience", "employment", "projects"]),
        "education": _section(clean, ["education", "academic background", "studies"]),
    }


def _extract_skills_from_text(text):
    lower = text.lower()
    skills_list = [
        'python', 'java', 'sql', 'machine learning', 'flask', 'django',
        'react', 'javascript', 'docker', 'linux', 'node.js', 'html', 'css',
        'power bi', 'excel', 'tableau', 'git', 'rest apis'
    ]
    return [skill for skill in skills_list if re.search(rf"\b{re.escape(skill)}\b", lower)]


def _guess_name(lines, email):
    for line in lines[:8]:
        if email and email in line:
            continue
        if re.search(r"\d|@|http|www", line, re.I):
            continue
        words = line.split()
        if 2 <= len(words) <= 4 and all(len(word) > 1 for word in words):
            return line
    return ""


def _guess_phone(text):
    for match in re.finditer(r"(?:\+?\d[\d\s().-]{7,}\d)", text):
        value = match.group(0).strip()
        digits = re.sub(r"\D", "", value)
        if len(digits) < 9:
            continue
        if re.fullmatch(r"20\d{2}\s*[-–]\s*20\d{2}", value):
            continue
        if value.startswith("20") and len(digits) <= 10:
            continue
        return value
    return ""


def _section(text, headings):
    heading_pattern = "|".join(re.escape(h) for h in headings)
    next_heading = (
        r"profile|summary|objective|about me|skills|experience|work experience|"
        r"employment|projects|education|academic background|studies|languages|certificates"
    )
    match = re.search(
        rf"(?is)(?:^|\n)\s*(?:{heading_pattern})\s*:?\s*\n?(.*?)(?=\n\s*(?:{next_heading})\s*:?\s*\n|$)",
        text,
    )
    if not match:
        return ""
    value = re.sub(r"\n{2,}", "\n", match.group(1)).strip()
    return value[:1200]
