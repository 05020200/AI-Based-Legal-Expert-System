
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
const questionnaire = document.getElementById('questionnaire');
const questionFields = document.getElementById('question-fields');
let questionnaireQuestions = [];
let currentReport = null;

axios.defaults.withCredentials = true;

// Boot up — no auth check needed
document.addEventListener('DOMContentLoaded', () => {
    questionnaire.addEventListener('submit', handleQuestionnaireSubmit);
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
    currentReport = null;
    currentSessionToken = null; // will be assigned by the backend on first message
    loadQuestionnaire();
}


async function loadQuestionnaire() {
    try {
        const response = await axios.get(`${API_BASE_URL}/phase1/questions`);
        questionnaireQuestions = response.data.questions;
        questionFields.innerHTML = questionnaireQuestions.map(renderQuestion).join('');
    } catch (error) {
        questionFields.innerHTML = '<p role="alert">The questionnaire could not be loaded. Please refresh and try again.</p>';
    }
}


function renderQuestion(question) {
    const key = escapeHtml(question.key);
    const prompt = escapeHtml(question.prompt);
    if (question.type === 'choice') {
        const options = question.options.map(option =>
            `<option value="${escapeHtml(option.value)}">${escapeHtml(option.label)}</option>`
        ).join('');
        return `<label class="question-field" for="question-${key}">
            <span>${prompt}</span>
            <select id="question-${key}" name="${key}" required>
                <option value="" selected disabled>Select an option</option>${options}
            </select>
        </label>`;
    }

    const options = question.options.map((option, index) => `
        <label class="answer-option" for="question-${key}-${index}">
            <input id="question-${key}-${index}" type="radio" name="${key}" value="${option.value}" required>
            <span>${escapeHtml(option.label)}</span>
        </label>`).join('');
    return `<fieldset class="question-field">
        <legend>${prompt}</legend>
        <div class="answer-options">${options}</div>
    </fieldset>`;
}


async function handleQuestionnaireSubmit(event) {
    event.preventDefault();
    if (!questionnaire.reportValidity()) return;

    const formData = new FormData(questionnaire);
    const answers = {};
    questionnaireQuestions.forEach(question => {
        const value = formData.get(question.key);
        answers[question.key] = question.type === 'boolean' ? value === 'true' : value;
    });
    const caseDetails = {};
    ['product_name', 'seller_name', 'purchase_date', 'amount_paid',
        'order_or_invoice_number', 'problem_description', 'seller_response'].forEach(key => {
        const value = String(formData.get(key) || '').trim();
        if (value) caseDetails[key] = value;
    });

    typingIndicator.classList.remove('hidden');

    try {
        const res = await axios.post(`${API_BASE_URL}/phase1/analyze`, {
            answers,
            case_details: caseDetails,
            session_token: currentSessionToken
        });

        typingIndicator.classList.add('hidden');
        processResponse(res.data);
    } catch (error) {
        typingIndicator.classList.add('hidden');
        console.error('API error:', error);
        const message = error.response?.data?.error || 'The report could not be prepared. Please try again.';
        appendMessage('assistant', `<p role="alert">${escapeHtml(message)}</p>`);
    }
}


function processResponse(data) {
    if (!data.success) {
        appendMessage('assistant', '<p role="alert">The report could not be prepared. Please try again.</p>');
        return;
    }

    currentSessionToken = data.session_token;
    currentReport = data.report;
    addToHistory(currentSessionToken);
    welcomeState.classList.add('hidden');
    appendMessage('assistant', renderReport(data.report));
    updateCasePanel(data.report);
    if (exportBtn) exportBtn.classList.remove('hidden');
    if (exportLink) exportLink.classList.remove('hidden');
}


function renderReport(report) {
    const law = report.legal_provision ? `
        <section class="legal-card">
            <h3>Relevant Legal Provision</h3>
            <h4>${escapeHtml(report.legal_provision.act_name)} — ${escapeHtml(report.legal_provision.section_number)}</h4>
            <strong>${escapeHtml(report.legal_provision.title)}</strong>
            <p>${escapeHtml(report.legal_provision.description)}</p>
            <a href="${escapeHtml(report.legal_provision.source_url)}" target="_blank" rel="noopener noreferrer">View source</a>
        </section>` : '';
    const options = report.possible_options.map(item => `<li>${escapeHtml(item)}</li>`).join('');
    const evidence = report.evidence_checklist.map(item => `
        <li>${escapeHtml(item.name)} <span>${item.available ? 'Available' : 'Not currently available'}</span></li>`).join('');
    const steps = report.next_steps.map(item => `<li>${escapeHtml(item)}</li>`).join('');

    return `<h2>${escapeHtml(report.title)}</h2>
        <p class="report-assessment">${escapeHtml(report.assessment)}</p>
        <section class="legal-card"><h3>Why these facts may matter</h3><p>${escapeHtml(report.why_relevant)}</p></section>
        ${law}
        <section class="legal-card"><h3>Possible options</h3><ul>${options}</ul></section>
        <section class="legal-card"><h3>Evidence to preserve</h3><ul class="report-evidence">${evidence}</ul></section>
        <section class="legal-card"><h3>Practical next steps</h3><ul>${steps}</ul></section>
        <section class="legal-card"><h3>Case Summary</h3>${renderSummary(report.case_summary)}</section>
        <p class="report-disclaimer">${escapeHtml(report.disclaimer)}</p>`;
}


function renderSummary(summary) {
    const resolution = summary.seller_response_resolution;
    const items = [
        ['Selected issue', summary.selected_issue],
        ['Purchased from a seller or business', yesNo(summary.product_purchased)],
        ['Product has a problem', yesNo(summary.product_has_problem)],
        ['Product name', summary.product_name],
        ['Seller name', summary.seller_name],
        ['Purchase date', summary.purchase_date],
        ['Amount paid', summary.amount_paid === null ? null : summary.amount_paid],
        ['Order / invoice number', summary.order_or_invoice_number],
        ['Problem / situation', summary.problem_situation],
        ['Seller contacted', yesNo(summary.seller_contacted)],
        ['Seller resolution', yesNo(resolution.problem_resolved)],
        ['Seller response details', resolution.response_details],
        ['Desired resolution', summary.desired_resolution],
    ];
    Object.entries(summary.evidence_availability).forEach(([name, available]) => {
        items.push([`Evidence: ${name}`, yesNo(available)]);
    });
    return `<dl class="summary-list">${items.map(([label, value]) => `
        <div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value === null || value === undefined || value === '' ? 'Not provided' : value)}</dd></div>`).join('')}
    </dl>`;
}


function yesNo(value) {
    return value === true ? 'Yes' : value === false ? 'No' : 'Not provided';
}


function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, character => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    })[character]);
}


function updateCasePanel(report) {
    casePanel.classList.remove('hidden');
    caseSummaryContent.innerHTML = renderSummary(report.case_summary);
    evidenceChecklist.innerHTML = `<ul>${report.evidence_checklist.map(item => `
        <li>${escapeHtml(item.name)} <span>${item.available ? 'Available' : 'Not currently available'}</span></li>`).join('')}
    </ul>`;
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
    if (!currentReport) {
        appendMessage('assistant', '<p>Prepare a guidance report before exporting.</p>');
        return;
    }

    const report = currentReport;
    const summary = report.case_summary;
    const resolution = summary.seller_response_resolution;
    const lines = [
        report.title,
        '',
        report.assessment,
        '',
        'Why these facts may matter',
        report.why_relevant,
        '',
        'Relevant legal provision',
        report.legal_provision
            ? `${report.legal_provision.act_name} — ${report.legal_provision.section_number}: ${report.legal_provision.title}\n${report.legal_provision.description}\nSource: ${report.legal_provision.source_url}`
            : 'No provision identified from the answers provided.',
        '',
        'Possible options',
        ...report.possible_options.map(item => `- ${item}`),
        '',
        'Evidence to preserve',
        ...report.evidence_checklist.map(item => `- ${item.name}: ${item.available ? 'Available' : 'Not currently available'}`),
        '',
        'Practical next steps',
        ...report.next_steps.map(item => `- ${item}`),
        '',
        'Case summary',
        `Selected issue: ${summary.selected_issue}`,
        `Purchased from a seller or business: ${yesNo(summary.product_purchased)}`,
        `Product has a problem: ${yesNo(summary.product_has_problem)}`,
        `Product name: ${summary.product_name || 'Not provided'}`,
        `Seller name: ${summary.seller_name || 'Not provided'}`,
        `Purchase date: ${summary.purchase_date || 'Not provided'}`,
        `Amount paid: ${summary.amount_paid ?? 'Not provided'}`,
        `Order / invoice number: ${summary.order_or_invoice_number || 'Not provided'}`,
        `Problem / situation: ${summary.problem_situation || 'Not provided'}`,
        `Seller contacted: ${yesNo(summary.seller_contacted)}`,
        `Seller resolved problem: ${yesNo(resolution.problem_resolved)}`,
        `Seller response: ${resolution.response_details || 'Not provided'}`,
        `Desired resolution: ${summary.desired_resolution}`,
        '',
        report.disclaimer,
    ];
    const blob = new Blob([lines.join('\n')], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'defective_product_guidance_report.txt';
    link.click();
    URL.revokeObjectURL(url);
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
