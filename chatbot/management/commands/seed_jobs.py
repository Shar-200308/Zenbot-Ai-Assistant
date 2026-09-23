"""
management/commands/seed_jobs.py
=================================
Disadvantage #5 fix: future job role changes no longer need a migration.

USAGE:
    .venv\\Scripts\\python.exe manage.py seed_jobs              # sync canonical roles
    .venv\\Scripts\\python.exe manage.py seed_jobs --dry-run    # preview without saving
    .venv\\Scripts\\python.exe manage.py seed_jobs --list       # list current DB postings

HOW IT WORKS:
    Uses update_or_create() keyed on (title, job_type) so:
    - Existing HR-managed postings are UPDATED (never deleted)
    - Missing canonical roles are CREATED
    - HR's custom postings are NOT touched
    - Safe to re-run at any time (fully idempotent)

    This replaces the old pattern of creating a new migration every time
    a job role's description, skills, or vacancies change.
"""
from django.core.management.base import BaseCommand

# ── Canonical Job Catalog ──────────────────────────────────────────────────────
# Edit this list (not a migration) whenever you add/modify canonical roles.
CANONICAL_ROLES = [
    # ── Full-time Jobs ──────────────────────────────────────────────────────────
    {
        "title": "Full Stack Developer",
        "job_type": "job",
        "department": "Engineering",
        "location": "Chennai, Tamil Nadu (OMR Tech Park)",
        "experience": "0-2 Years / Freshers Eligible",
        "skills": "Python, Django, React, PostgreSQL, REST APIs, JavaScript, Git",
        "description": "Design and develop scalable web applications, RESTful APIs, and responsive user interfaces.",
        "vacancies": 15,
        "is_active": True,
    },
    {
        "title": "Java Backend Developer",
        "job_type": "job",
        "department": "Engineering",
        "location": "Pune, Maharashtra (Global HQ, Kharadi)",
        "experience": "1-3 Years",
        "skills": "Java, Spring Boot, Microservices, Hibernate, PostgreSQL, REST APIs, Docker, Maven",
        "description": "Architect and develop resilient backend microservices and enterprise integrations.",
        "vacancies": 10,
        "is_active": True,
    },
    {
        "title": "AI / ML Engineer",
        "job_type": "job",
        "department": "Artificial Intelligence",
        "location": "Bengaluru, Karnataka (Whitefield Campus)",
        "experience": "1-3 Years",
        "skills": "Python, PyTorch, TensorFlow, Scikit-learn, LLMs, NLP, MLOps, RAG Architectures",
        "description": "Design and deploy machine learning models and fine-tune foundation LLMs.",
        "vacancies": 8,
        "is_active": True,
    },
    {
        "title": "Cloud & DevOps Engineer",
        "job_type": "job",
        "department": "Cloud & Infrastructure",
        "location": "Hyderabad, Telangana (Hitec City Campus)",
        "experience": "1-3 Years",
        "skills": "AWS, Azure DevOps, Docker, Kubernetes, CI/CD, Terraform, Linux, Jenkins",
        "description": "Manage automated cloud infrastructure and container orchestration pipelines.",
        "vacancies": 12,
        "is_active": True,
    },
    {
        "title": "Data Analyst / BI Specialist",
        "job_type": "job",
        "department": "Data & Analytics",
        "location": "Chennai, Tamil Nadu (DLF IT Park)",
        "experience": "1-3 Years",
        "skills": "SQL, Power BI, Tableau, Advanced Excel, Python, Data Modeling, Business Intelligence",
        "description": "Extract insights and build operational and executive BI dashboards.",
        "vacancies": 10,
        "is_active": True,
    },
    {
        "title": "Software Engineer (SAP / ERP)",
        "job_type": "job",
        "department": "Enterprise Solutions",
        "location": "Pune, Maharashtra (Global HQ, Kharadi)",
        "experience": "1-3 Years",
        "skills": "SAP ABAP, SAP S/4HANA, SAP Fiori, BAPI, BADI, SAP SD/MM/FI, ABAP OOP",
        "description": "Develop and maintain enterprise SAP solutions across modules.",
        "vacancies": 8,
        "is_active": True,
    },
    {
        "title": "Quality Engineer (Automation, Mobile & AI-Led Testing)",
        "job_type": "job",
        "department": "Testing & QA",
        "location": "Pune, Maharashtra (Global HQ, Kharadi)",
        "experience": "0-3 Years (Freshers & Experienced Eligible)",
        "skills": "Test Automation, Selenium, Appium, Cypress, Playwright, Mobile Application Testing (iOS/Android), AI-Led Testing, API Testing (Postman/RestAssured), Python, Java, JIRA",
        "description": "End-to-end quality engineering across automation, mobile, application, and AI-led testing domains.",
        "vacancies": 12,
        "is_active": True,
    },
    # ── Internships ─────────────────────────────────────────────────────────────
    {
        "title": "Python Developer Intern",
        "job_type": "internship",
        "department": "Engineering",
        "location": "Chennai, Tamil Nadu (OMR Campus)",
        "experience": "Fresher / College Students",
        "skills": "Python, Django/Flask, SQLite, OOP, REST APIs, Git, Problem Solving",
        "description": "Hands-on internship building backend features under senior engineering mentorship.",
        "vacancies": 20,
        "is_active": True,
    },
    {
        "title": "AI / ML Developer Intern",
        "job_type": "internship",
        "department": "Artificial Intelligence",
        "location": "Bengaluru, Karnataka (Whitefield Campus)",
        "experience": "Fresher / College Students",
        "skills": "Python, PyTorch, Scikit-learn, LLMs, NLP, Prompt Engineering",
        "description": "Explore generative AI, build LLM pipelines, and implement RAG architectures.",
        "vacancies": 15,
        "is_active": True,
    },
    {
        "title": "Cloud & DevOps Intern",
        "job_type": "internship",
        "department": "Cloud & Infrastructure",
        "location": "Hyderabad, Telangana (Hitec City Campus)",
        "experience": "Fresher / College Students",
        "skills": "AWS/Azure Basics, Docker, Linux, Git, CI/CD Concepts, Python/Bash scripting",
        "description": "Learn cloud infrastructure and DevOps automation through live project exposure.",
        "vacancies": 12,
        "is_active": True,
    },
    {
        "title": "Data Science Intern",
        "job_type": "internship",
        "department": "Data & Analytics",
        "location": "Chennai, Tamil Nadu (DLF IT Park)",
        "experience": "Fresher / College Students",
        "skills": "Python, Pandas, NumPy, Scikit-learn, SQL, Matplotlib, Jupyter",
        "description": "Work on real datasets, build predictive models, and create analytical dashboards.",
        "vacancies": 15,
        "is_active": True,
    },
    {
        "title": "Quality Engineering & Testing Intern",
        "job_type": "internship",
        "department": "Testing & QA",
        "location": "Chennai, Tamil Nadu (DLF IT Park)",
        "experience": "Fresher / College Students",
        "skills": "Automation Testing, Selenium, Appium Mobile Testing, AI-Led Testing Concepts, API Testing, Python, Java",
        "description": "Hands-on internship in quality engineering covering automation, mobile, and API testing.",
        "vacancies": 15,
        "is_active": True,
    },
]


class Command(BaseCommand):
    help = (
        'Syncs canonical job postings to the DB using update_or_create(). '
        'Safe to re-run — never deletes HR-managed postings.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            default=False,
            help='Preview what would be created/updated without saving to DB.',
        )
        parser.add_argument(
            '--list',
            action='store_true',
            default=False,
            help='List all current job postings in the DB and exit.',
        )

    def handle(self, *args, **options):
        from chatbot.models import JobPosting

        if options['list']:
            postings = JobPosting.objects.order_by('job_type', 'title')
            self.stdout.write(f'\n{"TYPE":<12} {"ACTIVE":<8} TITLE')
            self.stdout.write('-' * 60)
            for p in postings:
                status = '✓' if p.is_active else '✗'
                self.stdout.write(f'{p.job_type:<12} {status:<8} {p.title}')
            self.stdout.write(f'\nTotal: {postings.count()} postings\n')
            return

        created_count = 0
        updated_count = 0

        for role in CANONICAL_ROLES:
            title    = role.pop('title')
            job_type = role.pop('job_type')

            if options['dry_run']:
                exists = JobPosting.objects.filter(title=title, job_type=job_type).exists()
                action = 'UPDATE' if exists else 'CREATE'
                self.stdout.write(f'[{action}] {title} ({job_type})')
                # Restore for next iteration
                role['title'] = title
                role['job_type'] = job_type
                continue

            _obj, created = JobPosting.objects.update_or_create(
                title=title,
                job_type=job_type,
                defaults=role,
            )

            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f'  [CREATED] {title} ({job_type})'))
            else:
                updated_count += 1
                self.stdout.write(f'  [UPDATED] {title} ({job_type})')

            # Restore for reporting
            role['title'] = title
            role['job_type'] = job_type

        if not options['dry_run']:
            self.stdout.write(self.style.SUCCESS(
                f'\nDone. Created: {created_count}, Updated: {updated_count}, '
                f'Total canonical roles: {len(CANONICAL_ROLES)}'
            ))
        else:
            self.stdout.write(self.style.NOTICE(
                f'\nDry run complete — {len(CANONICAL_ROLES)} roles previewed. '
                'Run without --dry-run to apply changes.'
            ))
