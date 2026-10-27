from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chatbot', '0014_knowledgebaseitem'),
    ]

    operations = [
        migrations.CreateModel(
            name='CandidateMessage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('application_id', models.IntegerField()),
                ('application_type', models.CharField(default='job', max_length=20)),
                ('candidate_email', models.EmailField(max_length=254)),
                ('sender', models.CharField(default='HR Recruitment Team', max_length=100)),
                ('subject', models.CharField(default='Interview Invitation', max_length=250)),
                ('message', models.TextField()),
                ('meeting_link', models.CharField(blank=True, max_length=500, null=True)),
                ('scheduled_time', models.CharField(blank=True, max_length=150, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
    ]
