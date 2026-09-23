// ==========================
// voice.js
// ==========================

let recognition = null;
let isListening = false;

// Initialize SpeechRecognition
function initVoice() {

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
        alert("Voice recognition is not supported in this browser.");
        return;
    }

    recognition = new SpeechRecognition();
    recognition.lang = "en-US";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    recognition.onresult = function (event) {

        const voiceText = event.results[0][0].transcript.trim();
        
        // Stop listening once we have a result
        isListening = false;
        recognition.stop();
        
        const micBtn = document.getElementById("micBtn");
        if (micBtn) {
            micBtn.classList.remove("mic-on");
            micBtn.innerHTML = "🎤";
        }

        // Ensure chatbot functions exist before calling
        if (typeof addUserMessage === "function") {
            addUserMessage(voiceText);
        }

        if (typeof sendToBot === "function") {
            sendToBot(voiceText);
        }

    };

    recognition.onerror = function (e) {
        console.error("Voice recognition error:", e);
    };

    recognition.onend = function () {
        if (isListening) {
            // This happens if the user stops talking or silence is detected
            isListening = false;
            const micBtn = document.getElementById("micBtn");
            if (micBtn) {
                micBtn.classList.remove("mic-on");
                micBtn.innerHTML = "🎤";
            }
        }
    };
}


// Toggle mic ON/OFF
function toggleVoice(button) {

    if (!recognition) {
        initVoice();
    }

    if (!recognition) return;

    if (!isListening) {
        // Stop any ongoing bot speech before listening
        if (window.speechSynthesis) {
            window.speechSynthesis.cancel();
        }

        recognition.start();
        isListening = true;

        if (button) {
            button.classList.add("mic-on");
            button.innerHTML = "🔴";
        }

    } else {

        recognition.stop();
        isListening = false;

        if (button) {
            button.classList.remove("mic-on");
            button.innerHTML = "🎤";
        }
    }
}


// Stop voice manually
function stopVoice() {

    if (recognition && isListening) {
        recognition.stop();
        isListening = false;
        
        const micBtn = document.getElementById("micBtn");
        if (micBtn) {
            micBtn.classList.remove("mic-on");
            micBtn.innerHTML = "🎤";
        }
    }

}