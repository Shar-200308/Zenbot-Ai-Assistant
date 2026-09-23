from django.db import migrations


def seed_15_chatdata_roles(apps, schema_editor):
    JobPosting = apps.get_model('chatbot', 'JobPosting')

    # Deactivate or clear previous postings to cleanly establish the 15 roles from chat-data.txt
    JobPosting.objects.all().delete()

    fifteen_postings = [
        {
            "title": "Full Stack Python Developer",
            "job_type": "job",
            "department": "Engineering",
            "location": "Chennai, Tamil Nadu (OMR Tech Park)",
            "experience": "0-2 Years / Freshers Eligible",
            "skills": "Python, Django, React, PostgreSQL, REST APIs, Git",
            "description": "Design and develop scalable web applications, REST APIs, and microservices using Python, Django, and React.",
            "is_active": True,
        },
        {
            "title": "Frontend (React) Developer",
            "job_type": "job",
            "department": "Engineering",
            "location": "Pune, Maharashtra (Global HQ, Kharadi)",
            "experience": "1-3 Years",
            "skills": "React.js, JavaScript (ES6+), Redux, HTML5, CSS3, REST APIs, Tailwind CSS",
            "description": "Build interactive, responsive user interfaces and client-side applications using React and modern frontend frameworks.",
            "is_active": True,
        },
        {
            "title": "Data Analyst / BI Specialist",
            "job_type": "job",
            "department": "Data & Analytics",
            "location": "Chennai, Tamil Nadu (DLF IT Park)",
            "experience": "1-3 Years",
            "skills": "SQL, Power BI, Tableau, Advanced Excel, Python, Data Modeling, Business Intelligence",
            "description": "Extract insights, build operational and executive BI dashboards, and analyze business metrics across company departments.",
            "is_active": True,
        },
        {
            "title": "Cloud & DevOps Engineer",
            "job_type": "job",
            "department": "Cloud & Infrastructure",
            "location": "Hyderabad, Telangana (Hitec City Campus)",
            "experience": "1-3 Years",
            "skills": "AWS, Azure DevOps, Docker, Kubernetes, CI/CD, Terraform, Linux, Jenkins",
            "description": "Manage automated cloud infrastructure, container orchestration, CI/CD pipelines, and secure cloud environments.",
            "is_active": True,
        },
        {
            "title": "QA Automation Engineer",
            "job_type": "job",
            "department": "Testing & QA",
            "location": "Pune, Maharashtra (Global HQ, Kharadi)",
            "experience": "1-3 Years",
            "skills": "Selenium, TOSCA, Java, Python, Test Automation, API Testing, JIRA",
            "description": "Develop automated test suites, conduct regression and end-to-end interface testing, and ensure software delivery quality.",
            "is_active": True,
        },
        {
            "title": "Mobile App Developer",
            "job_type": "job",
            "department": "Mobile Engineering",
            "location": "Bengaluru, Karnataka (Whitefield Campus)",
            "experience": "1-3 Years",
            "skills": "Flutter, React Native, Dart, JavaScript, iOS, Android, REST APIs",
            "description": "Create seamless cross-platform mobile applications for iOS and Android with robust offline capabilities and cloud sync.",
            "is_active": True,
        },
        {
            "title": "Finance & Accounts Executive",
            "job_type": "job",
            "department": "Finance & Operations",
            "location": "Pune, Maharashtra (Global HQ, Kharadi)",
            "experience": "0-2 Years (B.Com / M.Com / MBA Finance)",
            "skills": "Accounts Payable, Accounts Receivable, Advanced Excel, Tally, Payroll, Financial Reporting",
            "description": "Handle corporate financial transactions, accounts reconciliation, vendor payments, payroll processing, and financial reporting for commerce graduates.",
            "is_active": True,
        },
        {
            "title": "Business Analyst (BFSI & Retail)",
            "job_type": "job",
            "department": "Domain Experts & Consulting",
            "location": "Chennai, Tamil Nadu (DLF IT Park)",
            "experience": "1-3 Years (BBA / MBA / Commerce / Economics)",
            "skills": "Business Analysis, Requirements Gathering, Process Mapping, BFSI & Retail Domains, Agile, Data Insights",
            "description": "Bridge business requirements and technical teams, analyze BFSI/retail client workflows, and author functional specification documents.",
            "is_active": True,
        },
        {
            "title": "HR Generalist & Talent Specialist",
            "job_type": "job",
            "department": "Talent & Learning",
            "location": "Pune, Maharashtra (Global HQ, Kharadi)",
            "experience": "0-2 Years (BBA / MBA / Commerce / HR)",
            "skills": "Talent Acquisition, Campus Recruitment, Employee Relations, HR Operations, Onboarding",
            "description": "Drive talent management, coordinate campus recruitment drives, facilitate employee engagement, and manage HR operations.",
            "is_active": True,
        },
        {
            "title": "Python/Django Developer Intern",
            "job_type": "internship",
            "department": "Engineering",
            "location": "Chennai, Tamil Nadu (OMR Campus)",
            "experience": "Fresher / College Students",
            "skills": "Python, Django, SQLite, REST APIs, Git, Problem Solving",
            "description": "Hands-on internship building backend features, database models, and REST endpoints under senior engineering mentorship.",
            "is_active": True,
        },
        {
            "title": "Frontend (React) Developer Intern",
            "job_type": "internship",
            "department": "Engineering",
            "location": "Pune, Maharashtra (Global HQ, Kharadi)",
            "experience": "Fresher / College Students",
            "skills": "React.js, HTML5, CSS3, JavaScript, Responsive Design, Git",
            "description": "Build clean, accessible web components and interface screens while mastering modern React state management.",
            "is_active": True,
        },
        {
            "title": "AI / ML Developer Intern",
            "job_type": "internship",
            "department": "Artificial Intelligence",
            "location": "Bengaluru, Karnataka (Whitefield Campus)",
            "experience": "Fresher / College Students",
            "skills": "Python, PyTorch, Scikit-learn, LLMs, NLP, Prompt Engineering",
            "description": "Explore generative AI, build LLM pipelines, implement retrieval augmented generation (RAG), and train machine learning models.",
            "is_active": True,
        },
        {
            "title": "Cloud/DevOps Intern",
            "job_type": "internship",
            "department": "Cloud & Infrastructure",
            "location": "Hyderabad, Telangana (Hitec City Campus)",
            "experience": "Fresher / College Students",
            "skills": "Linux, AWS Basics, Docker, CI/CD Concepts, Shell Scripting",
            "description": "Gain real-world experience in cloud hosting, containerizing microservices with Docker, and configuring automated deployment workflows.",
            "is_active": True,
        },
        {
            "title": "Mobile App Developer Intern",
            "job_type": "internship",
            "department": "Mobile Engineering",
            "location": "Chennai, Tamil Nadu (DLF IT Park)",
            "experience": "Fresher / College Students",
            "skills": "Flutter, React Native, Dart, Mobile UI Design, API Integration",
            "description": "Design and code cross-platform mobile user flows, screen animations, and state architectures for Android and iOS devices.",
            "is_active": True,
        },
        {
            "title": "UI/UX Design Intern",
            "job_type": "internship",
            "department": "Design & Experience",
            "location": "Pune, Maharashtra (Global HQ, Kharadi)",
            "experience": "Fresher / Design Students",
            "skills": "Figma, Adobe XD, Wireframing, Prototyping, User Research, Design Systems",
            "description": "Create user-centric wireframes, high-fidelity prototypes, design system components, and visual design assets for client portals.",
            "is_active": True,
        },
    ]

    for item in fifteen_postings:
        JobPosting.objects.create(**item)


class Migration(migrations.Migration):

    dependencies = [
        ('chatbot', '0022_alter_candidatemessage_calendar_link_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_15_chatdata_roles, reverse_code=migrations.RunPython.noop),
    ]
