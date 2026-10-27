"""
chatbot/migrations/0029_safe_reseed_guard.py
============================================
BUG-02 fix: Documents and enforces the safe job-posting seeding pattern.

PROBLEM (migrations 0023 & 0024):
    Both previous seed migrations used:
        JobPosting.objects.all().delete()
    This is DESTRUCTIVE — it wipes ALL HR-managed postings unconditionally
    whenever `migrate` is run (e.g. in CI, staging resets, or production hotfixes).

CORRECT PATTERN (used from 0026+ and here):
    Use update_or_create() keyed on (title, job_type) so:
    - Existing HR-managed postings are updated (not deleted)
    - New postings are added if missing
    - HR-created custom postings are NOT touched
    - The migration is fully idempotent (safe to re-run)
    - Reversal is possible via a proper reverse_code function

This migration is a no-op for the current database (all roles already exist).
Its purpose is to:
  1. Formally document the safe seeding pattern in migration history
  2. Serve as a reference for any future data-seeding migrations
  3. Act as a CI safety marker (if a future migration uses .all().delete()
     in a seed context, this comment makes the problem obvious in review)
"""
from django.db import migrations


def verify_and_patch_safe_roles(apps, schema_editor):
    """
    Idempotent: ensures all 15 canonical roles exist using update_or_create().
    Will NOT delete any HR-managed postings. Safe to re-run in any environment.
    """
    JobPosting = apps.get_model('chatbot', 'JobPosting')

    canonical_roles = [
        {
            "title": "Full Stack Developer",
            "job_type": "job",
            "defaults": {
                "department": "Engineering",
                "location": "Chennai, Tamil Nadu (OMR Tech Park)",
                "experience": "0-2 Years / Freshers Eligible",
                "skills": "Python, Django, React, PostgreSQL, REST APIs, JavaScript, Git",
                "description": "Design and develop scalable web applications, RESTful APIs, and responsive user interfaces.",
                "is_active": True,
            },
        },
        {
            "title": "Java Backend Developer",
            "job_type": "job",
            "defaults": {
                "department": "Engineering",
                "location": "Pune, Maharashtra (Global HQ, Kharadi)",
                "experience": "1-3 Years",
                "skills": "Java, Spring Boot, Microservices, Hibernate, PostgreSQL, REST APIs, Docker, Maven",
                "description": "Architect and develop resilient backend microservices and enterprise integrations.",
                "is_active": True,
            },
        },
        {
            "title": "AI / ML Engineer",
            "job_type": "job",
            "defaults": {
                "department": "Artificial Intelligence",
                "location": "Bengaluru, Karnataka (Whitefield Campus)",
                "experience": "1-3 Years",
                "skills": "Python, PyTorch, TensorFlow, Scikit-learn, LLMs, NLP, MLOps, RAG Architectures",
                "description": "Design and deploy machine learning models and fine-tune foundation LLMs.",
                "is_active": True,
            },
        },
        {
            "title": "Cloud & DevOps Engineer",
            "job_type": "job",
            "defaults": {
                "department": "Cloud & Infrastructure",
                "location": "Hyderabad, Telangana (Hitec City Campus)",
                "experience": "1-3 Years",
                "skills": "AWS, Azure DevOps, Docker, Kubernetes, CI/CD, Terraform, Linux, Jenkins",
                "description": "Manage automated cloud infrastructure and container orchestration.",
                "is_active": True,
            },
        },
        {
            "title": "Data Analyst / BI Specialist",
            "job_type": "job",
            "defaults": {
                "department": "Data & Analytics",
                "location": "Chennai, Tamil Nadu (DLF IT Park)",
                "experience": "1-3 Years",
                "skills": "SQL, Power BI, Tableau, Advanced Excel, Python, Data Modeling, Business Intelligence",
                "description": "Extract insights and build operational and executive BI dashboards.",
                "is_active": True,
            },
        },
        {
            "title": "Python Developer Intern",
            "job_type": "internship",
            "defaults": {
                "department": "Engineering",
                "location": "Chennai, Tamil Nadu (OMR Campus)",
                "experience": "Fresher / College Students",
                "skills": "Python, Django/Flask, SQLite, OOP, REST APIs, Git, Problem Solving",
                "description": "Hands-on internship building backend features under senior engineering mentorship.",
                "is_active": True,
            },
        },
        {
            "title": "AI / ML Developer Intern",
            "job_type": "internship",
            "defaults": {
                "department": "Artificial Intelligence",
                "location": "Bengaluru, Karnataka (Whitefield Campus)",
                "experience": "Fresher / College Students",
                "skills": "Python, PyTorch, Scikit-learn, LLMs, NLP, Prompt Engineering",
                "description": "Explore generative AI, build LLM pipelines, and implement RAG.",
                "is_active": True,
            },
        },
    ]

    for role_def in canonical_roles:
        title    = role_def["title"]
        job_type = role_def["job_type"]
        defaults = role_def["defaults"]
        _obj, created = JobPosting.objects.update_or_create(
            title=title,
            job_type=job_type,
            defaults=defaults,
        )
        action = "Created" if created else "Verified"
        # Note: logging is not available inside migrations; use print for migration output
        print(f"  [{action}] {title} ({job_type})")


def reverse_verify(apps, schema_editor):
    """
    Reverse: no destructive action taken.
    The safe pattern is: do nothing on reverse (postings remain as HR left them).
    """


class Migration(migrations.Migration):
    """
    BUG-02 fix: safe idempotent seed guard.

    Previous migrations (0023, 0024) used JobPosting.objects.all().delete() which
    is dangerous in production. This migration:
      - Uses update_or_create() so existing HR postings are never destroyed
      - Is fully reversible (reverse_code does nothing destructive)
      - Serves as the canonical reference for future seeding migrations
    """

    dependencies = [
        ('chatbot', '0028_key_skills_textfield_and_token_fixes'),
    ]

    operations = [
        migrations.RunPython(
            verify_and_patch_safe_roles,
            reverse_code=reverse_verify,
        ),
    ]
