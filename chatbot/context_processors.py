from django.conf import settings


def company_context(request):
    """
    Supplies company and tenant branding settings to all templates dynamically.
    Allows easy customization of company name, portal title, and support details.
    """
    return {
        'company_name': getattr(settings, 'COMPANY_NAME', 'Zensar Technologies'),
        'portal_title': getattr(settings, 'PORTAL_TITLE', 'ZenBot Career Portal'),
        'company_tagline': getattr(settings, 'COMPANY_TAGLINE', 'Empowering Digital Transformation Through Talent'),
        'hr_support_email': getattr(settings, 'HR_SUPPORT_EMAIL', 'campusrecruitment@zensar.com'),
    }
