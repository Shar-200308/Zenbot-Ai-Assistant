import os
import re
from django.db import migrations, models


def seed_knowledge_from_text(apps, schema_editor):
    KnowledgeBaseItem = apps.get_model('chatbot', 'KnowledgeBaseItem')
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    qa_path = os.path.join(base_dir, 'data', 'chat-data.txt')

    if not os.path.exists(qa_path):
        return

    try:
        with open(qa_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Match Q: ... and A: ... blocks
        pattern = re.compile(r'Q:\s*(.*?)\s*\nA:\s*(.*?)(?=\n\s*\d+\s*\n|\n\s*Q:|\Z)', re.DOTALL)
        matches = pattern.findall(content)

        items_to_create = []
        seen = set()

        for q, a in matches:
            clean_q = q.strip()
            clean_a = a.strip()
            if not clean_q or not clean_a:
                continue
            if clean_q.lower() in seen:
                continue
            seen.add(clean_q.lower())

            cat = "General"
            q_lower = clean_q.lower()
            if any(k in q_lower for k in ["intern", "stipend", "duration", "training"]):
                cat = "Internship"
            elif any(k in q_lower for k in ["job", "salary", "package", "hiring", "eligibility", "criteria", "cgpa"]):
                cat = "Recruitment"
            elif any(k in q_lower for k in ["zensar", "company", "ceo", "location", "office", "headquarter"]):
                cat = "Company Info"
            elif any(k in q_lower for k in ["python", "django", "frontend", "react", "cloud", "aws", "data", "ai"]):
                cat = "Technical Roles"

            items_to_create.append(
                KnowledgeBaseItem(
                    category=cat,
                    question=clean_q,
                    answer=clean_a,
                    is_active=True,
                )
            )

        if items_to_create:
            KnowledgeBaseItem.objects.bulk_create(items_to_create, ignore_conflicts=True)
    except Exception as e:
        print("Knowledge seeding notice:", e)


class Migration(migrations.Migration):

    dependencies = [
        ('chatbot', '0013_jobposting'),
    ]

    operations = [
        migrations.CreateModel(
            name='KnowledgeBaseItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('category', models.CharField(default='General FAQ', max_length=100)),
                ('question', models.TextField()),
                ('answer', models.TextField()),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.RunPython(seed_knowledge_from_text, reverse_code=migrations.RunPython.noop),
    ]
