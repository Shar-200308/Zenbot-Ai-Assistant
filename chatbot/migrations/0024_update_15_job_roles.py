from django.db import migrations


def update_15_job_roles(apps, schema_editor):
    JobPosting = apps.get_model('chatbot', 'JobPosting')

    # Clean existing postings to establish the exact 15 roles requested
    JobPosting.objects.all().delete()

    fifteen_postings = [
        # 1. Full Stack Developer (Job)
        {
            "title": "Full Stack Developer",
            "job_type": "job",
            "department": "Engineering",
            "location": "Chennai, Tamil Nadu (OMR Tech Park)",
            "experience": "0-2 Years / Freshers Eligible",
            "skills": "Python, Django, React, PostgreSQL, REST APIs, JavaScript, Git",
            "description": "Design and develop scalable web applications, RESTful APIs, and responsive user interfaces using Python, Django, and React.",
            "is_active": True,
        },
        # 2. Java Backend Developer (Job)
        {
            "title": "Java Backend Developer",
            "job_type": "job",
            "department": "Engineering",
            "location": "Pune, Maharashtra (Global HQ, Kharadi)",
            "experience": "1-3 Years",
            "skills": "Java, Spring Boot, Microservices, Hibernate, PostgreSQL, REST APIs, Docker, Maven",
            "description": "Architect and develop resilient backend microservices, enterprise integrations, and high-throughput APIs using Java and Spring Boot.",
            "is_active": True,
        },
        # 3. AI / ML Engineer (Job)
        {
            "title": "AI / ML Engineer",
            "job_type": "job",
            "department": "Artificial Intelligence",
            "location": "Bengaluru, Karnataka (Whitefield Campus)",
            "experience": "1-3 Years",
            "skills": "Python, PyTorch, TensorFlow, Scikit-learn, LLMs, NLP, MLOps, RAG Architectures",
            "description": "Design and deploy machine learning models, fine-tune foundation LLMs, and optimize generative AI pipelines.",
            "is_active": True,
        },
        # 4. Junior AI Developer (Job)
        {
            "title": "Junior AI Developer",
            "job_type": "job",
            "department": "Artificial Intelligence",
            "location": "Pune, Maharashtra (Global HQ, Kharadi)",
            "experience": "0-1 Years / Freshers Eligible",
            "skills": "Python, LangChain, Prompt Engineering, OpenAI/Gemini APIs, Vector DBs, Machine Learning Basics",
            "description": "Assist in developing AI-powered agents, prompt workflows, intelligent document processing, and AI integrations.",
            "is_active": True,
        },
        # 5. Cloud & DevOps Engineer (Job)
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
        # 6. Data Analyst / BI Specialist (Job)
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
        # 7. QA Automation Engineer (Job)
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
        # 8. Finance & Accounts Executive (Job - Commerce)
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
        # 9. Business Analyst (BFSI & Retail) (Job - Commerce/Management)
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
        # 10. Python Developer Intern (Internship)
        {
            "title": "Python Developer Intern",
            "job_type": "internship",
            "department": "Engineering",
            "location": "Chennai, Tamil Nadu (OMR Campus)",
            "experience": "Fresher / College Students",
            "skills": "Python, Django/Flask, SQLite, OOP, REST APIs, Git, Problem Solving",
            "description": "Hands-on internship building backend features, database models, and REST endpoints under senior engineering mentorship.",
            "is_active": True,
        },
        # 11. Java Developer Intern (Internship)
        {
            "title": "Java Developer Intern",
            "job_type": "internship",
            "department": "Engineering",
            "location": "Pune, Maharashtra (Global HQ, Kharadi)",
            "experience": "Fresher / College Students",
            "skills": "Core Java, OOP Concepts, Collections, Spring Basics, JDBC, SQL, Git",
            "description": "Learn and develop server-side Java applications, data structures, and database connectivity under senior mentorship.",
            "is_active": True,
        },
        # 12. Frontend Developer Intern (Internship)
        {
            "title": "Frontend Developer Intern",
            "job_type": "internship",
            "department": "Engineering",
            "location": "Hyderabad, Telangana (Hitec City Campus)",
            "experience": "Fresher / College Students",
            "skills": "React.js, JavaScript, HTML5, CSS3, Responsive Design, Git",
            "description": "Develop modern, responsive web user interfaces and interactive components while mastering React state management.",
            "is_active": True,
        },
        # 13. Backend Developer Intern (Internship)
        {
            "title": "Backend Developer Intern",
            "job_type": "internship",
            "department": "Engineering",
            "location": "Bengaluru, Karnataka (Whitefield Campus)",
            "experience": "Fresher / College Students",
            "skills": "Node.js/Python, REST APIs, SQL/NoSQL Databases, Git, Postman",
            "description": "Construct scalable server-side APIs, database operations, and authentication services under senior developer guidance.",
            "is_active": True,
        },
        # 14. AI / ML Developer Intern (Internship)
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
        # 15. Cloud / DevOps Intern (Internship)
        {
            "title": "Cloud / DevOps Intern",
            "job_type": "internship",
            "department": "Cloud & Infrastructure",
            "location": "Chennai, Tamil Nadu (DLF IT Park)",
            "experience": "Fresher / College Students",
            "skills": "Linux Fundamentals, AWS Basics, Docker, CI/CD Concepts, Shell Scripting",
            "description": "Gain real-world experience in cloud hosting, containerizing microservices with Docker, and configuring automated deployment workflows.",
            "is_active": True,
        },
    ]

    for item in fifteen_postings:
        JobPosting.objects.create(**item)


class Migration(migrations.Migration):

    dependencies = [
        ('chatbot', '0023_seed_15_chatdata_roles'),
    ]

    operations = [
        migrations.RunPython(update_15_job_roles, reverse_code=migrations.RunPython.noop),
    ]
