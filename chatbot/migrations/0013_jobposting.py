from django.db import migrations, models


def seed_initial_postings(apps, schema_editor):
    JobPosting = apps.get_model('chatbot', 'JobPosting')
    initial_jobs = [
        {
            "title": "Full Stack Python Developer",
            "job_type": "job",
            "department": "Engineering",
            "location": "Pune / Hybrid",
            "experience": "0-2 Years",
            "skills": "Python, Django, PostgreSQL, REST APIs, HTML/CSS/JS",
            "description": "Design and build web applications, APIs, and scalable backend services with Django.",
            "is_active": True,
        },
        {
            "title": "Data Analyst / BI Specialist",
            "job_type": "job",
            "department": "Data & Analytics",
            "location": "Pune / Hybrid",
            "experience": "0-2 Years",
            "skills": "Python, SQL, Power BI, Pandas, Data Visualization",
            "description": "Analyze company metrics, extract business insights, and create interactive data dashboards.",
            "is_active": True,
        },
        {
            "title": "Cloud & DevOps Engineer",
            "job_type": "job",
            "department": "Cloud & Infrastructure",
            "location": "Pune / Hybrid",
            "experience": "1-3 Years",
            "skills": "AWS/GCP, Docker, Linux, CI/CD, Terraform",
            "description": "Maintain cloud deployments, CI/CD automated pipelines, and cloud monitoring.",
            "is_active": True,
        },
        {
            "title": "AI / ML Developer Intern",
            "job_type": "internship",
            "department": "Artificial Intelligence",
            "location": "Pune / Remote",
            "experience": "Fresher",
            "skills": "Python, Machine Learning, NLP, LangChain, Generative AI",
            "description": "Work with LLMs, prompt engineering, vector databases, and RAG architectures.",
            "is_active": True,
        },
        {
            "title": "Software Engineering Intern",
            "job_type": "internship",
            "department": "Engineering",
            "location": "Pune / Hybrid",
            "experience": "Fresher",
            "skills": "Python, JavaScript, SQL, Git, Problem Solving",
            "description": "Hands-on software development across frontend and backend modules under senior mentor guidance.",
            "is_active": True,
        },
    ]
    for item in initial_jobs:
        JobPosting.objects.get_or_create(title=item["title"], defaults=item)


class Migration(migrations.Migration):

    dependencies = [
        ('chatbot', '0012_remove_firebaseuser_role'),
    ]

    operations = [
        migrations.CreateModel(
            name='JobPosting',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=200)),
                ('job_type', models.CharField(choices=[('job', 'Full-time Job'), ('internship', 'Internship')], default='job', max_length=20)),
                ('department', models.CharField(default='Engineering', max_length=100)),
                ('location', models.CharField(default='Pune / Hybrid', max_length=150)),
                ('experience', models.CharField(default='Fresher / 0-2 Years', max_length=100)),
                ('skills', models.CharField(blank=True, max_length=300, null=True)),
                ('description', models.TextField(blank=True, null=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.RunPython(seed_initial_postings, reverse_code=migrations.RunPython.noop),
    ]
