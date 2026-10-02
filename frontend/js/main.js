
const API_BASE_URL = '/api';
let currentSessionToken = null;
let currentCaseDetails = {};
let currentAnswers = {};
let currentCase = null;
let currentQuestion = null;
let currentReport = null;
let currentUser = null;
let moduleOptions = [];
let currentGlossaryDomain = 'consumer';
let glossaryEntries = [];
let glossaryLoaded = false;
let currentDraft = '';
let pendingDocumentType = null;
let pendingDocumentTitle = '';
let pendingConsumerDetails = {};
let generatedDocumentPdf = null;
let pendingDeleteToken = null;
const RECOMMENDED_EVIDENCE = [
    'Warranty Card / Warranty Document',
    'Product Serial Number / IMEI',
    'Order Confirmation / Order Details',
    'Payment Proof',
    'Repair / Service Records',
    'Previous Complaint / Service Request Number',
    'Product Packaging / Label',
];
const CASE_DETAIL_KEYS_BY_MODULE = {
    defective_product: ['product_name', 'seller_name', 'seller_address', 'purchase_date', 'amount_paid', 'order_or_invoice_number', 'problem_description', 'seller_response'],
    refund_replacement: ['product_name', 'seller_name', 'seller_address', 'purchase_date', 'amount_paid', 'order_or_invoice_number', 'problem_description', 'seller_response'],
    warranty: ['product_name', 'seller_name', 'seller_address', 'purchase_date', 'amount_paid', 'order_or_invoice_number', 'problem_description', 'seller_response'],
    ecommerce: ['product_name', 'platform_name', 'seller_name', 'seller_address', 'purchase_date', 'amount_paid', 'order_or_invoice_number', 'problem_description', 'seller_response'],
    service_deficiency: ['seller_name', 'seller_address', 'order_or_invoice_number'],
    unfair_trade_practice: ['platform_name', 'seller_name', 'seller_address', 'purchase_date', 'amount_paid', 'order_or_invoice_number'],
};
const CASE_FACT_EQUIVALENTS = [
    ['product_name', 'product', 'product_or_service', 'advertised_product'],
    ['platform_name', 'advertisement_source'],
    ['seller_name', 'seller', 'business_name', 'service_provider', 'provider_name', 'advertiser_or_business'],
    ['seller_address', 'business_address', 'provider_address'],
    ['purchase_date', 'order_date'],
    ['amount_paid', 'payment_amount', 'service_amount_paid'],
    ['order_or_invoice_number', 'order_number', 'invoice_number', 'order_reference'],
    ['problem_description', 'service_problem_description', 'reason_for_request', 'actual_experience'],
    ['seller_response', 'provider_response', 'business_response', 'warranty_refusal_reason'],
    ['seller_contacted', 'provider_contacted', 'business_contacted', 'seller_or_service_contacted'],
    ['seller_resolved', 'issue_resolved'],
    ['desired_resolution', 'selected_resolution'],
    ['purchase_proof_available', 'order_proof_available'],
    ['seller_communication_available', 'communication_available'],
    ['product_purchased', 'product_or_service_purchased'],
    ['product_has_problem', 'service_problem_exists'],
];

// DOM Elements
const chatMessages = document.getElementById('chat-messages');
const typingIndicator = document.getElementById('typing-indicator');
const historyList = document.getElementById('history-list');
const newChatBtn = document.getElementById('new-chat-btn');
const exportBtn = document.getElementById('export-btn');
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
const recommendedEvidenceList = document.getElementById('recommended-evidence-list');
const questionnaire = document.getElementById('questionnaire');
const questionFields = document.getElementById('question-fields');
const deleteCaseDialog = document.getElementById('delete-case-dialog');
const deleteCaseError = document.getElementById('delete-case-error');
const confirmDeleteCaseButton = document.getElementById('confirm-delete-case');

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
    document.getElementById('cancel-delete-case').addEventListener('click', () => deleteCaseDialog.close());
    confirmDeleteCaseButton.addEventListener('click', confirmCaseDeletion);
    deleteCaseDialog.addEventListener('cancel', () => { pendingDeleteToken = null; });
    chatMessages.addEventListener('click', handleReportActions);
    chatMessages.addEventListener('submit', previewDocument);

    document.querySelectorAll('[data-screen="dashboard"]').forEach(button => {
        button.addEventListener('click', () => showScreen('dashboard'));
    });
    document.getElementById('my-cases-btn').addEventListener('click', () => {
        historyList.scrollIntoView({behavior: 'smooth', block: 'nearest'});
    });
    if (exportBtn) exportBtn.addEventListener('click', handleExport);
    if (glossaryBtn) glossaryBtn.addEventListener('click', event => {
        event.preventDefault();
        openGlossary();
    });
    if (closeGlossary) closeGlossary.addEventListener('click', closeGlossaryModal);
    document.querySelectorAll('[data-glossary-domain]').forEach(button => {
        button.addEventListener('click', () => {
            currentGlossaryDomain = button.dataset.glossaryDomain;
            document.querySelectorAll('[data-glossary-domain]').forEach(tab => {
                tab.setAttribute('aria-selected', String(tab === button));
            });
            renderGlossary();
        });
    });
    glossaryOverlay.addEventListener('click', event => {
        if (event.target === glossaryOverlay) closeGlossaryModal();
    });
    document.addEventListener('keydown', event => {
        if (event.key === 'Escape' && !glossaryOverlay.classList.contains('hidden')) {
            closeGlossaryModal();
        }
    });
    if (glossarySearch) {
        let debounceTimer;
        glossarySearch.addEventListener('input', () => {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => renderGlossary(), 150);
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
    if (exportBtn) exportBtn.classList.add('hidden');
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
        historyList.innerHTML = '<li class="empty-cases">No cases yet.</li>';
        dashboardCases.innerHTML = '<li class="empty-cases">No cases yet.</li>';
        return;
    }
    cases.forEach(item => {
        const historyItem = document.createElement('li');
        historyItem.className = 'case-history-item';
        historyItem.innerHTML = `<div><strong>${escapeHtml(item.case_title)}</strong><span>${escapeHtml(item.case_id)}</span></div>`;
        const historyActions = document.createElement('div');
        historyActions.className = 'case-actions';
        historyActions.append(createOpenCaseButton(item), createDeleteCaseButton(item));
        historyItem.append(historyActions);
        historyList.appendChild(historyItem);

        const dashboardItem = document.createElement('li');
        dashboardItem.className = 'dashboard-case';
        dashboardItem.innerHTML = `<div><strong>${escapeHtml(item.case_title)}</strong><span>${escapeHtml(item.case_id)}</span></div>`;
        const actions = document.createElement('div');
        actions.className = 'case-actions';
        actions.append(createOpenCaseButton(item), createDeleteCaseButton(item));
        dashboardItem.append(actions);
        dashboardCases.appendChild(dashboardItem);
    });
}


function createOpenCaseButton(item) {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = item.status === 'In Progress' ? 'Continue' : 'Open';
    button.addEventListener('click', () => openCase(item.session_token));
    return button;
}


function createDeleteCaseButton(item) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'delete-case-button';
    button.textContent = 'Delete Case';
    button.setAttribute('aria-label', `Delete ${item.case_id}`);
    button.addEventListener('click', event => {
        event.stopPropagation();
        pendingDeleteToken = item.session_token;
        deleteCaseError.textContent = '';
        deleteCaseDialog.showModal();
    });
    return button;
}


async function confirmCaseDeletion() {
    if (!pendingDeleteToken) return;
    const token = pendingDeleteToken;
    confirmDeleteCaseButton.disabled = true;
    deleteCaseError.textContent = '';
    try {
        await axios.delete(`${API_BASE_URL}/cases/${encodeURIComponent(token)}`);
        deleteCaseDialog.close();
        pendingDeleteToken = null;
        if (currentSessionToken === token) {
            currentSessionToken = null;
            currentCase = null;
            currentCaseDetails = {};
            currentAnswers = {};
            currentQuestion = null;
            currentReport = null;
            generatedDocumentPdf = null;
            showScreen('dashboard');
        }
        await loadCases();
    } catch (error) {
        deleteCaseError.textContent = error.response?.data?.error || 'Unable to delete this case.';
    } finally {
        confirmDeleteCaseButton.disabled = false;
    }
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
        } else if (currentCase.module_id) {
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
    if (!currentCase || !moduleOptions.some(module => module.id === moduleId && module.available)) return;
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
    const endpoint = currentCase.module_id === 'defective_product'
        ? `${API_BASE_URL}/phase1/question`
        : `${API_BASE_URL}/modules/${encodeURIComponent(currentCase.module_id)}/question`;
    let nextKey = currentKey;
    let nextDirection = direction;
    let response;
    let skippedKnownQuestion = false;
    for (let attempts = 0; attempts < 100; attempts += 1) {
        response = await axios.post(endpoint, {
            answers: currentAnswers,
            current_key: nextKey,
            direction: nextDirection,
        });
        if (response.data.visible_keys) {
            const visibleKeys = new Set(response.data.visible_keys);
            Object.keys(currentAnswers).forEach(key => {
                if (!visibleKeys.has(key)) delete currentAnswers[key];
            });
        }
        const question = response.data.question;
        if (!question || nextDirection === 'previous') break;
        const knownFact = knownQuestionFact(question);
        if (!knownFact.found) break;
        if (!Object.prototype.hasOwnProperty.call(currentAnswers, question.key)) {
            currentAnswers[question.key] = knownFact.value;
        }
        skippedKnownQuestion = true;
        nextKey = question.key;
        nextDirection = 'next';
    }
    if (!response?.data.question) {
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
    if (skippedKnownQuestion) {
        await saveCurrentCase({
            answers: currentAnswers,
            case_details: currentCaseDetails,
            current_question_key: currentQuestion.key,
        });
    }
    showScreen('interview');
}


function renderQuestion(question) {
    const key = escapeHtml(question.key);
    const prompt = escapeHtml(question.prompt);
    const currentModule = moduleOptions.find(module => module.id === currentCase?.module_id);
    document.getElementById('interview-module-label').textContent = currentModule?.name || 'Consumer Issue';
    document.getElementById('interview-module-title').textContent = currentModule?.name || 'Consumer Issue';
    document.getElementById('interview-introduction').textContent = currentModule?.description || '';
    questionProgress.textContent = `Question ${question.step} of ${question.total}`;
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

    if (question.type === 'text') {
        questionFields.innerHTML = `<label class="question-field" for="question-${key}">
            <span>${prompt}</span>
            <textarea id="question-${key}" name="${key}" rows="3" ${question.required ? 'required' : ''}>${escapeHtml(currentAnswers[question.key] || '')}</textarea>
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
    const submitButton = questionnaire.querySelector('button[type="submit"]');
    if (submitButton?.disabled || !currentQuestion) return;
    if (!questionnaire.reportValidity()) return;

    if (submitButton) submitButton.disabled = true;
    const formData = new FormData(questionnaire);
    const key = currentQuestion.key;
    const rawValue = formData.get(key);
    if (currentQuestion.type === 'boolean') {
        currentAnswers[key] = rawValue === 'true';
    } else if (currentQuestion.type === 'text' && !String(rawValue || '')) {
        delete currentAnswers[key];
    } else {
        currentAnswers[key] = rawValue;
    }
    if (currentCase.module_id === 'defective_product') pruneAnswers(key);
    try {
        await navigateQuestion(key, 'next');
        if (currentQuestion) {
            await saveCurrentCase({current_question_key: currentQuestion.key});
        }
    } catch (error) {
        appendMessage('assistant', '<p role="alert">Unable to save this answer. Please try again.</p>');
    } finally {
        if (submitButton) submitButton.disabled = false;
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
    currentCaseDetails = {...currentCaseDetails, ...(details || {})};
    const visibleFields = new Set(CASE_DETAIL_KEYS_BY_MODULE[currentCase?.module_id] || []);
    Array.from(detailsForm.elements).forEach(input => {
        if (!input.name) return;
        const label = input.closest('label');
        if (!label) return;
        const knownFact = knownCaseFact(input.name);
        const ecommerceProblemKnown = input.name === 'problem_description'
            && currentCase?.module_id === 'ecommerce'
            && hasCaseFactValue(currentAnswers.ecommerce_problem_type);
        label.classList.toggle('hidden', !visibleFields.has(input.name) || knownFact.found || ecommerceProblemKnown);
        input.value = currentCaseDetails[input.name] ?? '';
    });
}


function caseFactAliases(key) {
    return CASE_FACT_EQUIVALENTS.find(group => group.includes(key)) || [key];
}


function hasCaseFactValue(value) {
    return value !== null && value !== undefined
        && !(typeof value === 'string' && value.trim() === '');
}


function knownCaseFact(key) {
    const facts = {...currentCaseDetails, ...currentAnswers};
    for (const alias of caseFactAliases(key)) {
        if (Object.prototype.hasOwnProperty.call(facts, alias)
            && hasCaseFactValue(facts[alias])) {
            return {found: true, value: facts[alias], key: alias};
        }
    }
    return {found: false, value: undefined, key: null};
}


function knownQuestionFact(question) {
    const known = knownCaseFact(question.key);
    if (known.found) {
        if (question.type === 'boolean' && typeof known.value !== 'boolean') {
            return {found: false, value: undefined, key: null};
        }
        if (question.type === 'choice'
            && !question.options.some(option => option.value === known.value)) {
            return {found: false, value: undefined, key: null};
        }
        return known;
    }

    const responseKeys = ['seller_response', 'provider_response', 'business_response', 'warranty_refusal_reason'];
    if (['seller_contacted', 'provider_contacted', 'business_contacted', 'seller_or_service_contacted'].includes(question.key)
        && responseKeys.some(key => knownCaseFact(key).found)) {
        return {found: true, value: true, key: 'reported_response'};
    }

    const detailAliases = key => knownCaseFact(key).found;
    if (['product_purchased', 'product_or_service_purchased'].includes(question.key)
        && ['product_name', 'service_type', 'product_or_service'].some(detailAliases)) {
        return {found: true, value: true, key: 'purchase_details'};
    }
    if (question.key === 'service_purchased' && detailAliases('service_type')) {
        return {found: true, value: true, key: 'service_type'};
    }
    if (question.key === 'online_purchase' && detailAliases('platform_name')) {
        return {found: true, value: true, key: 'platform_name'};
    }
    if (['product_has_problem', 'service_problem_exists'].includes(question.key)
        && detailAliases('problem_description')) {
        return {found: true, value: true, key: 'problem_description'};
    }
    if (question.key === 'claim_made' && detailAliases('claim_description')) {
        return {found: true, value: true, key: 'claim_description'};
    }
    if (question.key === 'advertisement_seen'
        && (detailAliases('advertisement_source') || detailAliases('claim_description'))) {
        return {found: true, value: true, key: 'advertisement_detail'};
    }
    if (question.key === 'order_placed' && detailAliases('order_or_invoice_number')) {
        return {found: true, value: true, key: 'order_or_invoice_number'};
    }
    return {found: false, value: undefined, key: null};
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
        const endpoint = currentCase.module_id === 'defective_product'
            ? `${API_BASE_URL}/phase1/analyze`
            : `${API_BASE_URL}/modules/${encodeURIComponent(currentCase.module_id)}/analyze`;
        const response = await axios.post(endpoint, {
            answers: currentAnswers,
            case_details: currentCaseDetails,
            session_token: currentSessionToken,
        });
        currentReport = response.data.report;
        const analysisState = currentCase.module_id === 'defective_product' ? {} : {
            facts: response.data.facts,
            derived_facts: response.data.derived_facts,
            reasoning_trace: response.data.reasoning_trace,
            backward_result: response.data.backward_result,
        };
        await saveCurrentCase({
            answers: currentAnswers,
            case_details: currentCaseDetails,
            report: currentReport,
            current_question_key: 'evidence_report',
            ...analysisState,
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
    recommendedEvidenceList.replaceChildren();
    const reportedEvidence = report.evidence_checklist.filter(item => item.available === true);
    if (!reportedEvidence.length) {
        const emptyRow = document.createElement('li');
        emptyRow.className = 'empty-cases';
        emptyRow.textContent = 'No evidence was reported as available.';
        evidenceReportList.appendChild(emptyRow);
    }
    reportedEvidence.forEach(item => {
        const row = document.createElement('li');
        const mark = document.createElement('span');
        mark.className = 'evidence-mark available';
        mark.textContent = '✓';
        const name = document.createElement('strong');
        name.textContent = item.name;
        row.append(mark, name);
        evidenceReportList.appendChild(row);
    });
    (report.recommended_evidence || RECOMMENDED_EVIDENCE).forEach(name => {
        const row = document.createElement('li');
        const mark = document.createElement('span');
        mark.className = 'evidence-mark recommended';
        mark.textContent = '○';
        const label = document.createElement('strong');
        label.textContent = name;
        const status = document.createElement('span');
        status.textContent = 'Recommended only';
        row.append(mark, label, status);
        recommendedEvidenceList.appendChild(row);
    });
    showScreen('evidence');
}


async function completeEvidenceStep() {
    try {
        await saveCurrentCase({current_question_key: null});
        showReport(currentReport);
        await loadCases();
    } catch (error) {
        appendMessage('assistant', '<p role="alert">Unable to continue to the guidance report.</p>');
    }
}


function showReport(report) {
    showScreen('report');
    appendMessage('assistant', `<p class="case-number">${escapeHtml(currentCase?.case_id || '')}</p>${renderReport(report)}`);
    if (exportBtn) exportBtn.classList.remove('hidden');
}


function renderReport(report) {
    const provisions = report.legal_provisions?.length
        ? report.legal_provisions
        : report.legal_provision ? [report.legal_provision] : [];
    const law = provisions.map(provision => `
        <article class="report-provision">
            <h4>${escapeHtml(provision.act_name)} — ${escapeHtml(provision.section_number)}</h4>
            <strong>${escapeHtml(provision.title)}</strong>
            <p>${escapeHtml(provision.description)}</p>
            ${provision.source_url ? `<a href="${escapeHtml(provision.source_url)}" target="_blank" rel="noopener noreferrer">View source</a>` : ''}
        </article>`).join('');
    const options = report.possible_options.map(item => `<li>${escapeHtml(item)}</li>`).join('');
    const isRefundReplacement = report.case_summary?.selected_issue === 'Refund / Replacement Issue';
    const isWarranty = report.case_summary?.selected_issue === 'Warranty Issue';
    const isEcommerce = report.case_summary?.selected_issue === 'E-Commerce Consumer Issue';
    const isServiceDeficiency = report.case_summary?.selected_issue === 'Deficiency in Service';
    const isUnfairTradePractice = report.case_summary?.selected_issue === 'Misleading Advertisement / Unfair Trade Practice';
    const hasSplitEvidence = isRefundReplacement || isWarranty || isEcommerce || isServiceDeficiency || isUnfairTradePractice;
    const reportedEvidence = report.evidence_checklist.filter(item => item.available === true);
    const reportedEvidenceNames = new Set(reportedEvidence.map(item => item.name));
    const otherRecommendedEvidence = (report.recommended_evidence || [])
        .filter(name => !reportedEvidenceNames.has(name));
    const evidence = hasSplitEvidence
        ? `<h4>Reported Available</h4><ul>${reportedEvidence.length
            ? reportedEvidence.map(item => `<li>${escapeHtml(item.name)}</li>`).join('')
            : '<li>None reported</li>'}</ul>
            <h4>Other Recommended Evidence</h4><ul>${otherRecommendedEvidence.length
                ? otherRecommendedEvidence.map(name => `<li>${escapeHtml(name)}</li>`).join('')
                : '<li>None</li>'}</ul>`
        : report.evidence_checklist.map(item => `
            <li><strong>${escapeHtml(item.name)}</strong><span>${item.available === true ? 'Reported available' : 'Not reported'}</span></li>`).join('');
    const steps = report.next_steps.map(item => `<li>${escapeHtml(item)}</li>`).join('');
    const where = renderComplaintGuidance(report.where_to_complain);
    const noComplaintRoute = report.case_summary?.warranty_service_provided === true
        || report.case_summary?.issue_resolved === true
        ? 'You reported that the issue was resolved; no unresolved complaint route is suggested.'
        : 'The answers do not indicate an unresolved request for a complaint route.';
    const complaintSection = isWarranty || isEcommerce || isServiceDeficiency || isUnfairTradePractice
        ? `<section class="report-section"><h3>Where To Complain</h3>${report.where_to_complain ? where : `<p>${escapeHtml(noComplaintRoute)}</p>`}</section>`
        : !report.where_to_complain || report.case_summary?.seller_response_resolution?.problem_resolved === true
            ? ''
            : `<section class="report-section"><h3>Where To Complain</h3>${where}</section>`;
    const documents = report.documents?.length ? report.documents : [
        {type: 'seller_complaint', label: 'Prepare Seller Complaint'},
        {type: 'replacement_request', label: 'Prepare Replacement Request'},
        {type: 'refund_request', label: 'Prepare Refund Request'},
        {type: 'consumer_commission_complaint', label: 'Prepare Consumer Commission Complaint'},
    ];
    const documentActions = documents.map(item =>
        `<button type="button" data-document-type="${escapeHtml(item.type)}">${escapeHtml(item.label)}</button>`
    ).join('');
    const timeline = renderTimeline(currentCase?.timeline || []);
    const disclaimer = isWarranty || isEcommerce || isServiceDeficiency || isUnfairTradePractice
        ? `<section class="report-section"><h3>Disclaimer</h3><p class="report-disclaimer">${escapeHtml(report.disclaimer)}</p></section>`
        : `<p class="report-disclaimer">${escapeHtml(report.disclaimer)}</p>`;

    return `<h2>${escapeHtml(report.title)}</h2>
        <section class="report-section"><h3>Case Summary</h3>${renderSummary(report.case_summary)}</section>
        <section class="report-section"><h3>Your Situation</h3><p>${escapeHtml(situationSummary(report.case_summary))}</p></section>
        <section class="report-section"><h3>Possible Legal Issue</h3><p class="report-assessment">${escapeHtml(report.possible_issue || report.assessment)}</p></section>
        <section class="report-section"><h3>Relevant Law</h3>${law}</section>
        <section class="report-section"><h3>Why This May Apply</h3><p>${escapeHtml(report.why_relevant)}</p></section>
        <section class="report-section"><h3>Evidence</h3>${hasSplitEvidence ? evidence : `<ul class="report-evidence">${evidence}</ul>`}</section>
        <section class="report-section"><h3>Possible Options / Remedies</h3><ul>${options}</ul></section>
        <section class="report-section"><h3>What To Do Next</h3><ol>${steps}</ol></section>
        ${complaintSection}
        ${timeline}
        <section class="report-section"><h3>Documents</h3>
            <p>Prepare a draft based on the information provided. Review the draft and current official filing requirements before submission.</p>
            <div class="document-actions">${documentActions}</div>
            <div id="consumer-details-step" class="generated-document hidden">
                <h4 id="consumer-details-heading">Document Details</h4>
                <form id="consumer-details-form" class="detail-grid">
                    <label>Consumer Name *<input name="consumer_name" required maxlength="500"></label>
                    <label>Consumer Address<input name="consumer_address" maxlength="500"></label>
                    <label>Consumer Phone<input name="consumer_phone" type="tel" maxlength="100"></label>
                    <label>Consumer Email<input name="consumer_email" type="email" maxlength="254"></label>
                    <label>Document Date<input name="document_date" type="date"></label>
                    <div class="wide-field question-navigation">
                        <button type="button" class="workflow-back" data-cancel-document>Cancel</button>
                        <button type="submit" class="submit-questionnaire">Preview Document</button>
                    </div>
                </form>
            </div>
            <div id="document-preview-step" class="generated-document hidden">
                <h4 id="generated-document-title"></h4>
                <pre id="generated-document-content"></pre>
                <button type="button" data-generate-document-pdf>Generate PDF</button>
            </div>
            <div id="document-pdf-ready" class="generated-document hidden" role="status">
                <p>PDF generated successfully.</p>
                <button type="button" data-download-document-pdf>Download PDF</button>
            </div>
        </section>
        ${disclaimer}`;
}


function situationSummary(summary) {
    if (summary.selected_issue === 'Refund / Replacement Issue' && summary.situation_text) {
        return summary.situation_text;
    }
    if ([
        'Warranty Issue',
        'E-Commerce Consumer Issue',
        'Deficiency in Service',
        'Misleading Advertisement / Unfair Trade Practice',
    ].includes(summary.selected_issue) && summary.situation_text) {
        return summary.situation_text;
    }
    const subject = summary.platform_name || summary.product_name || 'Product or platform details not provided';
    const problem = summary.problem_situation || 'Problem details not provided';
    const seller = summary.seller_name ? ` from ${summary.seller_name}` : '';
    return `${summary.selected_issue}: ${subject}${seller}. Reported situation: ${problem}.`;
}


function renderComplaintGuidance(guidance = {}) {
    if (!guidance) return '<p>Complaint information is not available for this assessment.</p>';
    const grievance = guidance.grievance_support || {};
    const pecuniary = guidance.pecuniary_jurisdiction || {};
    const territory = (guidance.territorial_jurisdiction_factors || [])
        .map(factor => `<li>${escapeHtml(factor)}</li>`).join('');
    return `<p>${escapeHtml(grievance.description || '')}</p>
        <p><strong>${escapeHtml(grievance.name || 'National Consumer Helpline')}</strong>: ${escapeHtml(grievance.phone || '')}${grievance.alternate_phone ? ` / ${escapeHtml(grievance.alternate_phone)}` : ''} ·
        <a href="${escapeHtml(grievance.url || '')}" target="_blank" rel="noopener noreferrer">Official portal</a></p>
        <p>${escapeHtml(guidance.formal_complaint?.message || '')}</p>
        <p><strong>Pecuniary jurisdiction:</strong> ${escapeHtml(pecuniary.message || 'Not determined.')}</p>
        ${pecuniary.authority ? `<p><strong>Informational estimate:</strong> ${escapeHtml(pecuniary.authority)}; based on consideration paid of INR ${escapeHtml(pecuniary.consideration_paid)}. ${escapeHtml(pecuniary.message)}</p>` : ''}
        <p>${escapeHtml(guidance.territorial_note || '')}</p>
        ${territory ? `<ul>${territory}</ul>` : ''}`;
}


function renderTimeline(events) {
    if (!events.length) return '';
    return `<section class="report-section"><h3>Case Activity</h3><ol class="case-timeline">${events.map(event => {
        const detail = event.details?.fact ? `: ${event.details.fact.replace(/_/g, ' ')}` : '';
        const date = new Date(event.at);
        const dateText = Number.isNaN(date.getTime()) ? event.at : new Intl.DateTimeFormat('en-GB', {
            day: '2-digit', month: 'long', year: 'numeric'
        }).format(date);
        return `<li><time>${escapeHtml(dateText)}</time><span>${escapeHtml(event.event + detail)}</span></li>`;
    }).join('')}</ol></section>`;
}


function renderSummary(summary) {
    if (summary.selected_issue === 'Refund / Replacement Issue') {
        const items = [
            ['Product or service purchased', yesNo(summary.product_or_service_purchased)],
            ['Refund or replacement requested', yesNo(summary.refund_or_replacement_requested)],
            ['Reason for request', summary.reason_for_request],
            ['Product or service still has a problem', yesNo(summary.product_has_problem)],
            ['Seller contacted', yesNo(summary.seller_contacted)],
            ['Seller agreed', yesNo(summary.seller_agreed)],
            ['Refund or replacement provided', yesNo(summary.refund_or_replacement_provided)],
            ['Seller response', summary.seller_agreed === true ? summary.seller_response : null],
            ['Desired resolution', summary.desired_resolution],
            ['Product name', summary.product_name],
            ['Seller name', summary.seller_name],
            ['Purchase date', summary.purchase_date ? formatPurchaseDate(summary.purchase_date) : null],
            ['Amount paid', summary.amount_paid ? formatAmount(summary.amount_paid) : null],
            ['Order / invoice number', summary.order_or_invoice_number],
        ];
        return `<dl class="summary-list">${items.filter(([, value]) => value !== null && value !== undefined && value !== '').map(([label, value]) => `
            <div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`).join('')}
        </dl>`;
    }
    if (summary.selected_issue === 'Warranty Issue') {
        const items = [
            ['Product purchased', summary.product_purchased === undefined ? null : yesNo(summary.product_purchased)],
            ['Warranty exists', summary.warranty_exists === undefined ? null : yesNo(summary.warranty_exists)],
            ['Product problem reported', summary.product_problem_exists === undefined ? null : yesNo(summary.product_problem_exists)],
            ['Warranty service requested', summary.warranty_service_requested === undefined ? null : yesNo(summary.warranty_service_requested)],
            ['Seller / service centre contacted', summary.seller_or_service_contacted === undefined ? null : yesNo(summary.seller_or_service_contacted)],
            ['Warranty service provided', summary.warranty_service_provided === undefined ? null : yesNo(summary.warranty_service_provided)],
            ['Service refused / incomplete', summary.warranty_service_refused === undefined ? null : yesNo(summary.warranty_service_refused)],
            ['Refusal reason', summary.warranty_refusal_reason],
            ['Desired resolution', summary.desired_resolution],
            ['Product name', summary.product_name],
            ['Seller / service centre', summary.seller_name],
            ['Seller address', summary.seller_address],
            ['Purchase date', summary.purchase_date ? formatPurchaseDate(summary.purchase_date) : null],
            ['Amount paid', summary.amount_paid ? formatAmount(summary.amount_paid) : null],
            ['Order / invoice number', summary.order_or_invoice_number],
            ['Additional problem details', summary.problem_description],
            ['Seller response details', summary.seller_response],
        ];
        return `<dl class="summary-list">${items.filter(([, value]) => value !== null && value !== undefined && value !== '').map(([label, value]) => `
            <div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`).join('')}
        </dl>`;
    }
    if (summary.selected_issue === 'E-Commerce Consumer Issue') {
        const problemLabels = {
            product_not_delivered: 'Product not delivered',
            wrong_product: 'Wrong product',
            damaged_product: 'Damaged product',
            defective_product: 'Defective product',
            incomplete_order: 'Incomplete order',
            product_not_as_described: 'Product not as described',
            refund_not_received: 'Refund not received',
            replacement_not_provided: 'Replacement not provided',
            cancellation_issue: 'Cancellation issue',
            other: 'Other order issue',
        };
        const items = [
            ['Online purchase', summary.online_purchase === undefined ? null : yesNo(summary.online_purchase)],
            ['Platform', summary.platform_name],
            ['Order placed', summary.order_placed === undefined ? null : yesNo(summary.order_placed)],
            ['Payment made', summary.payment_made === undefined ? null : yesNo(summary.payment_made)],
            ['Delivery received', summary.delivery_received === undefined ? null : yesNo(summary.delivery_received)],
            ['Order issue', problemLabels[summary.ecommerce_problem_type] || summary.ecommerce_problem_type],
            ['Seller / platform contacted', summary.seller_contacted === undefined ? null : yesNo(summary.seller_contacted)],
            ['Seller / platform response', summary.seller_response],
            ['Issue resolved', summary.issue_resolved === undefined ? null : yesNo(summary.issue_resolved)],
            ['Desired resolution', summary.desired_resolution],
            ['Product name', summary.product_name],
            ['Seller / business', summary.seller_name],
            ['Seller address', summary.seller_address],
            ['Purchase date', summary.purchase_date ? formatPurchaseDate(summary.purchase_date) : null],
            ['Amount paid', summary.amount_paid ? formatAmount(summary.amount_paid) : null],
            ['Order / invoice number', summary.order_or_invoice_number],
            ['Additional problem details', summary.problem_description],
        ];
        return `<dl class="summary-list">${items.filter(([, value]) => value !== null && value !== undefined && value !== '').map(([label, value]) => `
            <div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`).join('')}
        </dl>`;
    }
    if (summary.selected_issue === 'Deficiency in Service'
        || summary.selected_issue === 'Misleading Advertisement / Unfair Trade Practice') {
        const labels = {
            service_purchased: 'Service purchased',
            service_type: 'Service type',
            service_provider: 'Service provider',
            service_date: 'Service date',
            amount_paid: 'Amount paid',
            service_problem_exists: 'Service problem reported',
            problem_description: 'Problem description',
            service_not_provided: 'Service not provided',
            service_delayed: 'Service delayed',
            service_inadequate: 'Service inadequate / incomplete',
            service_not_as_agreed: 'Service not as agreed',
            provider_contacted: 'Provider contacted',
            provider_response: 'Provider response',
            issue_resolved: 'Issue resolved',
            desired_resolution: 'Desired resolution',
            purchase_proof_available: 'Purchase proof available',
            service_evidence_available: 'Service evidence available',
            communication_available: 'Provider communication available',
            advertisement_seen: 'Advertisement seen',
            advertisement_source: 'Advertisement source',
            advertiser_or_business: 'Advertiser / business',
            product_or_service: 'Product / service advertised',
            claim_made: 'Specific claim made',
            claim_description: 'Claim description',
            actual_experience: 'Actual experience',
            claim_false_or_misleading: 'Claim reported false / misleading',
            important_information_hidden: 'Important information hidden',
            price_or_discount_claim: 'Price / discount claim',
            product_or_service_received: 'Product / service received',
            difference_from_advertisement: 'Difference from advertisement',
            business_contacted: 'Business contacted',
            business_response: 'Business response',
            advertisement_evidence_available: 'Advertisement evidence available',
            platform_name: 'Platform / website / app',
            product_name: 'Product name',
            seller_name: 'Seller / business name',
            seller_address: 'Business address',
            purchase_date: 'Purchase date',
            amount_paid: 'Amount paid',
            order_or_invoice_number: 'Order / invoice number',
        };
        const items = Object.entries(summary)
            .filter(([key, value]) => key !== 'selected_issue' && key !== 'situation_text'
                && labels[key] && value !== null && value !== undefined && value !== '')
            .map(([key, value]) => [
                labels[key],
                typeof value === 'boolean' ? yesNo(value)
                    : key === 'purchase_date' ? formatPurchaseDate(value)
                        : key === 'amount_paid' ? formatAmount(value)
                            : value,
            ]);
        return `<dl class="summary-list">${items.map(([label, value]) => `
            <div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`).join('')}
        </dl>`;
    }
    const resolution = summary.seller_response_resolution;
    const items = [
        ['Case ID', currentCase?.case_id],
        ['Case title', currentCase?.case_title],
        ['Selected issue', summary.selected_issue],
        ['Purchased from a seller or business', yesNo(summary.product_purchased)],
        ['Product has a problem', yesNo(summary.product_has_problem)],
        ['Product name', summary.product_name],
        ['Seller name', summary.seller_name],
        ['Purchase date', formatPurchaseDate(summary.purchase_date)],
        ['Amount paid', formatAmount(summary.amount_paid)],
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
    Object.entries(summary.issue_details || {}).forEach(([label, value]) => {
        items.push([label, typeof value === 'boolean' ? yesNo(value) : value]);
    });
    return `<dl class="summary-list">${items.map(([label, value]) => `
        <div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value === null || value === undefined || value === '' ? 'Not provided' : value)}</dd></div>`).join('')}
    </dl>`;
}


function formatPurchaseDate(value) {
    if (!value) return 'Not provided';
    const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!match) return String(value);
    const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
    return new Intl.DateTimeFormat('en-GB', {
        day: 'numeric', month: 'long', year: 'numeric'
    }).format(date);
}


function formatAmount(value) {
    if (value === null || value === undefined || value === '') return 'Not provided';
    const amount = Number(value);
    if (!Number.isFinite(amount)) return String(value);
    return new Intl.NumberFormat('en-IN', {
        style: 'currency', currency: 'INR', maximumFractionDigits: 0
    }).format(amount);
}


function yesNo(value) {
    return value === true ? 'Yes' : value === false ? 'No' : 'Not provided';
}


function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, character => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    })[character]);
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
    if (!currentSessionToken || !currentReport) {
        appendMessage('assistant', '<p>Prepare a guidance report before exporting.</p>');
        return;
    }
    try {
        const response = await axios.get(`${API_BASE_URL}/cases/${encodeURIComponent(currentSessionToken)}/pdf`, {
            responseType: 'blob',
        });
        const url = URL.createObjectURL(response.data);
        const link = document.createElement('a');
        link.href = url;
        link.download = `${currentCase.case_id}-report.pdf`;
        link.click();
        URL.revokeObjectURL(url);
        await openCase(currentSessionToken);
    } catch (error) {
        appendMessage('assistant', '<p role="alert">The PDF could not be exported. Please try again.</p>');
    }
}


async function handleReportActions(event) {
    if (event.target.closest('[data-cancel-document]')) {
        closeDocumentFlow();
        return;
    }
    if (event.target.closest('[data-generate-document-pdf]')) {
        await generateDocumentPdf();
        return;
    }
    if (event.target.closest('[data-download-document-pdf]')) {
        downloadDocumentPdf();
        return;
    }
    const documentButton = event.target.closest('[data-document-type]');
    if (documentButton) {
            openDocumentDetails(documentButton.dataset.documentType, documentButton.textContent);
        return;
    }
}


function openDocumentDetails(documentType, label) {
    pendingDocumentType = documentType;
    pendingDocumentTitle = label;
    generatedDocumentPdf = null;
    document.getElementById('document-preview-step').classList.add('hidden');
    document.getElementById('document-pdf-ready').classList.add('hidden');
    document.getElementById('consumer-details-step').classList.remove('hidden');
    document.getElementById('consumer-details-heading').textContent = `${label} — Consumer Details`;
    document.getElementById('consumer-details-form').elements.consumer_name.value = '';
    document.getElementById('consumer-details-form').elements.consumer_address.value = '';
    document.getElementById('consumer-details-form').elements.consumer_phone.value = '';
    document.getElementById('consumer-details-form').elements.consumer_email.value = '';
    document.getElementById('consumer-details-form').elements.document_date.value = '';
    document.getElementById('consumer-details-form').scrollIntoView({behavior: 'smooth', block: 'center'});
}


function closeDocumentFlow() {
    document.getElementById('consumer-details-step').classList.add('hidden');
    document.getElementById('document-preview-step').classList.add('hidden');
    document.getElementById('document-pdf-ready').classList.add('hidden');
}


async function previewDocument(event) {
    event.preventDefault();
    const form = event.target.closest('#consumer-details-form');
    if (!form) return;
    const formData = new FormData(form);
    pendingConsumerDetails = Object.fromEntries(
        [...formData.entries()].map(([key, value]) => [key, String(value).trim()])
    );
    if (!pendingConsumerDetails.consumer_name) return;
    try {
        const response = await axios.post(
            `${API_BASE_URL}/cases/${encodeURIComponent(currentSessionToken)}/documents`,
            {document_type: pendingDocumentType, consumer_details: pendingConsumerDetails}
        );
        currentDraft = response.data.preview;
        document.getElementById('generated-document-title').textContent = response.data.title;
        document.getElementById('generated-document-content').textContent = currentDraft;
        document.getElementById('consumer-details-step').classList.add('hidden');
        document.getElementById('document-preview-step').classList.remove('hidden');
        document.getElementById('document-preview-step').scrollIntoView({behavior: 'smooth', block: 'center'});
    } catch (error) {
        appendMessage('assistant', `<p role="alert">${escapeHtml(error.response?.data?.error || 'Unable to prepare this document preview.')}</p>`);
    }
}


async function generateDocumentPdf() {
    try {
        const response = await axios.post(
            `${API_BASE_URL}/cases/${encodeURIComponent(currentSessionToken)}/documents/pdf`,
            {document_type: pendingDocumentType, consumer_details: pendingConsumerDetails},
            {responseType: 'blob'}
        );
        generatedDocumentPdf = response.data;
        document.getElementById('document-preview-step').classList.add('hidden');
        document.getElementById('document-pdf-ready').classList.remove('hidden');
        const refreshed = await axios.get(`${API_BASE_URL}/cases/${encodeURIComponent(currentSessionToken)}`);
        currentCase = refreshed.data.case;
        await saveCurrentCase({status: 'Completed', current_question_key: null});
        await loadCases();
    } catch (error) {
        appendMessage('assistant', '<p role="alert">The document could not be generated or the case could not be completed.</p>');
    }
}


function downloadDocumentPdf() {
    if (!generatedDocumentPdf) return;
    const url = URL.createObjectURL(generatedDocumentPdf);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${currentCase.case_id}-${pendingDocumentType}.pdf`;
    link.click();
    URL.revokeObjectURL(url);
}


// ---------------------------------------------------------
// Glossary
// ---------------------------------------------------------

const GLOSSARY_DOMAIN_ACTS = {
    consumer: ['consumer protection act'],
    rental: ['transfer of property act', 'rent control'],
    cyber: ['information technology act', 'indian penal code / bharatiya nyaya'],
    contract: ['indian contract act'],
};
const GLOSSARY_DOMAIN_NAMES = {
    consumer: 'Consumer',
    rental: 'Rental',
    cyber: 'Cyber',
    contract: 'Contract',
};


async function openGlossary() {
    glossaryOverlay.classList.remove('hidden');
    glossarySearch.value = '';
    glossaryResults.innerHTML = '<p class="glossary-loading">Loading glossary entries…</p>';
    glossarySearch.focus();
    if (!glossaryLoaded) {
        try {
            const response = await axios.get(`${API_BASE_URL}/glossary`, {params: {q: ''}});
            glossaryEntries = response.data.results || [];
            glossaryLoaded = true;
        } catch (error) {
            glossaryResults.innerHTML = '<p class="glossary-empty" role="alert">The glossary could not be loaded.</p>';
            return;
        }
    }
    renderGlossary();
}


function closeGlossaryModal() {
    glossaryOverlay.classList.add('hidden');
    glossaryBtn?.focus();
}


function searchGlossary() {
    renderGlossary();
}


function glossaryTermName(key) {
    return key.replace(/_/g, ' ').replace(/\b\w/g, character => character.toUpperCase());
}


function glossaryProvisionDomain(provision) {
    const act = (provision.act_name || '').toLowerCase();
    return Object.entries(GLOSSARY_DOMAIN_ACTS)
        .find(([, names]) => names.some(name => act.includes(name)))?.[0] || null;
}


function glossaryMatches(entry, query) {
    if (!query) return true;
    const searchable = entry.type === 'concept'
        ? `${entry.key} ${entry.domain} ${entry.description}`
        : `${entry.act_name} ${entry.section_number} ${entry.title} ${entry.description}`;
    return searchable.toLowerCase().includes(query);
}


function renderGlossary() {
    const domain = currentGlossaryDomain;
    const query = glossarySearch.value.trim().toLowerCase();
    const concepts = glossaryEntries.filter(entry =>
        entry.type === 'concept' && entry.domain === domain && glossaryMatches(entry, query)
    );
    const provisions = glossaryEntries.filter(entry =>
        entry.type === 'provision' && glossaryProvisionDomain(entry) === domain && glossaryMatches(entry, query)
    );
    if (!concepts.length && !provisions.length) {
        glossaryResults.innerHTML = `<p class="glossary-empty">No ${escapeHtml(GLOSSARY_DOMAIN_NAMES[domain])} knowledge-base entries match this search.</p>`;
        return;
    }

    const termCards = concepts.map(concept => {
        const related = provisions.filter(provision => {
            const term = glossaryTermName(concept.key).toLowerCase();
            return provision.title.toLowerCase().includes(term)
                || term.includes(provision.title.toLowerCase());
        });
        const references = related.map(provision => {
            const label = `${escapeHtml(provision.section_number)} · ${escapeHtml(provision.act_name)}`;
            return provision.source_url
                ? `<a class="glossary-law-reference" href="${escapeHtml(provision.source_url)}" target="_blank" rel="noopener noreferrer">${label}</a>`
                : `<span class="glossary-law-reference">${label}</span>`;
        }).join('');
        return `<article class="glossary-entry glossary-concept">
            <div class="glossary-entry-meta"><span>Term</span><span>${escapeHtml(GLOSSARY_DOMAIN_NAMES[domain])}</span></div>
            <h3>${escapeHtml(glossaryTermName(concept.key))}</h3>
            <p class="glossary-definition"><span>Simple definition</span>${escapeHtml(concept.description)}</p>
            <p class="glossary-practical">In practice, use this term to describe the kind of issue involved; its legal application depends on the facts.</p>
            ${references ? `<div class="glossary-references"><span>Relevant law</span>${references}</div>` : ''}
        </article>`;
    }).join('');

    const provisionCards = provisions.map(provision => `
        <article class="glossary-entry glossary-provision">
            <div class="glossary-entry-meta"><span>Legal provision</span><span>${escapeHtml(provision.section_number)}</span></div>
            <h3>${escapeHtml(provision.title)}</h3>
            <p class="glossary-act">${escapeHtml(provision.act_name)}</p>
            ${provision.description ? `<p class="glossary-definition"><span>Legal meaning</span>${escapeHtml(provision.description)}</p>` : ''}
            ${provision.source_url ? `<a class="glossary-source" href="${escapeHtml(provision.source_url)}" target="_blank" rel="noopener noreferrer">Open verified source</a>` : ''}
        </article>`).join('');

    glossaryResults.innerHTML = `<p class="glossary-result-count">${concepts.length + provisions.length} knowledge-base entries · ${escapeHtml(GLOSSARY_DOMAIN_NAMES[domain])}</p>${termCards}${provisionCards}`;
}
