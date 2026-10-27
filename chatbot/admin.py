from django.contrib import admin, messages
from django.utils.html import format_html

from .email_utils import send_status_email
from .models import (
    CandidateMessage,
    ChatMessage,
    FirebaseUser,
    InternshipApplication,
    JobApplication,
    JobPosting,
    KnowledgeBaseItem,
)


@admin.register(FirebaseUser)
class FirebaseUserAdmin(admin.ModelAdmin):
    list_display = ("email", "name", "uid", "created_at")
    search_fields = ("email", "name")
    readonly_fields = ("uid", "email", "created_at")
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("user", "short_message", "created_at")
    search_fields = ("user__email", "message")
    list_filter = ("created_at",)
    readonly_fields = ("user", "message", "response", "created_at")
    ordering = ("-created_at",)

    def short_message(self, obj):
        return obj.message[:50] + "..." if len(obj.message) > 50 else obj.message
    short_message.short_description = "User Message"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# ── Status badge helper ──────────────────────────────────────────────────────
STATUS_COLORS = {
    'pending':      ('#b45309', '#fef3c7'),
    'under_review': ('#1d4ed8', '#dbeafe'),
    'shortlisted':  ('#7c3aed', '#ede9fe'),
    'rejected':     ('#b91c1c', '#fee2e2'),
    'selected':     ('#15803d', '#dcfce7'),
}

def status_badge(obj):
    fg, bg = STATUS_COLORS.get(obj.status, ('#374151', '#f3f4f6'))
    return format_html(
        '<span style="background:{};color:{};padding:3px 10px;border-radius:12px;'
        'font-size:12px;font-weight:600;">{}</span>',
        bg, fg, obj.get_status_display()
    )
status_badge.short_description = "Status"


# ── InternshipApplication Admin ──────────────────────────────────────────────

@admin.register(InternshipApplication)
class InternshipApplicationAdmin(admin.ModelAdmin):
    list_display = ("full_name", "role", "email", "course", status_badge, "applied_at")
    search_fields = ("full_name", "email", "role", "course")
    list_filter = ("status", "role", "course", "applied_at")
    readonly_fields = ("user", "role", "full_name", "email", "phone", "course",
                       "ug_college", "ug_cgpa", "pg_college", "pg_cgpa", "photo", "resume", "applied_at")
    fields = ("user", "role", "full_name", "email", "phone", "course",
              "ug_college", "ug_cgpa", "pg_college", "pg_cgpa", "photo", "resume", "status", "applied_at")
    ordering = ("-applied_at",)
    actions = ("action_accept", "action_reject", "action_under_review", "action_shortlist")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return True

    # ── Actions ──────────────────────────────────────────────────────────────

    def action_accept(self, request, queryset):
        updated = 0
        for app in queryset.exclude(status="selected"):
            app.status = "selected"
            app.save(update_fields=["status"])
            send_status_email(app, "Internship", "selected")
            updated += 1
        skipped = queryset.count() - updated
        msg = f"✅ {updated} application(s) marked as Selected and congratulations email sent."
        if skipped:
            msg += f" ({skipped} already selected — skipped)"
        self.message_user(request, msg, messages.SUCCESS)
    action_accept.short_description = "✅  Accept — Mark Selected & Send Congratulations Email"

    def action_reject(self, request, queryset):
        updated = 0
        for app in queryset.exclude(status="rejected"):
            app.status = "rejected"
            app.save(update_fields=["status"])
            send_status_email(app, "Internship", "rejected")
            updated += 1
        skipped = queryset.count() - updated
        msg = f"❌ {updated} application(s) marked as Rejected and notification email sent."
        if skipped:
            msg += f" ({skipped} already rejected — skipped)"
        self.message_user(request, msg, messages.WARNING)
    action_reject.short_description = "❌  Reject — Mark Rejected & Send Notification Email"

    def action_under_review(self, request, queryset):
        count = queryset.update(status="under_review")
        self.message_user(request, f"🔍 {count} application(s) marked as Under Review.", messages.SUCCESS)
    action_under_review.short_description = "🔍  Mark as Under Review"

    def action_shortlist(self, request, queryset):
        count = queryset.update(status="shortlisted")
        self.message_user(request, f"⭐ {count} application(s) marked as Shortlisted.", messages.SUCCESS)
    action_shortlist.short_description = "⭐  Mark as Shortlisted"


# ── JobApplication Admin ─────────────────────────────────────────────────────

@admin.register(JobApplication)
class JobApplicationAdmin(admin.ModelAdmin):
    list_display = ("full_name", "role", "email", "course", status_badge, "applied_at")
    search_fields = ("full_name", "email", "role", "course")
    list_filter = ("status", "role", "course", "applied_at")
    readonly_fields = ("user", "role", "full_name", "email", "phone", "course", "ug_course",
                       "ug_college", "ug_cgpa", "pg_college", "pg_cgpa", "photo", "resume", "applied_at")
    fields = ("user", "role", "full_name", "email", "phone", "course", "ug_course",
              "ug_college", "ug_cgpa", "pg_college", "pg_cgpa", "photo", "resume", "status", "applied_at")
    ordering = ("-applied_at",)
    actions = ("action_accept", "action_reject", "action_under_review", "action_shortlist")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return True

    # ── Actions ──────────────────────────────────────────────────────────────

    def action_accept(self, request, queryset):
        updated = 0
        for app in queryset.exclude(status="selected"):
            app.status = "selected"
            app.save(update_fields=["status"])
            send_status_email(app, "Job", "selected")
            updated += 1
        skipped = queryset.count() - updated
        msg = f"✅ {updated} application(s) marked as Selected and congratulations email sent."
        if skipped:
            msg += f" ({skipped} already selected — skipped)"
        self.message_user(request, msg, messages.SUCCESS)
    action_accept.short_description = "✅  Accept — Mark Selected & Send Congratulations Email"

    def action_reject(self, request, queryset):
        updated = 0
        for app in queryset.exclude(status="rejected"):
            app.status = "rejected"
            app.save(update_fields=["status"])
            send_status_email(app, "Job", "rejected")
            updated += 1
        skipped = queryset.count() - updated
        msg = f"❌ {updated} application(s) marked as Rejected and notification email sent."
        if skipped:
            msg += f" ({skipped} already rejected — skipped)"
        self.message_user(request, msg, messages.WARNING)
    action_reject.short_description = "❌  Reject — Mark Rejected & Send Notification Email"

    def action_under_review(self, request, queryset):
        count = queryset.update(status="under_review")
        self.message_user(request, f"🔍 {count} application(s) marked as Under Review.", messages.SUCCESS)
    action_under_review.short_description = "🔍  Mark as Under Review"

    def action_shortlist(self, request, queryset):
        count = queryset.update(status="shortlisted")
        self.message_user(request, f"⭐ {count} application(s) marked as Shortlisted.", messages.SUCCESS)
    action_shortlist.short_description = "⭐  Mark as Shortlisted"


@admin.register(JobPosting)
class JobPostingAdmin(admin.ModelAdmin):
    list_display = ("title", "job_type", "department", "location", "is_active", "created_at")
    list_filter = ("job_type", "is_active", "department")
    search_fields = ("title", "skills", "department")
    list_editable = ("is_active",)


@admin.register(KnowledgeBaseItem)
class KnowledgeBaseItemAdmin(admin.ModelAdmin):
    list_display = ("question", "category", "is_active", "updated_at")
    list_filter = ("category", "is_active")
    search_fields = ("question", "answer", "category")
    list_editable = ("is_active",)


@admin.register(CandidateMessage)
class CandidateMessageAdmin(admin.ModelAdmin):
    list_display = ("subject", "candidate_email", "application_type", "scheduled_time", "created_at")
    list_filter = ("application_type", "created_at")
    search_fields = ("candidate_email", "subject", "message")
