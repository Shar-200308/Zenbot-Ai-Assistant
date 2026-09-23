import argparse
import contextlib
import csv
import json
import random
import sys
from datetime import datetime, timedelta, timezone

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8")

# Default role definitions with specific skill stacks and vacancy estimations
ROLE_CONFIGS = {
    "Software Engineer": {
        "full_name": "Software Engineer (Core Engineering & System Design)",
        "vacancies": 15,
        "core_skills": {"Python": 7.0, "Java": 6.0, "C++": 5.0, "Data Structures": 7.0, "Algorithms": 6.0, "SQL": 5.0},
        "bonus_skills": ["Git", "REST APIs", "Docker", "Linux", "System Design", "OOP", "Microservices", "PostgreSQL"],
        "cert_keywords": ["HackerRank 5-Star Problem Solving", "LeetCode Gold", "AWS Certified Cloud Practitioner", "Oracle Certified Associate"]
    },
    "Full Stack Developer": {
        "full_name": "Full Stack Developer (Python / Django + React)",
        "vacancies": 12,
        "core_skills": {"Python": 7.0, "Django": 6.0, "FastAPI": 5.0, "React.js": 6.0, "JavaScript": 4.0, "PostgreSQL": 4.0},
        "bonus_skills": ["Redis", "Docker", "Celery", "AWS (EC2/S3)", "RESTful APIs", "Git", "TypeScript", "TailwindCSS"],
        "cert_keywords": ["AWS Certified", "Meta Certified Backend", "React Developer", "Docker", "HackerRank 5-Star"]
    },
    "AI / ML Engineer": {
        "full_name": "AI / ML Engineer (Python, PyTorch & LLMs)",
        "vacancies": 8,
        "core_skills": {"Python": 7.0, "PyTorch": 6.0, "TensorFlow": 5.0, "Scikit-Learn": 5.0, "FastAPI": 4.0, "Pandas": 4.0},
        "bonus_skills": ["LangChain", "HuggingFace", "ChromaDB", "Docker", "MLOps", "Git", "CUDA", "NLP"],
        "cert_keywords": ["TensorFlow Developer", "AWS Machine Learning", "DeepLearning.AI", "HackerRank 5-Star", "Google Cloud AI"]
    },
    "Java Backend Developer": {
        "full_name": "Java Backend Developer (Spring Boot & Microservices)",
        "vacancies": 10,
        "core_skills": {"Java": 7.0, "Spring Boot": 7.0, "Microservices": 5.0, "MySQL": 4.0, "Hibernate": 4.0},
        "bonus_skills": ["Kafka", "Docker", "Kubernetes", "Redis", "RESTful APIs", "Git", "AWS", "JUnit"],
        "cert_keywords": ["Oracle Certified Professional Java", "AWS Certified", "Spring Professional", "HackerRank 5-Star"]
    },
    "Cloud & DevOps Engineer": {
        "full_name": "Cloud & DevOps Engineer (AWS, Kubernetes, Terraform)",
        "vacancies": 6,
        "core_skills": {"AWS (EC2/S3)": 8.0, "Docker": 6.0, "Kubernetes": 6.0, "Linux": 5.0, "CI/CD": 4.0},
        "bonus_skills": ["Terraform", "Ansible", "Python", "Git", "Prometheus", "Bash", "Grafana", "Nginx"],
        "cert_keywords": ["AWS Solutions Architect", "CKA (Certified Kubernetes Admin)", "HashiCorp Terraform", "Red Hat Linux"]
    },
    "Quality Engineer (Automation, Mobile & AI-Led Testing)": {
        "full_name": "Quality Engineer (Automation, Mobile, Application & AI-Led Testing)",
        "vacancies": 12,
        "core_skills": {"Test Automation": 8.0, "Selenium": 7.0, "Appium (Mobile Testing)": 6.0, "AI-Led Testing": 6.0, "Python/Java": 5.0, "API Testing": 5.0},
        "bonus_skills": ["Cypress", "Playwright", "Autonomous Testing", "JIRA", "CI/CD", "Postman", "Self-Healing Tests", "Git"],
        "cert_keywords": ["ISTQB Certified Tester", "Selenium Automation", "Appium Mobile Certification", "AWS Certified", "LambdaTest Certified"]
    },
    "QA Automation Engineer": {
        "full_name": "QA Automation Engineer (Web, Mobile & AI-Led Testing)",
        "vacancies": 10,
        "core_skills": {"Selenium": 7.0, "Test Automation": 7.0, "Mobile Testing": 6.0, "AI-Led Testing": 5.0, "API Testing": 5.0, "Python": 4.0},
        "bonus_skills": ["Playwright", "Cypress", "Appium", "JIRA", "Jenkins", "Postman", "JUnit", "Git"],
        "cert_keywords": ["ISTQB Certified", "Selenium Certified", "Test Automation Professional"]
    }
}

FIRST_NAMES = [
    "Aarav", "Aditi", "Ananya", "Ashwin", "Bhavna", "Charan", "Deepak", "Divya",
    "Ganesh", "Gayathri", "Hari", "Harini", "Ishaan", "Karthik", "Kavya", "Keerthi",
    "Madhav", "Manish", "Meera", "Mithun", "Naveen", "Nithya", "Pooja", "Pranav",
    "Praveen", "Priya", "Rahul", "Rajesh", "Rakshitha", "Rithvik", "Rohit", "Sai",
    "Sanjay", "Santhosh", "Saravanan", "Shalini", "Siddharth", "Sneha", "Sowmya",
    "Srihari", "Surya", "Swetha", "Tarun", "Tejas", "Vaishnavi", "Varun", "Vignesh",
    "Vijay", "Vikram", "Yuvraj"
]

LAST_NAMES = [
    "Sharma", "Iyer", "Nair", "Reddy", "Patel", "Sundaram", "Krishnan", "Raman",
    "Kumar", "Balaji", "Subramanian", "Murugan", "Pillai", "Menon", "Chopra",
    "Varma", "Ganesan", "Srinivasan", "Venkatesh", "Natarajan", "Anand", "Rajendran"
]

COLLEGES = [
    "IIT Madras", "NIT Trichy", "Anna University (CEG)", "PSG Tech Coimbatore",
    "SSN College of Engineering", "Vellore Institute of Technology (VIT)",
    "SRM Institute of Science and Technology", "SASTRA University",
    "Coimbatore Institute of Technology (CIT)", "Thiagarajar College of Engineering"
]

def generate_applicant_pool(role_key="Full Stack Developer", total_apps=1000, seed=42):
    """Generates realistic applicant pool tailored to the requested role."""
    random.seed(seed)
    config = ROLE_CONFIGS.get(role_key, ROLE_CONFIGS["Full Stack Developer"])
    available_skills = list(config["core_skills"].keys()) + config["bonus_skills"]
    cert_pool = config["cert_keywords"] + ["None"]

    applicants = []
    for i in range(1, total_apps + 1):
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        full_name = f"{first} {last}"
        email = f"{first.lower()}.{last.lower()}{random.randint(10, 99)}@gmail.com"
        phone = f"+91 9{random.randint(100000000, 999999999)}"
        college = random.choice(COLLEGES)

        # CGPA (Normal distribution around 7.8, min 5.8, max 9.9)
        cgpa = round(min(9.9, max(5.8, random.gauss(7.8, 0.85))), 2)

        # Job Experience in months (0 to 36 months)
        job_exp_months = max(0, int(random.triangular(0, 36, 12)))

        # Intern Experience in months (0 to 12 months)
        intern_exp_months = max(0, int(random.triangular(0, 12, 4)))

        # Skills (sample 4 to 9 skills)
        num_skills = random.randint(4, min(9, len(available_skills)))
        skills = random.sample(available_skills, num_skills)

        # Certifications
        has_cert = random.random() < 0.65
        certs = random.sample([c for c in cert_pool if c != "None"], k=random.randint(1, 2)) if has_cert else []

        applicants.append({
            "id": f"APP-{i:04d}",
            "name": full_name,
            "email": email,
            "phone": phone,
            "college": college,
            "cgpa": cgpa,
            "job_exp_months": job_exp_months,
            "intern_exp_months": intern_exp_months,
            "skills": skills,
            "certifications": certs,
            "applied_role": config["full_name"]
        })

    return applicants

def score_applicant(cand, config):
    """
    Evaluates applicant using 5-Pillar Matrix (Max 100 points):
    1. Skills Match (30 pts)
    2. Job Experience (25 pts)
    3. Intern Experience (15 pts)
    4. Academics / CGPA (20 pts)
    5. Certifications (10 pts)
    """
    skills = cand["skills"]
    job_exp = cand["job_exp_months"]
    intern_exp = cand["intern_exp_months"]
    cgpa = cand["cgpa"]
    certs = cand["certifications"]

    # 1. Skills Score (Max 30)
    s_score = 0.0
    for core_s, weight in config["core_skills"].items():
        if core_s in skills:
            s_score += weight
    bonus_matches = [s for s in skills if s in config["bonus_skills"]]
    s_score += min(8.0, len(bonus_matches) * 1.5)
    s_score = min(30.0, s_score)

    # 2. Job Experience Score (Max 25)
    if job_exp >= 24:
        j_score = 25.0
    elif job_exp >= 18:
        j_score = 22.0
    elif job_exp >= 12:
        j_score = 18.0
    elif job_exp >= 6:
        j_score = 14.0
    elif job_exp > 0:
        j_score = 9.0
    else:
        j_score = 5.0

    # 3. Intern Experience Score (Max 15)
    if intern_exp >= 6:
        i_score = 15.0
    elif intern_exp >= 4:
        i_score = 12.0
    elif intern_exp >= 2:
        i_score = 9.0
    elif intern_exp > 0:
        i_score = 6.0
    else:
        i_score = 2.0

    # 4. CGPA Score (Max 20)
    if cgpa >= 9.0:
        c_score = 20.0
    elif cgpa >= 8.5:
        c_score = 18.0
    elif cgpa >= 8.0:
        c_score = 16.0
    elif cgpa >= 7.5:
        c_score = 14.0
    elif cgpa >= 7.0:
        c_score = 12.0
    elif cgpa >= 6.5:
        c_score = 10.0
    else:
        c_score = 5.0

    # 5. Certifications Score (Max 10)
    if len(certs) >= 2:
        cert_score = 10.0
    elif len(certs) == 1:
        cert_score = 6.5
    else:
        cert_score = 2.0

    total_score = round(s_score + j_score + i_score + c_score + cert_score, 1)

    return {
        "skills_score": s_score,
        "job_score": j_score,
        "intern_score": i_score,
        "cgpa_score": c_score,
        "cert_score": cert_score,
        "total_score": total_score
    }

def schedule_dynamic_interviews(candidates, start_date_str="2026-09-23"):
    """
    Dynamically schedules N candidates across necessary business days.
    Capacity: 16-18 candidates per day across 2 parallel panels.
    """
    start_dt = datetime.strptime(start_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    time_slots = [
        "09:30 AM - 10:15 AM",
        "10:20 AM - 11:05 AM",
        "11:15 AM - 12:00 PM",
        "12:05 PM - 12:50 PM",
        "02:00 PM - 02:45 PM",
        "02:50 PM - 03:35 PM",
        "03:45 PM - 04:30 PM",
        "04:35 PM - 05:20 PM",
        "05:25 PM - 06:10 PM"
    ]

    # Generate business days (skip Saturday/Sunday)
    business_days = []
    curr = start_dt
    while len(business_days) < 10:
        if curr.weekday() < 5:  # Monday to Friday
            day_name = curr.strftime("%A")
            business_days.append(f"{curr.strftime('%Y-%m-%d')} ({day_name})")
        curr += timedelta(days=1)

    scheduled_list = []
    slot_idx = 0
    day_idx = 0
    panel_toggle = 1

    for rank, cand in enumerate(candidates, 1):
        date_str = business_days[day_idx]
        slot_str = time_slots[slot_idx]
        panel = f"Panel {panel_toggle} ({'Technical Architecture & Core' if panel_toggle == 1 else 'Live Problem Solving & Coding'})"

        cand["rank"] = rank
        cand["interview_date"] = date_str
        cand["interview_time"] = slot_str
        cand["interview_panel"] = panel
        cand["venue"] = "Zenbot OMR Tech Park Campus, Chennai / Google Meet (meet.google.com/zen-interview)"
        cand["status"] = "Shortlisted for Interview (Round 1)"
        scheduled_list.append(cand)

        # Advance slot / panel
        if panel_toggle == 1:
            panel_toggle = 2
        else:
            panel_toggle = 1
            slot_idx += 1
            if slot_idx >= len(time_slots):
                slot_idx = 0
                day_idx = min(day_idx + 1, len(business_days) - 1)

    return scheduled_list

def run_dynamic_shortlist(role="Full Stack Developer", count=50, total_apps=1000):
    """
    Main dynamic shortlisting function requested by HR:
    - Analyzes 1000 candidate resumes for the given role
    - Filters by minimum qualification
    - Scores based on 5 pillars
    - Returns exact top N best resumes
    - Schedules interviews dynamically
    """
    role_key = "Full Stack Developer"
    for k in ROLE_CONFIGS:
        if k.lower() in role.lower():
            role_key = k
            break

    config = ROLE_CONFIGS[role_key]
    vacancies = config["vacancies"]

    applicants = generate_applicant_pool(role_key=role_key, total_apps=total_apps)

    # Score all applicants
    for cand in applicants:
        breakdown = score_applicant(cand, config)
        cand.update(breakdown)

    # Eligibility cutoff: CGPA >= 6.5 and total score >= 50
    eligible = [c for c in applicants if c["cgpa"] >= 6.5 and c["total_score"] >= 50.0]

    # Sort descending: total_score -> skills_score -> job_score -> cgpa
    sorted_candidates = sorted(
        eligible,
        key=lambda x: (x["total_score"], x["skills_score"], x["job_score"], x["cgpa"]),
        reverse=True
    )

    # Select requested top N count
    top_candidates = sorted_candidates[:count]
    scheduled = schedule_dynamic_interviews(top_candidates)

    return {
        "role_key": role_key,
        "role_full_name": config["full_name"],
        "vacancies": vacancies,
        "total_applicants": total_apps,
        "eligible_count": len(eligible),
        "requested_shortlist_count": count,
        "candidates": scheduled
    }

def main():
    parser = argparse.ArgumentParser(description="Zenbot AI Dynamic Candidate Shortlisting Engine")
    parser.add_argument("--role", type=str, default="Full Stack Developer", help="Target Role name")
    parser.add_argument("--count", type=int, default=50, help="Number of candidates HR wants to shortlist (e.g. 50, 75)")
    parser.add_argument("--apps", type=int, default=1000, help="Total application pool size")
    args = parser.parse_args()

    result = run_dynamic_shortlist(role=args.role, count=args.count, total_apps=args.apps)

    print("=" * 75)
    print("🎯 ZENBOT AI DYNAMIC SHORTLIST REPORT FOR HR")
    print("=" * 75)
    print(f"Role Requested     : {result['role_full_name']}")
    print(f"Open Vacancies     : {result['vacancies']} Positions")
    print(f"Total Applications : {result['total_applicants']} Resumes Processed")
    print(f"Eligible Resumes   : {result['eligible_count']} Passed Cutoff (CGPA >= 6.5)")
    print(f"HR Requested Count : Top {result['requested_shortlist_count']} Candidates Selected")
    print(f"Selection Ratio    : 1 : {result['requested_shortlist_count'] / result['vacancies']:.1f}")
    print("=" * 75)

    candidates = result["candidates"]

    # Save results to dynamic file names
    slug = args.role.lower().replace(" ", "_").replace("/", "")
    csv_file = f"chatbot/data/shortlist_{slug}_{args.count}.csv"
    json_file = f"chatbot/data/shortlist_{slug}_{args.count}.json"

    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "rank", "id", "name", "email", "phone", "college", "cgpa",
            "job_exp_months", "intern_exp_months", "skills", "certifications",
            "skills_score", "job_score", "intern_score", "cgpa_score", "cert_score",
            "total_score", "interview_date", "interview_time", "interview_panel", "venue", "status"
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for cand in candidates:
            row = cand.copy()
            row["skills"] = ", ".join(row["skills"])
            row["certifications"] = ", ".join(row["certifications"]) if row["certifications"] else "None"
            row.pop("applied_role", None)
            writer.writerow(row)

    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(f"\n✅ Successfully generated Top {args.count} candidates for '{args.role}'.")
    print(f"📁 CSV exported  : {csv_file}")
    print(f"📁 JSON exported : {json_file}")

    print("\n--- SAMPLE TOP 5 SELECTED RESUMES ---")
    for c in candidates[:5]:
        print(f"Rank {c['rank']:02d}: {c['name']:<20} | Score: {c['total_score']} pts | CGPA: {c['cgpa']} | Job Exp: {c['job_exp_months']}m | Intern: {c['intern_exp_months']}m | Interview: {c['interview_date']} @ {c['interview_time']}")

    print("\n--- LAST 3 CANDIDATES IN SHORTLIST CUTOFF ---")
    for c in candidates[-3:]:
        print(f"Rank {c['rank']:02d}: {c['name']:<20} | Score: {c['total_score']} pts | CGPA: {c['cgpa']} | Job Exp: {c['job_exp_months']}m | Intern: {c['intern_exp_months']}m | Interview: {c['interview_date']} @ {c['interview_time']}")

if __name__ == "__main__":
    main()
