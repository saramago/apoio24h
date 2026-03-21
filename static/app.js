const state = {
    onboarding: null,
    previousResponseId: null,
    isBusy: false,
};

const hero = document.querySelector("#hero");
const onboardingPanel = document.querySelector("#onboarding-panel");
const chatPanel = document.querySelector("#chat-panel");
const onboardingForm = document.querySelector("#onboarding-form");
const chatForm = document.querySelector("#chat-form");
const chatInput = document.querySelector("#chat-input");
const chatLog = document.querySelector("#chat-log");
const startButton = document.querySelector("#start-button");
const statusText = document.querySelector("#status-text");
const sessionBadge = document.querySelector("#session-badge");

startButton.addEventListener("click", () => {
    onboardingPanel.classList.remove("hidden");
    onboardingPanel.scrollIntoView({ behavior: "smooth", block: "start" });
});

onboardingForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    const formData = new FormData(onboardingForm);
    state.onboarding = Object.fromEntries(formData.entries());

    setBusy(true, "A iniciar sessão...");
    appendMessage(
        "system",
        `A preparar a sessão para ${state.onboarding.preferredName || state.onboarding.firstName}.`
    );

    try {
        const response = await fetch("/api/session/start", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ onboarding: state.onboarding }),
        });

        const payload = await response.json();
        if (!response.ok) {
            throw new Error(payload.error || "Não foi possível iniciar a sessão.");
        }

        state.previousResponseId = payload.response_id || null;
        onboardingPanel.classList.add("hidden");
        chatPanel.classList.remove("hidden");
        hero.classList.add("hidden");
        sessionBadge.textContent = "Sessão ativa";
        statusText.textContent = "Sessão iniciada. Pode continuar a conversa.";
        appendMessage("assistant", payload.message);
        chatInput.focus();
        chatPanel.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (error) {
        appendMessage("system", error.message);
        statusText.textContent = error.message;
    } finally {
        setBusy(false);
    }
});

chatForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (state.isBusy) {
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
                message,
                previous_response_id: state.previousResponseId,
                onboarding: state.onboarding,
            }),
        });

        const payload = await response.json();
        if (!response.ok) {
            throw new Error(payload.error || "Erro ao obter resposta.");
        }

        state.previousResponseId = payload.response_id || state.previousResponseId;
        appendMessage("assistant", payload.message);
        statusText.textContent = "Resposta recebida.";
    } catch (error) {
        appendMessage("system", error.message);
        statusText.textContent = error.message;
    } finally {
        setBusy(false);
        chatInput.focus();
    }
});

function appendMessage(role, content) {
    const message = document.createElement("article");
    message.className = `message ${role}`;
    message.textContent = content;
    chatLog.appendChild(message);
    chatLog.scrollTop = chatLog.scrollHeight;
}

function setBusy(value, text = "Pronto.") {
    state.isBusy = value;
    onboardingForm.querySelector("button[type='submit']").disabled = value;
    chatForm.querySelector("button[type='submit']").disabled = value;
    chatInput.disabled = value;
    statusText.textContent = text;
}
