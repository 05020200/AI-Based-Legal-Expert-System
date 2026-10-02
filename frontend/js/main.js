
const API_BASE_URL = 'http://127.0.0.1:5000/api';
let currentSessionToken = null;
let currentCaseDetails = {};
let currentAnswers = {};
let currentCase = null;
let currentQuestion = null;
let currentReport = null;
let currentUser = null;
let moduleOptions = [];

// DOM Elements
const chatMessages = document.getElementById('chat-messages');
const typingIndicator = document.getElementById('typing-indicator');
const historyList = document.getElementById('history-list');
const newChatBtn = document.getElementById('new-chat-btn');
const casePanel = document.getElementById('case-panel');
const caseSummaryContent = document.getElementById('case-summary-content');
const evidenceChecklist = document.getElementById('evidence-checklist');
const exportBtn = document.getElementById('export-btn');
const exportLink = document.getElementById('export-link');
const glossaryBtn = document.getElementById('glossary-btn');
const glossaryOverlay = document.getElementById('glossary-overlay');
const closeGlossary = document.getElementById('close-glossary');
const glossarySearch = document.getElementById('glossary-search');
const glossaryResults = document.getElementById('glossary-results');
const authState = document.getElementById('auth-state');
const application = document.getElementById('application');
const loginForm = document.getElementById('login-form');
const registerForm = document.getElementById('register-form');
const authMessage = document.getElementById('auth-message');
const guestEntry = document.getElementById('guest-entry');
const logoutBtn = document.getElementById('logout-btn');
const dashboardState = document.getElementById('dashboard-state');
const dashboardGreeting = document.getElementById('dashboard-greeting');
const dashboardCases = document.getElementById('dashboard-cases');
const dashboardNewCase = document.getElementById('dashboard-new-case');
const moduleSelection = document.getElementById('module-selection');
const moduleCards = document.getElementById('module-cards');
const interviewState = document.getElementById('interview-state');
const questionProgress = document.getElementById('question-progress');
const questionBack = document.getElementById('question-back');
const detailsState = document.getElementById('details-state');
const detailsForm = document.getElementById('details-form');
const skipDetails = document.getElementById('skip-details');
const evidenceState = document.getElementById('evidence-state');
const evidenceReportList = document.getElementById('evidence-report-list');
const questionnaire = document.getElementById('questionnaire');
const questionFields = document.getElementById('question-fields');

axios.defaults.withCredentials = true;

document.addEventListener('DOMContentLoaded', () => {
    loginForm.addEventListener('submit', handleLogin);
    registerForm.addEventListener('submit', handleRegister);
    document.getElementById('show-register').addEventListener('click', () => toggleAuthForm('register'));
    document.getElementById('show-login').addEventListener('click', () => toggleAuthForm('login'));
    guestEntry.addEventListener('click', () => enterApplication(null));
    logoutBtn.addEventListener('click', handleLogout);
    newChatBtn.addEventListener('click', startNewCase);
    dashboardNewCase.addEventListener('click', startNewCase);
    questionnaire.addEventListener('submit', handleQuestionnaireSubmit);
    questionBack.addEventListener('click', goBackQuestion);
    detailsForm.addEventListener('submit', handleDetailsSubmit);
    skipDetails.addEventListener('click', () => finishQuestionnaire({}));
    document.getElementById('evidence-continue').addEventListener('click', completeEvidenceStep);

    document.querySelectorAll('[data-screen="dashboard"]').forEach(button => {
        button.addEventListener('click', () => showScreen('dashboard'));
    });
    if (exportBtn) exportBtn.addEventListener('click', handleExport);
    if (exportLink) exportLink.addEventListener('click', event => {
        event.preventDefault();
        handleExport();
    });
    if (glossaryBtn) glossaryBtn.addEventListener('click', event => {
        event.preventDefault();
        openGlossary();
    });
    if (closeGlossary) closeGlossary.addEventListener('click', closeGlossaryModal);
    if (glossarySearch) {
        let debounceTimer;
        glossarySearch.addEventListener('input', () => {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => searchGlossary(glossarySearch.value), 300);
        });
    }

    checkExistingLogin();
});


async function checkExistingLogin() {
    try {
        const response = await axios.get(`${API_BASE_URL}/me`);
        enterApplication({ name: response.data.name || response.data.username });
    } catch (error) {
        authState.classList.remove('hidden');
    }
}


function toggleAuthForm(mode) {
    const registering = mode === 'register';
    loginForm.classList.toggle('hidden', registering);
    registerForm.classList.toggle('hidden', !registering);
    authMessage.textContent = '';
}


async function handleLogin(event) {
    event.preventDefault();
    const form = new FormData(loginForm);
    try {
        const response = await axios.post(`${API_BASE_URL}/login`, {
            username: String(form.get('username')).trim(),
            password: form.get('password'),
        });
        enterApplication({ name: response.data.name || response.data.username });
    } catch (error) {
        authMessage.textContent = error.response?.data?.error || 'Unable to sign in.';
    }
}


async function handleRegister(event) {
    event.preventDefault();
    const form = new FormData(registerForm);
    if (form.get('password') !== form.get('confirm_password')) {
        authMessage.textContent = 'Passwords do not match.';
        return;
    }
    try {
        const response = await axios.post(`${API_BASE_URL}/register`, {
            name: String(form.get('name')).trim(),
            email: String(form.get('email')).trim(),
            password: form.get('password'),
        });
        toggleAuthForm('login');
        loginForm.elements.username.value = String(form.get('email')).trim();
        authMessage.textContent = response.data.message;
    } catch (error) {
        authMessage.textContent = error.response?.data?.error || 'Unable to create the account.';
    }
}


async function handleLogout() {
    try {
        await axios.post(`${API_BASE_URL}/logout`);
    } finally {
        currentUser = null;
        currentCase = null;
        application.classList.add('hidden');
        authState.classList.remove('hidden');
        toggleAuthForm('login');
    }
}


function enterApplication(user) {
    currentUser = user;
    authState.classList.add('hidden');
    application.classList.remove('hidden');
    document.getElementById('user-name-display').textContent = user?.name || 'Guest';
    document.getElementById('user-avatar').textContent = (user?.name || 'Guest').charAt(0).toUpperCase();
    logoutBtn.classList.toggle('hidden', !user);
    dashboardGreeting.textContent = user ? `Welcome, ${user.name}` : 'Welcome, Guest';
    showScreen('dashboard');
    loadCases();
}


function showScreen(screen) {
    [dashboardState, moduleSelection, interviewState, detailsState, evidenceState].forEach(item => item.classList.add('hidden'));
    chatMessages.innerHTML = '';
    casePanel.classList.add('hidden');
    if (exportBtn) exportBtn.classList.add('hidden');
    if (exportLink) exportLink.classList.add('hidden');
    const screens = {
        dashboard: dashboardState,
        modules: moduleSelection,
        interview: interviewState,
        details: detailsState,
        evidence: evidenceState,
        report: null,
    };
    if (screens[screen]) screens[screen].classList.remove('hidden');
}


async function loadCases() {
    try {
        const response = await axios.get(`${API_BASE_URL}/cases`);
        renderCases(response.data.cases || []);
    } catch (error) {
        renderCases([]);
    }
}


function renderCases(cases) {
    historyList.replaceChildren();
    dashboardCases.replaceChildren();
    if (!cases.length) {
        dashboardCases.innerHTML = '<li class="empty-cases">No cases yet.</li>';
        return;
    }
    cases.forEach(item => {
        const historyItem = document.createElement('li');
        const openButton = document.createElement('button');
        openButton.className = 'case-history-button';
        openButton.textContent = `${item.case_id} · ${item.issue} · ${item.status}`;
        openButton.addEventListener('click', () => openCase(item.session_token));
        historyItem.appendChild(openButton);
        historyList.appendChild(historyItem);

        const dashboardItem = document.createElement('li');
        dashboardItem.className = 'dashboard-case';
        dashboardItem.innerHTML = `<div><strong>${escapeHtml(item.case_id)}</strong><span>${escapeHtml(item.issue)} · ${escapeHtml(item.status)}</span></div>`;
        const continueButton = document.createElement('button');
        continueButton.type = 'button';
        continueButton.textContent = item.status === 'Completed' ? 'Open' : 'Continue';
        continueButton.addEventListener('click', () => openCase(item.session_token));
        dashboardItem.appendChild(continueButton);
        dashboardCases.appendChild(dashboardItem);
    });
}


async function startNewCase() {
    try {
        const response = await axios.post(`${API_BASE_URL}/cases`);
        currentCase = response.data.case;
        currentSessionToken = currentCase.session_token;
        currentAnswers = {};
        currentCaseDetails = {};
        currentReport = null;
        await loadModules();
        showScreen('modules');
    } catch (error) {
        appendMessage('assistant', '<p role="alert">A new case could not be created. Please try again.</p>');
    }
}


async function openCase(token) {
    try {
        const response = await axios.get(`${API_BASE_URL}/cases/${encodeURIComponent(token)}`);
        currentCase = response.data.case;
        currentSessionToken = currentCase.session_token;
        currentAnswers = currentCase.answers || {};
        currentCaseDetails = currentCase.case_details || {};
        currentReport = currentCase.report || null;
        if (currentReport) {
            if (currentCase.current_question_key === 'evidence_report') {
                showEvidence(currentReport);
            } else {
                showReport(currentReport);
            }
        } else if (currentCase.module_id === 'defective_product') {
            if (currentCase.current_question_key === 'additional_details') {
                populateDetailsForm(currentCaseDetails);
                showScreen('details');
            } else {
                await navigateQuestion(currentCase.current_question_key || null, 'current');
            }
        } else {
            await loadModules();
            showScreen('modules');
        }
    } catch (error) {
        appendMessage('assistant', '<p role="alert">This case could not be opened.</p>');
    }
}


async function loadModules() {
    const response = await axios.get(`${API_BASE_URL}/modules`);
    moduleOptions = response.data.modules;
    moduleCards.replaceChildren();
    moduleOptions.forEach(module => {
        const card = document.createElement('article');
        card.className = 'module-card';
        const title = document.createElement('h2');
        title.textContent = module.name;
        const description = document.createElement('p');
        description.textContent = module.description;
        const button = document.createElement('button');
        button.type = 'button';
        button.textContent = module.available ? 'Select' : 'Coming later';
        button.disabled = !module.available;
        if (module.available) button.addEventListener('click', () => selectModule(module.id));
        card.append(title, description, button);
        moduleCards.appendChild(card);
    });
}


async function selectModule(moduleId) {
    if (!currentCase || moduleId !== 'defective_product') return;
    currentCase.module_id = moduleId;
    currentAnswers = {};
    currentQuestion = null;
    await saveCurrentCase({module_id: moduleId, answers: currentAnswers, current_question_key: null});
    await navigateQuestion(null, 'current');
}


async function saveCurrentCase(changes = {}) {
    const response = await axios.put(`${API_BASE_URL}/cases/${encodeURIComponent(currentSessionToken)}`, {
        module_id: currentCase.module_id,
        answers: currentAnswers,
        case_details: currentCaseDetails,
        current_question_key: currentQuestion?.key || null,
        ...changes,
    });
    currentCase = response.data.case;
}


async function navigateQuestion(currentKey, direction) {
    const response = await axios.post(`${API_BASE_URL}/phase1/question`, {
        answers: currentAnswers,
        current_key: currentKey,
        direction,
    });
    if (!response.data.question) {
        currentQuestion = null;
        await saveCurrentCase({current_question_key: 'additional_details'});
        populateDetailsForm(currentCaseDetails);
        showScreen('details');
        return;
    }
    currentQuestion = response.data.question;
    currentQuestion.step = response.data.step;
    currentQuestion.total = response.data.total;
    renderQuestion(currentQuestion);
    showScreen('interview');
}


function renderQuestion(question) {
    const key = escapeHtml(question.key);
    const prompt = escapeHtml(question.prompt);
    questionProgress.textContent = `Question ${question.step} of 8`;
    if (question.type === 'choice') {
        const options = question.options.map(option =>
            `<option value="${escapeHtml(option.value)}" ${currentAnswers[question.key] === option.value ? 'selected' : ''}>${escapeHtml(option.label)}</option>`
        ).join('');
        questionFields.innerHTML = `<label class="question-field" for="question-${key}">
            <span>${prompt}</span>
            <select id="question-${key}" name="${key}" required>
                <option value="" disabled ${currentAnswers[question.key] ? '' : 'selected'}>Select an option</option>${options}
            </select>
        </label>`;
        return;
    }

    const options = question.options.map((option, index) => `
        <label class="answer-option" for="question-${key}-${index}">
            <input id="question-${key}-${index}" type="radio" name="${key}" value="${option.value}" ${currentAnswers[question.key] === option.value ? 'checked' : ''} required>
            <span>${escapeHtml(option.label)}</span>
        </label>`).join('');
    questionFields.innerHTML = `<fieldset class="question-field">
        <legend>${prompt}</legend>
        <div class="answer-options">${options}</div>
    </fieldset>`;
}


async function handleQuestionnaireSubmit(event) {
    event.preventDefault();
    if (!questionnaire.reportValidity()) return;

    const formData = new FormData(questionnaire);
    const key = currentQuestion.key;
    const rawValue = formData.get(key);
    currentAnswers[key] = currentQuestion.type === 'boolean' ? rawValue === 'true' : rawValue;
    pruneAnswers(key);
    try {
        await navigateQuestion(key, 'next');
        if (currentQuestion) {
            await saveCurrentCase({current_question_key: currentQuestion.key});
        }
    } catch (error) {
        appendMessage('assistant', '<p role="alert">Unable to save this answer. Please try again.</p>');
    }
}


function pruneAnswers(changedKey) {
    if (changedKey === 'product_purchased' && currentAnswers.product_purchased === false) {
        Object.keys(currentAnswers).forEach(key => {
            if (key !== 'product_purchased') delete currentAnswers[key];
        });
    }
    if (changedKey === 'product_has_problem' && currentAnswers.product_has_problem === false) {
        ['seller_contacted', 'seller_resolved', 'desired_resolution', 'purchase_proof_available',
            'problem_evidence_available', 'seller_communication_available'].forEach(key => delete currentAnswers[key]);
    }
    if (changedKey === 'seller_contacted' && currentAnswers.seller_contacted === false) {
        delete currentAnswers.seller_resolved;
    }
}


async function goBackQuestion() {
    if (!currentQuestion || currentQuestion.key === 'product_purchased') {
        showScreen('modules');
        return;
    }
    try {
        await navigateQuestion(currentQuestion.key, 'previous');
        await saveCurrentCase({current_question_key: currentQuestion.key});
    } catch (error) {
        appendMessage('assistant', '<p role="alert">Unable to return to the previous question.</p>');
    }
}


function populateDetailsForm(details) {
    Object.entries(details || {}).forEach(([key, value]) => {
        if (detailsForm.elements[key]) detailsForm.elements[key].value = value;
    });
}


async function handleDetailsSubmit(event) {
    event.preventDefault();
    const formData = new FormData(detailsForm);
    const details = {};
    for (const [key, value] of formData.entries()) {
        const normalized = String(value).trim();
        if (normalized) details[key] = normalized;
    }
    await finishQuestionnaire(details);
}


async function finishQuestionnaire(details) {
    currentCaseDetails = {...currentCaseDetails, ...details};
    try {
        await saveCurrentCase({
            case_details: currentCaseDetails,
            current_question_key: 'analysis',
        });
        const response = await axios.post(`${API_BASE_URL}/phase1/analyze`, {
            answers: currentAnswers,
            case_details: currentCaseDetails,
            session_token: currentSessionToken,
        });
        currentReport = response.data.report;
        await saveCurrentCase({
            answers: currentAnswers,
            case_details: currentCaseDetails,
            report: currentReport,
            status: 'In Progress',
            current_question_key: 'evidence_report',
        });
        showEvidence(currentReport);
        await loadCases();
    } catch (error) {
        const message = error.response?.data?.error || 'The report could not be prepared. Please try again.';
        appendMessage('assistant', `<p role="alert">${escapeHtml(message)}</p>`);
    }
}


function showEvidence(report) {
    evidenceReportList.replaceChildren();
    report.evidence_checklist.forEach(item => {
        const row = document.createElement('li');
        const mark = document.createElement('span');
        mark.className = item.available === true ? 'evidence-mark available' : 'evidence-mark unavailable';
        mark.textContent = item.available === true ? '✓' : '×';
        const name = document.createElement('strong');
        name.textContent = item.name;
        const status = document.createElement('span');
        status.textContent = item.available === true ? 'Reported available' : 'Not reported';
        row.append(mark, name, status);
        evidenceReportList.appendChild(row);
    });
    showScreen('evidence');
}


async function completeEvidenceStep() {
    try {
        await saveCurrentCase({status: 'Completed', current_question_key: null});
        showReport(currentReport);
        await loadCases();
    } catch (error) {
        appendMessage('assistant', '<p role="alert">Unable to continue to the guidance report.</p>');
    }
}


function showReport(report) {
    showScreen('report');
    appendMessage('assistant', `<p class="case-number">${escapeHtml(currentCase?.case_id || '')}</p>${renderReport(report)}`);
    updateCasePanel(report);
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
