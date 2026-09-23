# ZenBot — AI-Powered Campus Recruitment & Hiring Platform

ZenBot is an intelligent, end-to-end recruitment automation platform designed for modern campus placement drives and talent acquisition. Built with **Django**, **Google Gemini AI**, **LangChain**, and **Firebase**, ZenBot bridges the gap between candidates and recruiters by automating candidate inquiries, resume parsing, ATS scoring, role recommendations, and HR pipeline management.

---

## 📌 Table of Contents

- [Overview](#overview)
- [How It Works](#how-it-works)
- [Key Features](#key-features)
  - [Candidate Portal](#candidate-portal)
  - [HR Recruiter Dashboard](#hr-recruiter-dashboard)
  - [AI & ATS Screening Engine](#ai--ats-screening-engine)
- [System Architecture](#system-architecture)
- [Technology Stack](#technology-stack)
- [Project Directory Structure](#project-directory-structure)
- [Configuration & Environment Variables](#configuration--environment-variables)
- [Step-by-Step Setup Guide](#step-by-step-setup-guide)
  - [Option A: Local Development](#option-a-local-development)
  - [Option B: Docker Compose](#option-b-docker-compose)
- [API Endpoints & Documentation](#api-endpoints--documentation)
- [Troubleshooting & FAQs](#troubleshooting--faqs)

---

## 📖 Overview

Campus hiring often involves screening hundreds of resumes, answering repetitive company policy queries, and coordinating interview schedules manually. 

**ZenBot solves this by offering a dual-sided platform:**
1. **For Students / Job Seekers**: A conversational AI portal where they can chat with a company assistant, upload their resumes for instant ATS analysis, receive automated job/internship role recommendations, and track application statuses.
2. **For HR Teams**: A centralized panel to review applications, dynamically filter and rank candidates by ATS score, schedule interviews with venue and calendar links, post dynamic openings, and maintain full audit compliance.

---

## 🔄 How It Works

```mermaid
flowchart TD
    subgraph Candidate Flow
        A[Candidate Signs Up / Logs In] --> B[AI Chatbot Support]
        A --> C[Upload Resume PDF]
        C --> D[AI Resume Parsing & Skill Extraction]
        D --> E[ATS Match Score & Role Suggestions]
        E --> F[Submit Job / Internship Application]
        F --> G[Track Application Status in Profile]
    end

    subgraph HR Recruiter Flow
        H[HR Accesses /hr/ Panel] --> I[View Submissions & ATS Scores]
        I --> J[Dynamic Shortlisting & Filtering]
        J --> K[Update Status: Selected / Under Review / Rejected]
        K --> L[Automated Email Notification to Candidate]
        H --> M[Post & Manage Job Openings]
        H --> N[Export Candidates to CSV & View Analytics]
    end
```

---

## ✨ Key Features

### 🎓 Candidate Portal
- **Secure Authentication**: Email/Password and Google OAuth sign-in powered by Firebase.
- **24/7 AI Chatbot**: Conversational assistant powered by Google Gemini and ChromaDB RAG (Retrieval-Augmented Generation) that accurately answers queries about company culture, hiring rounds, policies, and openings.
- **Smart Resume Parsing**: Automatically extracts text, contact information, education, GPA, and skill keywords from PDF resumes.
- **AI Role Recommendation**: Compares candidate skill sets against company vacancy requirements to recommend the best-matching job or internship roles.
- **Real-Time ATS Scoring**: Evaluates resume compatibility against industry benchmarks, highlighting core strengths and identified skill gaps.
- **One-Click Application**: Pre-fills application forms from parsed resume data for internships and full-time positions.
- **Live Status Tracking**: View real-time application stages (`Pending`, `Under Review`, `Shortlisted`, `Selected`, `Rejected`) under the user profile.

---

### 💼 HR Recruiter Dashboard (`/hr/`)
- **Centralized Pipeline**: Review and manage both internship and full-time job applicants in one place.
- **Dynamic Shortlisting**: Filter candidates by minimum ATS threshold, graduation course, role, or specific technical skill keywords.
- **Automated Email Communications**: Send professionally formatted interview invitations, status updates, or offer notifications with interview venues, time slots, and Google Calendar links.
- **One-Click Email Actions**: Recruiters can update candidate status directly from notification links with secure tokens.
- **Dynamic Job Openings Management**: Add, activate, toggle, or delete job and internship postings dynamically without redeploying code.
- **Compliance & Audit Logging**: Every recruiter action (status change, candidate communication, job deletion) is recorded in `HRAuditLog` for transparency.
- **Analytics & Reporting**: Visual metric counters (Total Applications, Shortlisted, Selected) and one-click CSV export of applicant pools.

---

### 🧠 AI & ATS Screening Engine
- **Multi-Model Gemini Cascade**: Leverages Google Gemini models (`gemini-3.5-flash`, `gemini-3.5-flash-lite`) with automatic API key rotation across key pools.
- **RAG Knowledge Base**: Uses ChromaDB vector embeddings over company documentation (`chat-data.txt`) to deliver accurate answers without hallucination.
- **Role Evaluation Matrix**: Pre-configured scoring engines across domains including Software Engineering, Full Stack (Python/React), AI/ML, Cloud/DevOps, Quality Assurance, and Testing.

---

## 🏗️ System Architecture

```text
[ Browser / Frontend Client ]
        │
        ├── HTML5 / Modern CSS / Vanilla JS (Outfit Typography)
        ├── Firebase Web Client SDK (Authentication)
        ▼
[ Django Web Server (Waitress / WSGI) ] ─── [ REST API: /api/v1/ ]
        │
        ├── Auth Middleware: Firebase Admin SDK verification
        ├── Cache Layer: Redis / Django DB Cache
        ├── Database: PostgreSQL (Production) / SQLite (Development)
        │
        ├── [ AI Engine ]
        │     ├── Google Gemini LLM API (Prompt Engineering & Key Rotation)
        │     ├── LangChain + ChromaDB (RAG Vector Store)
        │     └── PyPDF2 Resume Text Extraction
        │
        ├── [ Background Worker ]
        │     ├── Celery Worker
        │     ├── Redis Message Broker
        │     └── Automated Email Notifications (SMTP)
        │
        └── [ Storage ]
              └── Cloudinary (Cloud) / Local Media Storage
```

---

## 🛠️ Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| **Backend Framework** | Django 4.2+ & Django REST Framework | Core web application, REST APIs, and business logic |
| **WSGI Server** | Waitress | Production-ready WSGI HTTP server |
| **AI / LLM** | Google Gemini (`google-generativeai`) | Conversational intelligence, resume evaluation, ATS insights |
| **RAG / Vector DB** | LangChain & ChromaDB | Document retrieval over company recruitment FAQs |
| **Authentication** | Firebase Admin SDK & Firebase Auth | Secure multi-tenant authentication and user identity |
| **Database** | PostgreSQL / SQLite (via `dj-database-url`) | Relational storage for users, applications, jobs, and audit logs |
| **Task Queue & Cache** | Celery & Redis (`django-redis`) | Asynchronous email delivery and cached resume analysis |
| **Media Storage** | Cloudinary / Local Disk | Secure storage for uploaded resumes and applicant photos |
| **API Documentation** | drf-spectacular (OpenAPI 3.0) | Interactive Swagger UI (`/api/docs/`) and ReDoc (`/api/redoc/`) |
| **Containerization** | Docker & Docker Compose | Multi-container orchestration (Web, DB, Redis, Celery) |

---

## 📁 Project Directory Structure

```text
Zenbot/
│
├── manage.py                          # Django management script
├── requirements.txt                   # Project dependencies
├── Dockerfile                         # Production multi-stage Docker build
├── docker-compose.yml                 # Local Docker environment (Django, Postgres, Redis, Celery)
├── firebase-service-account.json      # Firebase Admin credentials
│
├── Zenbot/                            # Project Configuration
│   ├── __init__.py
│   ├── asgi.py
│   ├── wsgi.py
│   ├── celery.py                      # Celery app initialization
│   ├── settings.py                    # Global settings (Database, Cache, Celery, AI, Security)
│   └── urls.py                        # Root URL routing & Swagger endpoints
│
└── chatbot/                           # Core Recruitment Application
    ├── admin.py                       # Django Admin configuration
    ├── apps.py                        # App configuration & startup tasks
    ├── candidate_screening_engine.py  # Standalone CLI screening and candidate ranking engine
    ├── email_utils.py                 # Email templates, SMTP dispatch, and action tokens
    ├── firebase_auth.py               # Custom DRF authentication backend for Firebase tokens
    ├── models.py                      # Database models (Applications, Jobs, AuditLog, Messages)
    ├── services.py                    # Helper utilities (ATS parsing, shortlisting logic)
    ├── tasks.py                       # Celery asynchronous background tasks
    ├── urls.py                        # Application routes and /api/v1/ endpoints
    │
    ├── ai/                            # AI & RAG Subsystem
    │   └── ai_engine.py               # Gemini LLM integration, key rotation, ChromaDB retriever
    │
    ├── data/                          # Knowledge base documents and vector stores
    │   ├── chat-data.txt              # Recruitment FAQ reference text
    │   └── chroma_db/                 # ChromaDB persistent vector database
    │
    ├── static/                        # CSS, JS, fonts, and brand assets
    │   ├── css/                       # Stylesheets (Modern UI, responsive layout)
    │   ├── js/                        # Client-side chat, resume upload, and HR panel logic
    │   └── assets/                    # Logos and illustrations
    │
    ├── templates/                     # HTML Templates
    │   ├── login.html                 # Login page with Firebase auth
    │   ├── signup.html                # Registration page
    │   ├── chat.html                  # Candidate AI chat & resume analysis interface
    │   ├── profile.html               # Candidate profile and application status
    │   ├── internship_apply.html      # Internship application form
    │   ├── job_apply.html             # Job application form
    │   ├── hr_panel.html              # Comprehensive HR dashboard
    │   └── hr_action_result.html      # Confirmation screen for one-click email actions
    │
    └── views/                         # Modular View Controllers
        ├── auth_views.py              # Login/signup pages, user sync, /health/ probe
        ├── chat_views.py              # Chat endpoints, streaming AI response, clear history
        ├── application_views.py       # Resume upload, ATS analysis, application submission
        ├── hr_views.py                # HR candidate list, status update, job posting management
        ├── analytics_views.py         # Recruiter metrics and CSV export
        └── common.py                  # Shared helpers and decorators
```

---

## ⚙️ Configuration & Environment Variables

Create a `.env` file in the root directory and configure the variables according to your environment:

| Variable | Description | Example / Default |
|---|---|---|
| `DJANGO_SECRET_KEY` | Secret key for cryptographic signing | `your_django_secret_key_here` |
| `DEBUG` | Toggle debug mode (`True` for local, `False` for production) | `True` |
| `ALLOWED_HOSTS` | Comma-separated list of permitted hostnames | `localhost,127.0.0.1` |
| `DATABASE_URL` | Database connection string (SQLite or PostgreSQL) | `postgresql://username:password@localhost:5432/zenbot_db` |
| `REDIS_URL` | Redis URL for Celery message broker and cache | `redis://localhost:6379/0` |
| `GEMINI_API_KEY` | Google Gemini API key (supports comma-separated keys) | `your_gemini_api_key_here` |
| `GEMINI_MODEL` | Primary Gemini model name | `gemini-3.5-flash` |
| `EMAIL_HOST_USER` | Gmail address for sending automated recruitment emails | `your_email@gmail.com` |
| `EMAIL_HOST_PASSWORD`| Google App Password (16 characters) | `your_16_character_app_password` |
| `HR_EMAIL` | Email designated for receiving alerts and accessing the HR panel | `your_hr_email@company.com` |
| `SITE_URL` | Public base URL used in email links and action buttons | `http://localhost:8000` |
| `CLOUDINARY_URL` | (Optional) Cloudinary storage connection string | `cloudinary://your_api_key:your_api_secret@your_cloud_name` |
| `COMPANY_NAME` | Organization name displayed across portal and emails | `Zensar Technologies` |
| `PORTAL_TITLE` | Application title in header and emails | `ZenBot Career Portal` |
| `HR_SUPPORT_EMAIL` | HR contact email shown to candidates | `campusrecruitment@zensar.com` |

#### Example `.env` Template
```env
DJANGO_SECRET_KEY=your_django_secret_key_here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=sqlite:///db.sqlite3
REDIS_URL=redis://localhost:6379/0
CHROMADB_DISABLED=0

# Gemini AI (comma-separated keys supported for rotation)
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.5-flash-lite

# Gmail SMTP Settings
EMAIL_HOST_USER=your_email@gmail.com
EMAIL_HOST_PASSWORD=your_16_character_app_password
HR_EMAIL=your_hr_email@company.com

# Site URL
SITE_URL=http://localhost:8000

# Optional Cloudinary Storage
CLOUDINARY_URL=

# Branding
COMPANY_NAME=Zensar Technologies
PORTAL_TITLE=ZenBot Career Portal
COMPANY_TAGLINE=Empowering Digital Transformation Through Talent
HR_SUPPORT_EMAIL=campusrecruitment@zensar.com
```

---

## 🚀 Step-by-Step Setup Guide

### Option A: Local Development

#### 1. Prerequisites
- **Python 3.10+** installed
- **Git** installed
- **Redis Server** (optional for basic local testing; required for Celery background tasks)
- **Firebase Project**: Create a project in [Firebase Console](https://console.firebase.google.com/), enable Email/Password & Google sign-in, and download your service account key as `firebase-service-account.json` into the root directory.

#### 2. Clone the Repository
```bash
git clone https://github.com/your-username/Zenbot.git
cd Zenbot
```

#### 3. Create and Activate Virtual Environment
```bash
# On Windows (PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# On Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
```

#### 4. Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

#### 5. Configure `.env`
Create a `.env` file in the project root with your database, Gemini API key, and email settings as outlined in the [Configuration](#configuration--environment-variables) section.

#### 6. Run Database Migrations & Create Cache
```bash
# Run schema migrations
python manage.py migrate

# Create the database cache table
python manage.py createcachetable
```

#### 7. Create a Superuser (Optional)
```bash
python manage.py createsuperuser
```

#### 8. Start Background Services (Redis & Celery)
In a separate terminal with the virtual environment activated:
```bash
# Start Celery Worker
python -m celery -A Zenbot worker -l info
```
*(Note: If Redis is not running, tasks will automatically run inline in eager mode on local environments).*

#### 9. Run the Development Server
```bash
python manage.py runserver
```
Visit **`http://localhost:8000/login/`** in your browser to access the portal.

---

### Option B: Docker Compose

Docker Compose builds the web application, PostgreSQL database, Redis, and a Celery worker in isolated containers with a single command.

```bash
# Build and start all services
docker compose up --build

# Run in background (detached mode)
docker compose up -d

# Stop services
docker compose down
```

The application will be live at **`http://localhost:8000/`**.

---

## 📡 API Endpoints & Documentation

ZenBot includes interactive OpenAPI 3.0 documentation generated through `drf-spectacular`:

- **Swagger UI**: [`http://localhost:8000/api/docs/`](http://localhost:8000/api/docs/)
- **ReDoc**: [`http://localhost:8000/api/redoc/`](http://localhost:8000/api/redoc/)
- **Health Probe**: [`http://localhost:8000/health/`](http://localhost:8000/health/) (Returns `200 OK` when DB, Redis, and cache are operational)

### Key Endpoints Overview

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/login/` | Candidate login interface |
| `GET` | `/chat/` | Main AI assistant & resume analysis portal |
| `POST` | `/api/v1/chat/` | Send message to AI chatbot |
| `GET` | `/api/v1/chat/stream/` | Streaming response from AI engine (Server-Sent Events) |
| `POST` | `/api/v1/upload-resume/` | Upload PDF resume for text extraction & ATS scoring |
| `POST` | `/api/v1/suggest-roles/` | Get AI-recommended job and internship roles |
| `POST` | `/api/v1/submit-job-application/` | Submit a full-time job application |
| `POST` | `/api/v1/submit-application/` | Submit an internship application |
| `GET` | `/api/v1/my-applications/` | Fetch status of submitted applications |
| `GET` | `/hr/` | Recruiter administration dashboard |
| `GET` | `/api/v1/hr/applications/` | Retrieve candidate submissions with filters |
| `POST` | `/api/v1/hr/update-status/` | Update candidate status (Selected, Rejected, Under Review) |
| `POST` | `/api/v1/hr/messages/send/` | Send interview invitation with venue & calendar link |
| `GET` | `/api/v1/hr/export-csv/` | Download candidate dataset as CSV |
| `GET` | `/api/v1/hr/audit-log/` | View compliance log of recruiter actions |
| `GET` | `/hr/action/` | Process one-click status change via email token |

---

## 🔧 Troubleshooting & FAQs

### 1. `Gemini API Quota Exceeded` or `ResourceExhausted`
- **Solution**: ZenBot supports key pooling. Add multiple Gemini API keys in `.env` separated by commas:
  ```env
  GEMINI_API_KEY=your_gemini_api_key_1,your_gemini_api_key_2,your_gemini_api_key_3
  ```
  The engine will automatically rotate to the next key when a rate limit is reached.

### 2. `Firebase App Not Initialized` or Authentication Errors
- Verify that `firebase-service-account.json` exists in the project root directory.
- Verify that your Firebase project has both **Email/Password** and **Google Sign-In** providers enabled under Authentication > Sign-in method.

### 3. Email Sending Fails (`SMTPAuthenticationError`)
- Gmail requires an **App Password** when 2-Factor Authentication is enabled.
- Generate one under Google Account > Security > 2-Step Verification > App passwords, and paste it into `EMAIL_HOST_PASSWORD` without spaces.

### 4. Background Emails Not Triggering
- Ensure Redis is running (`redis-cli ping` returns `PONG`).
- Start the Celery worker via `python -m celery -A Zenbot worker -l info`.
- For quick local testing without Redis, Celery automatically falls back to synchronous inline execution when SQLite is detected.

---

## 📄 License

This project is licensed under the MIT License — see the LICENSE file for details.
