from django.db import models


class FirebaseUser(models.Model):
    uid = models.CharField(max_length=200, unique=True)
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=200, blank=True, null=True)
    resume_text = models.TextField(blank=True, null=True)  # Persists resume text across requests (no session expiry)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    @property
    def is_active(self):
        return True

    def __str__(self):
        return self.email


class ChatMessage(models.Model):
    user = models.ForeignKey(
        FirebaseUser,
        on_delete=models.CASCADE,
        related_name="chats"
    )
    message = models.TextField()
    response = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)


# ── Shared status choices ─────────────────────────────────────────────────────
APPLICATION_STATUS_CHOICES = [
    ('pending',      'Pending'),
    ('under_review', 'Under Review'),
    ('shortlisted',  'Shortlisted'),
    ('rejected',     'Rejected'),
    ('selected',     'Selected'),
]


class InternshipApplication(models.Model):
    user = models.ForeignKey(
        FirebaseUser,
        on_delete=models.CASCADE,
        related_name="applications"
    )
    role = models.CharField(max_length=100)
    full_name = models.CharField(max_length=200)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True, null=True)
    course = models.CharField(max_length=100, blank=True, null=True)
    ug_course = models.CharField(max_length=100, blank=True, null=True)
    ug_college = models.CharField(max_length=200, blank=True, null=True)
    pg_college = models.CharField(max_length=200, blank=True, null=True)
    ug_cgpa = models.CharField(max_length=10, blank=True, null=True)
    pg_cgpa = models.CharField(max_length=10, blank=True, null=True)
    photo = models.FileField(upload_to='photos/', blank=True, null=True)
    resume = models.FileField(upload_to='resumes/', blank=True, null=True)
    location = models.CharField(max_length=250, blank=True, null=True)  # BUG 2 fix: stores role location for correct venue in emails
    status = models.CharField(
        max_length=20,
        choices=APPLICATION_STATUS_CHOICES,
        default='pending',
        db_index=True,
    )
    ats_score = models.IntegerField(default=85, blank=True, null=True)
    key_skills = models.TextField(blank=True, null=True)  # Changed from CharField(350) — no more silent truncation
    applied_at = models.DateTimeField(auto_now_add=True, db_index=True)
    hr_archived = models.BooleanField(default=False, db_index=True)
    hr_deleted = models.BooleanField(default=False, db_index=True)

    def __str__(self):
        return f"{self.full_name} - {self.role} [{self.get_status_display()}]"


class JobApplication(models.Model):
    user = models.ForeignKey(
        FirebaseUser,
        on_delete=models.CASCADE,
        related_name="job_applications"
    )
    role = models.CharField(max_length=100)
    full_name = models.CharField(max_length=200)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True, null=True)
    course = models.CharField(max_length=100, blank=True, null=True)
    ug_course = models.CharField(max_length=100, blank=True, null=True)
    ug_college = models.CharField(max_length=200, blank=True, null=True)
    pg_college = models.CharField(max_length=200, blank=True, null=True)
    ug_cgpa = models.CharField(max_length=10, blank=True, null=True)
    pg_cgpa = models.CharField(max_length=10, blank=True, null=True)
    photo = models.FileField(upload_to='photos/', blank=True, null=True)
    resume = models.FileField(upload_to='resumes/', blank=True, null=True)
    location = models.CharField(max_length=250, blank=True, null=True)  # BUG 2 fix: stores role location for correct venue in emails
    status = models.CharField(
        max_length=20,
        choices=APPLICATION_STATUS_CHOICES,
        default='pending',
        db_index=True,
    )
    ats_score = models.IntegerField(default=85, blank=True, null=True)
    key_skills = models.TextField(blank=True, null=True)  # Changed from CharField(350) — no more silent truncation
    applied_at = models.DateTimeField(auto_now_add=True, db_index=True)
    hr_archived = models.BooleanField(default=False, db_index=True)
    hr_deleted = models.BooleanField(default=False, db_index=True)

    def __str__(self):
        return f"{self.full_name} - {self.role} [{self.get_status_display()}]"


# ── Dynamic Job & Internship Openings (HR Managed) ───────────────────────────
JOB_TYPE_CHOICES = [
    ('job', 'Full-time Job'),
    ('internship', 'Internship'),
]


class JobPosting(models.Model):
    title = models.CharField(max_length=200)
    job_type = models.CharField(
        max_length=20,
        choices=JOB_TYPE_CHOICES,
        default='job',
    )
    department = models.CharField(max_length=100, default='Engineering')
    location = models.CharField(max_length=150, default='Pune / Hybrid')
    experience = models.CharField(max_length=100, default='Fresher / 0-2 Years')
    vacancies = models.PositiveIntegerField(default=5)
    skills = models.CharField(max_length=300, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} ({self.get_job_type_display()}) - {'Active' if self.is_active else 'Closed'}"


# ── Centralized Company Knowledge Base (PostgreSQL) ──────────────────────────
class KnowledgeBaseItem(models.Model):
    category = models.CharField(max_length=100, default='General FAQ')
    question = models.TextField()
    answer = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"[{self.category}] {self.question[:60]}"


# ── HR Direct Candidate Communication & Interview Scheduling ────────────────
class CandidateMessage(models.Model):
    application_id = models.IntegerField(db_index=True)
    application_type = models.CharField(max_length=20, default='job', db_index=True)  # 'job' or 'internship'
    candidate_email = models.EmailField(db_index=True)
    sender = models.CharField(max_length=100, default='HR Recruitment Team')
    subject = models.CharField(max_length=250, default='Interview Invitation')
    message = models.TextField()
    venue_address = models.TextField(blank=True, null=True)
    interview_type = models.CharField(max_length=50, blank=True, null=True)  # 'job' (3 rounds) or 'internship' (1 round)
    meeting_link = models.TextField(blank=True, null=True)
    scheduled_time = models.CharField(max_length=150, blank=True, null=True)
    calendar_link = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return f"{self.subject} -> {self.candidate_email} ({self.created_at.strftime('%d %b %Y')})"


# ── HR Audit Log (tracks all HR panel actions for compliance) ─────────────────
class HRAuditLog(models.Model):
    """Every HR action is logged here for full audit trail and compliance."""
    actor_email = models.EmailField(db_index=True)
    action = models.CharField(max_length=100, db_index=True)
    # action values: 'status_update', 'delete_application', 'archive_application',
    #                'job_create', 'job_toggle', 'job_delete', 'message_send', 'csv_export'
    target_type = models.CharField(max_length=20, blank=True, null=True)
    # target_type: 'internship', 'job', 'job_posting'
    target_id = models.IntegerField(null=True, blank=True)
    detail = models.TextField(blank=True, null=True)  # JSON-serializable detail string
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        ts = self.timestamp.strftime('%d %b %Y %H:%M')
        return f"[{ts}] {self.actor_email} → {self.action}"
