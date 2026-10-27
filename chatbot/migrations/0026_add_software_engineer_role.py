from django.db import migrations


def add_software_engineer_roles(apps, schema_editor):
    JobPosting = apps.get_model('chatbot', 'JobPosting')

    # 1. Full-time Software Engineer
    JobPosting.objects.get_or_create(
        title="Software Engineer",
        job_type="job",
        defaults={
            "department": "Engineering",
            "location": "Pune, Maharashtra (Global HQ, Kharadi)",
            "experience": "0-2 Years / Freshers Eligible",
            "skills": "Python, Java, C++, Data Structures, Algorithms, SQL, Git, REST APIs, OOP",
            "description": "Design and develop scalable software applications, build robust backend and frontend components, implement algorithms and data structures, and collaborate with cross-functional engineering teams at Zensar.",
            "vacancies": 15,
            "is_active": True,
        }
    )

    # 2. Software Engineering Intern
    JobPosting.objects.get_or_create(
        title="Software Engineering Intern",
        job_type="internship",
        defaults={
            "department": "Engineering",
            "location": "Pune, Maharashtra (Global HQ, Kharadi)",
            "experience": "Fresher / College Students",
            "skills": "Python, Java, Data Structures, OOP, SQL, Git, Problem Solving",
            "description": "Hands-on software engineering internship working with data structures, API integrations, component development, and code reviews under senior engineering mentors.",
            "vacancies": 20,
            "is_active": True,
        }
    )


def remove_software_engineer_roles(apps, schema_editor):
    JobPosting = apps.get_model('chatbot', 'JobPosting')
    JobPosting.objects.filter(title__in=["Software Engineer", "Software Engineering Intern"]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('chatbot', '0025_jobposting_vacancies'),
    ]

    operations = [
        migrations.RunPython(add_software_engineer_roles, reverse_code=remove_software_engineer_roles),
    ]
