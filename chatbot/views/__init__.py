"""
chatbot.views
=============
Modularized views package for the Zenbot HR Recruitment Platform.
Re-exports all views for seamless backward compatibility.
"""

from .analytics_views import (
    hr_analytics_api,
)
from .application_views import (
    analyze_selected_role,
    delete_application,
    get_active_jobs_api,
    get_analyzed_resume,
    internship_apply_page,
    job_apply_page,
    my_applications,
    submit_application,
    submit_job_application,
    suggest_roles,
    upload_resume,
)
from .auth_views import (
    login_page,
    profile_page,
    save_user,
    signup_page,
)
from .chat_views import (
    chat_api,
    chat_page,
    clear_history,
    get_chats,
    save_chat,
    streaming_chat_api,
)
from .common import (
    _compute_ats_score_and_skills,
    _resolve_ats_score_and_skills,
    format_short_name,
)
from .hr_views import (
    _is_hr,
    hr_create_job_posting,
    hr_delete_application,
    hr_delete_job_posting,
    hr_dynamic_shortlist,
    hr_email_action,
    hr_export_csv,
    hr_get_applications,
    hr_get_audit_log,
    hr_get_job_postings,
    hr_panel_page,
    hr_restore_application,
    hr_send_candidate_message,
    hr_toggle_job_posting,
    hr_update_status,
)

__all__ = [
    '_compute_ats_score_and_skills',
    '_is_hr',
    '_resolve_ats_score_and_skills',
    'analyze_selected_role',
    'chat_api',
    # Chat & SSE
    'chat_page',
    'clear_history',
    'delete_application',
    # Common / ATS helpers
    'format_short_name',
    'get_active_jobs_api',
    'get_analyzed_resume',
    'get_chats',
    # Visual Analytics & BI
    'hr_analytics_api',
    'hr_create_job_posting',
    'hr_delete_application',
    'hr_delete_job_posting',
    'hr_dynamic_shortlist',
    'hr_email_action',
    'hr_export_csv',
    'hr_get_applications',
    'hr_get_audit_log',
    'hr_get_job_postings',
    # HR Panel & Actions
    'hr_panel_page',
    'hr_restore_application',
    'hr_send_candidate_message',
    'hr_toggle_job_posting',
    'hr_update_status',
    # Applications & Candidates
    'internship_apply_page',
    'job_apply_page',
    # Auth & Pages
    'login_page',
    'my_applications',
    'profile_page',
    'save_chat',
    'save_user',
    'signup_page',
    'streaming_chat_api',
    'submit_application',
    'submit_job_application',
    'suggest_roles',
    'upload_resume',
]
