import { auth } from "./firebase.js";
import { onAuthStateChanged } from "https://www.gstatic.com/firebasejs/10.7.1/firebase-auth.js";

// Keep auth accessible globally
window._firebaseAuth = auth;

// Listen for auth state changes - Firebase automatically handles token refresh in the background
onAuthStateChanged(auth, async (user) => {
    if (user) {
        try {
            // Get fresh ID token (forceRefresh: false lets Firebase refresh automatically if needed)
            const token = await user.getIdToken();
            localStorage.setItem("firebaseToken", token);
            localStorage.setItem("userEmail", user.email || "");
            if (user.displayName) {
                localStorage.setItem("userName", user.displayName);
            }
            window.dispatchEvent(new CustomEvent("firebaseAuthReady", { detail: { token, user } }));
        } catch (e) {
            console.error("Failed to get fresh Firebase token on auth state change:", e);
        }
    } else {
        window.dispatchEvent(new CustomEvent("firebaseAuthLoggedOut"));
    }
});

// Explicit token refresh function (e.g. called on 401 Unauthorized)
export async function getFreshToken(forceRefresh = true) {
    if (typeof auth.authStateReady === "function") {
        try {
            await auth.authStateReady();
        } catch (_) {}
    }
    if (auth.currentUser) {
        try {
            const token = await auth.currentUser.getIdToken(forceRefresh);
            localStorage.setItem("firebaseToken", token);
            return token;
        } catch (e) {
            console.error("Token refresh failed:", e);
        }
    }
    return localStorage.getItem("firebaseToken") || "";
}

window.refreshFirebaseAuthToken = getFreshToken;
