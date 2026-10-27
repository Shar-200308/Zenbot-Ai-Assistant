// ==========================
// chatbot.js
// ==========================

const chatBox = document.getElementById("chatBox");
const historyList = document.getElementById("historyList");
const botAvatar = "/static/assets/Zenbot.png?v=4";
let allChats = [];

function formatShortName(name) {
    if (!name || name === "User") return "User";
    const trimmed = name.trim();
    // Use same logic: first alphabetical part, then capitalize
    const match = trimmed.match(/^[a-zA-Z]+/);
    if (match) {
        const part = match[0];
        return part.charAt(0).toUpperCase() + part.slice(1).toLowerCase();
    }
    const fallback = trimmed.split(/[\d\s]/)[0];
    return (fallback.charAt(0).toUpperCase() + fallback.slice(1).toLowerCase()) || "User";
}

async function ensureUserInfo() {
    let name = localStorage.getItem("userName");
    let email = localStorage.getItem("userEmail");
    const token = localStorage.getItem("firebaseToken");

    if (token) {
        try {
            const res = await fetch("/save-user/", {
                method: "POST",
                headers: { "Authorization": "Bearer " + token }
            });
            const data = await res.json();
            if (data.status === "user_saved") {
                if (data.userName) {
                    name = formatShortName(data.userName);
                    localStorage.setItem("userName", name);
                }
                if (data.userEmail) {
                    email = data.userEmail;
                    localStorage.setItem("userEmail", email);
                }
                if (data.is_hr !== undefined) {
                    localStorage.setItem("is_hr", data.is_hr ? "true" : "false");
                }
                return { name, email };
            }
        } catch (err) {
            console.error("Error fetching user info:", err);
        }
    }

    // Final fallback: Use email prefix if name is still 'User' or missing
    if (!name || name === "User") {
        if (email) {
            name = formatShortName(email.split("@")[0]);
            localStorage.setItem("userName", name);
        }
    }

    return { name: formatShortName(name), email };
}


// ==========================
// AUTH GUARD
// ==========================
function handleUnauthorized() {
    localStorage.clear();
    window.location.href = "/login/";
}


// ==========================
// CSRF TOKEN
// ==========================
function getCSRFToken() {
    let cookieValue = null;
    if (document.cookie && document.cookie !== "") {

        const cookies = document.cookie.split(";");

        for (let cookie of cookies) {

            cookie = cookie.trim();

            if (cookie.startsWith("csrftoken=")) {
                cookieValue = cookie.substring("csrftoken=".length);
                break;
            }
        }
    }

    return cookieValue;
}

// ==========================
// LOAD HISTORY
// ==========================
function loadChatHistory() {
    const token = localStorage.getItem("firebaseToken");
    if (!token) return;

    fetch("/get-chats/", {
        headers: {
            "Authorization": "Bearer " + token
        }
    })
        .then(res => {
            if (res.status === 401) { handleUnauthorized(); return null; }
            return res.json();
        })
        .then(data => {
            if (!data) return;
            if (data.chats) {
                allChats = data.chats;
                renderHistoryList();

                // Clear chatBox before loading history
                chatBox.innerHTML = "";

                // If there's history, show it
                if (allChats.length > 0) {
                    let lastScorecardData = null;
                    allChats.forEach(chat => {
                        addUserMessage(chat.message);

                        // Add bot message
                        const div = document.createElement("div");
                        div.className = "bot-message";

                        // Check if response is a scorecard
                        let isJson = false;
                        let matchData = null;
                        try {
                            if (chat.response.trim().startsWith("{") && chat.response.trim().includes('"score"')) {
                                matchData = JSON.parse(chat.response);
                                isJson = true;
                                lastScorecardData = matchData;
                            }
                        } catch (e) { }

                        if (isJson) {
                            div.innerHTML = `
                            <img src="${botAvatar}" class="bot-avatar" style="align-self: flex-start; margin-top: 5px;">
                            <div class="bot-text" style="width: 100%;">${generateScorecardHtml(matchData)}</div>
                        `;
                        } else {
                            div.innerHTML = `
                            <img src="${botAvatar}" class="bot-avatar" style="align-self: flex-start; margin-top: 5px;">
                            <div class="bot-text">${parseMarkdown(chat.response)}</div>
                        `;
                        }
                        chatBox.appendChild(div);
                    });

                    scrollChat();
                } else {
                    // Restore greeting if no history
                    const name = localStorage.getItem("userName") || "User";
                    const email = localStorage.getItem("userEmail") || "";
                    chatBox.innerHTML = `
                    <div class="bot-message">
                        <img src="${botAvatar}" class="bot-avatar">
                        <div class="bot-text">
                            Hi ${name} (${email}) 👋 I’m <b>ZenBot</b>.<br>
                            Welcome to ZenBot chatbot. How can I assist you today?
                        </div>
                    </div>
                `;
                }
            }
        })
        .catch(err => console.error("Error loading history:", err));
}

function renderHistoryList() {
    historyList.innerHTML = "";

    allChats.forEach((item, index) => {
        const li = document.createElement("li");
        const btn = document.createElement("button");

        // Use the question text as a preview or the time
        btn.textContent = item.time + " - " + (item.message.substring(0, 15) + "...");
        btn.onclick = () => openChat(index);

        li.appendChild(btn);
        historyList.appendChild(li);
    });
}


// ==========================
// OPEN OLD CHAT
// ==========================
function openChat(index) {
    const selectedChat = allChats[index];
    if (!selectedChat) return;

    // Clear current box
    chatBox.innerHTML = "";

    // Add the specific message pair
    addUserMessage(selectedChat.message);
    addBotMessage(selectedChat.response);

    scrollChat();

    // Close sidebar on mobile after selecting a chat
    if (window.innerWidth <= 768) {
        toggleSidebar();
    }
}


// ==========================
// NEW CHAT
// ==========================
function newChat() {
    const name = localStorage.getItem("userName") || "User";
    chatBox.innerHTML = `
        <div class="bot-message">
            <img src="${botAvatar}" class="bot-avatar">
            <div class="bot-text">Hello ${name}! 👋 I am <b>ZenBot</b>. How can I help you today?</div>
        </div>
    `;

    scrollChat();

    // Close sidebar on mobile
    if (window.innerWidth <= 768) {
        toggleSidebar();
    }
}


// ==========================
// CLEAR HISTORY
// ==========================
function clearHistory() {
    const token = localStorage.getItem("firebaseToken");

    fetch("/clear-history/", {
        method: "POST",
        headers: {
            "Authorization": "Bearer " + token
        }
    })
        .then(res => {
            if (res.status === 401) { handleUnauthorized(); return null; }
            return res.json();
        })
        .then(data => {
            if (!data) return;
            if (data.status === "history_cleared") {
                historyList.innerHTML = "";
                allChats = [];
                newChat();
                // Close sidebar on mobile after clearing
                if (window.innerWidth <= 768) {
                    toggleSidebar();
                }
            }
        })
        .catch(err => console.error("Error clearing history:", err));
}


// ==========================
// ADD USER MESSAGE
// ==========================
function addUserMessage(text) {

    const div = document.createElement("div");

    div.className = "user-message";

    div.textContent = text;

    chatBox.appendChild(div);

    scrollChat();
}


// ==========================
// ADD BOT MESSAGE
// ==========================
function addBotMessage(text) {
    const div = document.createElement("div");
    div.className = "bot-message";

    let isJson = false;
    let matchData = null;
    try {
        if (typeof text === "object" && text !== null && (text.score !== undefined || text.role_identified)) {
            matchData = text;
            isJson = true;
        } else if (typeof text === "string" && text.trim().startsWith("{") && text.trim().includes('"score"')) {
            matchData = JSON.parse(text);
            isJson = true;
        }
    } catch (e) { }

    if (isJson && matchData) {
        try {
            div.innerHTML = `
                <img src="${botAvatar}" class="bot-avatar" style="align-self: flex-start; margin-top: 5px;">
                <div class="bot-text" style="width: 100%;">${generateScorecardHtml(matchData)}</div>
            `;
        } catch (renderErr) {
            console.error("Scorecard render error:", renderErr);
            div.innerHTML = `
                <img src="${botAvatar}" class="bot-avatar" style="align-self: flex-start; margin-top: 5px;">
                <div class="bot-text">Failed to render scorecard. Please try again.</div>
            `;
        }
    } else {
        const textStr = typeof text === "string" ? text : (typeof text === "object" ? JSON.stringify(text) : String(text));
        div.innerHTML = `
            <img src="${botAvatar}" class="bot-avatar" style="align-self: flex-start; margin-top: 5px;">
            <div class="bot-text">${parseMarkdown(textStr)}</div>
        `;
        speakBot(textStr);
    }

    chatBox.appendChild(div);
    scrollChat();
}

function showTypingIndicator() {
    const div = document.createElement("div");
    div.className = "typing-indicator";
    div.id = "typingIndicator";
    div.innerHTML = `
        <div class="typing-dot"></div>
        <div class="typing-dot" style="animation-delay: 0.2s"></div>
        <div class="typing-dot" style="animation-delay: 0.4s"></div>
    `;
    chatBox.appendChild(div);
    scrollChat();
}

function hideTypingIndicator() {
    const indicator = document.getElementById("typingIndicator");
    if (indicator) indicator.remove();
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

function parseMarkdown(text) {
    // Escape HTML first to prevent XSS, then apply markdown formatting
    let safe = escapeHtml(text);
    return safe
        .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
        .replace(/\*(.*?)\*/g, "<em>$1</em>")
        .replace(/\[(.*?)\]\((.*?)\)/g, '<a href="$2" class="chat-link" style="color: #58a6ff; text-decoration: underline;">$1</a>')
        .replace(/\n/g, "<br>");
}

// ==========================================
// ZENSAR ROLES CATALOG — DYNAMIC (DB-DRIVEN)
// Loaded from /api/active-jobs/ on page init.
// Static fallback used only if API fails.
// Adding a new role to HR dashboard auto-syncs here — no manual update needed.
// ==========================================
let ZENSAR_ROLES_CATALOG = {};  // populated by _loadRolesCatalog()

const _ROLES_CATALOG_FALLBACK = {
    "software engineer": { vacancies: 15, exp: "0-2 Years (Freshers Eligible)", location: "Pune, Maharashtra (Global HQ, Kharadi)" },
    "full stack developer": { vacancies: 12, exp: "0-2 Years (Freshers Eligible)", location: "Chennai, Tamil Nadu (OMR Tech Park)" },
    "ai / ml engineer": { vacancies: 8, exp: "1-3 Years", location: "Bengaluru, Karnataka (Whitefield Campus)" },
    "qa automation engineer": { vacancies: 10, exp: "0-3 Years", location: "Pune, Maharashtra (Global HQ, Kharadi)" },
};

async function _loadRolesCatalog() {
    try {
        const resp = await fetch('/api/active-jobs/?type=all', { method: 'GET' });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        const jobs = data.jobs || [];
        const catalog = {};
        jobs.forEach(job => {
            const key = String(job.title || '').trim().toLowerCase();
            catalog[key] = {
                vacancies: job.vacancies || 0,
                exp: job.experience || '0-2 Years',
                location: job.location || 'Chennai, Tamil Nadu (OMR Tech Park)',
                department: job.department || '',
                job_type: job.job_type || 'job',
            };
        });
        ZENSAR_ROLES_CATALOG = catalog;
        console.log(`[Zenbot] Roles catalog loaded: ${Object.keys(catalog).length} active roles`);
    } catch (err) {
        console.warn('[Zenbot] Could not load roles from API, using static fallback:', err.message);
        ZENSAR_ROLES_CATALOG = _ROLES_CATALOG_FALLBACK;
    }
}

// Load roles immediately on page init
_loadRolesCatalog();

function getRoleMeta(roleName) {
    if (!roleName) return { vacancies: 10, exp: "0-2 Years", location: "Chennai, Tamil Nadu (OMR Tech Park)" };
    const key = String(roleName).trim().toLowerCase();
    if (ZENSAR_ROLES_CATALOG[key]) return ZENSAR_ROLES_CATALOG[key];
    for (const [k, v] of Object.entries(ZENSAR_ROLES_CATALOG)) {
        if (key.includes(k) || k.includes(key)) return v;
    }
    if (key.includes("intern")) return { vacancies: 15, exp: "Fresher / College Students", location: "Chennai, Tamil Nadu (OMR Tech Park)" };
    if (key.includes("lead") || key.includes("architect")) return { vacancies: 4, exp: "5-10 Years", location: "Bengaluru, Karnataka (Whitefield Campus)" };
    if (key.includes("director")) return { vacancies: 2, exp: "8-16 Years", location: "Pune, Maharashtra (Global HQ, Kharadi)" };
    if (key.includes("senior")) return { vacancies: 8, exp: "2-8 Years", location: "Chennai, Tamil Nadu (OMR Tech Park)" };
    return { vacancies: 10, exp: "0-2 Years", location: "Chennai, Tamil Nadu (OMR Tech Park)" };
}

function generateScorecardHtml(matchData) {
    const isAvail = matchData.is_role_available || 'Yes';
    const statusColor = isAvail === 'Yes' ? '#56d364' : isAvail === 'Maybe' ? '#e3b341' : '#f85149';
    const statusIcon = isAvail === 'Yes' ? '🏢' : isAvail === 'Maybe' ? '❔' : '❌';

    const profileType = matchData.profile_type || 'Technical Profile';
    let profileColor = '#8b949e'; // Default gray
    if (profileType.includes('Non-Technical')) profileColor = '#d29922';
    else if (profileType.includes('Partially')) profileColor = '#58a6ff';
    else if (profileType.includes('Technical')) profileColor = '#3fb950';

    let cleanLoc = matchData.location || (typeof _currentResumeLocation !== 'undefined' ? _currentResumeLocation : 'Chennai, Tamil Nadu (OMR Tech Park)');
    if (cleanLoc.includes(' / ')) {
        if (cleanLoc.toLowerCase().includes('pune')) {
            cleanLoc = 'Pune, Maharashtra (Global HQ, Kharadi)';
        } else if (cleanLoc.toLowerCase().includes('bengaluru') || cleanLoc.toLowerCase().includes('bangalore')) {
            cleanLoc = 'Bengaluru, Karnataka (Whitefield Campus)';
        } else if (cleanLoc.toLowerCase().includes('hyderabad')) {
            cleanLoc = 'Hyderabad, Telangana (Hitec City Campus)';
        } else {
            cleanLoc = 'Chennai, Tamil Nadu (OMR Tech Park)';
        }
    }
    let locParam = 'Chennai';
    if (cleanLoc.toLowerCase().includes('pune')) locParam = 'Pune';
    else if (cleanLoc.toLowerCase().includes('bengaluru') || cleanLoc.toLowerCase().includes('bangalore')) locParam = 'Bengaluru';
    else if (cleanLoc.toLowerCase().includes('hyderabad')) locParam = 'Hyderabad';

    const isInternship = matchData.is_internship === true;
    const meta = getRoleMeta(matchData.role_identified);
    const vacanciesCount = (matchData.vacancies != null && matchData.vacancies !== '') ? matchData.vacancies : meta.vacancies;
    const expReq = matchData.experience_required || matchData.experience || (isInternship ? 'Fresher / College Students' : meta.exp);

    // 4-Pillar Score Normalization
    const overallScore = Math.max(0, Math.min(100, Math.round(Number(matchData.score) || 0)));
    const skillsScore = Math.max(0, Math.min(100, Math.round(Number(matchData.skills_score !== undefined ? matchData.skills_score : matchData.score) || 0)));
    const projectsScore = Math.max(0, Math.min(100, Math.round(Number(matchData.projects_score !== undefined ? matchData.projects_score : Math.max(20, overallScore - 10)) || 0)));
    const expScore = Math.max(0, Math.min(100, Math.round(Number(matchData.experience_score !== undefined ? matchData.experience_score : Math.max(20, overallScore - 15)) || 0)));
    const certScore = Math.max(0, Math.min(100, Math.round(Number(matchData.certifications_score !== undefined ? matchData.certifications_score : Math.max(20, overallScore - 10)) || 0)));

    if (overallScore > 0) {
        try {
            localStorage.setItem('latestAnalyzedScore', String(overallScore));
            if (matchData.role_identified) {
                localStorage.setItem('analyzedScore_' + matchData.role_identified.trim().toLowerCase(), String(overallScore));
            }
        } catch (e) {}
    }

    const applyUrl = isInternship ? 
        `/apply-internship/?role=${encodeURIComponent(matchData.role_identified || 'General Role')}&location=${encodeURIComponent(locParam)}&score=${overallScore}` : 
        `/apply-job/?role=${encodeURIComponent(matchData.role_identified || 'General Role')}&location=${encodeURIComponent(locParam)}&score=${overallScore}`;
    const formTypeText = isInternship ? "Internship Application Form" : "Job Application Form";

    function getPillarColor(val) {
        if (val >= 75) return '#3fb950';
        if (val >= 50) return '#d29922';
        return '#f85149';
    }

    function getPillarGradient(val) {
        if (val >= 75) return 'linear-gradient(90deg, #3fb950, #56d364)';
        if (val >= 50) return 'linear-gradient(90deg, #d29922, #e3b341)';
        return 'linear-gradient(90deg, #f85149, #ff7b72)';
    }

    function getRelClass(rel) {
        const r = String(rel || '').toLowerCase();
        if (r.includes('high')) return 'high';
        if (r.includes('low')) return 'low';
        return 'medium';
    }

    // Projects list HTML
    const projectsList = Array.isArray(matchData.projects_analyzed) ? matchData.projects_analyzed : [];
    let projectsHtml = '';
    if (projectsList.length > 0) {
        projectsHtml = projectsList.map(p => `
            <div class="resume-item-row">
                <div class="resume-item-header">
                    <span class="resume-item-name"><i class="fas fa-folder-open" style="color:#58a6ff; margin-right:4px;"></i> ${escapeHtml(p.title || 'Project')}</span>
                    <span class="relevance-pill ${getRelClass(p.relevance)}">${escapeHtml(p.relevance || 'Medium')} Relevance</span>
                </div>
                ${p.tech_stack ? `<div style="font-size:11px; color:#58a6ff; margin-bottom:2px;">Tech: ${escapeHtml(p.tech_stack)}</div>` : ''}
                ${p.description ? `<div class="resume-item-detail">${escapeHtml(p.description)}</div>` : ''}
            </div>
        `).join('');
    } else {
        projectsHtml = `<div style="font-size: 12px; color: #8b949e; font-style: italic;">No specific technical projects detected in the resume. Adding relevant projects will boost this score.</div>`;
    }

    // Experience list HTML
    const expList = Array.isArray(matchData.experience_details) ? matchData.experience_details : [];
    let expHtml = '';
    if (expList.length > 0) {
        expHtml = expList.map(e => `
            <div class="resume-item-row">
                <div class="resume-item-header">
                    <span class="resume-item-name"><i class="fas fa-briefcase" style="color:#34d399; margin-right:4px;"></i> ${escapeHtml(e.role || 'Role / Internship')}</span>
                    <span class="relevance-pill ${getRelClass(e.relevance)}">${escapeHtml(e.relevance || 'Medium')} Relevance</span>
                </div>
                <div style="font-size: 11px; color: #8b949e; margin-bottom: 2px;">
                    ${e.company ? `<strong>${escapeHtml(e.company)}</strong>` : ''}
                    ${e.duration ? ` &bull; ${escapeHtml(e.duration)}` : ''}
                </div>
            </div>
        `).join('');
    } else {
        expHtml = `<div style="font-size: 12px; color: #8b949e; font-style: italic;">Fresher profile / No formal internship recorded. Practical coursework and academic training evaluated.</div>`;
    }

    // Certifications HTML
    const certsFound = Array.isArray(matchData.certifications_found) ? matchData.certifications_found : [];
    const certsRec = Array.isArray(matchData.certifications_recommended) ? matchData.certifications_recommended : [];

    return `
        <div class="resume-match-card">
            <!-- Header & Overall Score -->
            <div class="resume-scorecard-header">
                <div>
                    <h4 class="resume-scorecard-role">Resume Evaluation</h4>
                    <p class="resume-scorecard-sub">
                        Target Role: <span style="color: #58a6ff; font-weight: 600;">${escapeHtml(matchData.role_identified || 'Target Role')}</span>
                        ${matchData.candidate_name ? ` &bull; <span style="color: #c9d1d9;">${escapeHtml(matchData.candidate_name)}</span>` : ''}
                    </p>
                </div>
                <div class="resume-overall-gauge">
                    <div class="resume-gauge-label">Match Accuracy</div>
                    <div class="resume-gauge-value" style="color: ${getPillarColor(overallScore)};">
                        ${overallScore}%
                    </div>
                </div>
            </div>

            <!-- Overall Progress Bar & Meta Badges -->
            <div style="margin-bottom: 10px; display: flex; flex-direction: column; gap: 6px;">
                <div style="height: 5px; width: 100%; background: #21262d; border-radius: 10px; overflow: hidden;">
                    <div style="height: 100%; width: ${overallScore}%; background: ${getPillarGradient(overallScore)}; border-radius: 10px; transition: width 1s ease-in-out;"></div>
                </div>
                
                <div style="display: flex; gap: 6px; flex-wrap: wrap;">
                    <span style="font-size: 10.5px; color: #c9d1d9; background: #21262d; border: 1px solid #30363d; padding: 2px 8px; border-radius: 14px; font-weight: 600;">
                        Profile: <span style="color: ${profileColor};">${escapeHtml(profileType)}</span>
                    </span>
                    <span style="font-size: 10.5px; color: ${statusColor}; font-weight: 600; background: ${statusColor}15; padding: 2px 8px; border-radius: 14px; border: 1px solid ${statusColor}40;">
                        ${statusIcon} Zensar Role: ${escapeHtml(isAvail)}
                    </span>
                    <span style="font-size: 10.5px; color: #fbbf24; font-weight: 700; background: rgba(245, 158, 11, 0.15); padding: 2px 8px; border-radius: 14px; border: 1px solid rgba(245, 158, 11, 0.4);">
                        🔥 Vacancies: <strong>${vacanciesCount} Openings</strong>
                    </span>
                    <span style="font-size: 10.5px; color: #c084fc; font-weight: 600; background: rgba(192, 132, 252, 0.15); padding: 2px 8px; border-radius: 14px; border: 1px solid rgba(192, 132, 252, 0.4);">
                        💼 Exp Req: <strong>${escapeHtml(String(expReq))}</strong>
                    </span>
                    <span style="font-size: 10.5px; color: #38bdf8; font-weight: 600; background: rgba(56, 189, 248, 0.12); padding: 2px 8px; border-radius: 14px; border: 1px solid rgba(56, 189, 248, 0.35);">
                        <i class="fas fa-map-marker-alt"></i> ${escapeHtml(cleanLoc)}
                    </span>
                </div>
                
                <p style="margin: 2px 0 0 0; font-size: 11px; color: #c9d1d9; line-height: 1.35; font-style: italic;">"${escapeHtml(matchData.availability_reason || 'Checked against corporate requirements.')}"</p>
            </div>

            <!-- 4-PILLAR METRICS BREAKDOWN -->
            <div style="margin-bottom: 6px;">
                <div style="font-size: 10px; color: #8b949e; text-transform: uppercase; letter-spacing: 0.8px; font-weight: 700; margin-bottom: 6px; display:flex; align-items:center; gap:5px;">
                    <i class="fas fa-chart-pie" style="color:#58a6ff;"></i> Evaluation Breakdown
                </div>
                <div class="resume-pillar-grid">
                    <!-- Pillar 1: Skills -->
                    <div class="resume-pillar-card">
                        <div class="resume-pillar-meta">
                            <span class="resume-pillar-title">🛠️ Skills</span>
                            <span class="resume-pillar-pct" style="color: ${getPillarColor(skillsScore)};">${skillsScore}%</span>
                        </div>
                        <div class="resume-pillar-bar-bg">
                            <div class="resume-pillar-bar-fill" style="width: ${skillsScore}%; background: ${getPillarGradient(skillsScore)};"></div>
                        </div>
                        <div class="resume-pillar-desc">Weight: 35%</div>
                    </div>

                    <!-- Pillar 2: Projects -->
                    <div class="resume-pillar-card">
                        <div class="resume-pillar-meta">
                            <span class="resume-pillar-title">💻 Projects</span>
                            <span class="resume-pillar-pct" style="color: ${getPillarColor(projectsScore)};">${projectsScore}%</span>
                        </div>
                        <div class="resume-pillar-bar-bg">
                            <div class="resume-pillar-bar-fill" style="width: ${projectsScore}%; background: ${getPillarGradient(projectsScore)};"></div>
                        </div>
                        <div class="resume-pillar-desc">Weight: 25%</div>
                    </div>

                    <!-- Pillar 3: Experience (Job) or Academics & CGPA (Internship) -->
                    <div class="resume-pillar-card">
                        <div class="resume-pillar-meta">
                            <span class="resume-pillar-title">${isInternship ? '🎓 Academics' : '💼 Intern/Exp'}</span>
                            <span class="resume-pillar-pct" style="color: ${getPillarColor(expScore)};">${expScore}%</span>
                        </div>
                        <div class="resume-pillar-bar-bg">
                            <div class="resume-pillar-bar-fill" style="width: ${expScore}%; background: ${getPillarGradient(expScore)};"></div>
                        </div>
                        <div class="resume-pillar-desc">${isInternship ? 'College & CGPA' : 'Weight: 25%'}</div>
                    </div>

                    <!-- Pillar 4: Certifications -->
                    <div class="resume-pillar-card">
                        <div class="resume-pillar-meta">
                            <span class="resume-pillar-title">📜 Certs</span>
                            <span class="resume-pillar-pct" style="color: ${getPillarColor(certScore)};">${certScore}%</span>
                        </div>
                        <div class="resume-pillar-bar-bg">
                            <div class="resume-pillar-bar-fill" style="width: ${certScore}%; background: ${getPillarGradient(certScore)};"></div>
                        </div>
                        <div class="resume-pillar-desc">Weight: 15%</div>
                    </div>
                </div>
            </div>

            <!-- SKILLS ANALYSIS (MATCHING VS MISSING) -->
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 8px;">
                <div style="background: rgba(35, 134, 54, 0.1); border: 1px solid rgba(63, 185, 80, 0.3); padding: 8px 10px; border-radius: 6px;">
                    <p style="margin: 0 0 6px 0; color: #3fb950; font-weight: 600; text-transform: uppercase; font-size: 10px; letter-spacing: 0.8px; display: flex; align-items: center; gap: 4px;">
                         <span>✓</span> Matching Skills
                    </p>
                    <div style="display: flex; flex-wrap: wrap; gap: 4px;">
                        ${matchData.matching_skills && matchData.matching_skills.length > 0 ? matchData.matching_skills.map(s => `<span style="background: #21262d; border: 1px solid #30363d; padding: 2px 7px; border-radius: 4px; font-size: 11px; color: #c9d1d9;">${escapeHtml(s)}</span>`).join("") : '<span style="color: #8b949e; font-size: 11px;">No specific matches</span>'}
                    </div>
                </div>

                <div style="background: rgba(248, 81, 73, 0.1); border: 1px solid rgba(248, 81, 73, 0.3); padding: 8px 10px; border-radius: 6px;">
                    <p style="margin: 0 0 6px 0; color: #f85149; font-weight: 600; text-transform: uppercase; font-size: 10px; letter-spacing: 0.8px; display: flex; align-items: center; gap: 4px;">
                         <span>⚠</span> Missing Skills
                    </p>
                    <div style="display: flex; flex-wrap: wrap; gap: 4px;">
                        ${matchData.missing_skills && matchData.missing_skills.length > 0 ? matchData.missing_skills.map(s => `<span style="background: #21262d; border: 1px solid #30363d; padding: 2px 7px; border-radius: 4px; font-size: 11px; color: #c9d1d9;">${escapeHtml(s)}</span>`).join("") : '<span style="color: #8b949e; font-size: 11px;">None identified</span>'}
                    </div>
                </div>
            </div>

            <!-- PROJECTS EVALUATION SECTION -->
            <div class="resume-analysis-card">
                <p class="resume-analysis-card-title" style="color: #58a6ff;">
                    <i class="fas fa-laptop-code"></i> Projects Evaluated (${projectsScore}%)
                </p>
                ${matchData.projects_summary ? `<div style="font-size: 11.5px; color: #c9d1d9; margin-bottom: 6px; line-height: 1.35;">${escapeHtml(matchData.projects_summary)}</div>` : ''}
                <div style="display: flex; flex-direction: column; gap: 4px;">
                    ${projectsHtml}
                </div>
            </div>

            ${isInternship ? `
            <!-- COLLEGE & CGPA PROFILE (FOR INTERNSHIPS) -->
            <div class="resume-analysis-card">
                <p class="resume-analysis-card-title" style="color: #34d399;">
                    <i class="fas fa-graduation-cap"></i> College & Academic Profile (${expScore}%)
                </p>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-bottom: 5px;">
                    <div class="resume-item-row" style="margin-bottom:0;">
                        <div style="font-size: 9.5px; color: #8b949e; text-transform: uppercase;">College / University</div>
                        <div style="font-size: 11.5px; color: #f0f6fc; font-weight: 600;">${escapeHtml(matchData.college_name || 'Academic Institution')}</div>
                    </div>
                    <div class="resume-item-row" style="margin-bottom:0;">
                        <div style="font-size: 9.5px; color: #8b949e; text-transform: uppercase;">Degree & Stream</div>
                        <div style="font-size: 11.5px; color: #f0f6fc; font-weight: 600;">${escapeHtml(matchData.degree_branch || 'Undergraduate')}</div>
                    </div>
                </div>
                ${matchData.cgpa ? `
                <div style="margin-bottom: 5px; font-size: 11px; color: #c9d1d9; background: rgba(52, 211, 153, 0.08); border: 1px solid rgba(52, 211, 153, 0.25); border-radius: 5px; padding: 4px 8px;">
                    <strong>Academic Standing / CGPA:</strong> <span style="color:#34d399; font-weight:800;">${escapeHtml(matchData.cgpa)}</span>
                </div>` : ''}
                ${matchData.academics_summary ? `<div style="font-size: 11px; color: #c9d1d9; line-height: 1.35; font-style: italic;">"${escapeHtml(matchData.academics_summary)}"</div>` : ''}
            </div>
            ` : `
            <!-- INTERNSHIP & EXPERIENCE SECTION (FOR JOBS) -->
            <div class="resume-analysis-card">
                <p class="resume-analysis-card-title" style="color: #34d399;">
                    <i class="fas fa-briefcase"></i> Internships & Practical Experience (${expScore}%)
                </p>
                ${matchData.experience_summary ? `<div style="font-size: 11.5px; color: #c9d1d9; margin-bottom: 6px; line-height: 1.35;">${escapeHtml(matchData.experience_summary)}</div>` : ''}
                <div style="display: flex; flex-direction: column; gap: 4px;">
                    ${expHtml}
                </div>
            </div>
            `}

            <!-- CERTIFICATIONS SECTION -->
            <div class="resume-analysis-card">
                <p class="resume-analysis-card-title" style="color: #c084fc;">
                    <i class="fas fa-award"></i> Certifications & Credentials (${certScore}%)
                </p>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 6px;">
                    <div>
                        <div style="font-size: 10px; color: #8b949e; font-weight: 600; margin-bottom: 4px;">DETECTED IN RESUME:</div>
                        <div style="display: flex; flex-wrap: wrap; gap: 4px;">
                            ${certsFound.length > 0 ? certsFound.map(c => `<span style="background: rgba(192, 132, 252, 0.12); border: 1px solid rgba(192, 132, 252, 0.35); padding: 2px 6px; border-radius: 4px; font-size: 11px; color: #e9d5ff;"><i class="fas fa-check-circle" style="color:#a855f7; margin-right:2px;"></i>${escapeHtml(c)}</span>`).join("") : '<span style="color: #8b949e; font-size: 11px; font-style:italic;">None detected</span>'}
                        </div>
                    </div>
                    <div>
                        <div style="font-size: 10px; color: #8b949e; font-weight: 600; margin-bottom: 4px;">RECOMMENDED FOR THIS ROLE:</div>
                        <div style="display: flex; flex-wrap: wrap; gap: 4px;">
                            ${certsRec.length > 0 ? certsRec.map(c => `<span style="background: rgba(56, 189, 248, 0.1); border: 1px solid rgba(56, 189, 248, 0.3); padding: 2px 6px; border-radius: 4px; font-size: 11px; color: #7dd3fc;"><i class="fas fa-star" style="color:#38bdf8; margin-right:2px;"></i>${escapeHtml(c)}</span>`).join("") : '<span style="color: #8b949e; font-size: 11px;">Standard domain certifications</span>'}
                        </div>
                    </div>
                </div>
            </div>

            <!-- STRATEGIC IMPROVEMENT SUGGESTIONS -->
            <div style="background: rgba(88, 166, 255, 0.05); border: 1px solid rgba(88, 166, 255, 0.2); padding: 10px 12px; border-radius: 6px; margin-bottom: 10px;">
                <p style="margin: 0 0 6px 0; color: #58a6ff; font-weight: 600; text-transform: uppercase; font-size: 10px; letter-spacing: 0.8px;">Strategic Suggestions to Boost Match Score</p>
                <ul style="list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 6px;">
                    ${matchData.suggestions && matchData.suggestions.length > 0 ? matchData.suggestions.map(s => `
                        <li style="font-size: 11.5px; color: #c9d1d9; line-height: 1.4; display: flex; align-items: flex-start; gap: 6px;">
                            <span style="color: #58a6ff; margin-top: 1px;">&bull;</span>
                            <span>${escapeHtml(s)}</span>
                        </li>
                    `).join("") : '<li style="color: #8b949e; font-size: 11px;">Review target role specifications to tailor your resume.</li>'}
                </ul>
            </div>

            <!-- DYNAMIC APPLICATION LINK -->
            <div style="text-align: center;">
                <div style="margin-bottom: 6px; font-size: 11px; color: #38bdf8; background: rgba(56, 189, 248, 0.08); border: 1px solid rgba(56, 189, 248, 0.22); border-radius: 6px; padding: 4px 10px; display: inline-block;">
                    <strong>Open Vacancy At:</strong> ${escapeHtml(cleanLoc)}
                </div>
                <a href="${applyUrl}" 
                   class="apply-now-btn"
                   style="display: block; background: linear-gradient(90deg, #238636, #2ea043); color: white; padding: 9px 16px; border-radius: 6px; text-decoration: none; font-weight: 700; font-size: 13.5px; transition: all 0.3s ease; box-shadow: 0 4px 12px rgba(35, 134, 54, 0.35); border: 1px solid rgba(255,255,255,0.1);">
                   Apply for ${escapeHtml(matchData.role_identified || 'this Role')} (${locParam})
                </a>
                <p style="margin: 6px 0 0 0; font-size: 10px; color: #8b949e;">Official <strong>${formTypeText}</strong> for ${locParam} location</p>
            </div>
        </div>
    `;
}


// ==========================
// SCROLL CHAT
// ==========================
function scrollChat() {

    chatBox.scrollTop = chatBox.scrollHeight;

}


// ==========================
// SEND MESSAGE
// ==========================
function sendMessage() {

    const input = document.getElementById("userInput");

    const msg = input.value.trim();

    if (!msg) return;

    addUserMessage(msg);

    input.value = "";

    sendToBot(msg);

}


// ==========================
// ENTER KEY TO SEND
// ==========================



// ==========================
// Store analyzed resume in IndexedDB for auto-attaching in application forms
function storeAnalyzedResume(file) {
    if (!window.indexedDB) return;
    try {
        const req = indexedDB.open("ZenbotResumeDB", 1);
        req.onupgradeneeded = (e) => {
            const db = e.target.result;
            if (!db.objectStoreNames.contains("resumes")) {
                db.createObjectStore("resumes", { keyPath: "id" });
            }
        };
        req.onsuccess = (e) => {
            const db = e.target.result;
            const tx = db.transaction("resumes", "readwrite");
            const store = tx.objectStore("resumes");
            store.put({
                id: "current_resume",
                file: file,
                name: file.name,
                size: file.size,
                type: file.type || "application/pdf",
                savedAt: Date.now()
            });
            localStorage.setItem("hasAnalyzedResume", "true");
            localStorage.setItem("analyzedResumeName", file.name);
        };
    } catch (err) {
        console.warn("Could not cache resume in IndexedDB:", err);
    }
}

// UPLOAD RESUME
// ==========================
function uploadResume(input) {
    const file = input.files[0];
    if (!file) return;

    // Reset input so the same file can be re-uploaded
    input.value = "";

    // Validate PDF
    if (!file.name.toLowerCase().endsWith(".pdf")) {
        addBotMessage("⚠️ Please upload a PDF file only.");
        return;
    }

    // Validate size (5MB)
    if (file.size > 5 * 1024 * 1024) {
        addBotMessage("⚠️ File is too large. Maximum size is 5MB.");
        return;
    }

    // Cache in IndexedDB for application form auto-attachment
    storeAnalyzedResume(file);

    // Show user message
    addUserMessage("📄 Resume Upload: " + file.name);

    // Show analyzing indicator
    const loadingDiv = document.createElement("div");
    loadingDiv.className = "bot-message resume-loading";
    loadingDiv.innerHTML = `
        <img src="${botAvatar}" class="bot-avatar">
        <div class="bot-text">
            <div class="analyzing-indicator">
                <span class="spinner"></span>
                Extracting resume...
            </div>
        </div>
    `;
    chatBox.appendChild(loadingDiv);
    scrollChat();

    // Upload to backend
    const token = localStorage.getItem("firebaseToken");
    const formData = new FormData();
    formData.append("resume", file);

    fetch("/upload-resume/", {
        method: "POST",
        headers: {
            "Authorization": "Bearer " + token
        },
        body: formData
    })
        .then(res => {
            if (res.status === 401) { handleUnauthorized(); return null; }
            return res.json();
        })
        .then(data => {
            // Remove loading indicator
            if (loadingDiv.parentNode) loadingDiv.remove();

            if (!data) return;

            if (data.error) {
                addBotMessage("❌ " + data.error);
            } else if (data.status === "ask_role_type") {
                renderAskRoleType();
            } else if (data.status === "suggested_roles") {
                renderRoleSuggestions(data.suggestions);
            } else if (data.match) {
                addBotMessage(data.match);
            }
        })
        .catch(err => {
            if (loadingDiv.parentNode) loadingDiv.remove();
            console.error("Resume upload error:", err);
            addBotMessage("❌ Failed to upload resume. Please try again.");
        });
}

let _currentResumeLocation = 'Chennai';

function renderAskRoleType() {
    const div = document.createElement("div");
    div.className = "bot-message";
    div.innerHTML = `
        <img src="${botAvatar}" class="bot-avatar" style="align-self: flex-start; margin-top: 5px;">
        <div class="bot-text" style="width: 100%;">
            <p style="margin-bottom: 4px; color: #f0f6fc; font-weight: 700; font-size: 14.5px;">
                Resume Uploaded Successfully!
            </p>
            <p style="margin-bottom: 12px; color: #8b949e; font-size: 13px;">
                Please select your track. ZenBot will analyze your resume and suggest matching open vacancies:
            </p>

            <div class="track-selection-container" style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                <button class="track-select-btn" style="margin:0; text-align:center; padding: 12px 14px; border: 1px solid rgba(88, 166, 255, 0.35); background: rgba(88, 166, 255, 0.08); border-radius: 8px; cursor: pointer; transition: all 0.2s;" onclick="selectJobType('job')">
                    <div class="track-name" style="color:#58a6ff; font-size: 14px; font-weight: 600; margin-bottom: 0;">Full-Time Job</div>
                </button>
                <button class="track-select-btn" style="margin:0; text-align:center; padding: 12px 14px; border: 1px solid rgba(52, 211, 153, 0.35); background: rgba(52, 211, 153, 0.08); border-radius: 8px; cursor: pointer; transition: all 0.2s;" onclick="selectJobType('intern')">
                    <div class="track-name" style="color:#34d399; font-size: 14px; font-weight: 600; margin-bottom: 0;">Internship</div>
                </button>
            </div>
        </div>
    `;
    chatBox.appendChild(div);
    scrollChat();
}

window.selectJobType = function(type) {
    const typeLabel = type === 'intern' ? 'Internship' : 'Full-Time Job';
    addUserMessage(`I am looking for ${typeLabel} opportunities.`);

    const loadingDiv = document.createElement("div");
    loadingDiv.className = "bot-message resume-loading";
    loadingDiv.innerHTML = `
        <img src="${botAvatar}" class="bot-avatar">
        <div class="bot-text">
            <div class="analyzing-indicator">
                <span class="spinner"></span>
                Matching resume with open ${typeLabel} vacancies...
            </div>
        </div>
    `;
    chatBox.appendChild(loadingDiv);
    scrollChat();

    const token = localStorage.getItem("firebaseToken");
    fetch("/suggest-roles/", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + token,
            "X-CSRFToken": getCSRFToken()
        },
        body: JSON.stringify({ type: type })
    })
    .then(res => res.json())
    .then(data => {
        if (loadingDiv.parentNode) loadingDiv.remove();
        if (data.error) {
            addBotMessage("❌ " + data.error);
        } else if (data.status === "suggested_roles") {
            renderRoleSuggestions(data.suggestions);
        }
    })
    .catch(err => {
        if (loadingDiv.parentNode) loadingDiv.remove();
        addBotMessage("❌ Error finding roles.");
    });
};

function renderRoleSuggestions(suggestionsData) {
    const div = document.createElement("div");
    div.className = "bot-message";

    const expLevel = suggestionsData.experience_level || "Professional Profile";
    const roles = suggestionsData.suggested_roles || [];

    window._currentSuggestedRoles = roles;

    let buttonsHtml = roles.map((r, idx) => {
        let singleLoc = r.location || 'Chennai, Tamil Nadu (OMR Tech Park)';
        if (singleLoc.includes(' / ')) {
            singleLoc = singleLoc.toLowerCase().includes('pune') ? 
                'Pune, Maharashtra (Global HQ, Kharadi)' : 
                'Chennai, Tamil Nadu (OMR Tech Park)';
        }
        const isChennai = singleLoc.toLowerCase().includes('chennai');
        const locColor = isChennai ? '#38bdf8' : '#c084fc';
        const vacancies = (r.vacancies != null && r.vacancies !== '') ? r.vacancies : 12;
        const exp = r.experience || (r.is_internship ? 'Fresher / College Students' : '0-2 Years');

        return `
        <button class="role-suggestion-btn" onclick="selectRoleByIndex(${idx})">
            <div style="display: flex; justify-content: space-between; align-items: center; width: 100%; flex-wrap: wrap; gap: 6px;">
                <div class="role-name" style="margin-bottom: 0;">${escapeHtml(r.role || 'Role')}</div>
                <div style="display: flex; gap: 6px; align-items: center; flex-wrap: wrap;">
                    <span class="badge-vacancies"><i class="fas fa-fire"></i> ${vacancies} Vacancies</span>
                    <span class="badge-exp"><i class="fas fa-user-clock"></i> ${escapeHtml(String(exp))}</span>
                </div>
            </div>
            <div class="role-reason">${escapeHtml(r.reason || 'Matching background')} &bull; <span style="color:${locColor}; font-weight:600;">📍 ${escapeHtml(singleLoc)}</span></div>
        </button>
        `;
    }).join("");

    div.innerHTML = `
        <img src="${botAvatar}" class="bot-avatar" style="align-self: flex-start; margin-top: 5px;">
        <div class="bot-text" style="width: 100%;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; background: rgba(88, 166, 255, 0.1); padding: 8px 12px; border-radius: 8px; border: 1px solid rgba(88, 166, 255, 0.2);">
                <span style="font-size: 13px; color: #c9d1d9;">Profile: <strong>${escapeHtml(expLevel)}</strong></span>
            </div>
            <p style="margin-bottom: 12px; color: #c9d1d9; font-size: 14px;">Based on your resume, here are matching open vacancies at <b>Zensar Technologies</b>. Select one to see your detailed match score:</p>
            <div class="role-suggestions-container">
                ${buttonsHtml}
            </div>
        </div>
    `;
    chatBox.appendChild(div);
    scrollChat();
}

window.selectRoleByIndex = function (idx) {
    const roles = window._currentSuggestedRoles || [];
    const r = roles[idx];
    if (r) {
        let singleLoc = r.location || 'Chennai, Tamil Nadu (OMR Tech Park)';
        const meta = getRoleMeta(r.role);
        const vacancies = (r.vacancies != null && r.vacancies !== '') ? r.vacancies : meta.vacancies;
        const exp = r.experience || (r.is_internship ? 'Fresher / College Students' : meta.exp);
        selectRoleForAnalysis(r.role, r.is_internship === true, singleLoc, vacancies, exp);
    }
};

window.selectRoleForAnalysis = function (roleName, isInternship = false, chosenLocation = 'Chennai', vacancies = null, exp = null) {
    const meta = getRoleMeta(roleName);
    const finalVacancies = (vacancies != null && vacancies !== '') ? vacancies : meta.vacancies;
    const finalExp = exp || (isInternship ? 'Fresher / College Students' : meta.exp);
    const loc = chosenLocation || meta.location || 'Chennai';
    _currentResumeLocation = loc;
    
    let userMsg = `I would like to analyze my resume for: ${roleName} (${loc}) [🔥 ${finalVacancies} Vacancies • 💼 Exp: ${finalExp}]`;
    addUserMessage(userMsg);

    const loadingDiv = document.createElement("div");
    loadingDiv.className = "bot-message resume-loading";
    loadingDiv.innerHTML = `
        <img src="${botAvatar}" class="bot-avatar">
        <div class="bot-text">
            <div class="analyzing-indicator">
                <span class="spinner"></span>
                Performing deep analysis for <strong>${escapeHtml(roleName)}</strong> (${escapeHtml(loc)})...<br>
                <div style="margin-top: 6px; display: flex; gap: 6px; align-items: center; flex-wrap: wrap;">
                    <span class="badge-vacancies"><i class="fas fa-fire"></i> ${finalVacancies} Vacancies</span>
                    <span class="badge-exp"><i class="fas fa-user-clock"></i> Exp Req: ${escapeHtml(String(finalExp))}</span>
                </div>
            </div>
        </div>
    `;
    chatBox.appendChild(loadingDiv);
    scrollChat();

    const token = localStorage.getItem("firebaseToken");

    // 60s timeout visual indicator — show "taking longer than usual" after 10s
    let _slowTimer = setTimeout(() => {
        const spinnerEl = loadingDiv.querySelector('.analyzing-indicator');
        if (spinnerEl) {
            const slowNote = document.createElement('div');
            slowNote.className = 'slow-ai-notice';
            slowNote.style.cssText = 'margin-top:8px;font-size:12px;color:#f59e0b;display:flex;align-items:center;gap:6px;';
            slowNote.innerHTML = '<i class="fas fa-hourglass-half"></i> AI is taking a bit longer than usual — almost there...';
            spinnerEl.appendChild(slowNote);
        }
    }, 10000);

    fetch("/analyze-role/", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + token,
            "X-CSRFToken": getCSRFToken()
        },
        body: JSON.stringify({ role: roleName, is_internship: isInternship, location: loc })
    })
        .then(res => res.json())
        .then(data => {
            clearTimeout(_slowTimer);
            if (loadingDiv.parentNode) loadingDiv.remove();
            if (data.match) {
                addBotMessage(data.match);
            } else if (data.error) {
                addBotMessage("❌ " + data.error);
            }
        })
        .catch(err => {
            clearTimeout(_slowTimer);
            if (loadingDiv.parentNode) loadingDiv.remove();
            addBotMessage("❌ Error analyzing role.");
        });
};

// ==========================================
// AUTOMATIC DOM UPGRADER FOR ROLE BUTTONS
// ==========================================
function upgradeExistingRoleButtons() {
    if (typeof document === 'undefined') return;

    // Actively purge badges and flex wrapper from track selection buttons (Job / Intern track)
    const trackButtons = document.querySelectorAll('.track-select-btn, button[onclick*="selectJobType"], .track-selection-container button');
    trackButtons.forEach((btn) => {
        btn.querySelectorAll('.badge-vacancies, .badge-exp, .badges-holder').forEach(el => el.remove());
        const header = btn.querySelector('.role-btn-header-flex');
        if (header) {
            const nameEl = header.querySelector('.track-name, .role-name, div');
            if (nameEl) {
                btn.appendChild(nameEl);
            }
            header.remove();
        }
        btn.classList.remove('role-suggestion-btn');
        btn.classList.add('track-select-btn');
    });

    const buttons = document.querySelectorAll('.role-suggestion-btn');
    buttons.forEach((btn) => {
        // Skip track selection buttons (Full-Time Job / Internship track chooser)
        const onclickAttr = btn.getAttribute('onclick') || '';
        const btnText = btn.textContent || '';
        if (onclickAttr.includes('selectJobType') || btn.classList.contains('track-select-btn') || btn.closest('.track-selection-container') || btnText.includes('Full-Time Job') || btnText.includes('Internship')) {
            btn.querySelectorAll('.badge-vacancies, .badge-exp, .badges-holder').forEach(el => el.remove());
            return;
        }
        if (!btn.querySelector('.badge-vacancies')) {
            const nameEl = btn.querySelector('.role-name');
            if (nameEl) {
                const roleName = nameEl.textContent.trim();
                const meta = getRoleMeta(roleName);
                nameEl.style.marginBottom = "0";

                let header = btn.querySelector('.role-btn-header-flex');
                if (!header) {
                    header = document.createElement('div');
                    header.className = 'role-btn-header-flex';
                    header.style.cssText = "display: flex; justify-content: space-between; align-items: center; width: 100%; flex-wrap: wrap; gap: 6px;";
                    nameEl.parentNode.insertBefore(header, nameEl);
                    header.appendChild(nameEl);

                    const badgeHolder = document.createElement('div');
                    badgeHolder.className = 'badges-holder';
                    badgeHolder.style.cssText = "display: flex; gap: 6px; align-items: center; flex-wrap: wrap;";
                    badgeHolder.innerHTML = `
                        <span class="badge-vacancies"><i class="fas fa-fire"></i> ${meta.vacancies} Vacancies</span>
                        <span class="badge-exp"><i class="fas fa-user-clock"></i> ${escapeHtml(String(meta.exp))}</span>
                    `;
                    header.appendChild(badgeHolder);
                }
            }
        }
    });
}

// Observe chatBox so any rendered role buttons are immediately enriched with badges
if (typeof MutationObserver !== 'undefined' && chatBox) {
    const chatObserver = new MutationObserver(() => {
        upgradeExistingRoleButtons();
    });
    chatObserver.observe(chatBox, { childList: true, subtree: true });
}

// Initial upgrade runs
setTimeout(upgradeExistingRoleButtons, 100);
setTimeout(upgradeExistingRoleButtons, 500);
document.addEventListener("DOMContentLoaded", upgradeExistingRoleButtons);


// ==========================
// SEND TO BACKEND
// ==========================
function sendToBot(message) {

    const token = localStorage.getItem("firebaseToken");

    showTypingIndicator();

    fetch("/chat/api/", {

        method: "POST",

        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": getCSRFToken(),
            "Authorization": "Bearer " + token
        },

        body: JSON.stringify({ message: message })

    })

        .then(res => {
            if (res.status === 401) { handleUnauthorized(); return null; }
            return res.json();
        })

        .then(data => {

            hideTypingIndicator();
            if (!data) return;

            if (data.error) {
                addBotMessage("Error: " + data.error);
            } else {
                addBotMessage(data.reply);
                
                // Optimized: Update local history array and sidebar without full re-fetch/re-render
                const newChatObj = {
                    message: message,
                    response: data.reply,
                    time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                };
                allChats.push(newChatObj);
                renderHistoryList();
            }

        })

        .catch(err => {

            hideTypingIndicator();
            console.error(err);

            addBotMessage("Server error.");

        });

}


// ==========================
// BOT SPEECH
// ==========================
function speakBot(text) {

    if (!window.speechSynthesis) return;

    const utterance = new SpeechSynthesisUtterance(text);

    utterance.lang = "en-US";

    window.speechSynthesis.speak(utterance);

}


// ==========================
// USER MENU
// ==========================
window.toggleUserMenu = function () {
    console.log("ZenBot: toggleUserMenu clicked.");
    document.getElementById("userMenu").classList.toggle("show");
}


window.logout = function () {
    const modal = document.getElementById("logoutModal");
    if (modal) {
        modal.classList.add("show");
    } else {
        // Fallback if modal isn't in DOM for some reason
        if (confirm("Are you sure you want to logout?")) {
            confirmLogout();
        }
    }
}

window.closeLogoutModal = function () {
    const modal = document.getElementById("logoutModal");
    if (modal) {
        modal.classList.remove("show");
    }
}

window.confirmLogout = function () {
    console.log("ZenBot: Logging out...");
    localStorage.clear(); // 🛡️ Total cleanup on logout
    sessionStorage.clear(); // 🛡️ Clear password storage
    window.location.href = "/login/";
}



window.showUserProfile = function () {
    window.location.href = "/profile/";
}

// ==========================
// MOBILE SIDEBAR TOGGLE
// ==========================
window.toggleSidebar = function () {
    const sidebar = document.querySelector(".sidebar");
    const overlay = document.getElementById("sidebarOverlay");
    if (sidebar && overlay) {
        sidebar.classList.toggle("active");
        overlay.classList.toggle("active");
    }
}


document.addEventListener("click", function (event) {

    const container = document.querySelector(".user-menu-container");

    if (container && !container.contains(event.target)) {

        document.getElementById("userMenu").classList.remove("show");

    }

});


// ==========================
// PAGE LOAD
// ==========================
window.onload = async function () {
    // 🛡️ Auth Check: Redirect to login if no token
    const token = localStorage.getItem("firebaseToken");
    if (!token) {
        window.location.href = "/login/";
        return;
    }

    // 🛡️ Immediate Isolation: Clear stale data before loading
    allChats = [];
    chatBox.innerHTML = "Loading your session...";
    historyList.innerHTML = "";

    const { name, email } = await ensureUserInfo();

    if (email) {
        document.getElementById("userEmailDisplay").textContent = email;
    }


    if (name) {
        document.getElementById("userNameDisplay").textContent = name;

        // Dynamic Greeting (Show immediately if no chats)
        if (chatBox.children.length <= 1) {
            chatBox.innerHTML = `
                <div class="bot-message">
                    <img src="${botAvatar}" class="bot-avatar">
                    <div class="bot-text">
                        Hi ${name} (${email}) 👋 I’m <b>ZenBot</b>.<br>
                        Welcome to ZenBot chatbot. How can I assist you today?
                    </div>
                </div>
            `;
        }
    }

    // Load history after ensuring user info
    loadChatHistory();
};

// ⌨️ Global Enter Key Support
document.addEventListener("keydown", function (e) {
    if (e.key === "Enter" || e.keyCode === 13) {
        const input = document.getElementById("userInput");
        if (e.target === input) {
            console.log("ZenBot: Enter key detected on input.");
            e.preventDefault();
            sendMessage();
        }
    }
}, true); // Capture phase to ensure it runs before other handlers