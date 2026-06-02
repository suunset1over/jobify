import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter


DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
LAST_ERROR = ""


def gemini_available():
    return bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))


def basic_match_score(profile, job):
    seeker_skills = _split_items(getattr(profile, "skills", ""))
    required_skills = _split_items(getattr(job, "required_skills", ""))
    skill_score = len(seeker_skills & required_skills) / (len(required_skills) or 1)

    experience_text = (getattr(profile, "experience", "") or "").lower()
    min_experience = getattr(job, "min_experience", 0) or 0
    experience_score = 1.0 if min_experience == 0 else min(1.0, _guess_years(experience_text) / min_experience)

    education_required = (getattr(job, "education_required", "") or "").lower()
    education_text = (getattr(profile, "education", "") or "").lower()
    education_score = 1.0 if not education_required else (1.0 if education_required in education_text else 0.5)

    score = (skill_score * 0.65) + (experience_score * 0.2) + (education_score * 0.15)
    return round(score * 100)


def skill_gap_analysis(profile, job):
    seeker_skills = _split_items(getattr(profile, "skills", ""))
    required_skills = _split_items(getattr(job, "required_skills", ""))
    matched = sorted(seeker_skills & required_skills)
    missing = sorted(required_skills - seeker_skills)
    optional = _related_skills(required_skills, seeker_skills)
    score = basic_match_score(profile, job)
    coverage = round((len(matched) / (len(required_skills) or 1)) * 100)
    if not missing:
        priority = "low"
        label = "Low gap"
    elif coverage >= 60:
        priority = "medium"
        label = "Medium gap"
    else:
        priority = "high"
        label = "High gap"
    return {
        "score": score,
        "coverage": coverage,
        "matched": matched,
        "missing": missing,
        "optional": optional,
        "priority": priority,
        "priority_label": label,
        "required_count": len(required_skills),
        "matched_count": len(matched),
    }


def analyze_candidate_fit(profile, job):
    fallback_score = basic_match_score(profile, job)
    has_key = gemini_available()
    fallback = {
        "score": fallback_score,
        "recommendation": _recommendation(fallback_score),
        "summary": (
            "Live Gemini analysis is unavailable right now, so Jobify is showing a local fit analysis based on skills, experience, and education."
            if has_key else
            "AI is not configured, so this report uses local skill, experience, and education matching."
        ),
        "strengths": sorted(_split_items(getattr(profile, "skills", "")) & _split_items(getattr(job, "required_skills", ""))),
        "gaps": sorted(_split_items(getattr(job, "required_skills", "")) - _split_items(getattr(profile, "skills", ""))),
        "interview_questions": [
            "Can you describe a recent project related to this role?",
            "Which required skill do you feel strongest in, and why?",
            "What would you learn first if selected for this position?"
        ],
        "next_steps": _local_next_steps(profile, job),
        "error": LAST_ERROR,
        "ai_used": False,
    }
    if not has_key:
        return fallback

    schema = {
        "score": "integer from 0 to 100",
        "recommendation": "Strong match, Potential match, or Weak match",
        "summary": "short recruiter-facing explanation",
        "strengths": ["candidate strengths relevant to job"],
        "gaps": ["missing or weak areas"],
        "interview_questions": ["specific interview questions"]
    }
    prompt = {
        "task": "Evaluate how well a candidate fits a job opening. Be fair, practical, and explainable.",
        "candidate": _profile_payload(profile),
        "job": _job_payload(job),
        "required_json_schema": schema,
    }
    data = _generate_json(prompt)
    if not data:
        fallback["error"] = _friendly_error(LAST_ERROR)
        return fallback

    data["score"] = _clamp_int(data.get("score"), fallback_score)
    data["recommendation"] = data.get("recommendation") or _recommendation(data["score"])
    data["summary"] = data.get("summary") or fallback["summary"]
    data["strengths"] = _clean_list(data.get("strengths")) or fallback["strengths"]
    data["gaps"] = _clean_list(data.get("gaps")) or fallback["gaps"]
    data["interview_questions"] = _clean_list(data.get("interview_questions")) or fallback["interview_questions"]
    data["next_steps"] = _clean_list(data.get("next_steps")) or fallback["next_steps"]
    data["ai_used"] = True
    return data


def extract_profile_from_cv_text(cv_text):
    if not gemini_available() or not cv_text:
        return None

    prompt = {
        "task": "Extract a structured candidate profile from this CV text.",
        "cv_text": cv_text[:12000],
        "required_json_schema": {
            "summary": "2-3 sentence professional profile",
            "skills": ["normalized technical and soft skills"],
            "experience": "concise work experience summary",
            "education": "concise education summary",
            "languages": ["languages if present"],
            "certificates": ["certificates if present"]
        },
    }
    data = _generate_json(prompt)
    if not data:
        return None
    return {
        "summary": (data.get("summary") or "").strip(),
        "skills": _clean_list(data.get("skills")),
        "experience": (data.get("experience") or "").strip(),
        "education": (data.get("education") or "").strip(),
        "languages": _clean_list(data.get("languages")),
        "certificates": _clean_list(data.get("certificates")),
    }


def improve_cv_content(cv_data):
    has_key = gemini_available()
    local_suggestions = _local_cv_suggestions(cv_data)
    fallback = {
        "summary": cv_data.get("summary", ""),
        "skills": cv_data.get("skills", ""),
        "experience": cv_data.get("experience", ""),
        "education": cv_data.get("education", ""),
        "suggestions": local_suggestions,
        "error": "",
        "ai_used": False,
    }
    if not has_key:
        return fallback

    prompt = {
        "task": "Improve this CV content for clarity, professionalism, and ATS compatibility. Keep it truthful and do not invent employers, degrees, or achievements.",
        "cv": cv_data,
        "required_json_schema": {
            "summary": "rewritten professional summary",
            "skills": "comma-separated optimized skills",
            "experience": "rewritten experience section",
            "education": "rewritten education section",
            "suggestions": ["specific improvement suggestions"]
        },
    }
    data = _generate_json(prompt)
    if not data:
        fallback["error"] = _friendly_error(LAST_ERROR)
        fallback["suggestions"] = [
            f"Live Gemini suggestions are unavailable. {_friendly_error(LAST_ERROR)}"
        ] + local_suggestions
        return fallback

    return {
        "summary": data.get("summary") or fallback["summary"],
        "skills": data.get("skills") or fallback["skills"],
        "experience": data.get("experience") or fallback["experience"],
        "education": data.get("education") or fallback["education"],
        "suggestions": _clean_list(data.get("suggestions")),
        "ai_used": True,
    }


def generate_cover_letter(profile, job):
    fallback = _local_cover_letter(profile, job)
    result = {
        "cover_letter": fallback,
        "tips": _cover_letter_tips(profile, job),
        "error": "",
        "ai_used": False,
    }
    if not gemini_available():
        result["error"] = "Gemini API key is missing. Local cover letter generated."
        return result

    prompt = {
        "task": (
            "Write a concise, professional cover letter for a job application. "
            "Use only the provided candidate facts. Do not invent employers, degrees, certifications, or achievements."
        ),
        "candidate": _profile_payload(profile),
        "job": _job_payload(job),
        "required_json_schema": {
            "cover_letter": "180-230 word cover letter with greeting, fit paragraph, motivation paragraph, and closing",
            "tips": ["short tips to personalize before sending"]
        },
    }
    data = _generate_json(prompt)
    if not data:
        result["error"] = _friendly_error(LAST_ERROR)
        return result

    result["cover_letter"] = (data.get("cover_letter") or fallback).strip()
    result["tips"] = _clean_list(data.get("tips")) or result["tips"]
    result["ai_used"] = True
    return result


def generate_interview_questions(profile, job):
    local_questions = _local_simulator_questions(profile, job)
    result = {"questions": local_questions, "error": "", "ai_used": False}
    if not gemini_available():
        result["error"] = "Gemini API key is missing. Local interview questions generated."
        return result

    prompt = {
        "task": (
            "Create a realistic interview simulation for a candidate applying to a job. "
            "Ask exactly 5 questions: motivation, technical or role knowledge, practical scenario, skill gap, and behavioral."
        ),
        "candidate": _profile_payload(profile),
        "job": _job_payload(job),
        "required_json_schema": {
            "questions": [
                {
                    "category": "Motivation, Technical, Scenario, Skill Gap, or Behavioral",
                    "question": "clear interview question",
                    "focus": "what the interviewer is checking"
                }
            ]
        },
    }
    data = _generate_json(prompt)
    if not data:
        result["error"] = _friendly_error(LAST_ERROR)
        return result

    result["questions"] = _normalize_interview_questions(data.get("questions"), local_questions)
    result["ai_used"] = True
    return result


def evaluate_interview_answers(profile, job, questions, answers):
    local_feedback = _local_interview_feedback(profile, job, questions, answers)
    result = {**local_feedback, "error": "", "ai_used": False}
    if not gemini_available():
        result["error"] = "Gemini API key is missing. Local interview feedback generated."
        return result

    prompt = {
        "task": (
            "Evaluate a candidate's mock interview answers. Be constructive, specific, and fair. "
            "Do not invent facts beyond the answers and candidate profile."
        ),
        "candidate": _profile_payload(profile),
        "job": _job_payload(job),
        "interview": [
            {
                "question": (questions[idx] or {}).get("question", ""),
                "category": (questions[idx] or {}).get("category", ""),
                "answer": answers[idx] if idx < len(answers) else "",
            }
            for idx in range(len(questions))
        ],
        "required_json_schema": {
            "score": "integer from 0 to 100",
            "summary": "2-3 sentence feedback summary",
            "strengths": ["what the candidate did well"],
            "improvements": ["specific improvements for weak answers"],
            "answer_feedback": [
                {
                    "question_index": "1-based number",
                    "score": "integer from 0 to 100",
                    "feedback": "short feedback for this answer"
                }
            ],
            "next_steps": ["practice actions before the real interview"]
        },
    }
    data = _generate_json(prompt)
    if not data:
        result["error"] = _friendly_error(LAST_ERROR)
        return result

    result["score"] = _clamp_int(data.get("score"), local_feedback["score"])
    result["summary"] = data.get("summary") or local_feedback["summary"]
    result["strengths"] = _clean_list(data.get("strengths")) or local_feedback["strengths"]
    result["improvements"] = _clean_list(data.get("improvements")) or local_feedback["improvements"]
    result["answer_feedback"] = _normalize_answer_feedback(data.get("answer_feedback"), questions, answers)
    result["next_steps"] = _clean_list(data.get("next_steps")) or local_feedback["next_steps"]
    result["ai_used"] = True
    return result


def recruiter_shortlist_report(profile, job, cover_letter=""):
    gap = skill_gap_analysis(profile, job)
    strengths = gap["matched"][:5]
    gaps = gap["missing"][:5]
    summary = _local_recruiter_summary(profile, job, gap)
    why = _local_why_candidate(profile, job, gap, cover_letter)
    questions = _local_interview_questions(job, gap)
    return {
        "score": gap["score"],
        "priority": gap["priority"],
        "priority_label": gap["priority_label"],
        "summary": summary,
        "why": why,
        "strengths": strengths,
        "gaps": gaps,
        "questions": questions,
        "ai_used": False,
    }


def candidate_profile_dashboard(profile, jobs=None, applications=None, user=None):
    jobs = jobs or []
    applications = applications or []
    skills = _clean_list(getattr(profile, "skills", "")) if profile else []
    completeness_items = {
        "Name": bool(getattr(profile, "name", None) or getattr(user, "name", None) or getattr(user, "username", None)),
        "Email": bool(getattr(profile, "email", None) or getattr(user, "email", None)),
        "Phone": bool(getattr(profile, "phone", None) or getattr(user, "phone", None)),
        "Summary": bool(getattr(profile, "summary", None)),
        "Skills": len(skills) >= 1,
        "Experience": bool(getattr(profile, "experience", None)),
        "Education": bool(getattr(profile, "education", None)),
        "CV file": bool(getattr(profile, "cv_path", None)),
    }
    completeness = round(sum(completeness_items.values()) / len(completeness_items) * 100)
    cv_quality = _cv_quality_score(profile, skills)
    best_fit = max([basic_match_score(profile, job) for job in jobs], default=0) if profile else 0
    readiness = round((completeness * 0.35) + (cv_quality * 0.35) + (best_fit * 0.3))
    timeline = _profile_timeline(profile)
    recommendations = _profile_recommendations(profile, completeness_items, skills, best_fit)
    submitted = len(applications)
    accepted = len([app for app in applications if getattr(app, "status", "") == "Accepted"])
    pending = len([app for app in applications if getattr(app, "status", "") == "Pending"])
    return {
        "skills": skills,
        "completeness_items": completeness_items,
        "completeness": completeness,
        "cv_quality": cv_quality,
        "readiness": readiness,
        "best_fit": best_fit,
        "timeline": timeline,
        "recommendations": recommendations,
        "submitted": submitted,
        "accepted": accepted,
        "pending": pending,
    }


def job_market_insights(profile, jobs=None):
    jobs = jobs or []
    skill_counter = Counter()
    city_counter = Counter()
    category_scores = {}
    category_counts = Counter()
    above_60 = 0
    for job in jobs:
        for skill in _split_items(getattr(job, "required_skills", "")):
            skill_counter[skill] += 1
        city = getattr(job, "city", None)
        if city:
            city_counter[city] += 1
        category = getattr(job, "category", None) or "Other"
        category_counts[category] += 1
        if profile:
            score = basic_match_score(profile, job)
            category_scores.setdefault(category, []).append(score)
            if score >= 60:
                above_60 += 1
    best_categories = []
    for category, scores in category_scores.items():
        best_categories.append({
            "name": category,
            "avg_score": round(sum(scores) / len(scores)),
            "jobs": category_counts[category],
        })
    best_categories.sort(key=lambda item: (item["avg_score"], item["jobs"]), reverse=True)
    return {
        "top_skills": skill_counter.most_common(8),
        "top_cities": city_counter.most_common(6),
        "best_categories": best_categories[:5],
        "jobs_above_60": above_60,
        "total_jobs": len(jobs),
    }


def check_gemini_connection():
    if not gemini_available():
        return {
            "configured": False,
            "ok": False,
            "model": os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL),
            "message": "GEMINI_API_KEY is missing.",
        }
    data = _generate_json({
        "task": "Connectivity check. Return {'ok': true, 'message': 'Gemini is connected'}.",
        "required_json_schema": {"ok": "boolean", "message": "short string"}
    })
    return {
        "configured": True,
        "ok": bool(data and data.get("ok")),
        "model": os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL),
        "message": (data or {}).get("message") or _friendly_error(LAST_ERROR) or "Gemini did not return a valid status response.",
    }


def _generate_json(prompt_payload):
    global LAST_ERROR
    LAST_ERROR = ""
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        LAST_ERROR = "GEMINI_API_KEY is missing."
        return None

    body = {
        "contents": [{
            "parts": [{
                "text": (
                    "Return only valid JSON. Do not use markdown fences.\n\n"
                    + json.dumps(prompt_payload, ensure_ascii=False)
                )
            }]
        }],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
        },
    }
    models = [os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)]
    models.extend([
        model.strip()
        for model in os.environ.get("GEMINI_FALLBACK_MODELS", "gemini-2.0-flash").split(",")
        if model.strip()
    ])
    models = list(dict.fromkeys(models))

    raw = None
    for model in models:
        request = urllib.request.Request(
            GEMINI_API_URL.format(model=model),
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                raw = json.loads(response.read().decode("utf-8"))
                LAST_ERROR = ""
                break
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")[:350]
            LAST_ERROR = f"Gemini model {model} HTTP {exc.code}: {detail}"
            if exc.code in (429, 503) and model != models[-1]:
                continue
            return None
        except urllib.error.URLError as exc:
            LAST_ERROR = f"Gemini connection error: {exc.reason}"
            return None
        except TimeoutError:
            LAST_ERROR = "Gemini request timed out."
            return None
        except json.JSONDecodeError:
            LAST_ERROR = "Gemini returned a response that could not be parsed as JSON."
            return None

    if raw is None:
        LAST_ERROR = LAST_ERROR or "Gemini returned no response."
        return None

    text = _candidate_text(raw)
    if not text:
        LAST_ERROR = "Gemini returned no candidate text."
        return None
    parsed = _parse_json_text(text)
    if parsed is None:
        LAST_ERROR = "Gemini returned text, but it was not valid JSON."
    return parsed


def _candidate_text(raw):
    try:
        parts = raw["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError):
        return ""
    return "\n".join(part.get("text", "") for part in parts if isinstance(part, dict))


def _parse_json_text(text):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None


def _profile_payload(profile):
    return {
        "name": getattr(profile, "name", None),
        "summary": getattr(profile, "summary", None),
        "skills": getattr(profile, "skills", None),
        "experience": getattr(profile, "experience", None),
        "education": getattr(profile, "education", None),
        "languages": getattr(profile, "languages", None),
        "certificates": getattr(profile, "certificates", None),
    }


def _job_payload(job):
    return {
        "title": getattr(job, "title", None),
        "description": getattr(job, "description", None),
        "required_skills": getattr(job, "required_skills", None),
        "min_experience": getattr(job, "min_experience", None),
        "education_required": getattr(job, "education_required", None),
        "category": getattr(job, "category", None),
        "city": getattr(job, "city", None),
        "country": getattr(job, "country", None),
    }


def _split_items(value):
    return {
        item.strip().lower()
        for item in re.split(r"[,;\n]", value or "")
        if item.strip()
    }


def _clean_list(value):
    if isinstance(value, str):
        value = re.split(r"[,;\n]", value)
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _guess_years(text):
    years = [int(match) for match in re.findall(r"(\d+)\+?\s*(?:years|yrs|ani|an)", text)]
    return max(years) if years else 0


def _clamp_int(value, default):
    try:
        return max(0, min(100, int(round(float(value)))))
    except (TypeError, ValueError):
        return default


def _recommendation(score):
    if score >= 75:
        return "Strong match"
    if score >= 45:
        return "Potential match"
    return "Weak match"


def _friendly_error(error):
    if not error:
        return ""
    lower = error.lower()
    if "http 429" in lower or "quota" in lower:
        return "Gemini quota is currently exhausted for this API key. Local recommendations are shown until the quota resets or a new key is used."
    if "api_key" in lower or "missing" in lower:
        return "Gemini API key is missing."
    if "timed out" in lower:
        return "Gemini request timed out. Try again later."
    if "connection" in lower:
        return "Gemini connection failed. Check internet access."
    return "Gemini did not return a valid response. Local recommendations are shown."


def _local_next_steps(profile, job):
    gaps = sorted(_split_items(getattr(job, "required_skills", "")) - _split_items(getattr(profile, "skills", "")))
    if not gaps:
        return [
            "Prepare a short project story that proves the strongest matching skills.",
            "Tailor the CV summary to mirror this job title and company context.",
            "Add quantified achievements before applying."
        ]
    focus = ", ".join(gaps[:3])
    return [
        f"Prioritize learning or demonstrating: {focus}.",
        "Add one portfolio project or CV bullet that connects current experience to the role.",
        "Prepare interview examples for the missing requirements before contacting the recruiter."
    ]


def _related_skills(required_skills, seeker_skills):
    groups = [
        {"python", "flask", "django", "fastapi", "sql", "postgresql", "mysql"},
        {"javascript", "typescript", "react", "node.js", "node", "rest apis", "html", "css"},
        {"docker", "linux", "kubernetes", "ci/cd", "aws", "azure", "devops"},
        {"machine learning", "data analysis", "pandas", "numpy", "power bi", "tableau"},
        {"cybersecurity", "siem", "network security", "penetration testing", "ids", "ips"},
        {"communication", "teamwork", "leadership", "project management", "agile", "scrum"},
    ]
    related = set()
    combined = required_skills | seeker_skills
    for group in groups:
        if group & combined:
            related.update(group - required_skills - seeker_skills)
    return sorted(related)[:6]


def _local_cv_suggestions(cv_data):
    suggestions = []
    summary = cv_data.get("summary", "")
    experience = cv_data.get("experience", "")
    education = cv_data.get("education", "")
    skills = _clean_list(cv_data.get("skills", ""))
    if len(summary.split()) < 18:
        suggestions.append("Expand the professional summary to 2-3 sentences with role, strongest skills, and target position.")
    if not re.search(r"\d|%|increased|reduced|built|created|managed|analyzed", experience, re.I):
        suggestions.append("Add measurable achievements or action verbs to the experience section.")
    if len(skills) < 6:
        suggestions.append("Add more relevant skills, including tools, frameworks, languages, and soft skills.")
    if len(education.split()) < 4:
        suggestions.append("Include institution, degree, specialization, and graduation year in education.")
    return suggestions or ["CV structure looks solid. Add quantified achievements to make it stronger."]


def _local_cover_letter(profile, job):
    name = getattr(profile, "name", None) or "Candidate"
    skills = _clean_list(getattr(profile, "skills", ""))[:6]
    skill_text = ", ".join(skills) if skills else "the skills required for this role"
    experience = (getattr(profile, "experience", "") or "my practical experience").strip()
    education = (getattr(profile, "education", "") or "my educational background").strip()
    title = getattr(job, "title", "this position")
    company_context = f"{getattr(job, 'city', '')}, {getattr(job, 'country', '')}".strip(", ")
    location_sentence = f" in {company_context}" if company_context else ""
    return (
        "Dear Hiring Team,\n\n"
        f"I am writing to apply for the {title} role{location_sentence}. "
        f"My background combines {education} with hands-on experience such as {experience}. "
        f"I am especially interested in this opportunity because it matches my strengths in {skill_text}.\n\n"
        f"After reviewing the role requirements, I believe I can contribute through a motivated learning mindset, "
        f"structured problem solving, and the ability to connect technical knowledge with practical results. "
        f"I would welcome the opportunity to discuss how my profile fits your team and how I can grow within this position.\n\n"
        "Thank you for your time and consideration.\n\n"
        f"Sincerely,\n{name}"
    )


def _cover_letter_tips(profile, job):
    gaps = sorted(_split_items(getattr(job, "required_skills", "")) - _split_items(getattr(profile, "skills", "")))
    tips = [
        "Replace 'Hiring Team' with the recruiter or company name if you know it.",
        "Add one measurable achievement before sending.",
    ]
    if gaps:
        tips.append(f"Briefly mention how you are improving the main gap: {gaps[0]}.")
    return tips


def _local_recruiter_summary(profile, job, gap):
    candidate_name = getattr(profile, "name", None) or f"Candidate #{getattr(profile, 'user_id', '')}"
    title = getattr(job, "title", "this role")
    if gap["score"] >= 75:
        fit = "a strong shortlist candidate"
    elif gap["score"] >= 45:
        fit = "a potential candidate worth screening"
    else:
        fit = "a weaker match who may need additional training"
    return (
        f"{candidate_name} is {fit} for {title}. "
        f"The profile matches {gap['matched_count']} of {gap['required_count']} required skills "
        f"with an overall fit score of {gap['score']}%."
    )


def _local_why_candidate(profile, job, gap, cover_letter):
    reasons = []
    if gap["matched"]:
        reasons.append(f"Direct skill overlap: {', '.join(gap['matched'][:4])}.")
    if getattr(profile, "experience", None):
        reasons.append("Experience section is available for recruiter review.")
    if cover_letter and len(cover_letter.split()) > 35:
        reasons.append("Candidate submitted a detailed cover letter.")
    if gap["missing"]:
        reasons.append(f"Main validation area: {', '.join(gap['missing'][:3])}.")
    return reasons or ["Review CV manually; the profile has limited structured data."]


def _local_interview_questions(job, gap):
    title = getattr(job, "title", "this role")
    questions = [
        f"Which project best proves your readiness for the {title} role?",
    ]
    for skill in gap["matched"][:2]:
        questions.append(f"Can you describe a practical example where you used {skill}?")
    for skill in gap["missing"][:2]:
        questions.append(f"How would you approach learning or applying {skill} in the first month?")
    while len(questions) < 4:
        questions.append("What would you need from the team to become productive quickly?")
    return questions[:5]


def _local_simulator_questions(profile, job):
    gap = skill_gap_analysis(profile, job)
    title = getattr(job, "title", "this role")
    matched = gap["matched"][:2]
    missing = gap["missing"][:2]
    strongest_skill = matched[0] if matched else "your strongest relevant skill"
    main_gap = missing[0] if missing else "a new tool or requirement"
    return [
        {
            "category": "Motivation",
            "question": f"Why are you interested in the {title} position, and how does it connect to your career goals?",
            "focus": "Motivation, role understanding, and fit.",
        },
        {
            "category": "Technical",
            "question": f"Describe a project or task where you used {strongest_skill}. What problem did you solve?",
            "focus": "Practical proof of relevant skill.",
        },
        {
            "category": "Scenario",
            "question": f"Imagine you join this team and receive an unclear task related to {title}. How would you clarify requirements and deliver it?",
            "focus": "Problem solving and communication.",
        },
        {
            "category": "Skill Gap",
            "question": f"This role may require {main_gap}. How would you become productive with it in the first month?",
            "focus": "Learning plan and self-awareness.",
        },
        {
            "category": "Behavioral",
            "question": "Tell me about a time you received feedback or had to improve your work. What changed afterward?",
            "focus": "Growth mindset and collaboration.",
        },
    ]


def _normalize_interview_questions(value, fallback):
    if not isinstance(value, list):
        return fallback
    questions = []
    for idx, item in enumerate(value[:5]):
        if isinstance(item, dict):
            question = str(item.get("question", "")).strip()
            category = str(item.get("category", "")).strip() or f"Question {idx + 1}"
            focus = str(item.get("focus", "")).strip() or "Interview readiness."
        else:
            question = str(item).strip()
            category = f"Question {idx + 1}"
            focus = "Interview readiness."
        if question:
            questions.append({"category": category, "question": question, "focus": focus})
    while len(questions) < 5:
        questions.append(fallback[len(questions)])
    return questions[:5]


def _local_interview_feedback(profile, job, questions, answers):
    strengths = []
    improvements = []
    answer_feedback = []
    total = 0
    required_skills = _split_items(getattr(job, "required_skills", ""))
    profile_skills = _split_items(getattr(profile, "skills", ""))
    relevant_terms = required_skills | profile_skills

    for idx, _question in enumerate(questions):
        answer = answers[idx].strip() if idx < len(answers) else ""
        word_count = len(answer.split())
        has_example = bool(re.search(r"\b(project|task|team|built|created|implemented|used|worked|managed|improved|solved)\b", answer, re.I))
        has_metric = bool(re.search(r"\d|%|users?|clients?|months?|years?|team|grade|score", answer, re.I))
        skill_hits = sum(1 for term in relevant_terms if term and term in answer.lower())
        score = 25
        if word_count >= 35:
            score += 30
        elif word_count >= 18:
            score += 20
        elif word_count >= 8:
            score += 10
        if has_example:
            score += 20
        if has_metric:
            score += 10
        if skill_hits:
            score += min(15, skill_hits * 5)
        score = min(100, score)
        total += score

        if score >= 75:
            feedback = "Strong answer: it is specific, relevant, and gives the interviewer evidence."
        elif score >= 50:
            feedback = "Good start: add a concrete example, tools used, or measurable result."
        else:
            feedback = "Needs more detail: answer with situation, action, result, and connection to the role."
        answer_feedback.append({
            "question_index": idx + 1,
            "score": score,
            "feedback": feedback,
        })

    overall = round(total / (len(questions) or 1))
    if any(item["score"] >= 75 for item in answer_feedback):
        strengths.append("Some answers give clear evidence instead of only general statements.")
    if any(re.search(r"\d|%|users?|clients?|team", answer, re.I) for answer in answers):
        strengths.append("You included measurable details, which makes answers more credible.")
    if not strengths:
        strengths.append("You completed the interview practice and have a clear baseline to improve.")

    if any(len(answer.split()) < 18 for answer in answers):
        improvements.append("Expand short answers using the STAR structure: situation, task, action, result.")
    if not any(re.search(r"\d|%|users?|clients?|team", answer, re.I) for answer in answers):
        improvements.append("Add numbers, scope, or results where possible.")
    missing_terms = sorted(required_skills - profile_skills)
    if missing_terms:
        improvements.append(f"Prepare one learning story for this gap: {missing_terms[0]}.")
    if not improvements:
        improvements.append("Practice speaking answers aloud and keep them concise for a real interview.")

    title = getattr(job, "title", "this role")
    return {
        "score": overall,
        "summary": f"Your mock interview readiness for {title} is {overall}%. Focus on sharper examples, measurable outcomes, and role-specific wording.",
        "strengths": strengths[:4],
        "improvements": improvements[:4],
        "answer_feedback": answer_feedback,
        "next_steps": [
            "Rewrite the weakest answer with one concrete project example.",
            "Prepare a 60-second introduction tailored to this job.",
            "Practice one answer about a missing skill and your learning plan.",
        ],
    }


def _normalize_answer_feedback(value, questions, answers):
    fallback = _local_interview_feedback(None, type("Job", (), {})(), questions, answers)["answer_feedback"]
    if not isinstance(value, list):
        return fallback
    normalized = []
    for idx, item in enumerate(value[:len(questions)]):
        if not isinstance(item, dict):
            continue
        fallback_item = fallback[min(idx, len(fallback) - 1)]
        normalized.append({
            "question_index": _clamp_int(item.get("question_index"), idx + 1),
            "score": _clamp_int(item.get("score"), fallback_item["score"]),
            "feedback": str(item.get("feedback") or fallback_item["feedback"]).strip(),
        })
    while len(normalized) < len(questions):
        normalized.append(fallback[len(normalized)])
    return normalized[:len(questions)]


def _cv_quality_score(profile, skills):
    if not profile:
        return 0
    score = 0
    summary = getattr(profile, "summary", "") or ""
    experience = getattr(profile, "experience", "") or ""
    education = getattr(profile, "education", "") or ""
    if len(summary.split()) >= 18:
        score += 25
    elif summary:
        score += 12
    if len(skills) >= 8:
        score += 25
    elif len(skills) >= 4:
        score += 16
    elif skills:
        score += 8
    if len(experience.split()) >= 18:
        score += 25
    elif experience:
        score += 12
    if len(education.split()) >= 5:
        score += 15
    elif education:
        score += 8
    if getattr(profile, "cv_path", None):
        score += 10
    return min(100, score)


def _profile_timeline(profile):
    if not profile:
        return []
    items = []
    summary = getattr(profile, "summary", None)
    education = getattr(profile, "education", None)
    experience = getattr(profile, "experience", None)
    certificates = getattr(profile, "certificates", None)
    if summary:
        items.append({"label": "Profile summary", "detail": summary})
    if education:
        items.append({"label": "Education", "detail": education})
    if experience:
        for idx, chunk in enumerate(re.split(r"\n+|;", experience)):
            chunk = chunk.strip()
            if chunk:
                items.append({"label": "Experience" if idx == 0 else "Experience detail", "detail": chunk})
    if certificates:
        items.append({"label": "Certificates", "detail": certificates})
    return items[:6]


def _profile_recommendations(profile, completeness_items, skills, best_fit):
    recommendations = []
    missing_fields = [name for name, complete in completeness_items.items() if not complete]
    if missing_fields:
        recommendations.append(f"Complete these profile fields: {', '.join(missing_fields[:3])}.")
    if len(skills) < 6:
        recommendations.append("Add more specific skills, including tools, frameworks, and soft skills.")
    if profile and not re.search(r"\d|%|built|created|improved|managed|analyzed", getattr(profile, "experience", "") or "", re.I):
        recommendations.append("Add measurable achievements or action verbs to your experience section.")
    if best_fit < 50:
        recommendations.append("Review the recommended jobs and add missing high-priority skills to improve readiness.")
    if not recommendations:
        recommendations.append("Your profile is strong. Tailor your CV summary for each application.")
    return recommendations[:4]
