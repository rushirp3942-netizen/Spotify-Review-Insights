// Spotify Review Analysis System - Frontend Application Logic

// State variables
let reviews = [];
let stats = {};
let config = {};
let smtpConfig = {};
let sentimentChart = null;
let categoryChart = null;
let cachedReportHtml = "";

// DOM Elements
const sidebarItems = document.querySelectorAll('.nav-item');
const tabPanes = document.querySelectorAll('.tab-pane');
const pageTitle = document.getElementById('page-title');
const statusDot = document.getElementById('status-dot');
const statusText = document.getElementById('status-text');
const loadingOverlay = document.getElementById('loading-overlay');
const loadingMessage = document.getElementById('loading-message');

// API Base URL (Relative for deployment)
const API_BASE = "";

// Show/Hide Loader
function showLoader(message = "Processing...") {
    loadingMessage.textContent = message;
    loadingOverlay.classList.add('active');
}

function hideLoader() {
    loadingOverlay.classList.remove('active');
}

// Simple Markdown to HTML formatter for Chat Responses
function formatMarkdown(text) {
    if (!text) return "";
    let html = text;
    
    // Escaping HTML characters first to prevent XSS
    html = html
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
        
    // Headers
    html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>');
    html = html.replace(/^## (.*$)/gim, '<h2>$1</h2>');
    html = html.replace(/^# (.*$)/gim, '<h1>$1</h1>');
    
    // Bold
    html = html.replace(/\*\*(.*?)\*\*/gim, '<strong>$1</strong>');
    
    // Bullet Lists
    html = html.replace(/^\s*-\s+(.*$)/gim, '<li>$1</li>');
    html = html.replace(/^\s*\*\s+(.*$)/gim, '<li>$1</li>');
    
    // Wrap lists
    // This is a naive wrapper but works well for structured responses
    html = html.replace(/(<li>.*<\/li>)/sim, '<ul>$1</ul>');
    
    // Paragraphs (newlines to breaks, double newlines to paragraphs)
    html = html.replace(/\n\n/g, '<br><br>');
    html = html.replace(/\n/g, '<br>');
    
    return html;
}

// App Initialization
document.addEventListener("DOMContentLoaded", async () => {
    // Tab switching event listeners
    sidebarItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const tabName = item.getAttribute('data-tab');
            
            // Toggle active sidebar link
            sidebarItems.forEach(i => i.classList.remove('active'));
            item.classList.add('active');
            
            // Toggle active pane
            tabPanes.forEach(pane => pane.classList.remove('active'));
            document.getElementById(`tab-${tabName}`).classList.add('active');
            
            // Update Page Title header
            const titlesMap = {
                dashboard: "Growth Insights Dashboard",
                explorer: "Review Data Explorer",
                assistant: "AI Product Assistant",
                reports: "Executive Growth Reports",
                settings: "Configuration & Scraping"
            };
            pageTitle.textContent = titlesMap[tabName] || "Spotify Insights";
            
            // Trigger tab-specific loaders
            if (tabName === 'dashboard') {
                loadDashboardData();
            } else if (tabName === 'explorer') {
                loadExplorerData();
            } else if (tabName === 'reports') {
                checkCachedReport();
            } else if (tabName === 'settings') {
                loadSettingsData();
            }
        });
    });

    // Load initial system state
    await checkConfigStatus();
    await loadDashboardData();
    initializeForms();
});

// Check Groq Config and update Status dot
async function checkConfigStatus() {
    try {
        const res = await fetch(`${API_BASE}/api/config`);
        config = await res.json();
        
        if (config.groq_api_key_configured) {
            statusDot.className = "status-dot green";
            statusText.textContent = `Groq: ${config.groq_model}`;
        } else {
            statusDot.className = "status-dot red";
            statusText.textContent = "Groq API Key Required";
        }
    } catch (e) {
        console.error("Failed to check configuration status:", e);
        statusDot.className = "status-dot red";
        statusText.textContent = "Backend Offline";
    }
}

// --- DASHBOARD TAB MODULE ---
async function loadDashboardData() {
    try {
        const statsRes = await fetch(`${API_BASE}/api/reviews/stats`);
        stats = await statsRes.json();
        
        // Update metric values
        document.getElementById('metric-total').textContent = stats.total_count;
        document.getElementById('metric-analyzed').textContent = stats.analyzed_count;
        document.getElementById('metric-discovery').textContent = `${stats.discovery_ratio}%`;
        document.getElementById('metric-rating').textContent = stats.average_rating ? `${stats.average_rating} ★` : "N/A";
        
        // Update charts
        renderSentimentChart(stats.sentiments);
        renderCategoryChart(stats.categories);
        
        // Update Top Pain Points List
        const listEl = document.getElementById('pain-points-list');
        listEl.innerHTML = "";
        
        if (!stats.top_pain_points || stats.top_pain_points.length === 0) {
            listEl.innerHTML = `<li class="loading-placeholder">No analyzed pain points. Go to Settings to run analysis.</li>`;
        } else {
            stats.top_pain_points.forEach(item => {
                const li = document.createElement('li');
                li.className = "pain-point-item";
                li.innerHTML = `
                    <span class="pain-point-title">${item.pain_point}</span>
                    <span class="pain-point-count">${item.count} reviews</span>
                `;
                listEl.appendChild(li);
            });
        }
    } catch (e) {
        console.error("Error loading dashboard metrics:", e);
    }
}

// Render Sentiment Chart.js (Doughnut)
function renderSentimentChart(sentimentData) {
    const ctx = document.getElementById('sentimentChart').getContext('2d');
    
    // Destroy previous instance
    if (sentimentChart) sentimentChart.destroy();
    
    const colors = {
        Positive: '#2ebd59',
        Neutral: '#a0a0a0',
        Negative: '#e91429'
    };
    
    const labels = Object.keys(sentimentData);
    const data = Object.values(sentimentData);
    
    sentimentChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: data,
                backgroundColor: labels.map(l => colors[l] || '#888'),
                borderWidth: 1,
                borderColor: '#121212'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { color: '#B3B3B3', font: { family: 'Inter', size: 11 } }
                }
            }
        }
    });
}

// Render Themes Chart.js (Horizontal Bar)
function renderCategoryChart(categoryData) {
    const ctx = document.getElementById('categoryChart').getContext('2d');
    
    if (categoryChart) categoryChart.destroy();
    
    const labels = Object.keys(categoryData);
    const data = Object.values(categoryData);
    
    categoryChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Feedback Count',
                data: data,
                backgroundColor: '#1DB954',
                borderColor: '#1ed760',
                borderWidth: 1,
                borderRadius: 4
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                x: {
                    grid: { color: '#282828' },
                    ticks: { color: '#B3B3B3', font: { family: 'Inter' } }
                },
                y: {
                    grid: { display: false },
                    ticks: { color: '#B3B3B3', font: { family: 'Inter' } }
                }
            }
        }
    });
}

// --- REVIEW EXPLORER TAB MODULE ---
async function loadExplorerData() {
    showLoader("Loading reviews...");
    try {
        // Fetch configs for count badge
        const statsRes = await fetch(`${API_BASE}/api/reviews/stats`);
        const st = await statsRes.json();
        document.getElementById('pending-count-badge').textContent = st.pending_count;
        
        // Compile filter query parameters
        const source = document.getElementById('filter-source').value;
        const sentiment = document.getElementById('filter-sentiment').value;
        const category = document.getElementById('filter-category').value;
        const discovery = document.getElementById('filter-discovery').value;
        const search = document.getElementById('filter-search').value;
        
        let url = `${API_BASE}/api/reviews?limit=100`;
        if (source) url += `&source=${source}`;
        if (sentiment) url += `&sentiment=${sentiment}`;
        if (category) url += `&category=${category}`;
        if (discovery) url += `&discovery_issue=${discovery}`;
        if (search) url += `&search=${encodeURIComponent(search)}`;
        
        const reviewsRes = await fetch(url);
        const reviewsData = await reviewsRes.json();
        
        document.getElementById('results-count').textContent = reviewsData.total;
        
        const feedEl = document.getElementById('reviews-feed');
        feedEl.innerHTML = "";
        
        if (!reviewsData.reviews || reviewsData.reviews.length === 0) {
            feedEl.innerHTML = `<div class="loading-placeholder">No reviews found matching the selected filters.</div>`;
            hideLoader();
            return;
        }
        
        reviewsData.reviews.forEach(r => {
            const card = document.createElement('div');
            card.className = "review-card";
            
            const analysis = r.analysis || {};
            const isAnalyzed = r.analysis_status === 'analyzed';
            
            // Build badges
            let badgesHtml = `<span class="badge badge-source ${r.source}">${r.source.replace('_', ' ')}</span>`;
            if (isAnalyzed) {
                badgesHtml += `
                    <span class="badge badge-sentiment ${analysis.sentiment}">${analysis.sentiment}</span>
                    <span class="badge badge-category">${analysis.category}</span>
                `;
                if (analysis.discovery_issue) {
                    badgesHtml += `<span class="badge badge-discovery"><i class="fa-solid fa-compass"></i> Discovery Issue</span>`;
                }
            } else {
                badgesHtml += `<span class="badge" style="background-color: #555;">Pending Analysis</span>`;
            }
            
            // Build stars for rating
            let ratingHtml = "";
            if (r.rating) {
                ratingHtml = `<span class="review-rating">${"★".repeat(r.rating)}${"☆".repeat(5 - r.rating)}</span>`;
            }
            
            card.innerHTML = `
                <div class="review-header-summary">
                    <div class="review-meta">
                        ${badgesHtml}
                        ${ratingHtml}
                        <span class="review-text-snippet">${r.content}</span>
                    </div>
                    <div class="review-expand-btn"><i class="fa-solid fa-chevron-down"></i></div>
                </div>
                <div class="review-detail-drawer">
                    <div class="drawer-grid">
                        <div class="original-box">
                            <h3>Original Review</h3>
                            <p>${r.content}</p>
                            <div class="author-info">By ${r.author} • ${new Date(r.timestamp).toLocaleDateString()}</div>
                        </div>
                        <div class="analysis-box">
                            <h3>AI Analysis Details</h3>
                            ${isAnalyzed ? `
                                <div class="analysis-field">
                                    <div class="field-label">One-Line Summary</div>
                                    <div class="field-value">${analysis.summary}</div>
                                </div>
                                <div class="analysis-field">
                                    <div class="field-label">Core Pain Point</div>
                                    <div class="field-value"><strong>${analysis.pain_point}</strong></div>
                                </div>
                                <div class="analysis-field">
                                    <div class="field-label">Model Used</div>
                                    <div class="field-value" style="font-family: monospace; font-size: 11px;">${analysis.model_used || "groq"}</div>
                                </div>
                            ` : `
                                <p style="font-size: 13px; color: var(--text-muted);">This review has not been analyzed yet. Save your Groq API key and click "Analyze Pending" to process.</p>
                            `}
                        </div>
                    </div>
                </div>
            `;
            
            // Accordion expand toggler
            card.querySelector('.review-header-summary').addEventListener('click', () => {
                card.classList.toggle('expanded');
            });
            
            feedEl.appendChild(card);
        });
        
    } catch (e) {
        console.error("Error loading reviews feed:", e);
    }
    hideLoader();
}

// --- AI ASSISTANT MODULE ---
const chatHistory = document.getElementById('chat-history');
const chatForm = document.getElementById('chat-form');
const chatInput = document.getElementById('chat-input');
const questionButtons = document.querySelectorAll('.q-btn');

questionButtons.forEach(btn => {
    btn.addEventListener('click', () => {
        questionButtons.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const qid = btn.getAttribute('data-qid');
        const questionText = btn.querySelector('.q-txt').textContent;
        submitAssistantQuery(qid, questionText);
    });
});

chatForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const queryText = chatInput.value.trim();
    if (!queryText) return;
    
    // Deselect predefined buttons
    questionButtons.forEach(b => b.classList.remove('active'));
    
    submitAssistantQuery("custom", queryText);
    chatInput.value = "";
});

async function submitAssistantQuery(qid, queryText) {
    if (!config.groq_api_key_configured) {
        appendChatMessage("System Info", "My API key is missing. Please save your Groq API key in the 'Settings' tab before querying.", "system");
        return;
    }
    
    // Append user message
    appendChatMessage("Growth PM", queryText, "user");
    
    // Append loading message placeholder
    const loadingMessageId = appendChatMessage("Groq AI", `<div class="spinner" style="width: 20px; height: 20px; border-width: 2px;"></div> Analyzing review corpus...`, "system");
    
    try {
        const bodyObj = { question_id: qid };
        if (qid === 'custom') bodyObj.custom_query = queryText;
        
        const res = await fetch(`${API_BASE}/api/query`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(bodyObj)
        });
        
        if (res.status !== 200) {
            const errData = await res.json();
            throw new Error(errData.detail || "Query failed");
        }
        
        const data = await res.json();
        
        // Remove loading placeholder and append actual styled response
        document.getElementById(loadingMessageId).remove();
        appendChatMessage("Groq AI", formatMarkdown(data.answer), "system");
        
    } catch (err) {
        document.getElementById(loadingMessageId).remove();
        appendChatMessage("Groq AI", `Error: ${err.message}`, "system");
    }
}

function appendChatMessage(sender, htmlContent, role) {
    const msgId = "msg_" + Math.random().toString(36).substr(2, 9);
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${role}`;
    msgDiv.id = msgId;
    
    const avatarIcon = role === 'user' ? 'fa-user-tie' : 'fa-robot';
    
    msgDiv.innerHTML = `
        <div class="avatar"><i class="fa-solid ${avatarIcon}"></i></div>
        <div class="msg-content">
            <h4 style="margin: 0 0 6px 0; font-size: 11px; text-transform: uppercase; color: var(--text-sub);">${sender}</h4>
            <div>${htmlContent}</div>
        </div>
    `;
    chatHistory.appendChild(msgDiv);
    chatHistory.scrollTop = chatHistory.scrollHeight;
    return msgId;
}

// --- EXECUTIVE GROWTH REPORT MODULE ---
const btnGenerateReport = document.getElementById('btn-generate-report');
const reportPreviewFrame = document.getElementById('report-preview-frame');
const btnCopyReport = document.getElementById('btn-copy-report');
const btnSendEmail = document.getElementById('btn-send-email');
const emailForm = document.getElementById('email-form');
const emailRecipient = document.getElementById('email-recipient');
const emailSubject = document.getElementById('email-subject');
const emailNote = document.getElementById('email-note');
const emailAlert = document.getElementById('email-status-alert');

btnGenerateReport.addEventListener('click', async () => {
    if (!config.groq_api_key_configured) {
        alert("Please configure your Groq API key in Settings first.");
        return;
    }
    
    showLoader("Ingesting corpus & compiling report. This takes a few seconds...");
    try {
        const res = await fetch(`${API_BASE}/api/report/generate-one-pager`, {
            method: "POST"
        });
        
        if (res.status !== 200) {
            const errData = await res.json();
            throw new Error(errData.detail || "Failed to generate report.");
        }
        
        const data = await res.json();
        cachedReportHtml = data.html_report;
        
        // Render in preview pane
        renderReportPreview(cachedReportHtml);
        
        // Enable copy and email sending
        btnCopyReport.disabled = false;
        btnSendEmail.disabled = false;
        
        // Pre-fill subject with current date
        const today = new Date().toLocaleDateString();
        emailSubject.value = `Spotify Music Discovery: One-Page Growth Report - ${today}`;
        
    } catch (e) {
        reportPreviewFrame.innerHTML = `<div class="empty-preview" style="color: var(--sentiment-neg);"><i class="fa-solid fa-triangle-exclamation"></i><p>Error: ${e.message}</p></div>`;
    }
    hideLoader();
});

function renderReportPreview(htmlContent) {
    // Create iframe to isolate CSS styling of the report from dashboard styles
    reportPreviewFrame.innerHTML = "";
    const iframe = document.createElement('iframe');
    reportPreviewFrame.appendChild(iframe);
    
    // Inject HTML content into iframe
    iframe.contentWindow.document.open();
    iframe.contentWindow.document.write(`
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {
                    margin: 0;
                    padding: 16px;
                    background-color: #121212;
                    color: #FFFFFF;
                    font-family: Arial, sans-serif;
                    font-size: 13px;
                    line-height: 1.5;
                }
            </style>
        </head>
        <body>
            ${htmlContent}
        </body>
        </html>
    `);
    iframe.contentWindow.document.close();
}

async function checkCachedReport() {
    // Just queries settings to see if SMTP or Groq are configured
    const res = await fetch(`${API_BASE}/api/config/smtp`);
    smtpConfig = await res.json();
    if (smtpConfig.sender_email) {
        emailRecipient.placeholder = `recipient@spotify.com (Sender: ${smtpConfig.sender_email})`;
    }
}

btnCopyReport.addEventListener('click', () => {
    if (!cachedReportHtml) return;
    navigator.clipboard.writeText(cachedReportHtml)
        .then(() => alert("HTML Report copied to clipboard!"))
        .catch(err => alert("Failed to copy report: " + err));
});

emailForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!cachedReportHtml) {
        alert("Please generate the report first.");
        return;
    }
    
    showLoader("Dispatching HTML report via Email...");
    emailAlert.style.display = "none";
    
    try {
        const res = await fetch(`${API_BASE}/api/report/send-email`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                recipient_email: emailRecipient.value.trim(),
                subject: emailSubject.value.trim(),
                personalized_note: emailNote.value.trim()
            })
        });
        
        if (res.status !== 200) {
            const errData = await res.json();
            throw new Error(errData.detail || "Email transmission failed.");
        }
        
        const data = await res.json();
        
        emailAlert.className = "alert alert-success";
        emailAlert.style.display = "block";
        
        if (data.simulation) {
            emailAlert.innerHTML = `
                <strong>Simulation Mode Active!</strong><br>
                SMTP credentials are not configured or failed. The HTML email has been logged to workspace:
                <br><a href="#" style="color:#2ebd59; font-weight:bold;">sent_emails_log.txt</a>
            `;
        } else {
            emailAlert.innerHTML = `<strong>Success!</strong> HTML Report delivered successfully to: ${data.recipients.join(', ')}`;
        }
        
    } catch (e) {
        emailAlert.className = "alert alert-error";
        emailAlert.style.display = "block";
        emailAlert.innerHTML = `<strong>Delivery Failed!</strong> ${e.message}`;
    }
    hideLoader();
});

// --- SETTINGS AND INGESTION MODULES ---
function initializeForms() {
    // Pre-fill Groq settings if configured
    fetch(`${API_BASE}/api/config`)
        .then(r => r.json())
        .then(data => {
            document.getElementById('settings-model').value = data.groq_model || "llama-3.3-70b-versatile";
            if (data.groq_api_key_configured) {
                document.getElementById('settings-key').placeholder = `•••••••••••• (${data.groq_api_key_preview})`;
            }
        });

    // Save Groq Settings
    const groqForm = document.getElementById('settings-groq-form');
    groqForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const key = document.getElementById('settings-key').value.trim();
        const model = document.getElementById('settings-model').value;
        
        showLoader("Saving API configuration...");
        try {
            const res = await fetch(`${API_BASE}/api/config`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ groq_api_key: key, groq_model: model })
            });
            if (res.status === 200) {
                alert("Groq Settings Saved successfully!");
                document.getElementById('settings-key').value = ""; // Clear
                await checkConfigStatus();
                // Refresh placeholder
                fetch(`${API_BASE}/api/config`)
                    .then(r => r.json())
                    .then(data => {
                        if (data.groq_api_key_configured) {
                            document.getElementById('settings-key').placeholder = `•••••••••••• (${data.groq_api_key_preview})`;
                        }
                    });
            } else {
                throw new Error("Failed to save.");
            }
        } catch (err) {
            alert(err.message);
        }
        hideLoader();
    });

    // Save SMTP settings
    const smtpForm = document.getElementById('settings-smtp-form');
    // Pre-fill if configured
    fetch(`${API_BASE}/api/config/smtp`)
        .then(r => r.json())
        .then(data => {
            document.getElementById('settings-smtp-host').value = data.host || "";
            document.getElementById('settings-smtp-port').value = data.port || "";
            document.getElementById('settings-smtp-user').value = data.username || "";
            document.getElementById('settings-smtp-sender').value = data.sender_email || "";
            if (data.password_configured) {
                document.getElementById('settings-smtp-pass').placeholder = "•••••••••••• (Configured)";
            }
        });

    smtpForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const host = document.getElementById('settings-smtp-host').value.trim();
        const port = document.getElementById('settings-smtp-port').value.trim();
        const username = document.getElementById('settings-smtp-user').value.trim();
        const password = document.getElementById('settings-smtp-pass').value.trim();
        const sender = document.getElementById('settings-smtp-sender').value.trim();
        
        showLoader("Saving SMTP Credentials...");
        try {
            const res = await fetch(`${API_BASE}/api/config/smtp`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ host, port, username, password, sender_email: sender })
            });
            if (res.status === 200) {
                alert("SMTP configurations saved successfully!");
                document.getElementById('settings-smtp-pass').value = "";
                document.getElementById('settings-smtp-pass').placeholder = "•••••••••••• (Configured)";
            }
        } catch (err) {
            alert(err.message);
        }
        hideLoader();
    });

    // Trigger Scraper Ingestion
    const scraperForm = document.getElementById('settings-scraper-form');
    const consoleBox = document.getElementById('scrape-console');
    const progressContainer = document.getElementById('scrape-progress-container');
    const progressBar = document.getElementById('scrape-progress-bar');
    const progressLabel = document.getElementById('scrape-progress-label');
    const progressStatus = document.getElementById('scrape-progress-status');
    const btnTriggerScrape = document.getElementById('btn-trigger-scrape');
    
    scraperForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const source = document.getElementById('scrape-source').value;
        const limit = parseInt(document.getElementById('scrape-limit').value);
        const query = document.getElementById('scrape-query').value.trim();
        
        const log = (text, err = false) => {
            const p = document.createElement('p');
            p.className = err ? "system-log err" : "system-log";
            p.textContent = `[${new Date().toLocaleTimeString()}] ${text}`;
            consoleBox.appendChild(p);
            consoleBox.scrollTop = consoleBox.scrollHeight;
        };
        
        log(`Scrape Job Submitted: Source=${source}, limit=${limit}, query="${query}"`);
        btnTriggerScrape.disabled = true;
        
        // Show progress UI
        progressContainer.style.display = "block";
        progressBar.value = 0;
        progressLabel.textContent = "Ingesting: 0%";
        progressStatus.textContent = "Queuing job...";
        progressStatus.style.color = "var(--spotify-green)";
        
        try {
            const res = await fetch(`${API_BASE}/api/scrape`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ source, limit, query })
            });
            
            const data = await res.json();
            
            if (data.status === "accepted") {
                const jobId = data.job_id;
                log(`Job Accepted. ID: ${jobId}. Starting status polling...`);
                
                // Polling interval
                const pollInterval = setInterval(async () => {
                    try {
                        const statusRes = await fetch(`${API_BASE}/api/scrape/status/${jobId}`);
                        const job = await statusRes.json();
                        
                        // Update progress bar
                        const count = job.current_count || 0;
                        const pct = Math.min(100, Math.round((count / limit) * 100));
                        progressBar.value = pct;
                        progressLabel.textContent = `Ingesting: ${pct}%`;
                        progressStatus.textContent = job.message;
                        
                        log(`[Progress] ${job.message}`);
                        
                        if (job.status === "completed") {
                            clearInterval(pollInterval);
                            btnTriggerScrape.disabled = false;
                            log(`Job Finished: ${job.message}`);
                            progressStatus.style.color = "#2ebd59";
                            await loadDashboardData();
                            alert("Ingestion completed successfully!");
                        } else if (job.status === "failed") {
                            clearInterval(pollInterval);
                            btnTriggerScrape.disabled = false;
                            log(`Job Failed: ${job.message}`, true);
                            progressStatus.style.color = "#e91429";
                            alert("Ingestion failed. See logs.");
                        }
                    } catch (pollErr) {
                        clearInterval(pollInterval);
                        btnTriggerScrape.disabled = false;
                        log(`Polling error: ${pollErr.message}`, true);
                    }
                }, 1000);
            } else {
                btnTriggerScrape.disabled = false;
                log("Error: Ingestion request rejected.", true);
            }
        } catch (err) {
            btnTriggerScrape.disabled = false;
            log(`Exception occurred: ${err.message}`, true);
        }
    });

    // Seed Mock Data
    const btnSeedMock = document.getElementById('btn-seed-mock');
    const dbStatusMsg = document.getElementById('db-status-msg');
    
    btnSeedMock.addEventListener('click', async () => {
        if (!confirm("Are you sure you want to overwrite your reviews database and seed it with pre-built mock discovery feedback?")) return;
        
        showLoader("Seeding Database...");
        dbStatusMsg.textContent = "";
        try {
            const res = await fetch(`${API_BASE}/api/mock-data`, { method: "POST" });
            if (res.status === 200) {
                const data = await res.json();
                dbStatusMsg.style.color = "#1DB954";
                dbStatusMsg.textContent = `Success! Loaded ${data.count} mock review records. Go to Review Explorer to check them out.`;
                await loadDashboardData();
            } else {
                throw new Error("Failed to seed database.");
            }
        } catch (err) {
            dbStatusMsg.style.color = "#e91429";
            dbStatusMsg.textContent = `Seeding failed: ${err.message}`;
        }
        hideLoader();
    });

    // Review Explorer filtering events
    document.getElementById('filter-source').addEventListener('change', loadExplorerData);
    document.getElementById('filter-sentiment').addEventListener('change', loadExplorerData);
    document.getElementById('filter-category').addEventListener('change', loadExplorerData);
    document.getElementById('filter-discovery').addEventListener('change', loadExplorerData);
    
    let searchTimeout;
    document.getElementById('filter-search').addEventListener('input', () => {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(loadExplorerData, 400); // Debounce search
    });
    
    document.getElementById('btn-reset-filters').addEventListener('click', () => {
        document.getElementById('filter-source').value = "";
        document.getElementById('filter-sentiment').value = "";
        document.getElementById('filter-category').value = "";
        document.getElementById('filter-discovery').value = "";
        document.getElementById('filter-search').value = "";
        loadExplorerData();
    });
    
    document.getElementById('btn-refresh-reviews').addEventListener('click', loadExplorerData);
    
    // Batch Analyze button
    const btnAnalyzePending = document.getElementById('btn-analyze-pending');
    const analysisProgressContainer = document.getElementById('analysis-progress-container');
    const analysisProgressBar = document.getElementById('analysis-progress-bar');
    const analysisProgressLabel = document.getElementById('analysis-progress-label');
    const analysisProgressStatus = document.getElementById('analysis-progress-status');

    btnAnalyzePending.addEventListener('click', async () => {
        if (!config.groq_api_key_configured) {
            alert("Groq is not configured. Please save API Key in Settings.");
            return;
        }
        
        btnAnalyzePending.disabled = true;
        analysisProgressContainer.style.display = "block";
        analysisProgressBar.value = 0;
        analysisProgressLabel.textContent = "Analyzing: 0%";
        analysisProgressStatus.textContent = "Initializing background classification...";
        analysisProgressStatus.style.color = "var(--spotify-green)";

        try {
            const res = await fetch(`${API_BASE}/api/analyze`, { method: "POST" });
            if (res.status !== 200) {
                const errData = await res.json();
                throw new Error(errData.detail || "Analysis request failed.");
            }
            const data = await res.json();
            
            if (data.status === "no_work") {
                analysisProgressContainer.style.display = "none";
                btnAnalyzePending.disabled = false;
                alert("No pending reviews left to classify!");
            } else if (data.status === "accepted") {
                const jobId = data.job_id;
                const totalPending = data.total_pending;
                
                // Poll status every 1 second
                const pollInterval = setInterval(async () => {
                    try {
                        const statusRes = await fetch(`${API_BASE}/api/analyze/status/${jobId}`);
                        if (statusRes.status !== 200) {
                            throw new Error("Failed to get status.");
                        }
                        const job = await statusRes.json();
                        
                        const current = job.current_count || 0;
                        const pct = Math.min(100, Math.round((current / totalPending) * 100));
                        analysisProgressBar.value = pct;
                        analysisProgressLabel.textContent = `Analyzing: ${pct}%`;
                        analysisProgressStatus.textContent = job.message;
                        
                        if (job.status === "completed") {
                            clearInterval(pollInterval);
                            btnAnalyzePending.disabled = false;
                            analysisProgressContainer.style.display = "none";
                            await loadExplorerData();
                            await loadDashboardData();
                            alert("Bulk classification completed successfully!");
                        } else if (job.status === "failed") {
                            clearInterval(pollInterval);
                            btnAnalyzePending.disabled = false;
                            analysisProgressStatus.style.color = "#e91429";
                            alert(`Bulk classification failed: ${job.message}`);
                        }
                    } catch (pollErr) {
                        clearInterval(pollInterval);
                        btnAnalyzePending.disabled = false;
                        alert(`Status polling error: ${pollErr.message}`);
                    }
                }, 1000);
            }
        } catch (e) {
            btnAnalyzePending.disabled = false;
            analysisProgressContainer.style.display = "none";
            alert("Error running analysis: " + e.message);
        }
    });
}
