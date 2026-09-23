import json
import logging
import re

from django.core.cache import cache

from chatbot.models import ChatMessage

logger = logging.getLogger(__name__)


def format_short_name(name):
    """Extracts only the first alphabetical part and capitalizes it."""
    if not name:
        return "User"
    match = re.search(r'^[a-zA-Z]+', name.strip())
    if match:
        return match.group(0).capitalize()
    return re.split(r'[\d\s]', name.strip())[0].capitalize() or "User"


def _compute_ats_score_and_skills(resume_text: str, role: str):
    """
    Computes a realistic, deterministic ATS match score (65-98%) and extracts
    matched key skills based on 4 pillars: skills, projects, internships/experience, and certifications.
    """
    if not resume_text:
        return 82, "Profile details submitted"

    text_lower = resume_text.lower()
    role_lower = role.lower()

    skill_map = {
        "python": ["python", "django", "fastapi", "flask", "postgresql", "sql", "git", "docker", "rest api"],
        "developer": ["git", "oop", "algorithms", "debugging", "agile", "unit testing", "api integration"],
        "engineer": ["python", "java", "c++", "sql", "git", "api", "system design", "algorithms", "data structures", "linux"],
        "data": ["python", "pandas", "numpy", "sql", "power bi", "tableau", "excel", "data analysis", "statistics"],
        "analyst": ["sql", "power bi", "tableau", "excel", "data analysis", "reporting", "data modeling"],
        "cloud": ["aws", "azure", "docker", "kubernetes", "ci/cd", "linux", "terraform", "devops", "cloud computing"],
        "ai": ["python", "machine learning", "deep learning", "nlp", "tensorflow", "pytorch", "transformers", "opencv"],
        "web": ["html", "css", "javascript", "react", "node.js", "bootstrap", "tailwind", "responsive design"],
        "software": ["c++", "java", "python", "sql", "data structures", "system design", "git", "linux"],
        "frontend": ["react", "javascript", "html", "css", "redux", "tailwind", "responsive design"],
        "qa": ["selenium", "tosca", "test automation", "test cases", "manual testing", "jira", "api testing", "regression testing", "postman"],
        "testing": ["selenium", "manual testing", "test cases", "jira", "automation", "api testing", "defect tracking"],
        "mobile": ["flutter", "react native", "dart", "android", "ios", "mobile app", "api integration"],
        "design": ["figma", "adobe xd", "wireframing", "prototyping", "user research", "ui design", "ux design"],
        "ui": ["figma", "wireframing", "prototyping", "responsive design", "design system", "user experience"],
        "finance": ["accounts payable", "accounts receivable", "payroll", "tally", "excel", "financial reporting", "auditing", "balance sheet", "reconciliation"],
        "account": ["accounting", "financial statements", "general ledger", "tally", "taxation", "excel", "invoicing", "payroll"],
        "business": ["business analysis", "requirements gathering", "process mapping", "agile", "stakeholder management", "documentation", "user stories"],
        "hr": ["talent acquisition", "recruitment", "onboarding", "employee relations", "sourcing", "screening", "hr operations"],
    }

    # 1. Technical Skills Match
    target_skills = set()
    for domain, skills in skill_map.items():
        if domain in role_lower:
            target_skills.update(skills)

    if not target_skills:
        target_skills = {"python", "sql", "git", "api", "communication", "problem solving"}

    matched = [skill.title() for skill in target_skills if skill in text_lower]

    # BUG-05 fix: require at least 2 skill hits to earn a meaningful skills score.
    # A single keyword mention (e.g. a 1-word resume) should not produce a high ratio.
    effective_matched = len(matched) if len(matched) >= 2 else 0
    skills_ratio = effective_matched / len(target_skills) if target_skills else 0.5

    # 2. Projects Match
    project_kws = ["project", "developed", "built", "implemented", "github", "designed", "application", "created"]
    proj_hits = sum(1 for kw in project_kws if kw in text_lower)
    projects_ratio = min(1.0, proj_hits / 3.0)

    # 3. Internships / Experience OR College & CGPA (for internships)
    is_intern = "intern" in role_lower or "trainee" in role_lower
    if is_intern:
        acad_kws = ["cgpa", "gpa", "college", "university", "b.tech", "b.e", "bca", "mca", "b.sc", "percentage", "aggregate", "institution"]
        acad_hits = sum(1 for kw in acad_kws if kw in text_lower)
        acad_or_exp_ratio = min(1.0, acad_hits / 3.0)
    else:
        exp_kws = ["intern", "internship", "experience", "work history", "trainee", "apprentice", "employment", "responsibilities"]
        exp_hits = sum(1 for kw in exp_kws if kw in text_lower)
        acad_or_exp_ratio = min(1.0, exp_hits / 2.0)

    # 4. Certifications Match
    cert_kws = ["certified", "certification", "certificate", "coursera", "udemy", "nptel", "aws", "azure", "license", "hackerrank", "credly"]
    cert_hits = sum(1 for kw in cert_kws if kw in text_lower)
    cert_ratio = min(1.0, cert_hits / 1.0)

    # Holistic ATS Score: Base 40 + weighted contributions across 4 dimensions
    # BUG-04 fix: lowered base from 66→40 so unqualified resumes don't show
    # a misleadingly high score (e.g. 65%) in the HR dashboard.
    score = int(40 + (skills_ratio * 30) + (projects_ratio * 14) + (acad_or_exp_ratio * 10) + (cert_ratio * 4))
    score = max(40, min(98, score))

    skills_str = ", ".join(matched[:6]) if matched else "Foundational domain skills"
    return score, skills_str


def _resolve_ats_score_and_skills(user, role: str, request=None):
    """
    Guarantees that the candidate's ATS Match Accuracy shown in the HR Panel
    exactly matches the analyzed accuracy score calculated during resume evaluation.
    Checks:
    1. Direct POST param 'ats_score' from application form
    2. Cached scorecard score from analyze_selected_role
    3. ChatMessage history scorecard JSON
    4. Deterministic 4-pillar fallback
    """
    final_score = None
    final_skills = None

    # 1. Direct POST parameter
    if request:
        post_val = request.POST.get('ats_score')
        if post_val:
            try:
                ps = int(post_val)
                if 1 <= ps <= 100:
                    final_score = ps
            except (ValueError, TypeError):
                pass

    clean_role = re.sub(r'[^a-zA-Z0-9_]', '_', (role or '').lower().strip())

    # 2. Check user's cached analysis score
    if not final_score and user and getattr(user, 'id', None):
        cached_data = cache.get(f"user_analyzed_score_{user.id}_{clean_role}") or cache.get(f"user_latest_analyzed_score_{user.id}")
        if cached_data and cached_data.get("score"):
            try:
                final_score = int(cached_data["score"])
                final_skills = cached_data.get("skills")
            except (ValueError, TypeError):
                pass

    # 3. Check ChatMessage history for the exact analysis response for this user
    if not final_score and user and getattr(user, 'id', None):
        try:
            analysis_chats = ChatMessage.objects.filter(
                user=user,
                message__icontains="Selected Role for Analysis"
            ).order_by('-created_at')[:5]

            for c in analysis_chats:
                if c.response:
                    try:
                        # BUG-06 fix: use iterative bracket-matching instead of greedy
                        # re.search(r'\{.*\}') which grabs from first '{' to last '}'
                        # and fails on nested objects or trailing text.
                        resp_text = c.response.strip()
                        json_start = resp_text.find('{')
                        if json_start == -1:
                            continue
                        # Walk forward to find the matching closing }
                        depth = 0
                        json_end = -1
                        for i, ch in enumerate(resp_text[json_start:], start=json_start):
                            if ch == '{':
                                depth += 1
                            elif ch == '}':
                                depth -= 1
                                if depth == 0:
                                    json_end = i + 1
                                    break
                        if json_end == -1:
                            continue
                        p_data = json.loads(resp_text[json_start:json_end])
                        sc = p_data.get('score')
                        if sc:
                            final_score = int(sc)
                            skills_list = p_data.get('matching_skills') or []
                            if skills_list:
                                final_skills = ", ".join(skills_list)
                            break
                    except Exception:
                        continue
        except Exception as e:
            logger.warning("Error querying ChatMessage analysis history: %s", e)

    # 4. Fallback to deterministic 4-pillar calculation if user applied directly
    if not final_score:
        fallback_score, fallback_skills = _compute_ats_score_and_skills(getattr(user, 'resume_text', '') or '', role)
        final_score = fallback_score
        if not final_skills:
            final_skills = fallback_skills

    if not final_skills:
        final_skills = "Core technical skills"

    return final_score, final_skills
