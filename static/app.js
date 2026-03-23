const state = {
    checkinId: null,
    customerPhone: "",
    previousResponseId: null,
    isBusy: false,
    paid: false,
    freeTurnUsed: false,
    transcript: "",
};

const recordButton = document.querySelector("#record-button");
const statusText = document.querySelector("#status-text");
const timerText = document.querySelector("#timer-text");
const transcriptPanel = document.querySelector("#transcript-panel");
const transcriptText = document.querySelector("#transcript-text");
const responsePanel = document.querySelector("#response-panel");
const responseText = document.querySelector("#response-text");
const paymentPanel = document.querySelector("#payment-panel");
const paymentForm = document.querySelector("#payment-form");
const phoneInput = document.querySelector("#phone-input");
const paymentNote = document.querySelector("#payment-note");

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
const recognition = SpeechRecognition ? new SpeechRecognition() : null;

let recognitionTimeout = null;
let statusPollTimer = null;

if (recognition) {
    recognition.lang = "pt-PT";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
}

recordButton.addEventListener("click", () => {
    if (!recognition) {
        setStatus("Este dispositivo nao suporta gravacao de voz no browser.");
        return;
    }

    if (state.isBusy) {
        return;
    }

    if (state.freeTurnUsed && !state.paid) {
        paymentPanel.classList.remove("hidden");
        phoneInput.focus();
        setStatus("Pode continuar por 1€.");
        return;
    }

    startRecording();
});

paymentForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (state.isBusy) {
        return;
    }

    const enteredPhone = phoneInput.value.trim();
    if (!enteredPhone) {
        phoneInput.focus();
        setStatus("Indique primeiro o seu numero MB WAY.");
        return;
    }

    state.customerPhone = enteredPhone;
    setBusy(true, "A preparar o pagamento...");
    paymentNote.textContent = "";

    try {
        const response = await fetch("/api/checkin", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                plan: "continue",
                customer_phone: state.customerPhone,
            }),
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

if (recognition) {
    recognition.addEventListener("result", async (event) => {
        const transcript = Array.from(event.results)
            .map((result) => result[0]?.transcript || "")
            .join(" ")
            .trim();

        stopRecordingTimer();

        if (!transcript) {
            setStatus("Nao foi possivel perceber o que disse. Tente novamente.");
            setBusy(false);
            return;
        }

        state.transcript = transcript;
        transcriptPanel.classList.remove("hidden");
        transcriptText.textContent = transcript;
        await sendTranscript(transcript);
    });

    recognition.addEventListener("error", () => {
        stopRecordingTimer();
        setBusy(false);
        setStatus("A gravacao foi interrompida. Tente novamente.");
    });

    recognition.addEventListener("end", () => {
        stopRecordingTimer();
    });
}

function startRecording() {
    state.transcript = "";
    transcriptPanel.classList.add("hidden");
    setBusy(true, "A ouvir...");
    timerText.classList.remove("hidden");
    timerText.textContent = "Pode falar ate 60 segundos.";

    recognition.start();
    recognitionTimeout = window.setTimeout(() => {
        recognition.stop();
    }, 60000);
}

function stopRecordingTimer() {
    if (recognitionTimeout) {
        window.clearTimeout(recognitionTimeout);
        recognitionTimeout = null;
    }
    timerText.classList.add("hidden");
}

async function sendTranscript(transcript) {
    setStatus("A organizar a resposta...");

    try {
        const response = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                plan: state.previousResponseId ? "continue" : "free",
                message: transcript,
                previous_response_id: state.previousResponseId,
            }),
        });

        const payload = await readJsonResponse(response);
        if (!response.ok) {
            throw new Error(payload.error || "Nao foi possivel gerar a resposta.");
        }

        state.previousResponseId = payload.response_id || state.previousResponseId;
        state.freeTurnUsed = true;
        responsePanel.classList.remove("hidden");
        responseText.textContent = payload.message;
        speakText(payload.message);

        if (!state.paid) {
            paymentPanel.classList.remove("hidden");
            paymentNote.textContent = "Pode continuar por 1€.";
            setStatus("Primeira resposta concluida.");
        } else {
            setStatus("Resposta pronta.");
        }
    } catch (error) {
        setStatus(normalizeStartupError(error.message));
    } finally {
        setBusy(false);
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
            paymentNote.textContent = "Pagamento confirmado. Pode voltar a falar quando quiser.";
            setStatus("Pode falar novamente.");
        }
    } catch (error) {
        clearStatusPoll();
        setStatus(error.message);
    }
}

function speakText(text) {
    if (!("speechSynthesis" in window)) {
        return;
    }

    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "pt-PT";
    utterance.rate = 0.92;
    utterance.pitch = 0.95;
    utterance.volume = 1;

    const voices = window.speechSynthesis.getVoices();
    const preferredVoice =
        voices.find((voice) => voice.lang === "pt-PT" && /catarina|joana|maria/i.test(voice.name)) ||
        voices.find((voice) => voice.lang === "pt-PT") ||
        voices.find((voice) => voice.lang.startsWith("pt")) ||
        null;

    if (preferredVoice) {
        utterance.voice = preferredVoice;
    }

    window.speechSynthesis.speak(utterance);
}

function setBusy(value, message) {
    state.isBusy = value;
    recordButton.disabled = value;
    phoneInput.disabled = value;
    paymentForm.querySelector("button[type='submit']").disabled = value;
    if (message) {
        setStatus(message);
    }
}

function setStatus(message) {
    statusText.textContent = message;
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

function normalizeStartupError(message) {
    if (message.includes("insufficient_quota") || message.includes("HTTP 429")) {
        return "De momento, nao foi possivel gerar a resposta. Tente novamente dentro de instantes.";
    }
    return message;
}

if ("speechSynthesis" in window) {
    window.speechSynthesis.onvoiceschanged = () => {};
}
