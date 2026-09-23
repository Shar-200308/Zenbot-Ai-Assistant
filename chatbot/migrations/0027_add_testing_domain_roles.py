from django.db import migrations


def add_testing_domain_roles(apps, schema_editor):
    JobPosting = apps.get_model('chatbot', 'JobPosting')

    # 1. Full-time Quality Engineer (Automation, Mobile & AI-Led Testing)
    JobPosting.objects.get_or_create(
        title="Quality Engineer (Automation, Mobile & AI-Led Testing)",
        job_type="job",
        defaults={
            "department": "Testing & QA",
            "location": "Pune, Maharashtra (Global HQ, Kharadi)",
            "experience": "0-3 Years (Freshers & Experienced Eligible)",
            "skills": "Test Automation, Selenium, Appium, Cypress, Playwright, Mobile Application Testing (iOS/Android), AI-Led Testing, Autonomous Testing, API Testing (Postman/RestAssured), Python, Java, JIRA",
            "description": "End-to-end quality engineering across automation, mobile, application, and AI-led testing domains. Build intelligent test automation suites, mobile app test harnesses, and autonomous self-healing regression frameworks.",
            "vacancies": 12,
            "is_active": True,
        }
    )

    # 2. Quality Engineering & Testing Intern (Internship)
    JobPosting.objects.get_or_create(
        title="Quality Engineering & Testing Intern",
        job_type="internship",
        defaults={
            "department": "Testing & QA",
            "location": "Chennai, Tamil Nadu (DLF IT Park)",
            "experience": "Fresher / College Students",
            "skills": "Automation Testing, Selenium, Appium Mobile Testing, AI-Led Testing Concepts, API Testing, Python, Java, Test Case Design",
            "description": "Hands-on internship in quality engineering covering automation, mobile application testing, API validation, and modern AI-led testing workflows.",
            "vacancies": 15,
            "is_active": True,
        }
    )

    # 3. Enhance existing QA Automation Engineer role to reflect the 4 testing domains
    JobPosting.objects.filter(title="QA Automation Engineer").update(
        skills="Selenium, Appium, Playwright, Cypress, Mobile Testing (iOS/Android), AI-Led Testing, API Testing, Python, Java, JIRA, Test Automation",
        description="Develop and execute comprehensive quality assurance across automation, mobile, application, and AI-led testing domains with self-healing tests and CI/CD pipelines.",
        vacancies=10,
        is_active=True,
    )


def remove_testing_domain_roles(apps, schema_editor):
    JobPosting = apps.get_model('chatbot', 'JobPosting')
    JobPosting.objects.filter(title__in=[
        "Quality Engineer (Automation, Mobile & AI-Led Testing)",
        "Quality Engineering & Testing Intern"
    ]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('chatbot', '0026_add_software_engineer_role'),
    ]

    operations = [
        migrations.RunPython(add_testing_domain_roles, reverse_code=remove_testing_domain_roles),
    ]
