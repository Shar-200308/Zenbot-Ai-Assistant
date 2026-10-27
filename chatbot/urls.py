from django.urls import include, path

from . import views
from .views.auth_views import health_check

# ── Versioned API routes (/api/v1/…) ─────────────────────────────────────────
# All API-only endpoints have a canonical /api/v1/ path.
# The original short-form paths below are kept as backward-compatible aliases.
# Fix 11: API versioning — frontend can migrate to /api/v1/ at its own pace.
v1_api_patterns = [
    path("save-user/",            views.save_user,                 name="v1_save_user"),
    path("save-chat/",            views.save_chat,                 name="v1_save_chat"),
    path("chat/",                 views.chat_api,                  name="v1_chat_api"),
    path("chat/stream/",          views.streaming_chat_api,        name="v1_chat_stream"),
    path("get-chats/",            views.get_chats,                 name="v1_get_chats"),
    path("clear-history/",        views.clear_history,             name="v1_clear_history"),
    path("upload-resume/",        views.upload_resume,             name="v1_upload_resume"),
    path("suggest-roles/",        views.suggest_roles,             name="v1_suggest_roles"),
    path("analyze-role/",         views.analyze_selected_role,     name="v1_analyze_role"),
    path("submit-application/",   views.submit_application,        name="v1_submit_application"),
    path("submit-job-application/", views.submit_job_application,  name="v1_submit_job_application"),
    path("my-applications/",      views.my_applications,           name="v1_my_applications"),
    path("delete-application/",   views.delete_application,        name="v1_delete_application"),
    path("get-analyzed-resume/",  views.get_analyzed_resume,       name="v1_get_analyzed_resume"),
    path("active-jobs/",          views.get_active_jobs_api,       name="v1_get_active_jobs"),
    # ── HR Panel API ─────────────────────────────────────────────────────────
    path("hr/applications/",      views.hr_get_applications,       name="v1_hr_get_applications"),
    path("hr/update-status/",     views.hr_update_status,          name="v1_hr_update_status"),
    path("hr/delete-application/",views.hr_delete_application,     name="v1_hr_delete_application"),
    path("hr/restore-application/",views.hr_restore_application,   name="v1_hr_restore_application"),
    path("hr/export-csv/",        views.hr_export_csv,             name="v1_hr_export_csv"),
    path("hr/jobs/",              views.hr_get_job_postings,        name="v1_hr_get_job_postings"),
    path("hr/jobs/create/",       views.hr_create_job_posting,     name="v1_hr_create_job_posting"),
    path("hr/jobs/toggle/",       views.hr_toggle_job_posting,     name="v1_hr_toggle_job_posting"),
    path("hr/jobs/delete/",       views.hr_delete_job_posting,     name="v1_hr_delete_job_posting"),
    path("hr/messages/send/",     views.hr_send_candidate_message, name="v1_hr_send_candidate_message"),
    path("hr/audit-log/",         views.hr_get_audit_log,          name="v1_hr_audit_log"),
    path("hr/dynamic-shortlist/", views.hr_dynamic_shortlist,      name="v1_hr_dynamic_shortlist"),
    path("hr/analytics/",         views.hr_analytics_api,          name="v1_hr_analytics"),
]

urlpatterns = [
    # ── Page views ────────────────────────────────────────────────────────────
    path("login/",       views.login_page,          name="login"),
    path("signup/",      views.signup_page,          name="signup"),
    path("chat/",        views.chat_page,            name="chat"),
    path("profile/",     views.profile_page,         name="profile"),
    path("apply-internship/", views.internship_apply_page, name="apply_internship"),
    path("apply-job/",   views.job_apply_page,       name="apply_job"),
    path("hr/",          views.hr_panel_page,        name="hr_panel"),
    path("hr/action/",   views.hr_email_action,      name="hr_email_action"),  # one-click email action
    path("health/",      health_check,               name="health_check"),     # Disadvantage #5 fix

    # ── Canonical versioned API (/api/v1/…) ──────────────────────────────────
    path("api/v1/", include((v1_api_patterns, "v1"))),

    # ── Legacy / backward-compatible API aliases (short-form paths) ───────────
    # These remain fully functional. Clients can migrate to /api/v1/ incrementally.
    path("save-user/",             views.save_user,                 name="save_user"),
    path("save-chat/",             views.save_chat,                 name="save_chat"),
    path("chat/api/",              views.chat_api,                  name="chat_api"),
    path("chat/stream/",           views.streaming_chat_api,        name="chat_stream"),
    path("get-chats/",             views.get_chats,                 name="get_chats"),
    path("clear-history/",         views.clear_history,             name="clear_history"),
    path("clear-chats/",           views.clear_history,             name="clear_chats"),
    path("upload-resume/",         views.upload_resume,             name="upload_resume"),
    path("suggest-roles/",         views.suggest_roles,             name="suggest_roles"),
    path("analyze-role/",          views.analyze_selected_role,     name="analyze_role"),
    path("submit-application/",    views.submit_application,        name="submit_application"),
    path("submit-job-application/",views.submit_job_application,    name="submit_job_application"),
    path("my-applications/",       views.my_applications,           name="my_applications"),
    path("delete-application/",    views.delete_application,        name="delete_application"),
    path("get-analyzed-resume/",   views.get_analyzed_resume,       name="get_analyzed_resume"),
    path("api/active-jobs/",       views.get_active_jobs_api,       name="get_active_jobs_api"),
    # HR legacy paths
    path("hr/applications/",       views.hr_get_applications,       name="hr_get_applications"),
    path("hr/update-status/",      views.hr_update_status,          name="hr_update_status"),
    path("hr/delete-application/", views.hr_delete_application,     name="hr_delete_application"),
    path("hr/restore-application/",views.hr_restore_application,    name="hr_restore_application"),
    path("hr/export-csv/",         views.hr_export_csv,             name="hr_export_csv"),
    path("hr/jobs/",               views.hr_get_job_postings,       name="hr_get_job_postings"),
    path("hr/jobs/create/",        views.hr_create_job_posting,     name="hr_create_job_posting"),
    path("hr/jobs/toggle/",        views.hr_toggle_job_posting,     name="hr_toggle_job_posting"),
    path("hr/jobs/delete/",        views.hr_delete_job_posting,     name="hr_delete_job_posting"),
    path("hr/messages/send/",      views.hr_send_candidate_message, name="hr_send_candidate_message"),
    path("hr/audit-log/",          views.hr_get_audit_log,          name="hr_audit_log"),
    path("hr/dynamic-shortlist/",  views.hr_dynamic_shortlist,      name="hr_dynamic_shortlist"),
    path("hr/analytics/",          views.hr_analytics_api,          name="hr_analytics"),
]
