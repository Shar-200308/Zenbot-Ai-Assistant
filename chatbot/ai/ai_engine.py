import contextlib
import json
import logging
import os
import re
import threading
import warnings

from django.conf import settings
from django.core.cache import cache  # BUG 4 fix: for TTL-based context caching

logger = logging.getLogger(__name__)

# Suppress noisy SDK warnings
warnings.filterwarnings("ignore", message=".*Core Pydantic V1.*")
warnings.filterwarnings("ignore", message=".*google.generativeai.*")
warnings.filterwarnings("ignore", category=DeprecationWarning)
logging.getLogger("google").setLevel(logging.ERROR)
# -----------------------------------------------------------------------------

# BUG-11 (ChromaDB) fix: single in-process lock prevents two workers from
# simultaneously deleting and rebuilding the ChromaDB directory.
_chroma_rebuild_lock = threading.Lock()

qa_path = os.path.join(settings.BASE_DIR, "chatbot", "data", "chat-data.txt")
chroma_path = os.path.join(settings.BASE_DIR, "chatbot", "data", "chroma_db")

# ================= RAG SETUP & GEMINI CONFIGURATION =================

# BUG-03 fix: declare _API_KEYS_POOL as a module-level mutable list so that
# tasks.py's `ai_engine._API_KEYS_POOL[:] = optimal` does not raise AttributeError.
# _get_api_keys() now returns this pool (populated lazily on first call).
_API_KEYS_POOL: list = []


def _get_api_keys() -> list:
    """Returns the active API key pool, populating it lazily from settings/env."""
    global _API_KEYS_POOL
    if not _API_KEYS_POOL:
        raw = getattr(settings, "GEMINI_API_KEY", "") or os.getenv("GEMINI_API_KEY", "")
        keys = [k.strip() for k in str(raw).split(",") if k.strip()]
        _API_KEYS_POOL = keys if keys else [""]
    return _API_KEYS_POOL

_current_key_idx = 0

def get_current_gemini_api_key() -> str:
    keys = _get_api_keys()
    return keys[_current_key_idx % len(keys)]

def rotate_gemini_api_key() -> bool:
    """Rotates to next available API key if multiple keys are configured in GEMINI_API_KEY."""
    global _current_key_idx, _json_llm, _llm
    keys = _get_api_keys()
    if len(keys) > 1:
        prev_idx = _current_key_idx % len(keys)
        _current_key_idx = (_current_key_idx + 1) % len(keys)
        logger.warning(
            "Gemini API key rotated from index %d to %d (total keys: %d)",
            prev_idx + 1, (_current_key_idx % len(keys)) + 1, len(keys)
        )
        _json_llm = None
        _llm = None
        return True
    return False

gemini_api_key = get_current_gemini_api_key()

# Default primary model and fallback cascade order:
# 1. Primary from settings/env (defaults to gemini-3.5-flash)
# 2. gemini-3.5-flash-lite (high speed, generous free tier limits)
# 3. gemini-flash-latest (stable alias)
# 4. gemini-2.5-flash (fallback)
DEFAULT_PRIMARY_MODEL = getattr(settings, "GEMINI_MODEL", None) or os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
GEMINI_CANDIDATE_MODELS = list(dict.fromkeys([
    DEFAULT_PRIMARY_MODEL,
    "gemini-3.5-flash-lite",
    "gemini-flash-latest",
    "gemini-3.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
]))

# ================= LAZY INITIALIZATION =================
_embeddings = None
_vector_db = None
_llm = None
_llm_model_name = None   # Tracks which model _llm was initialized with
_json_llm = None  # Dedicated LLM instance for JSON-only responses
# BUG 4 fix: _cached_zensar_context removed as module-level global.
# Now uses Django's DB-backed cache with a 10-minute TTL so HR updates
# are reflected automatically without requiring a server restart.


def get_embeddings():
    """Returns a LangChain-compatible embeddings object.
    Uses models/gemini-embedding-001 via google.generativeai.embed_content()
    which calls the 'embedContent' endpoint (supported by this API key).
    """
    global _embeddings
    if _embeddings is None:
        logger.info("Initializing Google Embeddings (gemini-embedding-001)...")
        try:
            import google.generativeai as _genai_old
            from langchain_core.embeddings import Embeddings as _LCEmbeddings

            _genai_old.configure(api_key=gemini_api_key)
            _EMBED_MODEL = "models/gemini-embedding-001"

            class _GoogleEmbeddings(_LCEmbeddings):
                """Wraps google.generativeai.embed_content (uses embedContent endpoint).
                Handles 429 quota errors with exponential backoff.
                """

                def _embed(self, text: str) -> list:
                    import time
                    import warnings
                    max_retries = 3
                    for attempt in range(max_retries):
                        try:
                            with warnings.catch_warnings():
                                warnings.simplefilter("ignore")
                                result = _genai_old.embed_content(
                                    model=_EMBED_MODEL,
                                    content=text,
                                )
                            return list(result['embedding'])
                        except Exception as e:
                            err_str = str(e)
                            is_quota = ('429' in err_str or 'Quota' in err_str or 'ResourceExhausted' in err_str)
                            if is_quota and attempt < max_retries - 1:
                                # Per-minute quota: must wait >60s for it to reset
                                wait = 65
                                logger.warning(
                                    "Embedding quota hit (attempt %d/%d). "
                                    "Waiting %ds for per-minute quota to reset...",
                                    attempt + 1, max_retries, wait
                                )
                                time.sleep(wait)
                            else:
                                raise

                def embed_documents(self, texts: list) -> list:
                    """Embeds multiple texts with rate-limit-aware delay between calls.
                    15s between calls = max 4 requests/min (safely under free tier quota).
                    """
                    import time
                    results = []
                    total = len(texts)
                    for i, t in enumerate(texts):
                        logger.info("Embedding chunk %d/%d...", i + 1, total)
                        results.append(self._embed(t))
                        if i < total - 1:
                            time.sleep(15)  # 15s gap = max 4 req/min (well under quota)
                    return results

                def embed_query(self, text: str) -> list:
                    return self._embed(text)

            _embeddings = _GoogleEmbeddings()
            # NOTE: No smoke test here — avoid quota hit on every server startup.
            # Embedding is validated on first real request instead.
            logger.info("Google Embeddings initialized. Model: %s", _EMBED_MODEL)
        except Exception as emb_err:
            logger.error("Google Embeddings initialization failed: %s", emb_err)
            raise
    return _embeddings

def get_vector_db(force_rebuild=False):
    global _vector_db

    # Fix: CHROMADB_DISABLED env flag — skip ChromaDB entirely and use PostgreSQL-only mode.
    # This makes all server workers stateless (no divergent in-process DBs) — enabling
    # horizontal scaling with multiple Gunicorn/uWSGI processes or Kubernetes pods.
    _chroma_disabled = os.getenv('CHROMADB_DISABLED', '').lower() in ('1', 'true', 'yes')
    if _chroma_disabled:
        raise RuntimeError("ChromaDB disabled via CHROMADB_DISABLED env flag — using PostgreSQL-only mode.")

    from langchain_chroma import Chroma
    embeddings = get_embeddings()
    if _vector_db is None or force_rebuild:
        if force_rebuild or not os.path.exists(chroma_path):
            if os.path.exists(qa_path):
                logger.info("Rebuilding Knowledge Base from chat-data.txt...")
                from langchain_core.documents import Document
                with open(qa_path, encoding='utf-8') as f:
                    content = f.read()
                docs = [Document(page_content=content, metadata={"source": qa_path})]

                from langchain_text_splitters import RecursiveCharacterTextSplitter
                splitter = RecursiveCharacterTextSplitter(
                    chunk_size=2000,   # Large chunks = fewer API calls (was 500 → 116 chunks)
                    chunk_overlap=100,
                    separators=["\n\n", "Q: ", "\nA: "]  # Fixed: removed duplicate \n\n
                )
                chunks = splitter.split_documents(docs)

                _vector_db = Chroma.from_documents(chunks, embeddings, persist_directory=chroma_path)
                with contextlib.suppress(AttributeError):
                    _vector_db.persist()
                logger.info(f"Knowledge Base built with {len(chunks)} fragments.")
        else:
            # Try loading existing DB; if incompatible (e.g. ChromaDB version mismatch), rebuild it
            try:
                logger.info("Connecting to existing ChromaDB...")
                _vector_db = Chroma(persist_directory=chroma_path, embedding_function=embeddings)
            except Exception as load_err:
                logger.warning(
                    f"ChromaDB load failed ({load_err}). Stale/incompatible DB detected — rebuilding..."
                )
                # BUG-11 (ChromaDB) fix: acquire in-process lock before deleting
                # and rebuilding ChromaDB so two concurrent workers cannot corrupt it.
                with _chroma_rebuild_lock:
                    # Re-check inside the lock: another worker may have already rebuilt
                    if _vector_db is not None and not force_rebuild:
                        logger.info("ChromaDB already rebuilt by another worker — skipping.")
                    else:
                        import shutil
                        shutil.rmtree(chroma_path, ignore_errors=True)
                        if os.path.exists(qa_path):
                            from langchain_core.documents import Document
                            with open(qa_path, encoding='utf-8') as f:
                                content = f.read()
                            docs = [Document(page_content=content, metadata={"source": qa_path})]

                            from langchain_text_splitters import (
                                RecursiveCharacterTextSplitter,
                            )
                            splitter = RecursiveCharacterTextSplitter(
                                chunk_size=500,
                                chunk_overlap=50,
                                separators=["\n\n", "Q: ", "\nA: "]  # BUG 3 fix: removed trailing duplicate \n\n
                            )
                            chunks = splitter.split_documents(docs)

                            _vector_db = Chroma.from_documents(chunks, embeddings, persist_directory=chroma_path)
                            with contextlib.suppress(AttributeError):
                                _vector_db.persist()
                            logger.info(f"Knowledge Base rebuilt with {len(chunks)} fragments.")


    # Safety guard: if vector_db is still None (both chroma_db and qa_path missing), raise clearly
    if _vector_db is None:
        raise RuntimeError(
            "ChromaDB could not be initialized: chat-data.txt not found and no existing chroma_db. "
            "Ensure chatbot/data/chat-data.txt exists and restart the server."
        )
    return _vector_db

def get_llm(model_name: str | None = None):
    global _llm, _llm_model_name
    if not model_name:
        model_name = DEFAULT_PRIMARY_MODEL
    # Invalidate cache if model name changed
    if _llm is not None and _llm_model_name != model_name:
        logger.info(f"Model changed from {_llm_model_name} to {model_name} — resetting LLM cache.")
        _llm = None
    if _llm is None:
        from langchain_google_genai import ChatGoogleGenerativeAI
        _llm = ChatGoogleGenerativeAI(
            model=model_name,
            temperature=0.2,
            api_key=get_current_gemini_api_key(),
            transport="rest",
        )
        _llm_model_name = model_name
        logger.info("Initialized LangChain LLM: %s", model_name)
    return _llm


def _fast_gemini_json(prompt: str, max_output_tokens: int = 8192) -> str:
    """Calls Gemini via the new google.genai SDK.
    Enforces response_mime_type='application/json' at the API level
    so the response is always valid JSON — no markdown fences, no truncation.
    Cascades automatically through GEMINI_CANDIDATE_MODELS (gemini-3.5-flash ->
    gemini-3.5-flash-lite -> ...) and supports API key rotation if configured.
    Retries transient per-minute rate limits with dynamic delay.
    """
    import time

    from google import genai
    from google.genai import types

    keys_count = max(1, len(_get_api_keys()))
    last_exc = None

    for key_attempt in range(keys_count):
        active_key = get_current_gemini_api_key()
        client = genai.Client(api_key=active_key)

        for model_name in GEMINI_CANDIDATE_MODELS:
            MAX_RETRIES = 2
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            temperature=0,
                            response_mime_type="application/json",
                            max_output_tokens=max_output_tokens,
                        ),
                    )

                    # Reconstruct full text from all parts to avoid truncation in response.text
                    try:
                        candidate = response.candidates[0]

                        # Check finish_reason at the API level — MAX_TOKENS means the response
                        # was cut off because we hit the token limit (guaranteed truncation).
                        finish_reason = getattr(candidate, "finish_reason", None)
                        if finish_reason is not None:
                            reason_str = str(finish_reason)
                            if "MAX_TOKENS" in reason_str or reason_str == "2":
                                raise ValueError(
                                    f"Gemini hit max_output_tokens ({max_output_tokens}) and "
                                    f"truncated the response (attempt {attempt}). "
                                    f"finish_reason={reason_str}"
                                )

                        full_text = "".join(
                            part.text for part in candidate.content.parts if hasattr(part, "text")
                        ).strip()
                    except ValueError:
                        raise  # Re-raise our own truncation errors
                    except (AttributeError, IndexError):
                        full_text = (response.text or "").strip()

                    if not full_text:
                        raise ValueError("Empty response from Gemini API")

                    # Early sanity check: detect obviously truncated JSON before returning
                    stripped = full_text.strip()
                    if stripped.startswith("{") and not stripped.endswith("}"):
                        raise ValueError(
                            f"Gemini returned truncated JSON (attempt {attempt}). "
                            f"Snippet: {stripped[:120]}"
                        )
                    if stripped.startswith("[") and not stripped.endswith("]"):
                        raise ValueError(
                            f"Gemini returned truncated JSON array (attempt {attempt}). "
                            f"Snippet: {stripped[:120]}"
                        )

                    return full_text

                except Exception as exc:
                    exc_str = str(exc)
                    last_exc = exc

                    is_rate_limit = (
                        "429" in exc_str or "RESOURCE_EXHAUSTED" in exc_str
                    )
                    is_unavailable = (
                        "503" in exc_str or "UNAVAILABLE" in exc_str
                    )
                    is_not_found = (
                        "404" in exc_str or "NOT_FOUND" in exc_str or "not supported" in exc_str.lower()
                    )
                    is_daily_limit = is_rate_limit and (
                        "PerDay" in exc_str or "GenerateRequestsPerDay" in exc_str or "daily quota" in exc_str.lower()
                    )
                    is_truncated = "truncated JSON" in exc_str

                    # If model hit daily quota, is not found, or is 503/high demand:
                    # Immediately cascade to next model! Do NOT sleep and retry an overloaded model!
                    if is_daily_limit or is_not_found or is_unavailable:
                        logger.warning(
                            f"Gemini model '{model_name}' high demand/unavailable/quota ({exc_str[:120]}). "
                            f"Immediately cascading to next candidate fallback model..."
                        )
                        break

                    if (is_rate_limit or is_truncated) and attempt < MAX_RETRIES:
                        actual_delay = None
                        import re as _re
                        m = _re.search(r"retry in (\d+(?:\.\d+)?)s", exc_str, _re.IGNORECASE)
                        if m:
                            actual_delay = min(int(float(m.group(1))) + 2, 30)

                        if actual_delay is None:
                            actual_delay = 5 * attempt

                        logger.warning(
                            f"Gemini API transient error on {model_name} "
                            f"(attempt {attempt}/{MAX_RETRIES}): {exc_str[:120]}. "
                            f"Retrying in {actual_delay}s..."
                        )
                        time.sleep(actual_delay)
                    else:
                        logger.warning(
                            f"Gemini model '{model_name}' failed after {attempt} attempt(s): {exc_str[:120]}. "
                            f"Cascading to next fallback model..."
                        )
                        break

        # If all models failed on the current key, try rotating API key if available
        if rotate_gemini_api_key():
            logger.warning("All models failed on previous key. Retrying with rotated Gemini API key...")
            continue
        else:
            break

    raise last_exc  # safety net


def _clean_json(raw: str) -> str:
    """Robustly extracts valid JSON from Gemini output.
    Handles markdown fences, leading/trailing text, and partial wrapping."""
    import re
    raw = raw.strip()

    # Step 1: Strip markdown code fences like ```json ... ``` or ``` ... ```
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]
    raw = raw.strip()

    # Step 2: If it already looks like valid JSON, return as-is
    if (raw.startswith("{") and raw.endswith("}")) or (raw.startswith("[") and raw.endswith("]")):
        return raw

    # Step 3: Extract first {...} block using regex (handles leading/trailing text)
    match = re.search(r'(\{.*\}|\[.*\])', raw, re.DOTALL)
    if match:
        return match.group(1).strip()

    # Step 4: Return as-is and let json.loads raise its own error
    return raw


def _safe_parse_json(content: str) -> dict | None:
    """Attempts to parse JSON with multiple fallback strategies.
    Returns parsed dict/list or None if all strategies fail."""
    # Strategy 1: Direct parse
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Strategy 2: Clean first then parse
    try:
        return json.loads(_clean_json(content))
    except (json.JSONDecodeError, Exception):
        pass

    # Strategy 3: Find just the JSON object with greedy regex
    import re
    match = re.search(r'\{[\s\S]*\}', content)
    if match:
        try:
            return json.loads(match.group(0))
        except (json.JSONDecodeError, Exception):
            pass

    # Strategy 4: Use ast.literal_eval (robust fallback for single-quoted JSON or Python dict representations)
    import ast
    try:
        cleaned = _clean_json(content)
        parsed = ast.literal_eval(cleaned)
        if isinstance(parsed, (dict, list)):
            return parsed
    except Exception:
        pass

    # Strategy 5: Try ast.literal_eval on the regex matched block
    if match:
        try:
            parsed = ast.literal_eval(match.group(0))
            if isinstance(parsed, (dict, list)):
                return parsed
        except Exception:
            pass

    logger.warning(f"All JSON parse strategies failed. Raw snippet: {content[:200]}")
    return None


def _sanitize_resume_text(text: str) -> str:
    """
    Cleans resume text before embedding in Gemini prompts.

    Guards against:
    - JSON corruption (quotes, backslashes)
    - Prompt injection (override keywords, SYSTEM: prefix, instruction phrases)
    - HTML/XML tag injection
    - Null bytes and excessive whitespace
    - Context overflow (hard 4500-char cap, leaving room for prompt structure)
    """
    import re
    import unicodedata

    if not text:
        return ''

    # 1. Normalise unicode to NFC (handles fancy quote variants etc.)
    text = unicodedata.normalize('NFC', text)

    # 2. Remove null bytes and control characters (except tab and newline)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', ' ', text)

    # 3. Strip HTML / XML tags — a resume should never contain markup
    text = re.sub(r'<[^>]{0,200}>', ' ', text)

    # 4. Neutralise prompt-injection override phrases (case-insensitive)
    _INJECTION_PATTERNS = [
        r'ignore\s+(all\s+)?(previous|above|prior)\s+instructions?',
        r'forget\s+(all\s+)?(previous|above|prior)\s+instructions?',
        r'you\s+are\s+now\s+(a|an)',
        r'act\s+as\s+(a|an)',
        r'disregard\s+(all\s+)?',
        r'new\s+instructions?:',
        r'system\s*:',
        r'assistant\s*:',
        r'### (instruction|prompt|system)',
        r'\[INST\]',
        r'<\|im_start\|>',
        r'<\|im_end\|>',
        r'jailbreak',
        r'do\s+anything\s+now',
        r'dan\s+mode',
    ]
    for pattern in _INJECTION_PATTERNS:
        text = re.sub(pattern, '[REMOVED]', text, flags=re.IGNORECASE)

    # 5. Replace JSON-breaking characters
    text = text.replace('\\', ' ')    # backslashes corrupt JSON generation
    text = text.replace('"', "'")     # double quotes → single quotes
    text = text.replace('\r', ' ')    # carriage returns

    # 6. Collapse 3+ blank lines to a single blank line
    text = re.sub(r'\n{3,}', '\n\n', text)

    # 7. Collapse excessive whitespace on a single line
    text = re.sub(r' {3,}', '  ', text)

    # 8. Hard character cap — prevents context overflow attacks
    text = text[:4500]

    return text.strip()


# ================= CHATBOT RAG =================


def gemini_response(message: str, user_name="User", conversation_history=None) -> str:
    """Uses ChromaDB context to answer user questions about Zensar technologies.
    conversation_history: list of {"role": "user"|"bot", "content": str} dicts (last 5 turns)
    """
    user_msg = message.lower().strip()

    # 1. FAST PATH: Check for very common greetings to respond instantly
    greetings = {
        "hi": f"Hello {user_name}! Welcome to Zensar technologies. How can I help you?",
        "hello": "Hi there! I'm your Zensar virtual assistant. How can I assist you today?",
        "hey": f"Hey {user_name}! Welcome to Zensar. What can I do for you?",
        "good morning": "Good morning! How can I assist you today?",
        "good evening": "Good evening! How may I help you?",
    }
    if user_msg in greetings:
        return greetings[user_msg]

    try:
        # 2. Knowledge injection directly from PostgreSQL (instant, multi-server ready, no ChromaDB locks)
        try:
            from chatbot.models import JobPosting, KnowledgeBaseItem
            openings = JobPosting.objects.filter(is_active=True)
            jobs_summary = "\n".join([f"- {j.title} ({j.get_job_type_display()} in {j.department}, {j.location}) | Skills: {j.skills or 'General'}" for j in openings])
            qa_records = KnowledgeBaseItem.objects.filter(is_active=True)[:60]
            qa_summary = "\n".join([f"Q: {q.question}\nA: {q.answer}" for q in qa_records])
            context = f"CURRENT COMPANY OPENINGS (PostgreSQL):\n{jobs_summary}\n\nKNOWLEDGE BASE FAQS (PostgreSQL):\n{qa_summary}"
        except Exception as db_err:
            logger.warning(f"PostgreSQL knowledge retrieval fallback: {db_err}")
            try:
                with open(qa_path, encoding='utf-8') as f:
                    context = f.read(8000)
            except FileNotFoundError:
                context = "Zensar Technologies recruitment assistant."

        # 3. Build conversation history string (last 5 turns for memory)
        history_str = ""
        if conversation_history:
            recent = conversation_history[-5:]  # Keep last 5 exchanges only
            history_lines = []
            for turn in recent:
                role = turn.get("role", "user")
                content = turn.get("content", "").strip()
                if role == "user":
                    history_lines.append(f"User: {content}")
                else:
                    history_lines.append(f"ZenBot: {content}")
            if history_lines:
                history_str = "\nCONVERSATION HISTORY (for context):\n" + "\n".join(history_lines) + "\n"

        from langchain_core.prompts import PromptTemplate
        prompt_template = """You are the official ZenBot, a senior AI recruitment assistant for Zensar Technologies.
Your goal is to provide accurate, helpful, and welcoming information to applicants and employees.

HEADQUARTERS & CORPORATE LOCATIONS:
- Global Headquarters: Pune, Maharashtra, India.
- Major Technology Innovation Centers in Chennai (2 Campuses):
  1. Chennai - OMR Tech Park (Software & Full Stack Engineering)
  2. Chennai - DLF Cybercity / IT Park (AI, Cloud & Data Science)
- Additional Regional Hubs: Bengaluru (Karnataka), Hyderabad (Telangana), Mumbai (Maharashtra).
- Work Mode: Onsite / Hybrid at designated campuses, plus Remote (Pan-India) for select engineering & AI roles.

USER NAME: {user_name}

KNOWLEDGE BASE (Priority Source):
{context}
{history}
STRICT INSTRUCTIONS:
1. Use the KNOWLEDGE BASE above as your primary source of truth.
2. When a user asks about jobs, internships, vacancies, or where the company is located:
   - Always state clearly that the company is headquartered in Pune, Maharashtra, with 2 major tech campuses in Chennai (OMR & DLF IT Park), plus offices in Bengaluru, Hyderabad, and Pan-India Remote options.
   - For ANY job or internship role mentioned, you MUST explicitly tell the user WHERE that vacancy is located (City, State, or Campus) BEFORE or alongside giving the application link!
3. If the user asks to apply or inquires about a specific role, provide the application link with the work location:
   "Great! You can apply for the [Role Name] role (Location: [Role Location]) here: [Apply Now](/apply-job/?role=[Encoded Role Name])" (or /apply-internship/ for internships)
4. Keep your answer professional, helpful, accurate, and concise.

QUESTION: {message}
ZENBOT ANSWER:"""

        prompt = PromptTemplate(template=prompt_template, input_variables=["context", "message", "user_name", "history"])
        llm = get_llm()
        chain = prompt | llm

        response = chain.invoke({
            "context": context,
            "message": message,
            "user_name": user_name,
            "history": history_str,
        })

        return response.content.strip()
    except Exception as e:
        logger.warning(f"Gemini API rate-limit/connection issue ({e}). Activating Zero-Downtime PostgreSQL Fallback...")
        fallback_answer = _fallback_postgresql_search(message, user_name)
        if fallback_answer:
            return fallback_answer

        careers_email = getattr(settings, 'COMPANY_CAREERS_EMAIL', 'hr@zensar.com')
        return f"Hello {user_name}! We are experiencing high traffic. For immediate assistance with recruitment and applications, please contact {careers_email}."


def gemini_response_stream(message: str, user_name="User", conversation_history=None):
    """
    Streaming version of gemini_response using Gemini's native generate_content_stream().
    Yields text chunks as they arrive — enables real-time typing effect via SSE.
    No Django Channels or WebSocket required — works with plain Django StreamingHttpResponse.

    Usage in views:
        from django.http import StreamingHttpResponse
        def stream_view(request):
            def sse():
                for chunk in ai_engine.gemini_response_stream(msg, user_name):
                    yield f"data: {json.dumps({'chunk': chunk})}\\n\\n"
                yield "data: {\"done\": true}\\n\\n"
            return StreamingHttpResponse(sse(), content_type='text/event-stream')
    """
    from google import genai
    from google.genai import types

    user_msg = message.lower().strip()

    # Fast-path greetings: stream the whole thing in one shot
    greetings = {
        "hi": f"Hello {user_name}! Welcome to Zensar technologies. How can I help you?",
        "hello": "Hi there! I'm your Zensar virtual assistant. How can I assist you today?",
        "hey": f"Hey {user_name}! Welcome to Zensar. What can I do for you?",
        "good morning": "Good morning! How can I assist you today?",
        "good evening": "Good evening! How may I help you?",
    }
    if user_msg in greetings:
        yield greetings[user_msg]
        return

    # Build context from PostgreSQL (same as non-streaming path)
    try:
        from chatbot.models import JobPosting, KnowledgeBaseItem
        openings = JobPosting.objects.filter(is_active=True)
        jobs_summary = "\n".join([
            f"- {j.title} ({j.get_job_type_display()} in {j.department}, {j.location}) | Skills: {j.skills or 'General'}"
            for j in openings
        ])
        qa_records = KnowledgeBaseItem.objects.filter(is_active=True)[:60]
        qa_summary = "\n".join([f"Q: {q.question}\nA: {q.answer}" for q in qa_records])
        context = f"CURRENT COMPANY OPENINGS:\n{jobs_summary}\n\nKNOWLEDGE BASE:\n{qa_summary}"
    except Exception:
        context = "Zensar Technologies recruitment assistant."

    # Build conversation history string
    history_str = ""
    if conversation_history:
        recent = conversation_history[-5:]
        lines = []
        for turn in recent:
            role = turn.get("role", "user")
            content = turn.get("content", "").strip()
            lines.append(f"{'User' if role == 'user' else 'ZenBot'}: {content}")
        if lines:
            history_str = "\nCONVERSATION HISTORY:\n" + "\n".join(lines) + "\n"

    prompt = f"""You are ZenBot, the official AI recruitment assistant for Zensar Technologies.

HEADQUARTERS: Pune, Maharashtra. Major tech campuses in Chennai (OMR & DLF IT Park), plus Bengaluru, Hyderabad.

USER NAME: {user_name}

KNOWLEDGE BASE:
{context}
{history_str}
INSTRUCTIONS:
1. Use the KNOWLEDGE BASE as your primary source of truth.
2. For job/internship queries, always mention WHERE the vacancy is located.
3. Provide the application link: /apply-job/?role=... or /apply-internship/?role=...
4. Be professional, helpful, accurate, and concise.

QUESTION: {message}
ZENBOT ANSWER:"""

    try:
        client = genai.Client(api_key=get_current_gemini_api_key())
        stream = client.models.generate_content_stream(
            model=DEFAULT_PRIMARY_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=2000,
            ),
        )
        for chunk in stream:
            if chunk.text:
                yield chunk.text
    except Exception as e:
        logger.warning(f"Streaming Gemini error: {e} — falling back to PostgreSQL search")
        fallback = _fallback_postgresql_search(message, user_name)
        if fallback:
            yield fallback
        else:
            careers_email = getattr(settings, 'COMPANY_CAREERS_EMAIL', 'hr@zensar.com')
            yield f"Hello {user_name}! We are experiencing high traffic. Please contact {careers_email} for immediate assistance."


def _fallback_postgresql_search(query: str, user_name: str = "User") -> str | None:
    """Zero-downtime offline & rate-limit fallback: searches PostgreSQL KnowledgeBaseItem directly."""
    try:
        from django.db.models import Q

        from chatbot.models import JobPosting, KnowledgeBaseItem

        q_clean = query.lower().strip()
        words = [w for w in re.split(r'\W+', q_clean) if len(w) > 2]

        # 1. Check if user is asking about active jobs or internships
        if any(w in q_clean for w in ['job', 'intern', 'opening', 'role', 'vacanc', 'hire', 'hiring']):
            openings = JobPosting.objects.filter(is_active=True)
            if openings.exists():
                lines = [f"• {j.title} ({j.get_job_type_display()} in {j.department}, {j.location})" for j in openings]
                return f"Hello {user_name}! Here are our current active openings:\n" + "\n".join(lines) + "\n\nYou can apply directly under the application tabs!"

        # 2. Check for exact question match
        exact = KnowledgeBaseItem.objects.filter(is_active=True, question__iexact=q_clean).first()
        if exact:
            return exact.answer

        # 3. Match across question words
        if words:
            query_filter = Q()
            for w in words[:4]:
                query_filter |= Q(question__icontains=w) | Q(answer__icontains=w)
            match = KnowledgeBaseItem.objects.filter(is_active=True).filter(query_filter).first()
            if match:
                return match.answer

    except Exception as err:
        logger.warning(f"PostgreSQL fallback query failed: {err}")
    return None


# ================= RESUME MATCHING AND VALIDATION =================


def _get_personalized_roles(resume_text: str, openings: list, is_intern: bool) -> list:
    """
    Ranks available job openings against the candidate's actual resume (skills, degree, domain)
    so candidates receive personalized matching roles (e.g. Commerce -> Finance/Business/Data Analyst,
    Frontend -> React, Testing -> QA, Cloud -> DevOps, Mobile -> Mobile App, AI -> AI/ML).
    Ensures candidates never receive one-size-fits-all generic roles.
    """
    import re
    text = (resume_text or '').lower()

    # Domain indicators with associated weight keywords and custom reasons
    domain_profiles = {
        "software_engineer": {
            "keywords": ["software engineer", "software engineering", "data structures", "algorithms", "dsa", "c++", "problem solving", "oop", "system design", "coding", "software developer", "c/c++"],
            "target_roles": ["Software Engineer", "Software Engineering Intern", "Full Stack Developer", "Backend Developer Intern"],
            "default_reason": "Core Software Engineering & DSA"
        },
        "java_backend": {
            "keywords": ["java", "spring", "spring boot", "hibernate", "microservices", "maven", "jdbc", "jpa", "j2ee"],
            "target_roles": ["Java Backend Developer", "Java Developer Intern", "Backend Developer Intern"],
            "default_reason": "Java & Backend Engineering fit"
        },
        "junior_ai": {
            "keywords": ["prompt engineering", "langchain", "gemini", "openai", "vector db", "genai", "generative ai", "rag", "agents", "llm"],
            "target_roles": ["Junior AI Developer", "AI / ML Engineer", "AI / ML Developer Intern"],
            "default_reason": "Generative AI & LLM development fit"
        },
        "ai_ml": {
            "keywords": ["machine learning", "deep learning", "nlp", "pytorch", "tensorflow", "ai", "llm",
                         "computer vision", "transformers", "scikit-learn", "data science"],
            "target_roles": ["AI / ML Engineer", "AI / ML Developer Intern", "Junior AI Developer"],
            "default_reason": "AI, ML & NLP skillset fit"
        },
        "fullstack": {
            "keywords": ["python", "django", "react", "full stack", "fullstack", "postgresql", "rest api", "javascript"],
            "target_roles": ["Full Stack Developer", "Python Developer Intern", "Frontend Developer Intern", "Backend Developer Intern"],
            "default_reason": "Full Stack engineering fit"
        },
        "python_developer": {
            "keywords": ["python", "django", "flask", "fastapi", "sqlite", "oop", "backend"],
            "target_roles": ["Python Developer Intern", "Full Stack Developer", "Backend Developer Intern"],
            "default_reason": "Python software development"
        },
        "backend_developer": {
            "keywords": ["backend", "node.js", "express", "apis", "server", "microservices", "sql", "database"],
            "target_roles": ["Backend Developer Intern", "Java Backend Developer", "Full Stack Developer"],
            "default_reason": "Backend API & Server-side architecture"
        },
        "frontend_developer": {
            "keywords": ["react", "frontend", "front-end", "javascript", "html", "css", "html5", "css3", "tailwind"],
            "target_roles": ["Frontend Developer Intern", "Full Stack Developer"],
            "default_reason": "Modern Frontend & UI engineering"
        },
        "cloud_devops": {
            "keywords": ["aws", "azure", "docker", "kubernetes", "terraform", "devops", "ci/cd", "jenkins",
                         "cloud", "linux", "infrastructure", "bash", "shell scripting"],
            "target_roles": ["Cloud & DevOps Engineer", "Cloud / DevOps Intern", "QA Automation Engineer"],
            "default_reason": "Cloud Infrastructure & DevOps"
        },
        "qa_testing": {
            "keywords": [
                "qa", "testing", "selenium", "tosca", "test cases", "manual testing", "automation testing",
                "test plan", "jira", "regression", "api testing", "postman", "defect", "junit", "cypress",
                "playwright", "appium", "mobile testing", "mobile app testing", "application testing",
                "ai-led testing", "ai testing", "autonomous testing", "quality engineer", "quality engineering",
                "test automation", "smartui", "self-healing test", "restassured"
            ],
            "target_roles": [
                "Quality Engineer (Automation, Mobile & AI-Led Testing)",
                "QA Automation Engineer",
                "Quality Engineering & Testing Intern",
                "Backend Developer Intern",
                "Java Developer Intern"
            ],
            "default_reason": "Automation, Mobile, App & AI-Led Testing fit"
        },
        "finance_commerce": {
            "keywords": ["b.com", "bcom", "m.com", "finance", "accounting", "accounts", "payable", "receivable",
                         "payroll", "tally", "audit", "auditing", "taxation", "balance sheet", "general ledger", "financial"],
            "target_roles": ["Finance & Accounts Executive", "Business Analyst (BFSI & Retail)", "Data Analyst / BI Specialist"],
            "default_reason": "Accounting & Finance background"
        },
        "business_analyst": {
            "keywords": ["business analyst", "requirements gathering", "process mapping", "bba", "mba", "bfsi",
                         "retail domain", "user stories", "agile", "stakeholder", "gap analysis", "functional specification"],
            "target_roles": ["Business Analyst (BFSI & Retail)", "Data Analyst / BI Specialist", "Finance & Accounts Executive"],
            "default_reason": "Business & Domain analysis fit"
        },
        "data_analytics": {
            "keywords": ["power bi", "tableau", "sql", "excel", "data analysis", "data analyst", "bi specialist",
                         "data modeling", "dax", "visualization", "kpi", "reporting", "pandas", "numpy"],
            "target_roles": ["Data Analyst / BI Specialist", "Business Analyst (BFSI & Retail)", "Cloud & DevOps Engineer"],
            "default_reason": "Data Analytics & BI skills"
        },
    }

    scored_openings = []
    for op in openings:
        score = 1
        reasons = []
        op_title_lower = op.title.lower()

        # Check domain affinities
        for d_info in domain_profiles.values():
            kw_hits = [kw for kw in d_info["keywords"] if kw in text]
            if kw_hits and any(tr.lower() in op_title_lower for tr in d_info["target_roles"]):
                score += len(kw_hits) * 3
                reasons.append(d_info["default_reason"])

        # Check direct skill matches from op.skills
        if op.skills:
            for s in op.skills.split(','):
                s_clean = s.strip().lower()
                if len(s_clean) > 2 and s_clean in text:
                    score += 2

        # Check title word matches
        for word in re.split(r'\W+', op_title_lower):
            if len(word) > 3 and word in text:
                score += 1

        primary_reason = reasons[0] if reasons else "Relevant background match"
        scored_openings.append({
            "role": op.title,
            "reason": primary_reason,
            "location": op.location,
            "vacancies": getattr(op, "vacancies", 5),
            "experience": getattr(op, "experience", "0-2 Years"),
            "is_internship": is_intern,
            "score": score,
        })

    scored_openings.sort(key=lambda x: x["score"], reverse=True)

    picked = []
    used_titles = set()

    for o in scored_openings:
        if len(picked) >= 3:
            break
        t_key = o["role"].lower()
        if t_key in used_titles:
            continue
        picked.append(o)
        used_titles.add(t_key)

    return [{
        "role": p["role"],
        "reason": p["reason"][:40],
        "location": p["location"],
        "vacancies": p.get("vacancies", 5),
        "experience": p.get("experience", "0-2 Years"),
        "is_internship": is_intern
    } for p in picked[:3]]


def suggest_roles_from_resume(resume_text: str, user_name="User", requested_type="job", requested_location=None) -> str:
    """
    Stage 1: Analyzes resume and suggests matching roles from Zensar active job openings.
    Ensures personalized matching: Commerce resumes get Finance/Business/Data Analyst,
    Tech resumes get Frontend/Python/DevOps/AI/QA/Mobile/Design based on their background.
    """
    if not resume_text:
        return '{"error": "Empty resume content."}'

    try:
        from chatbot.models import JobPosting
        db_type = 'internship' if requested_type == 'intern' else 'job'
        openings = list(JobPosting.objects.filter(is_active=True, job_type=db_type))
        vacancies_context = "\n".join([
            f"- Role: {j.title} | Location: {j.location} | Dept: {j.department} | Skills: {j.skills or 'General'} | {j.experience}"
            for j in openings
        ])
    except Exception as ctx_err:
        logger.warning(f"Could not load PostgreSQL postings: {ctx_err}")
        openings = []
        vacancies_context = "- Full Stack Python Developer | Location: Chennai, Tamil Nadu (OMR Tech Park)"

    is_intern = (requested_type == 'intern')

    # Pre-rank available openings to create a personalized fallback pool matching THIS specific candidate
    tailored_pool = _get_personalized_roles(resume_text, openings, is_intern)

    # Sanitize resume text before embedding in prompt to prevent JSON corruption
    safe_resume = _sanitize_resume_text(resume_text[:5000])

    role_type = "Internship" if requested_type == "intern" else "Full-Time Job"

    prompt = f"""Zensar Technologies recruitment AI. Analyze resume for "{user_name}".
Target Role Type: {role_type}

AVAILABLE ZENSAR {role_type.upper()} VACANCIES:
{vacancies_context}

RESUME:
{safe_resume}

If NOT a resume, return: {{"is_resume": false, "error": "This is not a resume, upload your resume."}}
Otherwise classify as 'Fresher' (0-1 yrs) or 'Experienced' (2+ yrs) and suggest EXACTLY 3 matching Zensar {role_type} roles from the available vacancies.

CANDIDATE BACKGROUND MATCHING RULES (CRITICAL):
- Carefully inspect the candidate's degree, certifications, and technical/business skills.
- SOFTWARE ENGINEERS & CORE CODING (Data Structures, Algorithms, C++, Java/Python, Problem Solving, Software Engineering): Strongly recommend 'Software Engineer' or 'Software Engineering Intern' or 'Full Stack Developer'.
- JAVA & BACKEND DEVELOPERS (Java, Spring Boot, Microservices, Hibernate, JDBC): Strongly recommend 'Java Backend Developer' or 'Java Developer Intern' or 'Backend Developer Intern'.
- JUNIOR AI & PROMPT ENGINEERS (Python, Prompt Engineering, LangChain, GenAI, APIs): Strongly recommend 'Junior AI Developer' or 'AI / ML Engineer' or 'AI / ML Developer Intern'.
- AI / ML & DATA SCIENCE CANDIDATES (Machine Learning, PyTorch, TensorFlow, NLP, LLMs): Strongly recommend 'AI / ML Engineer' or 'AI / ML Developer Intern'.
- FULL STACK DEVELOPERS (Python, React, Django, Full Stack, Web): Strongly recommend 'Full Stack Developer' or 'Python Developer Intern' or 'Frontend Developer Intern'.
- FRONTEND DEVELOPERS (React, JavaScript, HTML, CSS, Redux): Strongly recommend 'Frontend Developer Intern' or 'Full Stack Developer'.
- BACKEND DEVELOPERS (Node.js, Python, APIs, SQL, Server architecture): Strongly recommend 'Backend Developer Intern' or 'Java Backend Developer'.
- COMMERCE / FINANCE CANDIDATES (B.Com, M.Com, Accounting, Finance, Tally, Audit, Excel): Strongly recommend 'Finance & Accounts Executive', 'Business Analyst (BFSI & Retail)', or 'Data Analyst / BI Specialist'.
- BUSINESS & MANAGEMENT CANDIDATES (BBA, MBA, Agile, Requirements): Strongly recommend 'Business Analyst (BFSI & Retail)' or 'Data Analyst / BI Specialist'.
- TESTING, QA, AUTOMATION, MOBILE & AI-LED TESTING CANDIDATES (Selenium, Appium, Cypress, Playwright, Mobile App Testing, API Testing, AI-Led Testing, Autonomous Testing, JIRA): Strongly recommend 'Quality Engineer (Automation, Mobile & AI-Led Testing)' or 'QA Automation Engineer' or 'Quality Engineering & Testing Intern'.
- CLOUD & DEVOPS CANDIDATES (AWS, Docker, Kubernetes, CI/CD, Linux): Strongly recommend 'Cloud & DevOps Engineer' or 'Cloud / DevOps Intern'.
- DO NOT assign the same default roles to every candidate. The roles suggested MUST directly match the candidate's actual resume skills and educational background.

ROLE RECOMMENDATION RULES:
- You MUST return EXACTLY 3 distinct roles in the "suggested_roles" array, ordered by strongest skill match first.
- The 3 roles MUST be chosen from the AVAILABLE ZENSAR VACANCIES listed above, with their exact official locations as provided.
- Any campus or state location is completely acceptable (Pune, Chennai, Bengaluru, Hyderabad). Prioritize the best skill match first!
- Set "is_internship" to {'true' if requested_type == 'intern' else 'false'} for all suggested roles.

Return ONLY this JSON (reason must be 5 words or fewer — be concise):
{{"is_resume": true, "experience_level": "Fresher/Experienced", "suggested_roles": [
    {{"role": "Role Name 1", "reason": "brief match reason", "location": "Exact Location From Vacancy List", "is_internship": true/false}},
    {{"role": "Role Name 2", "reason": "brief match reason", "location": "Exact Location From Vacancy List", "is_internship": true/false}},
    {{"role": "Role Name 3", "reason": "brief match reason", "location": "Exact Location From Vacancy List", "is_internship": true/false}}
]}}
"""
    try:
        content = _fast_gemini_json(prompt)
        parsed = _safe_parse_json(content)
        if parsed is not None:
            if "suggested_roles" not in parsed:
                parsed["suggested_roles"] = []
            if "is_resume" not in parsed:
                parsed["is_resume"] = True
            if "experience_level" not in parsed or not parsed["experience_level"]:
                parsed["experience_level"] = "Fresher"

            roles = parsed.get("suggested_roles", [])

            # Deduplicate by title
            existing_roles = set()
            unique_roles = []
            for r in roles:
                if isinstance(r, dict) and r.get("role"):
                    t_key = r["role"].strip().lower()
                    if t_key not in existing_roles:
                        existing_roles.add(t_key)
                        unique_roles.append(r)
            roles = unique_roles

            # Supplement from tailored pool (NOT a generic static list) to ensure 3 distinct roles
            for fallback_r in tailored_pool:
                if len(roles) >= 3:
                    break
                t_key = fallback_r["role"].strip().lower()
                if t_key not in existing_roles:
                    roles.append(dict(fallback_r))
                    existing_roles.add(t_key)

            roles = roles[:3]

            # Enforce at least 1 Chennai location
            has_chennai = any('chennai' in r.get('location', '').lower() for r in roles)
            if not has_chennai and tailored_pool:
                chennai_fallback = next((tp for tp in tailored_pool if 'chennai' in tp['location'].lower()), None)
                if chennai_fallback:
                    roles[0]["location"] = chennai_fallback["location"]

            for r in roles:
                r["is_internship"] = is_intern
                matched_job = next((op for op in openings if op.title.strip().lower() == r.get("role", "").strip().lower()), None)
                if not matched_job:
                    matched_job = next((op for op in openings if op.title.strip().lower() in r.get("role", "").strip().lower() or r.get("role", "").strip().lower() in op.title.strip().lower()), None)
                if matched_job:
                    r["vacancies"] = getattr(matched_job, "vacancies", 5)
                    r["experience"] = getattr(matched_job, "experience", "0-2 Years")
                    r["location"] = matched_job.location
                else:
                    r["vacancies"] = r.get("vacancies", 5)
                    r["experience"] = r.get("experience", "Fresher / 0-2 Years")

            parsed["suggested_roles"] = roles
            return json.dumps(parsed)
        raise ValueError("JSON parse failed after all strategies")
    except Exception as e:
        logger.error(f"Role Suggestion Error: {e}")
        # Always return tailored personalized roles rather than generic defaults
        return json.dumps({
            "is_resume": True,
            "experience_level": "Fresher",
            "suggested_roles": tailored_pool
        })
def check_resume_match(resume_text: str, user_name="User", category="Job", role="Not specified", is_internship=False, location="Chennai") -> str:
    """Uses Gemini to extract structured JSON data about the resume fit for ANY role, focusing on Zensar context and single location."""
    if not resume_text:
        return '{"error": "Could not extract text from PDF."}'

    # Fetch authoritative context from PostgreSQL (JobPostings & KnowledgeBaseItems)
    # BUG 4 fix: use Django cache with 10-min TTL instead of permanent module-level global
    _CONTEXT_CACHE_KEY = 'zensar_role_match_context'
    zensar_role_context = cache.get(_CONTEXT_CACHE_KEY)
    if zensar_role_context is None:
        try:
            from chatbot.models import JobPosting, KnowledgeBaseItem
            postings = JobPosting.objects.filter(is_active=True)
            posting_lines = [
                f"- Role: {p.title} ({p.get_job_type_display()}) | Location: {p.location} | Dept: {p.department} | Exp: {p.experience} | Skills: {p.skills or 'General'} | Details: {p.description or 'N/A'}"
                for p in postings
            ]
            policies = KnowledgeBaseItem.objects.filter(is_active=True, category__in=['Recruitment', 'Internship', 'Technical Roles'])[:30]
            policy_lines = [f"Q: {k.question}\nA: {k.answer}" for k in policies]
            zensar_role_context = "COMPANY OPENINGS (PostgreSQL):\n" + "\n".join(posting_lines) + "\n\nRECRUITMENT POLICIES:\n" + "\n".join(policy_lines)
            cache.set(_CONTEXT_CACHE_KEY, zensar_role_context, timeout=600)  # 10-minute TTL
            logger.info("Loaded role match context from PostgreSQL and stored in cache.")
        except Exception as ctx_err:
            logger.warning(f"Could not load context from PostgreSQL: {ctx_err}")
            if os.path.exists(qa_path):
                with open(qa_path, encoding='utf-8') as f:
                    zensar_role_context = f.read(5000)
            else:
                zensar_role_context = "Zensar Technologies offers roles in Python/Django, Cloud, Data Science, and AI/ML."
            # Don't cache fallback text — retry DB on next call
    else:
        logger.debug("Role match context served from Django cache.")

    # Sanitize resume text before embedding in prompt
    safe_resume = _sanitize_resume_text(resume_text[:5000])

    loc_lower = str(location or "").lower()
    if "chennai" in loc_lower:
        norm_loc = "Chennai"
    elif "pune" in loc_lower:
        norm_loc = "Pune"
    elif "bengaluru" in loc_lower or "bangalore" in loc_lower:
        norm_loc = "Bengaluru"
    elif "hyderabad" in loc_lower:
        norm_loc = "Hyderabad"
    else:
        norm_loc = "Chennai"

    if is_internship:
        prompt = f"""Zensar Technologies Campus Recruitment AI. Analyze "{user_name}"'s resume specifically for an INTERNSHIP role: "{role}".
Location: {norm_loc}

ZENSAR RECRUITMENT & INTERNSHIP ELIGIBILITY CONTEXT:
- Zensar Internship eligibility: Candidates pursuing or completed B.E / B.Tech / BCA / MCA / B.Sc / relevant degree with 60% or 6.0+ CGPA.
{zensar_role_context}

CANDIDATE RESUME:
{safe_resume}

INTERNSHIP 4-PILLAR EVALUATION INSTRUCTIONS:
Since this is an INTERNSHIP candidate (student / fresher), do NOT penalize for lack of full-time work experience. Instead, evaluate the candidate across these 4 dimensions:

1. TECHNICAL & CORE SKILLS (Weight: 35%):
   - Compare candidate's technical/programming skills with this internship role "{role}".
   - skills_score: 0-100.
   - matching_skills: max 6 matching skills found in resume.
   - missing_skills: max 6 key missing/foundational skills for this role.

2. COLLEGE, DEGREE & CGPA ACADEMIC STANDING (Weight: 25%):
   - Extract college/university name, degree, department/branch, and CGPA or percentage marks.
   - academics_score: 0-100 (If CGPA >= 8.0 or >= 80%: score 85-95; if CGPA 6.5-8.0 or 65-80%: score 75-84; if CGPA 6.0-6.5 or 60-65%: score 65-74; if < 60% or not specified: score 50-60).
   - college_name: name of candidate's college / university extracted from resume.
   - degree_branch: candidate's degree and stream (e.g., "B.Tech - Computer Science").
   - cgpa: candidate's CGPA or percentage extracted from resume (e.g., "8.2 CGPA" or "78%").
   - academics_summary: 1 concise sentence evaluating academic standing against Zensar criteria.

3. PROJECTS & PRACTICAL ASSIGNMENTS (Weight: 25%):
   - Evaluate academic, capstone, mini-projects, hackathons, or personal projects in resume.
   - projects_score: 0-100 (if relevant projects present: 75-95; if minimal/basic: 45-65; if none: 25-40).
   - projects_analyzed: list of up to 3 relevant projects (each with "title", "tech_stack", "relevance": "High/Medium/Low", "description": 1 concise sentence).
   - projects_summary: 1 concise sentence evaluating practical project strength.

4. CERTIFICATIONS & WORKSHOPS (Weight: 15%):
   - Identify online courses, certifications, workshops, or training (Coursera, Udemy, NPTEL, HackerRank, AWS, etc.).
   - certifications_score: 0-100 (if relevant certs: 75-95; if none: 25-45).
   - certifications_found: list of up to 4 certifications detected in resume.
   - certifications_recommended: list of 1-3 specific recognized certifications to help them stand out for this internship.

5. OVERALL INTERNSHIP MATCH SCORE:
   - score = round((0.35 * skills_score) + (0.25 * academics_score) + (0.25 * projects_score) + (0.15 * certifications_score))

6. PROFILE & ZENSAR AVAILABILITY:
   - profile_type: "Technical", "Partially Technical", or "Non-Technical".
   - is_role_available: "Yes", "Maybe", or "No".
   - availability_reason: 1 concise sentence explaining vacancy match.
   - suggestions: 3 actionable, personalized tips for a student/intern to increase selection probability.

Return ONLY valid JSON matching this schema:
{{
  "candidate_name": "{user_name}",
  "role_identified": "{role}",
  "is_internship": true,
  "score": 0,
  "skills_score": 0,
  "academics_score": 0,
  "projects_score": 0,
  "certifications_score": 0,
  "college_name": "College Name",
  "degree_branch": "Degree and Branch",
  "cgpa": "CGPA / Percentage",
  "academics_summary": "Academic standing assessment",
  "is_role_available": "Yes/No/Maybe",
  "availability_reason": "Reason based on context",
  "profile_type": "Technical/Non-Technical/Partially Technical",
  "matching_skills": ["Skill 1", "Skill 2"],
  "missing_skills": ["Skill 3", "Skill 4"],
  "projects_analyzed": [
    {{"title": "Project Title", "tech_stack": "Tech used", "relevance": "High/Medium/Low", "description": "Brief note"}}
  ],
  "projects_summary": "Summary of project strength",
  "certifications_found": ["Cert 1"],
  "certifications_recommended": ["Recommended Cert 1", "Recommended Cert 2"],
  "suggestions": ["Tip 1", "Tip 2", "Tip 3"]
}}
"""
    else:
        prompt = f"""Zensar Technologies HR AI. Analyze "{user_name}"'s resume for Full-Time Job role: "{role}".
Location: {norm_loc}

ZENSAR RECRUITMENT & VACANCY CONTEXT:
{zensar_role_context}

CANDIDATE RESUME:
{safe_resume}

COMPREHENSIVE 4-PILLAR EVALUATION INSTRUCTIONS:
Evaluate the candidate's resume across ALL 4 pillars specifically for the target Full-Time Job role "{role}":

1. TECHNICAL & DOMAIN SKILLS (Weight: 35%):
   - Compare technical/functional skills from resume with requirements for this role.
   - skills_score: 0-100.
   - matching_skills: max 6 exact matching skills found.
   - missing_skills: max 6 key missing/required skills for this role.

2. PROJECTS & PRACTICAL IMPLEMENTATION (Weight: 25%):
   - Evaluate academic, personal, open-source, or live projects in the resume.
   - projects_score: 0-100 (if no projects: 20-40; if highly relevant: 80-95).
   - projects_analyzed: list of up to 3 most relevant projects found (each with "title", "tech_stack", "relevance": "High/Medium/Low", "description": 1 concise sentence).
   - projects_summary: 1 concise sentence evaluating the candidate's practical project strength.

3. INTERNSHIPS & WORK EXPERIENCE (Weight: 25%):
   - Evaluate prior internships, trainee roles, full-time/part-time jobs, or practical work exposure.
   - experience_score: 0-100 (for freshers with no internships, evaluate academic lab/course exposure fairly between 30-55; for relevant intern/work exp score 75-95).
   - experience_details: list of up to 3 relevant internships or roles found (each with "role", "company", "duration", "relevance": "High/Medium/Low").
   - experience_summary: 1 concise sentence summarizing internship/work experience fit.

4. CERTIFICATIONS & CREDENTIALS (Weight: 15%):
   - Identify recognized certifications, online specializations (Coursera, Udemy, AWS, Azure, NPTEL, Oracle, HackerRank, etc.).
   - certifications_score: 0-100 (if no certifications detected: 25-45; if relevant certs present: 75-95).
   - certifications_found: list of up to 4 certifications detected in resume.
   - certifications_recommended: list of 1-3 specific recognized certifications to bridge gaps for this role.

5. OVERALL MATCH SCORE:
   - score = round((0.35 * skills_score) + (0.25 * projects_score) + (0.25 * experience_score) + (0.15 * certifications_score))

6. PROFILE & ZENSAR AVAILABILITY:
   - profile_type: "Technical", "Partially Technical", or "Non-Technical".
   - is_role_available: "Yes", "Maybe", or "No" based on Zensar context.
   - availability_reason: 1 concise sentence explaining vacancy match.
   - suggestions: 3 actionable, personalized tips to boost their match percentage.

Return ONLY valid JSON matching this schema:
{{
  "candidate_name": "{user_name}",
  "role_identified": "{role}",
  "is_internship": false,
  "score": 0,
  "skills_score": 0,
  "projects_score": 0,
  "experience_score": 0,
  "certifications_score": 0,
  "is_role_available": "Yes/No/Maybe",
  "availability_reason": "Reason based on context",
  "profile_type": "Technical/Non-Technical/Partially Technical",
  "matching_skills": ["Skill 1", "Skill 2"],
  "missing_skills": ["Skill 3", "Skill 4"],
  "projects_analyzed": [
    {{"title": "Project Title", "tech_stack": "Tech used", "relevance": "High/Medium/Low", "description": "Brief note"}}
  ],
  "projects_summary": "Summary of project strength",
  "experience_details": [
    {{"role": "Intern/Role", "company": "Company/Org", "duration": "Duration", "relevance": "High/Medium/Low"}}
  ],
  "experience_summary": "Summary of practical experience",
  "certifications_found": ["Cert 1"],
  "certifications_recommended": ["Recommended Cert 1", "Recommended Cert 2"],
  "suggestions": ["Tip 1", "Tip 2", "Tip 3"]
}}
"""

    try:
        # Direct Gemini call with forced JSON output
        content = _fast_gemini_json(prompt)

        # Use robust multi-strategy JSON parsing
        data = _safe_parse_json(content)

        if data is None:
            logger.error(f"Resume JSON all parse strategies failed. Raw: {content[:300]}")
            raise ValueError("JSON parse failed")

        # Standardize and clamp numerical scores
        def _parse_score(val, default=0):
            try:
                num = int(float(val))
                return max(0, min(100, num))
            except (ValueError, TypeError):
                return default

        skills_sc = _parse_score(data.get("skills_score"), 0)
        proj_sc = _parse_score(data.get("projects_score"), 0)
        cert_sc = _parse_score(data.get("certifications_score"), 0)

        if is_internship:
            acad_sc = _parse_score(data.get("academics_score") or data.get("experience_score"), 0)
            exp_sc = acad_sc
            data["academics_score"] = acad_sc
        else:
            exp_sc = _parse_score(data.get("experience_score"), 0)
            data["academics_score"] = exp_sc

        # If individual scores were evaluated, compute weighted score
        if any([skills_sc, proj_sc, exp_sc, cert_sc]):
            weighted_score = round(
                (0.35 * skills_sc) + (0.25 * proj_sc) + (0.25 * exp_sc) + (0.15 * cert_sc)
            )
            ai_score = _parse_score(data.get("score"), 0)
            if ai_score > 0 and abs(ai_score - weighted_score) <= 8:
                data["score"] = ai_score
            else:
                data["score"] = weighted_score
        else:
            data["score"] = _parse_score(data.get("score"), 70)
            skills_sc = data["score"]
            proj_sc = max(20, data["score"] - 10)
            exp_sc = max(20, data["score"] - 15)
            cert_sc = max(20, data["score"] - 10)

        data["skills_score"] = skills_sc
        data["projects_score"] = proj_sc
        data["experience_score"] = exp_sc
        data["academics_score"] = data.get("academics_score", exp_sc)
        data["certifications_score"] = cert_sc
        data["score"] = max(0, min(100, data["score"]))

        # Standardize academic fields
        data["college_name"] = str(data.get("college_name", "")).strip()
        data["degree_branch"] = str(data.get("degree_branch", "")).strip()
        data["cgpa"] = str(data.get("cgpa", "")).strip()
        data["academics_summary"] = str(data.get("academics_summary", "")).strip()

        # Helper to clean string list
        def _clean_str_list(lst, max_items=6):
            res = []
            if isinstance(lst, list):
                for item in lst:
                    if isinstance(item, str) and item.strip():
                        res.append(item.strip())
                    elif isinstance(item, dict) and item:
                        # Extract first non-empty string value if dict returned by mistake
                        val = next((str(v).strip() for v in item.values() if v), "")
                        if val:
                            res.append(val)
            return res[:max_items]

        data["matching_skills"] = _clean_str_list(data.get("matching_skills", []), 6)
        data["missing_skills"] = _clean_str_list(data.get("missing_skills", []), 6)
        data["certifications_found"] = _clean_str_list(data.get("certifications_found", []), 5)
        data["certifications_recommended"] = _clean_str_list(data.get("certifications_recommended", []), 4)
        data["suggestions"] = _clean_str_list(data.get("suggestions", []), 4)

        # Standardize projects_analyzed
        cleaned_projects = []
        raw_projects = data.get("projects_analyzed", [])
        if isinstance(raw_projects, list):
            for p in raw_projects:
                if isinstance(p, dict):
                    cleaned_projects.append({
                        "title": str(p.get("title", p.get("name", "Project"))).strip(),
                        "tech_stack": str(p.get("tech_stack", "")).strip(),
                        "relevance": str(p.get("relevance", "Medium")).strip(),
                        "description": str(p.get("description", "")).strip(),
                    })
                elif isinstance(p, str) and p.strip():
                    cleaned_projects.append({
                        "title": p.strip(),
                        "tech_stack": "",
                        "relevance": "Medium",
                        "description": "",
                    })
        data["projects_analyzed"] = cleaned_projects[:4]

        # Standardize experience_details
        cleaned_exp = []
        raw_exp = data.get("experience_details", [])
        if isinstance(raw_exp, list):
            for e in raw_exp:
                if isinstance(e, dict):
                    cleaned_exp.append({
                        "role": str(e.get("role", e.get("title", "Role / Internship"))).strip(),
                        "company": str(e.get("company", e.get("organization", ""))).strip(),
                        "duration": str(e.get("duration", "")).strip(),
                        "relevance": str(e.get("relevance", "Medium")).strip(),
                    })
                elif isinstance(e, str) and e.strip():
                    cleaned_exp.append({
                        "role": e.strip(),
                        "company": "",
                        "duration": "",
                        "relevance": "Medium",
                    })
        data["experience_details"] = cleaned_exp[:4]

        data["projects_summary"] = str(data.get("projects_summary", "")).strip()
        data["experience_summary"] = str(data.get("experience_summary", "")).strip()

        # Ensure candidate_name is set
        if "candidate_name" not in data or not data["candidate_name"]:
            data["candidate_name"] = user_name

        # Ensure role_identified is set
        if "role_identified" not in data or not data["role_identified"]:
            data["role_identified"] = role

        data["is_internship"] = bool(is_internship)

        # Attach single location from PostgreSQL (no slashes)
        matched_loc = None
        matched_vacancies = 5
        matched_exp = "Fresher / 0-2 Years"
        try:
            from chatbot.models import JobPosting
            p_obj = JobPosting.objects.filter(title__iexact=role, location__icontains=norm_loc).first()
            if not p_obj:
                p_obj = JobPosting.objects.filter(title__icontains=role.split()[0], location__icontains=norm_loc).first()
            if not p_obj:
                p_obj = JobPosting.objects.filter(title__iexact=role).first()
            if p_obj:
                matched_loc = p_obj.location
                matched_vacancies = getattr(p_obj, "vacancies", 5)
                matched_exp = p_obj.experience
        except Exception:
            pass

        if not matched_loc:
            if "chennai" in norm_loc.lower():
                matched_loc = "Chennai, Tamil Nadu (OMR Tech Park)"
            elif "bengaluru" in norm_loc.lower():
                matched_loc = "Bengaluru, Karnataka (Whitefield Campus)"
            elif "hyderabad" in norm_loc.lower():
                matched_loc = "Hyderabad, Telangana (Hitec City Campus)"
            else:
                matched_loc = "Pune, Maharashtra (Global HQ, Kharadi)"
        data["location"] = matched_loc
        data["vacancies"] = matched_vacancies
        data["experience_required"] = matched_exp

        return json.dumps(data)

    except Exception as e:
        logger.error(f"Resume JSON error: {e}")
        # Return a clean structured fallback with 4-pillar data populated
        return json.dumps({
            "candidate_name": user_name,
            "role_identified": role,
            "is_internship": is_internship,
            "score": 0,
            "skills_score": 0,
            "academics_score": 0,
            "projects_score": 0,
            "experience_score": 0,
            "certifications_score": 0,
            "college_name": "",
            "degree_branch": "",
            "cgpa": "",
            "academics_summary": "",
            "is_role_available": "Maybe",
            "availability_reason": "Could not fully analyze at this time.",
            "profile_type": "Technical",
            "matching_skills": [],
            "missing_skills": [],
            "projects_analyzed": [],
            "projects_summary": "Project analysis unavailable at this moment.",
            "experience_details": [],
            "experience_summary": "Experience analysis unavailable at this moment.",
            "certifications_found": [],
            "certifications_recommended": [],
            "suggestions": [
                "Please try uploading your resume again.",
                "Ensure your PDF is readable.",
                "If the issue persists, contact hr@zensar.com."
            ]
        })


# ================= OPTICAL CHARACTER RECOGNITION (OCR) =================

def extract_text_with_ocr(pdf_bytes: bytes) -> str:
    """Uses Google Gemini Vision to extract text from scanned, photographed, or image-only PDF resumes.
    Acts as an intelligent OCR fallback when local PyPDF2 text extraction returns empty or insufficient text.
    """
    if not pdf_bytes:
        return ""

    logger.info("Triggering AI Vision OCR on scanned/image-based resume PDF...")
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=get_current_gemini_api_key())
        document_part = types.Part.from_bytes(
            data=pdf_bytes,
            mime_type="application/pdf",
        )

        ocr_prompt = (
            "You are a high-precision OCR and document analysis engine for recruitment. "
            "The user has uploaded a scanned or image-based resume. "
            "Please perform Optical Character Recognition (OCR) on this document. "
            "Extract all text accurately, preserving candidate name, contact details (email, phone, LinkedIn), "
            "education (degrees, colleges, CGPA/marks), technical skills, work experience, projects, and certifications. "
            "Return only the clean, transcribed plain text of the resume without any conversational commentary or introductory text."
        )

        for model_name in GEMINI_CANDIDATE_MODELS:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=[document_part, ocr_prompt],
                )
                extracted_text = (response.text or "").strip()
                if extracted_text:
                    logger.info("AI Vision OCR successfully extracted %d characters using %s.", len(extracted_text), model_name)
                    return extracted_text
            except Exception as m_exc:
                logger.warning("AI Vision OCR error on %s: %s. Trying next candidate model...", model_name, m_exc)

        return ""

    except Exception as exc:
        logger.error("AI Vision OCR failed: %s", exc)
        return ""
