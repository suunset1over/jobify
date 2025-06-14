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