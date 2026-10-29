// AutoMail Frontend Engine

let currentTab = 'leads';
let currentFilter = 'all';
let currentSearch = '';
let leadsData = [];
let activeModalLead = null;
let pollTimer = null;
let stagedUploadFile = null;

document.addEventListener('DOMContentLoaded', () => {
    initApp();
});

async function initApp() {
    const s = await fetchSettings();
    await fetchStats();
    await fetchGroqLimits(false);
    await fetchLeads();
    await fetchLogs();

    // If new user or friend opening with no email configured, auto-open setup onboarding modal
    if (!s || !s.smtp_user) {
        setTimeout(() => openAccountModal(), 600);
    }

    // Start adaptive polling: polls smoothly (2s) only during active campaigns;
    // stays quiet (10s) when the system is idle.
    scheduleNextPoll(10000);
}

function scheduleNextPoll(delayMs = 10000) {
    if (pollTimer) clearTimeout(pollTimer);
    pollTimer = setTimeout(async () => {
        const isRunning = await fetchStats();
        if (currentTab === 'logs' && isRunning) {
            await fetchLogs();
        }
        // If active outreach is underway, poll every 2s for countdown and progress bar.
        // If idle, poll quietly every 10s.
        scheduleNextPoll(isRunning ? 2000 : 10000);
    }, delayMs);
}

// ----------------- TABS -----------------
function switchTab(tab) {
    currentTab = tab;
    ['leads', 'ai', 'smtp', 'settings', 'logs'].forEach(t => {
        const el = document.getElementById(`tab-${t}`);
        const btn = document.getElementById(`tab-btn-${t}`);
        if (el && btn) {
            if (t === tab) {
                el.classList.remove('hidden');
                btn.className = 'segmented-item segmented-active px-4 py-1.5 flex items-center gap-1.5';
            } else {
                el.classList.add('hidden');
                btn.className = 'segmented-item px-4 py-1.5 text-white/60 hover:text-white flex items-center gap-1.5';
            }
        }
    });
    if (tab === 'logs') fetchLogs();
    if (tab === 'ai') fetchGroqLimits();
    lucide.createIcons();
}

// ----------------- STATS & DISPATCHER STATE -----------------
async function fetchStats() {
    try {
        const res = await fetch('/api/stats');
        const data = await res.json();
        const s = data.stats;
        const d = data.dispatcher;

        document.getElementById('stat-total').innerText = s.total;
        document.getElementById('stat-pending').innerText = s.pending;
        document.getElementById('stat-generated').innerText = s.generated;
        document.getElementById('stat-approved').innerText = s.approved || 0;
        document.getElementById('stat-sent').innerText = s.sent;
        document.getElementById('stat-failed').innerText = s.failed;

        // Dispatcher state
        const bannerText = document.getElementById('campaign-status-text');
        const progressBar = document.getElementById('live-progress-bar');
        const progressPct = document.getElementById('live-progress-pct');
        const countdownBadge = document.getElementById('countdown-badge');
        const countdownVal = document.getElementById('countdown-val');
        const pingIndicator = document.getElementById('ping-indicator');

        const btnStart = document.getElementById('btn-start');
        const btnDryRun = document.getElementById('btn-dry-run');
        const btnPause = document.getElementById('btn-pause');
        const btnStop = document.getElementById('btn-stop');
        const pauseBtnText = document.getElementById('pause-btn-text');

        bannerText.innerText = d.status_message || 'System Ready.';

        if (d.is_running) {
            btnStart.classList.add('hidden');
            btnDryRun.classList.add('hidden');
            btnPause.classList.remove('hidden');
            btnStop.classList.remove('hidden');

            pauseBtnText.innerText = d.is_paused ? 'Resume' : 'Pause';
            pingIndicator.classList.remove('hidden');

            const pct = d.total_leads > 0 ? Math.round((d.current_index / d.total_leads) * 100) : 0;
            progressBar.style.width = `${pct}%`;
            progressPct.innerText = `${pct}%`;

            if (d.countdown_seconds > 0) {
                countdownBadge.classList.remove('hidden');
                countdownVal.innerText = d.countdown_seconds;
            } else {
                countdownBadge.classList.add('hidden');
            }
        } else {
            btnStart.classList.remove('hidden');
            btnDryRun.classList.remove('hidden');
            btnPause.classList.add('hidden');
            btnStop.classList.add('hidden');
            countdownBadge.classList.add('hidden');
            pingIndicator.classList.add('hidden');

            if (s.total > 0 && s.sent > 0) {
                const pct = Math.round((s.sent / s.total) * 100);
                progressBar.style.width = `${pct}%`;
                progressPct.innerText = `${pct}%`;
            } else {
                progressBar.style.width = '0%';
                progressPct.innerText = '0%';
            }
        }
        return Boolean(d && d.is_running);
    } catch (e) {
        console.error('Error fetching stats:', e);
        return false;
    }
}

// ----------------- GROQ RATE LIMITS -----------------
async function fetchGroqLimits(force = false) {
    try {
        const res = await fetch(`/api/groq/limits${force ? '?refresh=true' : ''}`);
        const data = await res.json();

        if (data.connected) {
            document.getElementById('api-status-badge').innerText = 'Active';
            document.getElementById('api-status-badge').className = 'px-1.5 py-0.5 rounded text-[10px] font-mono bg-emerald-500/20 text-emerald-400 border border-emerald-500/30';
            document.getElementById('api-model-name').innerText = `Model: ${data.model} (LPU Inference)`;

            document.getElementById('api-req-rem').innerText = data.remaining_requests;
            document.getElementById('api-req-lim').innerText = data.limit_requests;
            document.getElementById('api-req-reset').innerText = `${data.reset_requests} reset`;
            document.getElementById('api-req-bar').style.width = `${data.request_pct}%`;

            document.getElementById('api-tok-rem').innerText = data.remaining_tokens;
            document.getElementById('api-tok-lim').innerText = data.limit_tokens;
            document.getElementById('api-tok-reset').innerText = `${data.reset_tokens} reset`;
            document.getElementById('api-tok-bar').style.width = `${data.token_pct}%`;
        } else {
            document.getElementById('api-status-badge').innerText = 'Offline';
            document.getElementById('api-status-badge').className = 'px-1.5 py-0.5 rounded text-[10px] font-mono bg-amber-500/20 text-amber-400 border border-amber-500/30';
        }
    } catch (e) {
        console.error('Error fetching Groq limits:', e);
    }
}

// ----------------- LEADS MANAGEMENT -----------------
async function fetchLeads() {
    try {
        let url = `/api/leads?limit=200`;
        if (currentFilter !== 'all') url += `&status=${currentFilter}`;
        if (currentSearch) url += `&search=${encodeURIComponent(currentSearch)}`;

        const res = await fetch(url);
        const data = await res.json();
        leadsData = data.leads || [];
        renderLeadsTable(leadsData);
    } catch (e) {
        console.error('Error fetching leads:', e);
    }
}

function renderLeadsTable(leads) {
    const tbody = document.getElementById('leads-tbody');
    if (!leads || leads.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" class="py-8 text-center text-slate-500">No leads in database. Upload a CSV or Excel file to begin!</td></tr>`;
        return;
    }

    tbody.innerHTML = leads.map(lead => {
        let statusBadge = '';
        if (lead.status === 'sent') {
            statusBadge = `<span class="px-2.5 py-0.5 rounded-full bg-[#30D158]/15 text-[#30D158] font-medium text-[10px] border border-[#30D158]/25">Delivered</span>`;
        } else if (lead.status === 'failed') {
            statusBadge = `<span class="px-2.5 py-0.5 rounded-full bg-[#FF453A]/15 text-[#FF453A] font-medium text-[10px] border border-[#FF453A]/25" title="${escapeHtml(lead.error_message || '')}">Failed</span>`;
        } else if (lead.status === 'approved') {
            statusBadge = `<span class="px-2.5 py-0.5 rounded-full bg-[#64D2FF]/15 text-[#64D2FF] font-medium text-[10px] border border-[#64D2FF]/25">Approved</span>`;
        } else if (lead.status === 'generated') {
            statusBadge = `<span class="px-2.5 py-0.5 rounded-full bg-[#BF5AF2]/15 text-[#BF5AF2] font-medium text-[10px] border border-[#BF5AF2]/25">AI Ready</span>`;
        } else {
            statusBadge = `<span class="px-2.5 py-0.5 rounded-full bg-white/[0.06] text-white/50 font-medium text-[10px] border border-white/[0.08]">Pending</span>`;
        }

        const subjectSnippet = lead.email_subject 
            ? `<div class="truncate max-w-xs font-medium text-white/90">${escapeHtml(lead.email_subject)}</div><div class="text-[10px] text-white/40 truncate max-w-xs mt-0.5">${escapeHtml(lead.email_body || '')}</div>` 
            : `<span class="text-white/30 italic text-[11px]">Not generated yet</span>`;

        return `
            <tr class="hover:bg-white/[0.03] transition duration-150">
                <td class="py-3 px-4">
                    <div class="font-semibold text-white apple-display">${escapeHtml(lead.first_name || 'Prospect')}</div>
                    <div class="text-xs text-[#0A84FF] font-medium">${escapeHtml(lead.company || '')}</div>
                </td>
                <td class="py-3 px-4">
                    <div class="text-white/80">${escapeHtml(lead.job_title || 'N/A')}</div>
                    ${lead.website ? `<a href="https://${lead.website}" target="_blank" class="text-[10px] text-white/40 hover:text-[#0A84FF] underline">${escapeHtml(lead.website)}</a>` : ''}
                </td>
                <td class="py-3 px-4 font-mono text-white/70 text-[11px]">${escapeHtml(lead.email)}</td>
                <td class="py-3 px-4">${statusBadge}</td>
                <td class="py-3 px-4 cursor-pointer" onclick="openLeadModal(${lead.id})">${subjectSnippet}</td>
                <td class="py-3 px-4 text-right">
                    <div class="flex items-center justify-end space-x-1">
                        <button onclick="sendSingleLeadDirect(${lead.id})" title="Send This Email Now to Prospect" class="apple-btn p-1.5 rounded-full hover:bg-[#30D158]/20 text-[#30D158]">
                            <i data-lucide="send" class="w-3.5 h-3.5"></i>
                        </button>
                        <button onclick="generateSingleLeadAI(${lead.id})" title="Generate / Re-write with Groq AI" class="apple-btn p-1.5 rounded-full hover:bg-[#BF5AF2]/20 text-[#BF5AF2]">
                            <i data-lucide="sparkles" class="w-3.5 h-3.5"></i>
                        </button>
                        <button onclick="approveLeadDirect(${lead.id})" title="Approve Draft for Sending" class="apple-btn p-1.5 rounded-full hover:bg-[#64D2FF]/20 text-[#64D2FF]">
                            <i data-lucide="check" class="w-3.5 h-3.5"></i>
                        </button>
                        <button onclick="sendLeadPreviewDirect(${lead.id})" title="Send Test Copy to My Inbox" class="apple-btn p-1.5 rounded-full hover:bg-white/10 text-white/60 hover:text-white">
                            <i data-lucide="mail-check" class="w-3.5 h-3.5"></i>
                        </button>
                        <button onclick="openLeadModal(${lead.id})" title="Inspect & Edit Email" class="apple-btn p-1.5 rounded-full hover:bg-[#0A84FF]/20 text-[#0A84FF]">
                            <i data-lucide="eye" class="w-3.5 h-3.5"></i>
                        </button>
                        <button onclick="deleteLead(${lead.id})" title="Delete Lead" class="apple-btn p-1.5 rounded-full hover:bg-[#FF453A]/20 text-[#FF453A]">
                            <i data-lucide="trash-2" class="w-3.5 h-3.5"></i>
                        </button>
                    </div>
                </td>
            </tr>
        `;
    }).join('');

    lucide.createIcons();
}

function filterLeads(filter) {
    currentFilter = filter;
    ['all', 'pending', 'generated', 'approved', 'sent', 'failed'].forEach(f => {
        const btn = document.getElementById(`filter-${f}`);
        if (btn) {
            if (f === filter) {
                btn.className = "segmented-item segmented-active px-3 py-1 text-xs";
            } else {
                btn.className = "segmented-item px-3 py-1 text-xs text-white/50 hover:text-white";
            }
        }
    });
    fetchLeads();
}

let searchTimeout = null;
function searchLeads(event) {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
        currentSearch = event.target.value.trim();
        fetchLeads();
    }, 250);
}

// ----------------- CSV & EXCEL UPLOAD PREVIEW -----------------
async function handleFileSelect(event) {
    const file = event.target.files[0];
    if (!file) return;
    stagedUploadFile = file;

    const formData = new FormData();
    formData.append("file", file);

    try {
        const res = await fetch("/api/leads/preview-file", {
            method: "POST",
            body: formData
        });
        const data = await res.json();
        if (!res.ok) {
            alert(`File preview error: ${data.detail || "Error reading file"}`);
            return;
        }

        openImportModal(data);
    } catch (e) {
        alert(`Error: ${e.message}`);
    }
    event.target.value = "";
}

function openImportModal(fileData) {
    document.getElementById('import-file-details').innerText = `${fileData.filename} • ${fileData.total_rows} rows found`;

    const cols = fileData.columns;
    const map = fileData.suggested_mapping;

    const fields = [
        { id: 'map-email', key: 'email', req: true },
        { id: 'map-first-name', key: 'first_name', req: false },
        { id: 'map-company', key: 'company', req: false },
        { id: 'map-job-title', key: 'job_title', req: false },
        { id: 'map-website', key: 'website', req: false },
        { id: 'map-notes', key: 'notes', req: false },
    ];

    fields.forEach(f => {
        const sel = document.getElementById(f.id);
        sel.innerHTML = `<option value="">-- None / Skip --</option>` + cols.map(c => {
            const isSelected = map[f.key] === c ? 'selected' : '';
            return `<option value="${escapeHtml(c)}" ${isSelected}>${escapeHtml(c)}</option>`;
        }).join('');
    });

    // Populate Top 5 preview table
    const thead = document.getElementById('import-preview-thead');
    const tbody = document.getElementById('import-preview-tbody');

    thead.innerHTML = `<tr>${cols.map(c => `<th class="py-2 px-3">${escapeHtml(c)}</th>`).join('')}</tr>`;
    tbody.innerHTML = fileData.preview_rows.map(row => {
        return `<tr>${cols.map(c => `<td class="py-1.5 px-3 whitespace-nowrap overflow-hidden text-ellipsis max-w-xs">${escapeHtml(String(row[c] || ''))}</td>`).join('')}</tr>`;
    }).join('');

    document.getElementById('import-modal').classList.remove('hidden');
    lucide.createIcons();
}

function closeImportModal() {
    document.getElementById('import-modal').classList.add('hidden');
    stagedUploadFile = null;
}

async function confirmImport() {
    if (!stagedUploadFile) return;

    const formData = new FormData();
    formData.append("file", stagedUploadFile);
    formData.append("email_col", document.getElementById('map-email').value);
    formData.append("first_name_col", document.getElementById('map-first-name').value);
    formData.append("company_col", document.getElementById('map-company').value);
    formData.append("job_title_col", document.getElementById('map-job-title').value);
    formData.append("website_col", document.getElementById('map-website').value);
    formData.append("notes_col", document.getElementById('map-notes').value);

    try {
        const res = await fetch("/api/leads/upload", {
            method: "POST",
            body: formData
        });
        const data = await res.json();
        if (res.ok) {
            closeImportModal();
            alert(`Success! Imported ${data.imported} leads (${data.duplicates} duplicates skipped).`);
            await fetchStats();
            await fetchLeads();
        } else {
            alert(`Import failed: ${data.detail || "Error"}`);
        }
    } catch (e) {
        alert(`Error importing file: ${e.message}`);
    }
}

// ----------------- APPROVAL & PREVIEW -----------------
async function approveLeadDirect(leadId) {
    try {
        const res = await fetch(`/api/leads/${leadId}/approve`, { method: "POST" });
        if (res.ok) {
            await fetchStats();
            await fetchLeads();
        }
    } catch (e) {
        alert(e.message);
    }
}

async function approveAllGenerated() {
    if (!confirm("Approve all AI-generated drafts for sending?")) return;
    try {
        await fetch("/api/leads/approve-all", { method: "POST" });
        await fetchStats();
        await fetchLeads();
    } catch (e) {
        alert(e.message);
    }
}

async function sendLeadPreviewDirect(leadId) {
    const lead = leadsData.find(l => l.id === leadId);
    if (!lead) return;
    if (!lead.email_subject || !lead.email_body) {
        alert("Please generate the AI email for this lead first before sending a preview.");
        return;
    }
    if (!confirm(`Send an exact test copy of the email for "${lead.company || lead.email}" to your authenticated Gmail inbox?`)) return;

    try {
        const res = await fetch(`/api/leads/${leadId}/send-preview`, { method: "POST" });
        const data = await res.json();
        if (res.ok) {
            alert(data.message || "Preview sent to your inbox! Check your Gmail.");
        } else {
            alert(data.detail || "Failed to send preview");
        }
    } catch (e) {
        alert(e.message);
    }
}

async function sendSingleLeadDirect(leadId) {
    const lead = leadsData.find(l => l.id === leadId);
    if (!lead) return;
    const recipient = lead.email;
    const company = lead.company || "prospect";

    if (!confirm(`Are you sure you want to send this cold outreach email directly to ${recipient} (${company}) now?`)) {
        return;
    }

    try {
        const res = await fetch(`/api/leads/${leadId}/send-now`, { method: "POST" });
        const data = await res.json();
        if (res.ok) {
            alert(data.message || `Outreach email delivered to ${recipient}!`);
            await fetchStats();
            await fetchLeads();
        } else {
            alert(`Send failed: ${data.detail || "Error"}`);
        }
    } catch (e) {
        alert(`Error sending email: ${e.message}`);
    }
}

async function modalSendLeadNow() {
    if (!activeModalLead) return;
    await saveModalChanges(false);
    await sendSingleLeadDirect(activeModalLead.id);
    closeLeadModal();
}

async function sendPreviewOfActiveLead() {
    if (!activeModalLead) return;
    await sendLeadPreviewDirect(activeModalLead.id);
}

async function modalApproveLead() {
    if (!activeModalLead) return;
    await approveLeadDirect(activeModalLead.id);
    closeLeadModal();
}

// ----------------- AI PERSONALIZATION -----------------
async function generateSingleLeadAI(leadId) {
    try {
        const res = await fetch(`/api/leads/${leadId}/generate`, { method: "POST" });
        const data = await res.json();
        if (res.ok) {
            await fetchStats();
            await fetchLeads();
            await fetchGroqLimits();
        } else {
            alert(data.detail || "Error generating email");
        }
    } catch (e) {
        alert(e.message);
    }
}

async function batchGenerateAI() {
    if (!confirm("Generate personalized emails for all pending leads using Groq AI?")) return;
    try {
        const res = await fetch("/api/leads/batch-generate", { method: "POST" });
        const data = await res.json();
        alert(`Completed! Generated ${data.count} personalized cold emails.`);
        await fetchStats();
        await fetchLeads();
        await fetchGroqLimits();
    } catch (e) {
        alert(e.message);
    }
}

async function runTestAIGeneration() {
    if (leadsData.length === 0) {
        alert("Please upload leads first to test AI generation.");
        return;
    }
    const sampleLead = leadsData[0];
    try {
        const res = await fetch(`/api/leads/${sampleLead.id}/generate`, { method: "POST" });
        const data = await res.json();
        if (res.ok) {
            const gen = data.generated;
            document.getElementById('ai-preview-box').classList.remove('hidden');
            document.getElementById('preview-subject').innerText = gen.subject;
            document.getElementById('preview-source').innerText = gen.source;
            document.getElementById('preview-hook').innerText = `Automation Angle: ${gen.custom_hook}`;
            document.getElementById('preview-body').innerText = gen.body;
            await fetchLeads();
            await fetchGroqLimits();
        } else {
            alert(data.detail || "Failed to generate sample email");
        }
    } catch (e) {
        alert(e.message);
    }
}

// ----------------- CAMPAIGN ACTIONS -----------------
async function startCampaign(dryRun = false) {
    const onlyApproved = document.getElementById('check-only-approved').checked;
    const mode = dryRun ? "Dry-Run Simulation" : "LIVE Send";

    const approvedCount = parseInt(document.getElementById('stat-approved').innerText || '0');
    const totalCount = parseInt(document.getElementById('stat-total').innerText || '0');

    if (totalCount === 0) {
        alert("No leads found in database. Please import a CSV or Excel spreadsheet first.");
        return;
    }

    if (onlyApproved && approvedCount === 0) {
        const doApprove = confirm("You have 'Only Send Approved' checked, but 0 leads are currently approved.\n\nWould you like to approve all AI-generated drafts now and start outreach?");
        if (doApprove) {
            await approveAllGenerated();
        } else {
            return;
        }
    }

    if (!dryRun) {
        let msg = "Are you sure you want to start sending LIVE cold outreach emails?";
        if (onlyApproved) msg += "\n(Only leads marked 'Approved' will be sent).";
        if (!confirm(msg)) return;
    }

    try {
        const res = await fetch("/api/campaign/start", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ dry_run: dryRun, only_approved: onlyApproved })
        });
        const data = await res.json();
        if (res.ok) {
            await fetchStats();
            scheduleNextPoll(1000);
        } else {
            alert(data.detail || "Failed to start campaign");
        }
    } catch (e) {
        alert(e.message);
    }
}

async function pauseCampaign() {
    try {
        await fetch("/api/campaign/pause", { method: "POST" });
        await fetchStats();
    } catch (e) {
        alert(e.message);
    }
}

async function stopCampaign() {
    if (!confirm("Stop the current outreach campaign?")) return;
    try {
        await fetch("/api/campaign/stop", { method: "POST" });
        await fetchStats();
    } catch (e) {
        alert(e.message);
    }
}

async function resetStatuses() {
    if (!confirm("Reset all lead statuses back to 'pending'? (This allows re-sending)")) return;
    try {
        await fetch("/api/leads/reset-status", { method: "POST" });
        await fetchStats();
        await fetchLeads();
    } catch (e) {
        alert(e.message);
    }
}

async function clearAllLeads() {
    if (!confirm("Are you sure you want to delete ALL leads and logs? This will clean out the database completely.")) return;
    try {
        await fetch("/api/leads/clear", { method: "POST" });
        await fetchStats();
        await fetchLeads();
    } catch (e) {
        alert(e.message);
    }
}

async function deleteLead(leadId) {
    try {
        await fetch(`/api/leads/${leadId}`, { method: "DELETE" });
        await fetchStats();
        await fetchLeads();
    } catch (e) {
        alert(e.message);
    }
}

// ----------------- SETTINGS & SMTP -----------------
async function fetchSettings() {
    try {
        const res = await fetch("/api/settings");
        const data = await res.json();
        const s = data.settings;

        document.getElementById('smtp-host').value = s.smtp_host || '';
        document.getElementById('smtp-port').value = s.smtp_port || '587';
        document.getElementById('smtp-user').value = s.smtp_user || '';
        document.getElementById('smtp-password').value = s.smtp_password_masked || '';
        document.getElementById('from-name').value = s.from_name || '';
        document.getElementById('reply-to').value = s.reply_to || '';

        document.getElementById('input-delay-min').value = s.delay_min_seconds || '35';
        document.getElementById('input-delay-max').value = s.delay_max_seconds || '75';
        document.getElementById('val-delay-min').innerText = s.delay_min_seconds || '35';
        document.getElementById('val-delay-max').innerText = s.delay_max_seconds || '75';
        document.getElementById('input-daily-limit').value = s.daily_send_limit || '40';

        document.getElementById('ai-agency-name').value = s.agency_name || '';
        document.getElementById('ai-sender-name').value = s.from_name || '';
        document.getElementById('ai-custom-prompt').value = s.agency_pitch || '';
        document.getElementById('gemini-api-key').value = s.gemini_api_key || '';
        if (document.getElementById('groq-api-key')) {
            document.getElementById('groq-api-key').value = s.groq_api_key || '';
        }
        if (document.getElementById('ai-provider-select')) {
            document.getElementById('ai-provider-select').value = s.ai_provider || 'groq';
        }
        if (document.getElementById('groq-model-select')) {
            document.getElementById('groq-model-select').value = s.groq_model || 'openai/gpt-oss-120b';
        }
        return s;
    } catch (e) {
        console.error('Error fetching settings:', e);
        return null;
    }
}

function applyPreset(provider) {
    if (provider === 'gmail') {
        document.getElementById('smtp-host').value = 'smtp.gmail.com';
        document.getElementById('smtp-port').value = '587';
        alert("Gmail preset applied! Make sure to use your 16-character Google App Password.");
    } else if (provider === 'outlook') {
        document.getElementById('smtp-host').value = 'smtp.office365.com';
        document.getElementById('smtp-port').value = '587';
    }
}

async function saveSMTPSettings(showAlert = true) {
    const payload = {
        smtp_host: document.getElementById('smtp-host').value.trim(),
        smtp_port: document.getElementById('smtp-port').value.trim(),
        smtp_user: document.getElementById('smtp-user').value.trim(),
        smtp_password: document.getElementById('smtp-password').value.trim(),
        from_name: document.getElementById('from-name').value.trim(),
        reply_to: document.getElementById('reply-to').value.trim(),
        delay_min_seconds: document.getElementById('input-delay-min').value.trim(),
        delay_max_seconds: document.getElementById('input-delay-max').value.trim(),
        daily_send_limit: document.getElementById('input-daily-limit').value.trim(),
    };

    try {
        const res = await fetch("/api/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        if (res.ok && showAlert) alert("Mailbox & safety settings saved successfully!");
        else if (!res.ok && showAlert) alert("Failed to save settings");
    } catch (e) {
        if (showAlert) alert(e.message);
    }
}

async function saveAISettings() {
    const payload = {
        agency_name: document.getElementById('ai-agency-name').value.trim(),
        from_name: document.getElementById('ai-sender-name').value.trim(),
        agency_pitch: document.getElementById('ai-custom-prompt').value.trim(),
        ai_provider: document.getElementById('ai-provider-select').value,
        groq_model: document.getElementById('groq-model-select').value,
    };
    try {
        const res = await fetch("/api/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        if (res.ok) alert("AI Agency Profile & Provider saved!");
    } catch (e) {
        alert(e.message);
    }
}

async function saveAllSettings() {
    const payload = {
        gemini_api_key: document.getElementById('gemini-api-key').value.trim(),
        groq_api_key: document.getElementById('groq-api-key') ? document.getElementById('groq-api-key').value.trim() : ""
    };
    try {
        const res = await fetch("/api/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        if (res.ok) {
            alert("Settings saved!");
            await fetchGroqLimits(true);
        }
    } catch (e) {
        alert(e.message);
    }
}

async function testSMTPConnection() {
    await saveSMTPSettings(false);
    try {
        const res = await fetch("/api/smtp/test-connection", { method: "POST" });
        const data = await res.json();
        alert(data.message);
    } catch (e) {
        alert(`Test connection error: ${e.message}`);
    }
}

async function sendTestEmail() {
    const target = document.getElementById('test-target-email').value.trim();
    if (!target) {
        alert("Please enter a destination email address.");
        return;
    }
    await saveSMTPSettings(false);
    try {
        const res = await fetch("/api/smtp/test-send", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ target_email: target })
        });
        const data = await res.json();
        alert(data.message);
    } catch (e) {
        alert(e.message);
    }
}

// ----------------- ACCOUNT ONBOARDING (FOR YOU & FRIENDS) -----------------
function openAccountModal() {
    const fromName = document.getElementById('from-name') ? document.getElementById('from-name').value : '';
    const agencyName = document.getElementById('ai-agency-name') ? document.getElementById('ai-agency-name').value : '';
    const smtpUser = document.getElementById('smtp-user') ? document.getElementById('smtp-user').value : '';
    const groqKey = document.getElementById('groq-api-key') ? document.getElementById('groq-api-key').value : '';

    document.getElementById('acc-from-name').value = fromName;
    document.getElementById('acc-agency-name').value = agencyName;
    document.getElementById('acc-email').value = smtpUser;
    document.getElementById('acc-password').value = '';
    document.getElementById('acc-groq-key').value = groqKey;

    const statusBox = document.getElementById('acc-status-box');
    statusBox.classList.add('hidden');
    statusBox.innerHTML = '';

    document.getElementById('account-modal').classList.remove('hidden');
    lucide.createIcons();
}

function closeAccountModal() {
    document.getElementById('account-modal').classList.add('hidden');
}

async function submitQuickSetup() {
    const btn = document.getElementById('btn-save-account');
    const originalText = btn.innerHTML;
    btn.innerHTML = `<span>Connecting...</span>`;

    const payload = {
        from_name: document.getElementById('acc-from-name').value.trim(),
        agency_name: document.getElementById('acc-agency-name').value.trim(),
        smtp_user: document.getElementById('acc-email').value.trim(),
        smtp_password: document.getElementById('acc-password').value.trim(),
        groq_api_key: document.getElementById('acc-groq-key').value.trim()
    };

    try {
        const res = await fetch("/api/account/quick-setup", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        const statusBox = document.getElementById('acc-status-box');
        statusBox.classList.remove('hidden');

        if (data.smtp_ok && data.groq_ok) {
            statusBox.className = "rounded-xl p-3 text-xs bg-[#30D158]/10 text-[#30D158] border border-[#30D158]/25";
            statusBox.innerHTML = `<strong>Connected & Verified!</strong><br>Gmail SMTP login succeeded and Groq AI is active with 1,000 daily requests. You are ready to send.`;
            await fetchSettings();
            await fetchGroqLimits(true);
            setTimeout(() => {
                closeAccountModal();
            }, 1800);
        } else {
            let errorText = "<strong>Configuration Warnings:</strong><br>";
            if (!data.smtp_ok) errorText += `• Gmail SMTP: ${escapeHtml(data.smtp_message)}<br>`;
            if (!data.groq_ok) errorText += `• Groq AI: ${escapeHtml(data.groq_message)}<br>`;
            statusBox.className = "rounded-xl p-3 text-xs bg-[#FF9F0A]/10 text-[#FF9F0A] border border-[#FF9F0A]/25";
            statusBox.innerHTML = errorText;
            await fetchSettings();
            await fetchGroqLimits(true);
        }
    } catch (e) {
        alert("Setup failed: " + e.message);
    } finally {
        btn.innerHTML = originalText;
        lucide.createIcons();
    }
}

async function clearAccountForFriend() {
    if (!confirm("This will clear all saved email passwords and API keys from the application so your friend can start with a fresh slate.\n\nContinue?")) return;
    try {
        const res = await fetch("/api/account/clear", { method: "POST" });
        const data = await res.json();
        alert(data.message || "Credentials cleared!");
        document.getElementById('acc-email').value = '';
        document.getElementById('acc-password').value = '';
        document.getElementById('acc-groq-key').value = '';
        await fetchSettings();
        await fetchGroqLimits(true);
        closeAccountModal();
    } catch (e) {
        alert(e.message);
    }
}

// ----------------- LOGS -----------------
async function fetchLogs() {
    try {
        const res = await fetch("/api/logs?limit=80");
        const data = await res.json();
        const logs = data.logs || [];
        const container = document.getElementById('logs-container');
        if (logs.length === 0) {
            container.innerHTML = '<div class="text-slate-500">No activity logged yet.</div>';
            return;
        }

        container.innerHTML = logs.map(l => {
            let color = 'text-slate-400';
            if (l.level === 'SUCCESS') color = 'text-emerald-400';
            else if (l.level === 'WARNING') color = 'text-amber-400';
            else if (l.level === 'ERROR') color = 'text-rose-400';

            return `
                <div class="flex items-start space-x-2 py-0.5 border-b border-slate-900/80">
                    <span class="text-slate-500 text-[10px] whitespace-nowrap">${l.timestamp.split('T')[1] || l.timestamp}</span>
                    <span class="text-[10px] font-semibold px-1 rounded bg-slate-900 ${color}">${l.level}</span>
                    <span class="${color} flex-1 break-all">${escapeHtml(l.message)}</span>
                </div>
            `;
        }).join('');
    } catch (e) {
        console.error('Error fetching logs:', e);
    }
}

// ----------------- LEAD MODAL -----------------
function openLeadModal(leadId) {
    const lead = leadsData.find(l => l.id === leadId);
    if (!lead) return;
    activeModalLead = lead;

    document.getElementById('modal-lead-name').innerText = lead.first_name || 'Prospect';
    document.getElementById('modal-lead-company').innerText = lead.company || 'Company';
    document.getElementById('modal-lead-title').innerText = `${lead.job_title || ''} • ${lead.email}`;

    document.getElementById('modal-subject').value = lead.email_subject || '';
    document.getElementById('modal-body').value = lead.email_body || '';
    
    const hookEl = document.getElementById('modal-hook');
    if (lead.custom_hook) {
        hookEl.classList.remove('hidden');
        hookEl.innerText = `Groq AI Automation Angle: ${lead.custom_hook}`;
    } else {
        hookEl.classList.add('hidden');
    }

    document.getElementById('lead-modal').classList.remove('hidden');
    lucide.createIcons();
}

function closeLeadModal() {
    document.getElementById('lead-modal').classList.add('hidden');
    activeModalLead = null;
}

async function saveModalChanges(showAlert = true) {
    if (!activeModalLead) return;
    const payload = {
        email_subject: document.getElementById('modal-subject').value.trim(),
        email_body: document.getElementById('modal-body').value.trim(),
        status: 'generated'
    };
    try {
        const res = await fetch(`/api/leads/${activeModalLead.id}/update`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        if (res.ok) {
            if (showAlert) alert("Changes saved!");
            closeLeadModal();
            await fetchStats();
            await fetchLeads();
        }
    } catch (e) {
        if (showAlert) alert(e.message);
    }
}

async function modalRegenerateAI() {
    if (!activeModalLead) return;
    try {
        const res = await fetch(`/api/leads/${activeModalLead.id}/generate`, { method: "POST" });
        const data = await res.json();
        if (res.ok) {
            const gen = data.generated;
            document.getElementById('modal-subject').value = gen.subject;
            document.getElementById('modal-body').value = gen.body;
            const hookEl = document.getElementById('modal-hook');
            hookEl.classList.remove('hidden');
            hookEl.innerText = `Groq AI Automation Angle: ${gen.custom_hook}`;
            await fetchLeads();
            await fetchGroqLimits();
        } else {
            alert(data.detail || "Failed to generate email");
        }
    } catch (e) {
        alert(e.message);
    }
}

function escapeHtml(text) {
    if (!text) return '';
    return text
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}
