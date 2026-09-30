
const API_BASE_URL = 'http://127.0.0.1:5000/api';
let currentSessionToken = null;
let currentFacts = {};
let currentCaseDetails = {};
let caseHistory = []; // local in-memory history

// DOM Elements
const chatMessages = document.getElementById('chat-messages');
const userInput = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');
const welcomeState = document.getElementById('welcome-state');
const typingIndicator = document.getElementById('typing-indicator');
const historyList = document.getElementById('history-list');
const newChatBtn = document.getElementById('new-chat-btn');
const casePanel = document.getElementById('case-panel');
const caseSummaryContent = document.getElementById('case-summary-content');
const caseTimeline = document.getElementById('case-timeline');
const evidenceChecklist = document.getElementById('evidence-checklist');
const exportBtn = document.getElementById('export-btn');
const exportLink = document.getElementById('export-link');
const glossaryBtn = document.getElementById('glossary-btn');
const glossaryOverlay = document.getElementById('glossary-overlay');
const closeGlossary = document.getElementById('close-glossary');
const glossarySearch = document.getElementById('glossary-search');
const glossaryResults = document.getElementById('glossary-results');

axios.defaults.withCredentials = true;

// Boot up — no auth check needed
document.addEventListener('DOMContentLoaded', () => {
    // Chat listeners
    sendBtn.addEventListener('click', handleSend);
    userInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') handleSend();
    });
    newChatBtn.addEventListener('click', startNewCase);

    // Export listeners
    if (exportBtn) exportBtn.addEventListener('click', handleExport);
    if (exportLink) exportLink.addEventListener('click', (e) => { e.preventDefault(); handleExport(); });

    // Glossary listeners
    if (glossaryBtn) glossaryBtn.addEventListener('click', (e) => { e.preventDefault(); openGlossary(); });
    if (closeGlossary) closeGlossary.addEventListener('click', closeGlossaryModal);
    if (glossarySearch) {
        let debounceTimer;
        glossarySearch.addEventListener('input', () => {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => searchGlossary(glossarySearch.value), 300);
        });
    }

    // Quick-reply suggestion buttons
    const quickBtns = document.querySelectorAll('.quick-reply-btn[data-text]');
    quickBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            userInput.value = btn.getAttribute('data-text');
            handleSend();
        });
    });

    // Start with a fresh session
    startNewCase();
});


function startNewCase() {
    chatMessages.innerHTML = '';
    welcomeState.classList.remove('hidden');
    casePanel.classList.add('hidden');
    if (exportBtn) exportBtn.classList.add('hidden');
    if (exportLink) exportLink.classList.add('hidden');
    currentFacts = {};
    currentCaseDetails = {};
    currentSessionToken = null; // will be assigned by the backend on first message
}


async function handleSend() {
    const text = userInput.value.trim();
    if (!text) return;

    appendMessage('user', text);
    userInput.value = '';
    welcomeState.classList.add('hidden');
    typingIndicator.classList.remove('hidden');

    try {
        const res = await axios.post(`${API_BASE_URL}/analyze`, {
            text: text,
            facts: currentFacts,
            case_details: currentCaseDetails,
            session_token: currentSessionToken
        });

        typingIndicator.classList.add('hidden');
        processResponse(res.data);
    } catch (error) {
        typingIndicator.classList.add('hidden');
        console.error('API error:', error);
        appendMessage('assistant', '<p>I encountered an error processing your request. Please check that the backend server is running and try again.</p>');
    }
}


function processResponse(data) {
    if (!data.success) {
        appendMessage('assistant', '<p>Sorry, something went wrong.</p>');
        return;
    }

    // Store session token and accumulated facts
    currentSessionToken = data.session_token;
    currentFacts = data.case.facts;
    currentCaseDetails = data.case.case_details || {};

    // Add to local case history
    addToHistory(currentSessionToken);

    let responseHtml = '';

    // 1. Conflicts
    if (data.conflicts && data.conflicts.length > 0) {
        responseHtml += '<div class="legal-card" style="border-left: 3px solid #e53e3e;">';
        responseHtml += '<h4 style="color:#e53e3e;">⚠ Potential Conflict</h4>';
        data.conflicts.forEach(c => responseHtml += `<p>${c}</p>`);
        responseHtml += '</div>';
    }

    // 2. Out-of-scope message
    if (data.out_of_scope && data.targeted_question) {
        responseHtml += `<p>${data.targeted_question}</p>`;
        appendMessage('assistant', responseHtml);
        return;
    }

    // 3. Targeted follow-up question (backward chaining)
    if (data.targeted_question && (!data.legal_guidance || data.legal_guidance.length === 0)) {
        responseHtml += `<p>${data.targeted_question}</p>`;
        appendMessage('assistant', responseHtml);
        updateCasePanel(data);
        return;
    }

    // 4. Legal guidance available
    if (data.legal_guidance && data.legal_guidance.length > 0) {
        data.legal_guidance.forEach(g => {
            responseHtml += `<p>Based on what you've told me, this may involve <strong>${g.issue}</strong>.</p>`;

            if (g.applicable_law && g.applicable_law.length > 0) {
                g.applicable_law.forEach(p => {
                    responseHtml += `
                    <div class="legal-card">
                        <h4>📜 Relevant Law</h4>
                        <h3>${p.act_name} — ${p.section_number}</h3>
                        <div class="law-section">
                            <strong>${p.title}</strong>
                            ${p.plain_language_description ? `<p>${p.plain_language_description}</p>` : ''}
                            ${p.applicability ? `<p><em>Applicability:</em> ${p.applicability}</p>` : ''}
                        </div>
                    </div>`;
                });
            }

            if (g.possible_remedies && g.possible_remedies.length > 0) {
                responseHtml += '<div class="list-section mt-4"><h5>💡 Possible Remedies</h5><ul>';
                g.possible_remedies.forEach(r => responseHtml += `<li>${r}</li>`);
                responseHtml += '</ul></div>';
            }

            if (g.next_steps && g.next_steps.length > 0) {
                responseHtml += '<div class="list-section mt-4"><h5>📋 Next Steps</h5><ul>';
                g.next_steps.forEach(step => responseHtml += `<li>${step}</li>`);
                responseHtml += '</ul></div>';
            }
        });

        // Where/how to complain
        if (data.authority) {
            if (data.authority.authority) {
                const auth = data.authority.authority;
                responseHtml += `
                <div class="legal-card">
                    <h4>🏛 Where to Complain</h4>
                    <p><strong>${auth.name}</strong> (${auth.jurisdiction_level || ''})</p>
                    ${auth.description ? `<p>${auth.description}</p>` : ''}
                </div>`;
            } else if (data.authority.note) {
                responseHtml += `<p><em>${data.authority.note}</em></p>`;
            }
        }

        // Offer to generate a complaint draft
        responseHtml += '<p style="margin-top:1rem; font-size:0.9em; color: var(--text-muted);"><em>If you would like a draft complaint template, just say "generate a complaint draft".</em></p>';

        // Show export button
        if (exportBtn) exportBtn.classList.remove('hidden');
        if (exportLink) exportLink.classList.remove('hidden');

    } else if (data.targeted_question) {
        // We have guidance AND a targeted question — show both
        responseHtml += `<p>${data.targeted_question}</p>`;
    } else {
        responseHtml += '<p>I need more information to identify the exact legal issue. Could you clarify what happened?</p>';
    }

    appendMessage('assistant', responseHtml);
    updateCasePanel(data);
}


function updateCasePanel(data) {
    casePanel.classList.remove('hidden');
    const f = data.case.facts;

    // 1. Summary
    let summaryHtml = "<ul>";
    if (f.product) summaryHtml += `<li><strong>Product:</strong> ${f.product}</li>`;
    if (f.product_purchased) summaryHtml += `<li><strong>Status:</strong> Purchased</li>`;
    if (f.product_defective) summaryHtml += `<li><strong>Issue:</strong> Defective/Damaged</li>`;
    if (f.service_purchased) summaryHtml += `<li><strong>Service:</strong> Purchased</li>`;
    if (f.service_deficient) summaryHtml += `<li><strong>Service Issue:</strong> Deficient</li>`;
    if (f.seller_contacted) summaryHtml += `<li><strong>Contact:</strong> Seller contacted</li>`;
    if (f.seller_denied_or_disputed_claim) summaryHtml += `<li><strong>Response:</strong> Claim denied/refused</li>`;
    if (f.refund_requested) summaryHtml += `<li><strong>Remedy:</strong> Refund requested</li>`;
    if (f.replacement_requested) summaryHtml += `<li><strong>Remedy:</strong> Replacement requested</li>`;
    if (f.warranty_exists) summaryHtml += `<li><strong>Warranty:</strong> Product under warranty</li>`;
    if (f.online_transaction) summaryHtml += `<li><strong>Channel:</strong> Online purchase</li>`;
    if (f.product_not_delivered) summaryHtml += `<li><strong>Delivery:</strong> Not delivered</li>`;
    if (f.wrong_product_delivered) summaryHtml += `<li><strong>Delivery:</strong> Wrong product</li>`;
    if (f.misleading_advertisement) summaryHtml += `<li><strong>Ad:</strong> Misleading advertisement</li>`;
    if (f.damaged_on_delivery === true) summaryHtml += `<li><strong>Timing:</strong> Damaged on delivery</li>`;
    if (f.damaged_on_delivery === false) summaryHtml += `<li><strong>Timing:</strong> Damaged after use</li>`;

    if (data.legal_guidance && data.legal_guidance.length > 0) {
        data.legal_guidance.forEach(g => {
            summaryHtml += `<li><strong>Identified Issue:</strong> ${g.issue}</li>`;
        });
    }
    summaryHtml += "</ul>";
    if (summaryHtml === "<ul></ul>") summaryHtml = "<p>No facts gathered yet.</p>";
    caseSummaryContent.innerHTML = summaryHtml;

    // 2. Timeline
    let timelineHtml = '<ul>';
    if (f.product_purchased || f.service_purchased) timelineHtml += '<li>✓ Product/Service purchased</li>';
    if (f.product_defective || f.service_deficient) timelineHtml += '<li>✓ Issue identified (defect/deficiency)</li>';
    if (f.seller_contacted) timelineHtml += '<li>✓ Seller contacted</li>';
    if (f.seller_denied_or_disputed_claim) timelineHtml += '<li>✓ Seller denied/disputed claim</li>';
    if (f.refund_requested || f.replacement_requested) timelineHtml += '<li>✓ Refund/replacement requested</li>';
    if (data.legal_guidance && data.legal_guidance.length > 0) timelineHtml += '<li>→ Legal issue identified</li>';
    timelineHtml += '</ul>';
    if (timelineHtml === '<ul></ul>') timelineHtml = '<p>Timeline will populate as you share details.</p>';
    caseTimeline.innerHTML = timelineHtml;

    // 3. Evidence Checklist
    if (data.documents && data.documents.recommended_documents_display) {
        let evHtml = '<ul>';
        data.documents.recommended_documents_display.forEach(doc => {
            evHtml += `<li>${doc.name}</li>`;
        });
        evHtml += '</ul>';
        if (evHtml === '<ul></ul>') evHtml = '<p>No specific evidence required yet.</p>';
        evidenceChecklist.innerHTML = evHtml;
    } else {
        // Fallback evidence checklist
        let evHtml = "<ul>";
        if (f.online_transaction) evHtml += "<li>Order Confirmation</li><li>Online Payment Receipt</li>";
        if (f.product_defective) evHtml += "<li>Photos of Defect</li><li>Videos of Malfunction</li>";
        if (f.seller_contacted) evHtml += "<li>Emails/Chats with Seller</li>";
        if (f.warranty_exists) evHtml += "<li>Warranty Card/Document</li>";
        evHtml += "</ul>";
        if (evHtml === "<ul></ul>") evHtml = "<p>No specific evidence required yet.</p>";
        evidenceChecklist.innerHTML = evHtml;
    }
}


function appendMessage(sender, content) {
    const wrapper = document.createElement('div');
    wrapper.className = `message-wrapper ${sender}`;

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';

    if (sender === 'user') {
        bubble.textContent = content;
    } else {
        bubble.innerHTML = content;
    }

    wrapper.appendChild(bubble);
    chatMessages.appendChild(wrapper);

    setTimeout(() => {
        const container = document.getElementById('chat-container');
        container.scrollTop = container.scrollHeight;
    }, 10);
}


// ---------------------------------------------------------
// Case History (local, in-memory)
// ---------------------------------------------------------

function addToHistory(token) {
    // Only add if not already present
    if (caseHistory.find(c => c.token === token)) return;
    caseHistory.unshift({
        token: token,
        date: new Date().toLocaleDateString(),
        label: 'Case ' + (caseHistory.length + 1)
    });
    renderHistory();
}

function renderHistory() {
    historyList.innerHTML = '';
    caseHistory.forEach(c => {
        const li = document.createElement('li');
        li.textContent = c.date + ' — ' + c.label;
        li.onclick = () => {
            currentSessionToken = c.token;
            // Re-send empty to reload facts (the backend returns accumulated facts)
            // For now, just indicate the case is loaded
            chatMessages.innerHTML = '';
            welcomeState.classList.add('hidden');
            casePanel.classList.remove('hidden');
            appendMessage('assistant', '<p>Case context loaded. How would you like to proceed?</p>');
        };
        historyList.appendChild(li);
    });
}


// ---------------------------------------------------------
// Export
// ---------------------------------------------------------

async function handleExport() {
    if (!currentSessionToken) {
        appendMessage('assistant', '<p>No active case to export. Please start a conversation first.</p>');
        return;
    }

    try {
        const res = await axios.post(`${API_BASE_URL}/export`, {
            session_token: currentSessionToken
        });

        if (res.data.success) {
            // Create a downloadable JSON file
            const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `case_export_${currentSessionToken.substring(0, 8)}.json`;
            a.click();
            URL.revokeObjectURL(url);
            appendMessage('assistant', '<p>📄 Case exported successfully.</p>');
        }
    } catch (e) {
        console.error('Export error:', e);
        appendMessage('assistant', '<p>Failed to export case. Please try again.</p>');
    }
}


// ---------------------------------------------------------
// Glossary
// ---------------------------------------------------------

function openGlossary() {
    glossaryOverlay.classList.remove('hidden');
    glossarySearch.value = '';
    glossaryResults.innerHTML = '<p style="color:var(--text-muted);">Type to search legal terms, sections, or concepts...</p>';
    glossarySearch.focus();
}

function closeGlossaryModal() {
    glossaryOverlay.classList.add('hidden');
}

async function searchGlossary(query) {
    try {
        const res = await axios.get(`${API_BASE_URL}/glossary`, { params: { q: query } });
        const results = res.data.results || [];

        if (results.length === 0) {
            glossaryResults.innerHTML = '<p style="color:var(--text-muted);">No results found.</p>';
            return;
        }

        let html = '';
        results.forEach(r => {
            if (r.type === 'concept') {
                html += `
                <div class="legal-card" style="margin-bottom:0.75rem;">
                    <strong>${r.key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}</strong>
                    <span style="color:var(--text-muted); font-size:0.8em;"> (${r.domain})</span>
                    <p>${r.description}</p>
                </div>`;
            } else if (r.type === 'provision') {
                html += `
                <div class="legal-card" style="margin-bottom:0.75rem;">
                    <strong>${r.act_name} — ${r.section_number}</strong>
                    <h4>${r.title}</h4>
                    ${r.description ? `<p>${r.description}</p>` : ''}
                </div>`;
            }
        });
        glossaryResults.innerHTML = html;
    } catch (e) {
        glossaryResults.innerHTML = '<p style="color:#e53e3e;">Error searching glossary.</p>';
    }
}
