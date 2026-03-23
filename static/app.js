const state = {
    currentQuery: "",
    currentResolvedQuery: "",
    currentTriageClass: null,
    freeResponseId: null,
    location: null,
    locationRequestInFlight: false,
    checkinId: null,
    paid: false,
    sessionId: null,
    browserSessionId: ensureBrowserSessionId(),
    isBusy: false,
    isAnalyzing: false,
    activeAbortController: null,
    requestSequence: 0,
    activeRequestId: 0,
    latestAppliedRequestId: 0,
    lastSubmittedKey: "",
    autoSubmitTimer: null,
    manualLocationTimer: null,
    pendingVoiceTranscript: "",
    deniedLocationKeys: new Set(),
};

const examplePlaceholders = [
    "dor no peito",
    "farmacia aberta",
    "hospital mais proximo",
    "nao sei o que fazer",
    "estou com ansiedade",
    "preciso de um medicamento",
];

const DEFAULT_DEBOUNCE_MS = 900;
const AMBIGUOUS_DEBOUNCE_MS = 1200;
const MIN_SUBMIT_LENGTH = 4;
const BLOCKED_AMBIGUOUS_TERMS = new Set(["dor", "ajuda", "ola", "falar"]);
const SLOW_AMBIGUOUS_TERMS = new Set(["hospital", "farmacia"]);

const form = document.querySelector("#triage-form");
const queryInput = document.querySelector("#query-input");
const continueButton = document.querySelector("#continue-button");
const voiceButton = document.querySelector("#voice-button");
const statusText = document.querySelector("#status-text");
const resultSection = document.querySelector("#result-section");
const resultKicker = document.querySelector("#result-kicker");
const resultHeadline = document.querySelector("#result-headline");
const resultSummary = document.querySelector("#result-summary");
const locationTools = document.querySelector("#location-tools");
const locationButton = document.querySelector("#location-button");
const locationManualInput = document.querySelector("#location-manual-input");
const locationText = document.querySelector("#location-text");
const resultActions = document.querySelector("#result-actions");
const resourcePanel = document.querySelector("#resource-panel");
const resourceHeading = document.querySelector("#resource-heading");
const resourceIntro = document.querySelector("#resource-intro");
const resourceList = document.querySelector("#resource-list");
const resourceNotes = document.querySelector("#resource-notes");
const freeResponseCard = document.querySelector("#free-response-card");
const freeResponseText = document.querySelector("#free-response-text");
const paymentPanel = document.querySelector("#payment-panel");
const paymentForm = document.querySelector("#payment-form");
const phoneInput = document.querySelector("#phone-input");
const paymentNote = document.querySelector("#payment-note");
const chatPanel = document.querySelector("#chat-panel");
const chatLog = document.querySelector("#chat-log");
const chatForm = document.querySelector("#chat-form");
const chatInput = document.querySelector("#chat-input");

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
const recognition = SpeechRecognition ? new SpeechRecognition() : null;

let placeholderIndex = 0;
let placeholderTimer = null;
let statusPollTimer = null;

if (recognition) {
    recognition.lang = "pt-PT";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
}

rotatePlaceholder();
placeholderTimer = window.setInterval(rotatePlaceholder, 2800);

form.addEventListener("submit", async (event) => {
    event.preventDefault();
    await requestSubmission({ source: "manual", force: true });
});

voiceButton.addEventListener("click", () => {
    if (!recognition) {
        setStatus("A gravacao de voz nao esta disponivel neste browser.");
        return;
    }
    if (state.isBusy || state.locationRequestInFlight) {
        return;
    }
    clearPendingSubmission();
    state.pendingVoiceTranscript = "";
    recognition.start();
    setStatus("A ouvir...");
});

queryInput.addEventListener("input", () => {
    if (!state.isAnalyzing && !state.isBusy && !state.locationRequestInFlight) {
        clearStatus();
    }
    scheduleAutoSubmit({ source: "text" });
});

if (recognition) {
    recognition.addEventListener("result", (event) => {
        const transcript = Array.from(event.results)
            .map((result) => result[0]?.transcript || "")
            .join(" ")
            .trim();

        if (!transcript) {
            state.pendingVoiceTranscript = "";
            return;
        }

        state.pendingVoiceTranscript = transcript;
        queryInput.value = transcript;
        setStatus("A analisar...");
    });

    recognition.addEventListener("end", () => {
        const transcript = state.pendingVoiceTranscript.trim();
        state.pendingVoiceTranscript = "";
        if (!transcript) {
            setStatus("Nao foi possivel captar um pedido util. Pode repetir.");
            return;
        }
        void requestSubmission({ source: "voice", force: true, explicitQuery: transcript });
    });

    recognition.addEventListener("error", () => {
        setStatus("A gravacao foi interrompida.");
    });
}

locationButton.addEventListener("click", async () => {
    await requestAutomaticLocation(state.currentResolvedQuery || queryInput.value, { forcedByUser: true });
});

locationManualInput.addEventListener("input", () => {
    if (!state.currentQuery && !queryInput.value.trim()) {
        return;
    }
    if (state.manualLocationTimer) {
        window.clearTimeout(state.manualLocationTimer);
    }
    const locationLabel = locationManualInput.value.trim();
    if (!locationLabel) {
        return;
    }
    state.manualLocationTimer = window.setTimeout(() => {
        void applyManualLocation(locationLabel);
    }, DEFAULT_DEBOUNCE_MS);
});

paymentForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (state.isBusy) {
        return;
    }
    if (state.currentTriageClass !== "light_conversation") {
        return;
    }

    const phone = phoneInput.value.trim();
    if (!phone) {
        phoneInput.focus();
        setStatus("Indique o numero MB WAY.");
        return;
    }

    setBusy(true, "A preparar o pagamento...");
    try {
        const response = await fetch("/api/checkin", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ plan: "continue_1", customer_phone: phone }),
        });
        const payload = await readJsonResponse(response);
        if (!response.ok) {
            throw new Error(payload.error || "Nao foi possivel iniciar o pagamento.");
        }

        state.checkinId = payload.checkin_id || null;
        paymentNote.textContent = payload.payment_note || "";
        setStatus(payload.status || "Pedido criado.");

        if (payload.payment_url && payload.payment_url.startsWith("mbway://")) {
            window.location.href = payload.payment_url;
        }

        startStatusPolling();
    } catch (error) {
        setStatus(error.message);
    } finally {
        setBusy(false);
    }
});

chatForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (state.isBusy || !state.sessionId) {
        return;
    }

    const message = chatInput.value.trim();
    if (!message) {
        chatInput.focus();
        return;
    }

    appendChatMessage("utilizador", message);
    chatInput.value = "";
    setBusy(true, "A responder...");

    try {
        const response = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id: state.sessionId, message }),
        });
        const payload = await readJsonResponse(response);
        if (!response.ok) {
            throw new Error(payload.error || "Nao foi possivel continuar a conversa.");
        }

        appendChatMessage("sistema", payload.message);
        setStatus("Resposta pronta.");
    } catch (error) {
        setStatus(error.message);
    } finally {
        setBusy(false);
    }
});

function scheduleAutoSubmit({ source }) {
    clearPendingSubmission();
    const query = queryInput.value;
    const normalized = normalizeQueryForComparison(query);
    const validation = validateAutoSubmission(normalized, source);
    if (!validation.allowed) {
        if (validation.blockedMessage && normalized) {
            state.autoSubmitTimer = window.setTimeout(() => {
                setStatus(validation.blockedMessage);
            }, validation.debounceMs);
        }
        return;
    }

    state.autoSubmitTimer = window.setTimeout(() => {
        void requestSubmission({ source });
    }, validation.debounceMs);
}

function clearPendingSubmission() {
    if (state.autoSubmitTimer) {
        window.clearTimeout(state.autoSubmitTimer);
        state.autoSubmitTimer = null;
    }
}

async function requestSubmission({ source, force = false, explicitQuery = "" } = {}) {
    const query = (explicitQuery || queryInput.value || "").trim();
    const normalized = normalizeQueryForComparison(query);
    const validation = validateAutoSubmission(normalized, source);
    if (!query || (!force && !validation.allowed)) {
        if (source === "voice" && normalized) {
            setStatus("Diga um pouco mais para eu perceber melhor.");
        }
        return false;
    }

    state.currentQuery = query;
    state.currentResolvedQuery = query;
    state.currentTriageClass = null;
    state.freeResponseId = null;
    state.checkinId = null;
    state.paid = false;
    state.sessionId = null;
    resetConversationPanels();
    return submitTriage(query, { source, force });
}

async function submitTriage(query, { source = "text", force = false } = {}) {
    clearPendingSubmission();
    const trimmedQuery = (query || "").trim();
    const normalized = normalizeQueryForComparison(trimmedQuery);
    const validation = validateAutoSubmission(normalized, source);
    if (!trimmedQuery || (!force && !validation.allowed)) {
        return false;
    }

    const locationPayload = buildLocationPayload();
    const submissionKey = `${normalized}::${buildLocationKey(locationPayload)}`;
    if (!force && submissionKey === state.lastSubmittedKey) {
        return false;
    }

    if (state.activeAbortController) {
        state.activeAbortController.abort();
    }

    const requestId = ++state.requestSequence;
    const controller = new AbortController();
    state.activeAbortController = controller;
    state.activeRequestId = requestId;
    state.isAnalyzing = true;
    setStatus(resultSection.classList.contains("hidden") ? "A analisar..." : "A atualizar resultado...");

    try {
        const response = await fetch("/api/triage", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query: trimmedQuery, location: locationPayload, session_id: state.browserSessionId }),
            signal: controller.signal,
        });
        const payload = await readJsonResponse(response);
        if (!response.ok) {
            throw new Error(payload.error || "Nao foi possivel analisar o pedido.");
        }
        if (requestId !== state.activeRequestId) {
            return false;
        }

        state.lastSubmittedKey = submissionKey;
        state.latestAppliedRequestId = requestId;
        renderTriageResult(payload);
        await maybeRequestLocation(payload, normalized, requestId);
        if (!state.locationRequestInFlight) {
            clearStatus();
        }
        return true;
    } catch (error) {
        if (error?.name === "AbortError") {
            return false;
        }
        if (requestId === state.activeRequestId) {
            setStatus(error.message);
        }
        return false;
    } finally {
        if (requestId === state.activeRequestId) {
            state.activeAbortController = null;
            state.isAnalyzing = false;
        }
    }
}

function normalizeQueryForComparison(value) {
    return (value || "")
        .toLowerCase()
        .trim()
        .replace(/[.,!?;:()[\]{}"'`´]+/g, " ")
        .replace(/\s+/g, " ");
}

function validateAutoSubmission(normalized, source = "text") {
    if (!normalized || normalized.length < MIN_SUBMIT_LENGTH) {
        return { allowed: false, debounceMs: DEFAULT_DEBOUNCE_MS, blockedMessage: "" };
    }
    if (BLOCKED_AMBIGUOUS_TERMS.has(normalized)) {
        return {
            allowed: false,
            debounceMs: AMBIGUOUS_DEBOUNCE_MS,
            blockedMessage: "Diga um pouco mais para eu perceber melhor.",
        };
    }
    if (source === "voice" && normalized.length < MIN_SUBMIT_LENGTH) {
        return { allowed: false, debounceMs: DEFAULT_DEBOUNCE_MS, blockedMessage: "Diga um pouco mais para eu perceber melhor." };
    }
    if (normalized === state.currentResolvedQuery && normalizeQueryForComparison(queryInput.value) === normalized) {
        // Keep typing continuity, but do not block reclassification with new location.
    }
    const debounceMs = SLOW_AMBIGUOUS_TERMS.has(normalized) ? AMBIGUOUS_DEBOUNCE_MS : DEFAULT_DEBOUNCE_MS;
    return { allowed: true, debounceMs, blockedMessage: "" };
}

function buildLocationPayload() {
    if (!state.location) {
        return null;
    }
    if (state.location.latitude !== undefined && state.location.longitude !== undefined) {
        return {
            latitude: state.location.latitude,
            longitude: state.location.longitude,
        };
    }
    if (state.location.label) {
        return { label: state.location.label };
    }
    return null;
}

function buildLocationKey(location) {
    if (!location) {
        return "none";
    }
    if (location.label) {
        return `label:${normalizeQueryForComparison(location.label)}`;
    }
    if (location.latitude !== undefined && location.longitude !== undefined) {
        return `coords:${location.latitude.toFixed(3)}:${location.longitude.toFixed(3)}`;
    }
    return "none";
}

async function maybeRequestLocation(payload, normalizedQuery, requestId) {
    const resources = payload.resources || {};
    updateLocationState(resources);
    if (!resources.requires_location || state.locationRequestInFlight) {
        return;
    }
    if (state.location || state.deniedLocationKeys.has(normalizedQuery)) {
        if (!state.location && state.deniedLocationKeys.has(normalizedQuery)) {
            showLocationFallback("Indique cidade ou distrito para refinar o resultado.");
        }
        return;
    }
    await requestAutomaticLocation(payload.memory?.resolved_query || state.currentResolvedQuery, { requestId });
}

async function requestAutomaticLocation(query, { forcedByUser = false, requestId = null } = {}) {
    const normalized = normalizeQueryForComparison(query);
    if (!forcedByUser && state.deniedLocationKeys.has(normalized)) {
        showLocationFallback("Indique cidade ou distrito para refinar o resultado.");
        return;
    }
    if (!navigator.geolocation) {
        showLocationFallback("A localizacao nao esta disponivel neste dispositivo.");
        return;
    }

    state.locationRequestInFlight = true;
    setStatus("A procurar opcoes perto de si...");

    navigator.geolocation.getCurrentPosition(
        async (position) => {
            if (requestId && requestId !== state.latestAppliedRequestId) {
                state.locationRequestInFlight = false;
                return;
            }
            const currentNormalized = normalizeQueryForComparison(queryInput.value || query);
            if (!forcedByUser && currentNormalized !== normalized) {
                state.locationRequestInFlight = false;
                return;
            }

            state.location = {
                latitude: position.coords.latitude,
                longitude: position.coords.longitude,
            };
            locationManualInput.classList.add("hidden");
            locationText.textContent = "A mostrar opcoes perto de si.";
            state.locationRequestInFlight = false;
            await submitTriage(queryInput.value || query, { source: "location-auto", force: true });
        },
        () => {
            state.locationRequestInFlight = false;
            state.deniedLocationKeys.add(normalized);
            showLocationFallback("Indique cidade ou distrito para refinar o resultado.");
        },
        { enableHighAccuracy: false, maximumAge: 300000, timeout: 8000 },
    );
}

async function applyManualLocation(locationLabel) {
    if (!locationLabel) {
        return;
    }
    state.location = { label: locationLabel };
    locationText.textContent = `Localizacao aproximada ativa: ${formatLocationLabel(locationLabel)}.`;
    locationManualInput.classList.remove("hidden");
    await submitTriage(queryInput.value || state.currentQuery, { source: "location-manual", force: true });
}

function updateLocationState(resources) {
    if (resources.location_label) {
        locationText.textContent = `Localizacao aproximada ativa: ${resources.location_label}.`;
        locationManualInput.classList.add("hidden");
        return;
    }
    if (state.location && state.location.label) {
        locationText.textContent = `Localizacao aproximada ativa: ${formatLocationLabel(state.location.label)}.`;
        return;
    }
    if (state.location && state.location.latitude !== undefined) {
        locationText.textContent = "A mostrar opcoes perto de si.";
        return;
    }
    if (!resources.requires_location) {
        locationText.textContent = "";
        locationManualInput.classList.add("hidden");
    }
}

function showLocationFallback(message) {
    locationManualInput.classList.remove("hidden");
    locationText.textContent = message;
    if (!locationManualInput.value) {
        locationManualInput.focus();
    }
}

function formatLocationLabel(value) {
    const trimmed = (value || "").trim();
    if (!trimmed) {
        return "";
    }
    return trimmed
        .split(/\s+/)
        .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
        .join(" ");
}

function renderTriageResult(payload) {
    const triage = payload.triage || {};
    const response = payload.response || {};
    const resources = payload.resources || {};
    const memory = payload.memory || {};
    state.currentResolvedQuery = memory.resolved_query || state.currentQuery;
    state.currentTriageClass = triage.triage_class || null;

    resultSection.classList.remove("hidden");
    resultKicker.textContent = buildResultKicker(triage);
    resultHeadline.textContent = response.title || buildResultHeadline(triage, state.currentResolvedQuery);
    resultSummary.innerHTML = formatStructuredText(response.message || buildResultSummary(triage, state.currentResolvedQuery));

    locationTools.classList.toggle("hidden", !["emergency_potential", "urgent_care", "practical_health"].includes(state.currentTriageClass));
    locationButton.classList.toggle("hidden", !resources.requires_location && !state.location);
    renderActions(response.actions || resources.actions || []);
    if (state.currentTriageClass === "light_conversation") {
        renderResources([], [], triage, state.currentResolvedQuery, []);
    } else {
        renderResources(
            resources.resources || [],
            resources.notes || [],
            triage,
            state.currentResolvedQuery,
            response.actions || [],
        );
    }

    if (state.currentTriageClass === "light_conversation") {
        freeResponseCard.classList.add("hidden");
        paymentPanel.classList.remove("hidden");
        if (response.payment_prompt) {
            paymentPanel.querySelector(".panel-label").textContent = response.payment_prompt;
        }
    } else {
        freeResponseCard.classList.add("hidden");
        paymentPanel.classList.add("hidden");
    }

    if (state.currentTriageClass === "emergency_potential") {
        paymentPanel.classList.add("hidden");
        chatPanel.classList.add("hidden");
    }
}

function renderActions(actions) {
    resultActions.innerHTML = "";
    if (!actions.length) {
        return;
    }
    actions.forEach((action) => {
        const element = document.createElement("a");
        element.className = `button ${action.style === "primary" ? "button-primary" : "button-secondary"}`;
        element.href = action.url;
        element.target = action.external === false ? "_self" : "_blank";
        element.rel = "noreferrer";
        element.textContent = action.label;
        resultActions.appendChild(element);
    });
}

function renderResources(resources, notes, triage, query, selectedActions) {
    const selectedLabels = new Set((selectedActions || []).map((action) => action.label));
    const filteredResources = (resources || [])
        .filter((item) => !selectedLabels.has(item.title))
        .slice(0, 2);
    const trimmedNotes = (notes || []).slice(0, 1);

    if (!filteredResources.length && !trimmedNotes.length) {
        resourcePanel.classList.add("hidden");
        resourceHeading.textContent = "";
        resourceIntro.textContent = "";
        return;
    }

    resourcePanel.classList.remove("hidden");
    resourceHeading.textContent = buildResourceHeading(triage, query);
    resourceIntro.textContent = buildResourceIntro(triage, query);
    resourceList.innerHTML = "";
    resourceNotes.innerHTML = "";

    filteredResources.forEach((item, index) => {
        const article = document.createElement("article");
        article.className = `resource-item${index === 0 ? " resource-item-primary" : ""}`;
        const target = item.url && item.url.startsWith("tel:") ? "_self" : "_blank";
        const rel = target === "_blank" ? ' rel="noreferrer"' : "";
        article.innerHTML = `
            <div class="resource-main">
                <h3>${escapeHtml(item.title || "")}</h3>
                <p>${escapeHtml(item.description || "")}</p>
                <div class="resource-meta">
                    ${item.region ? `<span>${escapeHtml(item.region)}</span>` : ""}
                    ${item.phone ? `<a href="tel:${escapeHtml(item.phone.replace(/\s+/g, ""))}">${escapeHtml(item.phone)}</a>` : ""}
                </div>
            </div>
            ${item.url ? `<a class="resource-open" href="${escapeHtml(item.url)}" target="${target}"${rel}>Abrir</a>` : ""}
        `;
        resourceList.appendChild(article);
    });

    trimmedNotes.forEach((note) => {
        const li = document.createElement("li");
        li.textContent = note;
        resourceNotes.appendChild(li);
    });
}

function startStatusPolling() {
    clearStatusPoll();
    if (!state.checkinId) {
        return;
    }
    statusPollTimer = window.setInterval(checkCheckinStatus, 1500);
    void checkCheckinStatus();
}

function clearStatusPoll() {
    if (statusPollTimer) {
        window.clearInterval(statusPollTimer);
        statusPollTimer = null;
    }
}

async function checkCheckinStatus() {
    if (!state.checkinId || state.paid) {
        clearStatusPoll();
        return;
    }

    try {
        const response = await fetch(`/api/checkin/status?id=${encodeURIComponent(state.checkinId)}`);
        const payload = await readJsonResponse(response);
        if (!response.ok) {
            throw new Error(payload.error || "Nao foi possivel validar o pagamento.");
        }

        setStatus(payload.status);
        paymentNote.textContent = payload.payment_note || paymentNote.textContent;

        if (payload.status_code === "AUTHORIZED" || payload.status_code === "Success") {
            state.paid = true;
            clearStatusPoll();
            paymentNote.textContent = "Pagamento confirmado.";
            await startPaidConversation();
        }
    } catch (error) {
        clearStatusPoll();
        setStatus(error.message);
    }
}

async function startPaidConversation() {
    setBusy(true, "A iniciar a conversa...");
    try {
        const response = await fetch("/api/session/start", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                plan: "continue_1",
                checkin_id: state.checkinId,
                original_query: state.currentResolvedQuery || state.currentQuery,
            }),
        });
        const payload = await readJsonResponse(response);
        if (!response.ok) {
            throw new Error(payload.error || "Nao foi possivel iniciar a conversa.");
        }

        state.sessionId = payload.session_id;
        paymentPanel.classList.add("hidden");
        chatPanel.classList.remove("hidden");
        appendChatMessage("sistema", payload.message);
        setStatus("Conversa pronta.");
    } catch (error) {
        setStatus(normalizeConversationError(error.message));
    } finally {
        setBusy(false);
    }
}

function appendChatMessage(role, message) {
    const entry = document.createElement("div");
    entry.className = `chat-entry ${role}`;
    entry.innerHTML = `<p>${escapeHtml(message).replace(/\n/g, "<br>")}</p>`;
    chatLog.appendChild(entry);
    chatLog.scrollTop = chatLog.scrollHeight;
}

function resetConversationPanels() {
    clearStatusPoll();
    freeResponseCard.classList.add("hidden");
    paymentPanel.classList.add("hidden");
    chatPanel.classList.add("hidden");
    paymentNote.textContent = "";
    chatLog.innerHTML = "";
}

function rotatePlaceholder() {
    queryInput.placeholder = examplePlaceholders[placeholderIndex % examplePlaceholders.length];
    placeholderIndex += 1;
}

function setBusy(value, message) {
    state.isBusy = value;
    continueButton.disabled = value;
    voiceButton.disabled = value;
    phoneInput.disabled = value;
    chatInput.disabled = value;
    paymentForm.querySelector("button[type='submit']").disabled = value;
    chatForm.querySelector("button[type='submit']").disabled = value;
    if (message) {
        setStatus(message);
    }
}

function setStatus(message) {
    statusText.textContent = message;
    statusText.classList.remove("hidden");
}

function clearStatus() {
    statusText.textContent = "";
    statusText.classList.add("hidden");
}

async function readJsonResponse(response) {
    const contentType = response.headers.get("content-type") || "";
    const rawText = await response.text();
    if (!contentType.includes("application/json")) {
        throw new Error("O servidor devolveu uma resposta invalida.");
    }
    try {
        return JSON.parse(rawText);
    } catch {
        throw new Error("O servidor devolveu JSON invalido.");
    }
}

function normalizeConversationError(message) {
    return "De momento, nao foi possivel continuar a conversa. Tente novamente dentro de instantes.";
}

function escapeHtml(value) {
    return (value || "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
}

function formatStructuredText(value) {
    return (value || "")
        .split("\n")
        .filter(Boolean)
        .map((line) => escapeHtml(line))
        .join("<br>");
}

function ensureBrowserSessionId() {
    const storageKey = "apoio24h_session_id";
    try {
        const existing = window.sessionStorage.getItem(storageKey);
        if (existing) {
            return existing;
        }
        const created = typeof crypto !== "undefined" && crypto.randomUUID
            ? crypto.randomUUID()
            : `sess-${Date.now()}-${Math.random().toString(16).slice(2)}`;
        window.sessionStorage.setItem(storageKey, created);
        return created;
    } catch {
        return `sess-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    }
}

function buildResourceHeading(triage, query) {
    const normalizedQuery = (query || "").toLowerCase();
    if (triage?.triage_class === "emergency_potential") {
        return "Acao seguinte";
    }
    if (normalizedQuery.includes("medic")) {
        return "Se precisar de mais uma opcao";
    }
    if (normalizedQuery.includes("farmac")) {
        return "Se precisar de mais uma opcao";
    }
    if (normalizedQuery.includes("hospital")) {
        return "Se precisar de mais uma opcao";
    }
    if (normalizedQuery.includes("urg")) {
        return "Se precisar de mais uma opcao";
    }
    return "Outras opcoes uteis";
}

function buildResourceIntro(triage, query) {
    const normalizedQuery = (query || "").toLowerCase();
    if (triage?.triage_class === "emergency_potential") {
        return "Se nao conseguir resolver com a primeira acao, use a segunda.";
    }
    if (normalizedQuery.includes("medic")) {
        return "Se a primeira acao nao chegar, use uma alternativa direta.";
    }
    if (normalizedQuery.includes("farmac")) {
        return "Use uma alternativa direta se precisar.";
    }
    if (normalizedQuery.includes("hospital")) {
        return "Escolha apenas a proxima acao util.";
    }
    if (normalizedQuery.includes("urg")) {
        return "Escolha apenas a proxima acao util.";
    }
    return "Use apenas o que fizer sentido agora.";
}

function buildResultHeadline(triage, query) {
    const normalizedQuery = (query || "").toLowerCase();
    if (triage?.triage_class === "emergency_potential") {
        return triage.headline || "Pode ser uma emergencia";
    }
    if (triage?.triage_class === "light_conversation") {
        return triage.headline || "Vamos organizar isto";
    }
    if (normalizedQuery.includes("medic")) {
        return "Para procurar medicamento";
    }
    if (normalizedQuery.includes("farmac")) {
        return "Para procurar farmacia";
    }
    if (normalizedQuery.includes("hospital")) {
        return "Para encontrar hospital";
    }
    if (normalizedQuery.includes("urg")) {
        return "Para procurar urgencia";
    }
    return triage.headline || "Recursos disponiveis";
}

function buildResultSummary(triage, query) {
    const normalizedQuery = (query || "").toLowerCase();
    if (triage?.triage_class === "emergency_potential") {
        return triage.summary || "";
    }
    if (triage?.triage_class === "light_conversation") {
        return triage.summary || "";
    }
    if (normalizedQuery.includes("medic")) {
        return "Veja primeiro a fonte oficial mais adequada para este pedido.";
    }
    if (normalizedQuery.includes("farmac")) {
        return "Veja a opcao mais proxima e o contacto antes de sair.";
    }
    if (normalizedQuery.includes("hospital")) {
        return "Veja primeiro o recurso institucional mais adequado.";
    }
    if (normalizedQuery.includes("urg")) {
        return "Veja o recurso mais proximo e como la chegar.";
    }
    return triage.summary || "";
}

function buildResultKicker(triage) {
    if (triage?.triage_class === "emergency_potential") {
        return "decisao imediata";
    }
    if (triage?.triage_class === "urgent_care") {
        return "avaliacao rapida";
    }
    if (triage?.triage_class === "practical_health") {
        return "acao pratica";
    }
    return "organizacao";
}
