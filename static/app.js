const state = {
    currentQuery: "",
    currentTriageClass: null,
    freeResponseId: null,
    location: null,
    checkinId: null,
    paid: false,
    sessionId: null,
    isBusy: false,
};

const examplePlaceholders = [
    "dor no peito",
    "farmacia aberta",
    "hospital mais proximo",
    "nao sei o que fazer",
    "estou com ansiedade",
    "preciso de um medicamento",
];

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
    if (state.isBusy) {
        return;
    }

    const query = queryInput.value.trim();
    if (!query) {
        queryInput.focus();
        setStatus("Escreva o que precisa antes de continuar.");
        return;
    }

    state.currentQuery = query;
    state.currentTriageClass = null;
    state.freeResponseId = null;
    state.checkinId = null;
    state.paid = false;
    state.sessionId = null;
    resetConversationPanels();
    await submitTriage(query);
});

queryInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        form.requestSubmit();
    }
});

voiceButton.addEventListener("click", () => {
    if (!recognition) {
        setStatus("A gravacao de voz nao esta disponivel neste browser.");
        return;
    }
    if (state.isBusy) {
        return;
    }
    recognition.start();
    setStatus("A ouvir...");
});

if (recognition) {
    recognition.addEventListener("result", (event) => {
        const transcript = Array.from(event.results)
            .map((result) => result[0]?.transcript || "")
            .join(" ")
            .trim();

        if (!transcript) {
            setStatus("Nao foi possivel perceber o que disse.");
            return;
        }

        queryInput.value = transcript;
        setStatus("Texto captado. Pode rever e continuar.");
    });

    recognition.addEventListener("error", () => {
        setStatus("A gravacao foi interrompida.");
    });
}

locationButton.addEventListener("click", async () => {
    if (!navigator.geolocation) {
        setStatus("A localizacao nao esta disponivel neste dispositivo.");
        return;
    }
    if (!state.currentQuery || state.isBusy) {
        return;
    }

    setStatus("A obter localizacao...");
    navigator.geolocation.getCurrentPosition(
        async (position) => {
            state.location = {
                latitude: position.coords.latitude,
                longitude: position.coords.longitude,
            };
            locationText.textContent = `Localizacao aproximada ativa (${position.coords.latitude.toFixed(3)}, ${position.coords.longitude.toFixed(3)}).`;
            await submitTriage(state.currentQuery);
        },
        () => {
            setStatus("Nao foi possivel obter a localizacao.");
        },
        { enableHighAccuracy: false, maximumAge: 300000, timeout: 8000 },
    );
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

async function submitTriage(query) {
    setBusy(true, "A analisar...");
    try {
        const response = await fetch("/api/triage", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query, location: state.location }),
        });
        const payload = await readJsonResponse(response);
        if (!response.ok) {
            throw new Error(payload.error || "Nao foi possivel analisar o pedido.");
        }

        renderTriageResult(payload);
        clearStatus();
    } catch (error) {
        setStatus(error.message);
    } finally {
        setBusy(false);
    }
}

function renderTriageResult(payload) {
    const triage = payload.triage || {};
    const resources = payload.resources || {};
    state.currentTriageClass = triage.triage_class || null;

    resultSection.classList.remove("hidden");
    resultKicker.textContent = triage.triage_class || "resultado";
    resultHeadline.textContent = buildResultHeadline(triage, state.currentQuery);
    resultSummary.textContent = buildResultSummary(triage, state.currentQuery);

    locationTools.classList.toggle("hidden", !["emergency_potential", "urgent_care", "practical_health"].includes(state.currentTriageClass));
    renderActions(resources.actions || []);
    renderResources(resources.resources || [], resources.notes || [], triage, state.currentQuery);

    if (state.currentTriageClass === "light_conversation" && payload.free_response) {
        freeResponseCard.classList.remove("hidden");
        freeResponseText.innerHTML = payload.free_response.message
            .split("\n")
            .map((line) => `<p>${escapeHtml(line)}</p>`)
            .join("");
        paymentPanel.classList.remove("hidden");
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

function renderResources(resources, notes, triage, query) {
    if (!resources.length && !notes.length) {
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

    resources.forEach((item, index) => {
        const article = document.createElement("article");
        article.className = `resource-item${index === 0 ? " resource-item-primary" : ""}`;
        article.innerHTML = `
            <div class="resource-main">
                <h3>${escapeHtml(item.title || "")}</h3>
                <p>${escapeHtml(item.description || "")}</p>
                <div class="resource-meta">
                    ${item.region ? `<span>${escapeHtml(item.region)}</span>` : ""}
                    ${item.phone ? `<a href="tel:${escapeHtml(item.phone.replace(/\s+/g, ""))}">${escapeHtml(item.phone)}</a>` : ""}
                </div>
            </div>
            ${item.url ? `<a class="resource-open" href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer">Abrir</a>` : ""}
        `;
        resourceList.appendChild(article);
    });

    if (!resources.length) {
        const empty = document.createElement("p");
        empty.className = "empty-note";
        empty.textContent = "Sem resultados adicionais para mostrar neste momento.";
        resourceList.appendChild(empty);
    }

    notes.forEach((note) => {
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
                original_query: state.currentQuery,
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

function buildResourceHeading(triage, query) {
    const normalizedQuery = (query || "").toLowerCase();
    if (triage?.triage_class === "emergency_potential") {
        return "Encaminhamento imediato";
    }
    if (normalizedQuery.includes("medic")) {
        return "Recursos para medicamento";
    }
    if (normalizedQuery.includes("farmac")) {
        return "Recursos para farmacia";
    }
    if (normalizedQuery.includes("hospital")) {
        return "Recursos para hospital";
    }
    if (normalizedQuery.includes("urg")) {
        return "Recursos para urgencia";
    }
    return "Recursos relevantes";
}

function buildResourceIntro(triage, query) {
    const normalizedQuery = (query || "").toLowerCase();
    if (triage?.triage_class === "emergency_potential") {
        return "Se houver risco imediato, comece por 112.";
    }
    if (normalizedQuery.includes("medic")) {
        return "Comece pela pesquisa oficial de medicamentos.";
    }
    if (normalizedQuery.includes("farmac")) {
        return "Comece por verificar a opcao mais proxima disponivel.";
    }
    if (normalizedQuery.includes("hospital")) {
        return "Comece pelo hospital mais adequado ao que descreveu.";
    }
    if (normalizedQuery.includes("urg")) {
        return "Comece pelo recurso mais proximo e institucional.";
    }
    return "Comece pelo primeiro recurso desta lista.";
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
