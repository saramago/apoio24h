const state = {
    plan: null,
    checkinId: null,
    customerPhone: null,
    previousResponseId: null,
    isBusy: false,
    sessionStarted: false,
};

const sessionButtons = document.querySelectorAll(".session-button");
const checkinForm = document.querySelector("#checkin-form");
const phoneInput = document.querySelector("#phone-input");
const checkinPanel = document.querySelector("#checkin-panel");
const chatPanel = document.querySelector("#chat-panel");
const statusText = document.querySelector("#status-text");
const paymentNote = document.querySelector("#payment-note");
const chatLog = document.querySelector("#chat-log");
const chatForm = document.querySelector("#chat-form");
const chatInput = document.querySelector("#chat-input");
const chatHelper = document.querySelector("#chat-helper");
let statusPollTimer = null;

sessionButtons.forEach((button) => {
    button.addEventListener("click", async () => {
        if (state.isBusy) {
            return;
        }

        const enteredPhone = phoneInput.value.trim();
        if (!enteredPhone) {
            phoneInput.focus();
            revealStatus("Indique primeiro o numero MB WAY do cliente.");
            return;
        }

        state.plan = button.dataset.plan;
        state.customerPhone = enteredPhone;
        state.sessionStarted = false;
        state.previousResponseId = null;
        state.checkinId = null;
        chatLog.innerHTML = "";
        chatPanel.classList.add("hidden");
        clearStatusPoll();
        setBusy(true, "A preparar o check-in...");
        revealStatus();

        try {
            const response = await fetch("/api/checkin", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    plan: state.plan,
                    customer_phone: state.customerPhone,
                }),
            });

            const payload = await readJsonResponse(response);
            if (!response.ok) {
                throw new Error(payload.error || "Nao foi possivel iniciar o check-in.");
            }

            state.checkinId = payload.checkin_id || null;
            paymentNote.textContent = payload.payment_note || "";
            statusText.textContent = payload.status || "Check-in criado.";

            if (payload.payment_url && payload.payment_url.startsWith("mbway://")) {
                window.location.href = payload.payment_url;
            }

            startStatusPolling();
        } catch (error) {
            paymentNote.textContent = "";
            statusText.textContent = error.message;
        } finally {
            setBusy(false);
        }
    });
});

chatForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (state.isBusy || !state.sessionStarted) {
        return;
    }

    const message = chatInput.value.trim();
    if (!message) {
        return;
    }

    appendMessage("user", message);
    chatInput.value = "";
    setBusy(true, "A gerar resposta...");

    try {
        const response = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                plan: state.plan,
                message,
                previous_response_id: state.previousResponseId,
            }),
        });

        const payload = await readJsonResponse(response);
        if (!response.ok) {
            throw new Error(payload.error || "Erro ao obter resposta.");
        }

        appendMessage("assistant", payload.message);
        state.previousResponseId = payload.response_id || state.previousResponseId;
        statusText.textContent = "Resposta recebida.";
    } catch (error) {
        appendMessage("system", error.message);
        statusText.textContent = error.message;
    } finally {
        setBusy(false);
        chatInput.focus();
    }
});

async function startConversation() {
    if (state.isBusy || !state.plan || !state.checkinId || state.sessionStarted) {
        return;
    }

    setBusy(true, "Pagamento autorizado. A iniciar a conversa...");

    try {
        const response = await fetch("/api/session/start", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                plan: state.plan,
                checkin_id: state.checkinId,
                customer_phone: state.customerPhone,
            }),
        });

        const payload = await readJsonResponse(response);
        if (!response.ok) {
            throw new Error(payload.error || "Nao foi possivel iniciar a conversa.");
        }

        state.previousResponseId = payload.response_id || null;
        state.sessionStarted = true;
        clearStatusPoll();
        chatPanel.classList.remove("hidden");
        chatPanel.scrollIntoView({ behavior: "smooth", block: "start" });
        appendMessage("assistant", payload.message);
        statusText.textContent = "Conversa iniciada.";
        chatInput.focus();
    } catch (error) {
        appendMessage("system", error.message);
        statusText.textContent = error.message;
    } finally {
        setBusy(false);
    }
}

function revealStatus(message) {
    checkinPanel.classList.remove("hidden");
    if (message) {
        statusText.textContent = message;
    }
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
    if (!state.checkinId || state.sessionStarted) {
        clearStatusPoll();
        return;
    }

    try {
        const response = await fetch(`/api/checkin/status?id=${encodeURIComponent(state.checkinId)}`);
        const payload = await readJsonResponse(response);
        if (!response.ok) {
            throw new Error(payload.error || "Nao foi possivel validar o pagamento.");
        }

        statusText.textContent = payload.status;
        paymentNote.textContent = payload.payment_note || paymentNote.textContent;

        if (payload.status_code === "AUTHORIZED" || payload.status_code === "Success") {
            await startConversation();
        }
    } catch (error) {
        clearStatusPoll();
        statusText.textContent = error.message;
    }
}

function appendMessage(role, content) {
    const item = document.createElement("article");
    item.className = `message ${role}`;
    item.textContent = content;
    chatLog.appendChild(item);
    chatLog.scrollTop = chatLog.scrollHeight;
}

function setBusy(value, message) {
    state.isBusy = value;
    sessionButtons.forEach((button) => {
        button.disabled = value;
    });
    phoneInput.disabled = value;
    chatInput.disabled = value || !state.sessionStarted;
    chatForm.querySelector("button[type='submit']").disabled = value || !state.sessionStarted;
    if (message) {
        statusText.textContent = message;
    }
}

async function readJsonResponse(response) {
    const contentType = response.headers.get("content-type") || "";
    const rawText = await response.text();

        if (!contentType.includes("application/json")) {
            if (rawText.includes("<html")) {
                throw new Error(
                "O frontend foi aberto sem backend ativo. Execute o server.py para usar check-in, pagamento e conversa com IA."
                );
            }
            throw new Error("A resposta do servidor nao veio em JSON.");
        }

    try {
        return JSON.parse(rawText);
    } catch (error) {
        throw new Error("O servidor devolveu JSON invalido.");
    }
}

checkinForm.addEventListener("submit", (event) => {
    event.preventDefault();
});

chatHelper.textContent = "Em modo mock, o pagamento e autorizado automaticamente para testes. Com OPENAI_API_KEY ativa, a conversa arranca logo depois.";
