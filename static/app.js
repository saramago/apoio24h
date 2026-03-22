const state = {
    plan: null,
    checkinId: null,
    customerPhone: null,
    previousResponseId: null,
    isBusy: false,
    sessionStarted: false,
};

const sessionButtons = document.querySelectorAll(".session-button");
const checkinPanel = document.querySelector("#checkin-panel");
const chatPanel = document.querySelector("#chat-panel");
const statusText = document.querySelector("#status-text");
const paymentNote = document.querySelector("#payment-note");
const chatLog = document.querySelector("#chat-log");
const chatForm = document.querySelector("#chat-form");
const chatInput = document.querySelector("#chat-input");
let statusPollTimer = null;

sessionButtons.forEach((button) => {
    button.addEventListener("click", async () => {
        if (state.isBusy) {
            return;
        }

        state.plan = button.dataset.plan;
        setBusy(true, "A preparar o check-in...");
        checkinPanel.classList.remove("hidden");
        chatPanel.classList.add("hidden");
        state.sessionStarted = false;
        state.previousResponseId = null;
        state.checkinId = null;
        state.customerPhone = null;
        chatLog.innerHTML = "";
        clearStatusPoll();

        try {
            const phoneInput = window.prompt("Introduza o numero MB WAY do cliente (ex.: 919999999):", "");
            if (phoneInput === null) {
                setBusy(false, "Check-in cancelado.");
                return;
            }

            state.customerPhone = phoneInput.trim();
            const response = await fetch("/api/checkin", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ plan: state.plan, customer_phone: state.customerPhone }),
            });

            const payload = await readJsonResponse(response);
            if (!response.ok) {
                throw new Error(payload.error || "Não foi possível iniciar o check-in.");
            }

            state.checkinId = payload.checkin_id || null;
            paymentNote.textContent = payload.payment_note;
            statusText.textContent = payload.status;
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
            throw new Error(payload.error || "Não foi possível iniciar a conversa.");
        }

        state.previousResponseId = payload.response_id || null;
        state.sessionStarted = true;
        clearStatusPoll();
        chatPanel.classList.remove("hidden");
        appendMessage("assistant", payload.message);
        statusText.textContent = "Conversa iniciada.";
    } catch (error) {
        appendMessage("system", error.message);
        statusText.textContent = error.message;
    } finally {
        setBusy(false);
        chatInput.focus();
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
            throw new Error(payload.error || "Não foi possível validar o pagamento.");
        }

        statusText.textContent = payload.status;
        paymentNote.textContent = payload.payment_note || paymentNote.textContent;

        if (payload.status_code === "AUTHORIZED") {
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
                "O site foi aberto sem backend ativo. Inicie o server.py localmente ou publique tambem a API."
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
