import { auth } from "./firebase.js";

import {
    createUserWithEmailAndPassword,
    signInWithEmailAndPassword,
    sendEmailVerification,
    updateProfile,
    sendPasswordResetEmail
} from "https://www.gstatic.com/firebasejs/10.7.1/firebase-auth.js";

window.signup = async function () {
    const msg = document.getElementById("msg");
    const nameEl = document.getElementById("name");
    const emailEl = document.getElementById("email");
    const passwordEl = document.getElementById("password");
    const confirmEl = document.getElementById("confirmPassword");
    const signUpBtn = document.querySelector("button[onclick='signup()']");

    if (!nameEl || !emailEl || !passwordEl || !confirmEl) {
        console.error("One or more input elements not found in the DOM.");
        return;
    }

    const name = nameEl.value.trim();
    const email = emailEl.value.trim();
    const password = passwordEl.value.trim();
    const confirmPassword = confirmEl.value.trim();

    if (!name || !email || !password || !confirmPassword) {
        if (msg) {
            msg.style.color = "red";
            msg.innerText = "All fields are required";
        }
        return;
    }

    if (password !== confirmPassword) {
        if (msg) {
            msg.style.color = "red";
            msg.innerText = "Passwords do not match";
        }
        return;
    }

    if (password.length < 6) {
        if (msg) {
            msg.style.color = "red";
            msg.innerText = "Password must be at least 6 characters";
        }
        return;
    }
    
    // UI feedback
    if (signUpBtn) {
        signUpBtn.innerText = "Signing up...";
        signUpBtn.disabled = true;
    }

    try {
        const userCred = await createUserWithEmailAndPassword(auth, email, password);

        // ✅ Update Firebase Display Name
        await updateProfile(userCred.user, {
            displayName: name
        });

        // ✅ Email verification ONLY on signup
        await sendEmailVerification(userCred.user);
        
        // Sync to backend even on signup so we have the name
        await fetch("/save-user/", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": "Bearer " + await userCred.user.getIdToken()
            }
        });

        // Password is handled securely by Firebase — never stored locally

        if (msg) {
            msg.style.color = "green";
            msg.innerText = "Signup successful! Check your email.";
        }

        setTimeout(() => {
            window.location.href = "/login/";
        }, 2000);

    } catch (error) {
        console.error("Signup error:", error);
        if (msg) {
            msg.style.color = "red";
            let friendlyMessage = error.message;
            if (error.code === "auth/email-already-in-use" || error.message.includes("email-already-in-use")) {
                friendlyMessage = "This email is already registered. Please login instead.";
            } else if (error.code === "auth/invalid-email" || error.message.includes("invalid-email")) {
                friendlyMessage = "Please enter a valid email address.";
            } else if (error.code === "auth/weak-password" || error.message.includes("weak-password")) {
                friendlyMessage = "Password is too weak. It must be at least 6 characters.";
            }
            msg.innerText = friendlyMessage;
        }
    } finally {
        if (signUpBtn) {
            signUpBtn.innerText = "Sign Up";
            signUpBtn.disabled = false;
        }
    }
};

window.login = async function () {
    // 🛡️ Aggressive Cleanup: Clear everything before starting a new session
    localStorage.clear();

    const msg = document.getElementById("msg");
    const emailEl = document.getElementById("email");
    const passwordEl = document.getElementById("password");
    const loginBtn = document.querySelector("button[onclick='login()']");

    if (!emailEl || !passwordEl) return;

    const email = emailEl.value.trim();
    const password = passwordEl.value.trim();

    if (!email || !password) {
        if (msg) {
            msg.style.color = "red";
            msg.innerText = "Email and password required";
        }
        return;
    }

    // UI feedback
    if (loginBtn) {
        loginBtn.innerText = "Logging in...";
        loginBtn.disabled = true;
    }

    try {
        const userCred = await signInWithEmailAndPassword(auth, email, password);

        const token = await userCred.user.getIdToken();
        localStorage.setItem("firebaseToken", token);
        localStorage.setItem("userEmail", userCred.user.email);
        localStorage.setItem("userName", userCred.user.displayName || "User");

        // SYNC USER TO BACKEND
        const response = await fetch("/save-user/", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": "Bearer " + token
            }
        });
        const data = await response.json();

        if (data.status === "user_saved") {
            localStorage.setItem("userName", data.userName || "User");
            localStorage.setItem("userEmail", data.userEmail || email);
        }

        // Redirect to ?next= URL if present (e.g. /hr/ after login from HR panel), else /chat/
        const params = new URLSearchParams(window.location.search);
        const next = params.get('next');
        window.location.href = (next && next.startsWith('/')) ? next : '/chat/';

    } catch (error) {
        console.error("Login error:", error);
        if (msg) {
            msg.style.color = "red";
            let friendlyMessage = error.message;
            if (error.code === "auth/wrong-password" || 
                error.code === "auth/user-not-found" || 
                error.code === "auth/invalid-credential" ||
                error.message.includes("wrong-password") ||
                error.message.includes("user-not-found") ||
                error.message.includes("invalid-credential")) {
                friendlyMessage = "Incorrect email or password. Please try again.";
            } else if (error.code === "auth/invalid-email" || error.message.includes("invalid-email")) {
                friendlyMessage = "Please enter a valid email address.";
            } else if (error.code === "auth/user-disabled" || error.message.includes("user-disabled")) {
                friendlyMessage = "This account has been disabled. Please contact support.";
            }
            msg.innerText = friendlyMessage;
        }
    } finally {
        if (loginBtn) {
            loginBtn.innerText = "Login";
            loginBtn.disabled = false;
        }
    }
};

// 🔑 Password Reset Flow (Firebase Auth)
window.forgotPassword = async function () {
    const emailEl = document.getElementById("email");
    const msg = document.getElementById("msg");
    let email = emailEl ? emailEl.value.trim() : "";

    if (!email) {
        email = prompt("Enter your registered email address to receive a password reset link:");
        if (email) email = email.trim();
    }

    if (!email) {
        if (msg) {
            msg.style.color = "#f87171";
            msg.innerText = "Please enter your email address to reset password.";
        }
        return;
    }

    if (msg) {
        msg.style.color = "#60a5fa";
        msg.innerText = "Sending password reset link...";
    }

    try {
        await sendPasswordResetEmail(auth, email);
        if (msg) {
            msg.style.color = "#34d399";
            msg.innerText = `✅ Password reset email sent to ${email}. Check your inbox!`;
        } else {
            alert(`Password reset email sent to ${email}. Please check your inbox or spam folder.`);
        }
    } catch (err) {
        console.error("Password reset error:", err);
        let errorMsg = "Could not send password reset email. Please verify your email address.";
        if (err.code === "auth/user-not-found" || (err.message && err.message.includes("user-not-found"))) {
            errorMsg = "No account found with this email address.";
        } else if (err.code === "auth/invalid-email" || (err.message && err.message.includes("invalid-email"))) {
            errorMsg = "Please enter a valid email address.";
        }
        if (msg) {
            msg.style.color = "#f87171";
            msg.innerText = errorMsg;
        } else {
            alert(errorMsg);
        }
    }
};

// ⌨️ Keyboard Support for Enter Key
document.addEventListener("keydown", function (e) {
    if (e.key === "Enter") {
        const activeElem = document.activeElement;
        const isInput = activeElem && (activeElem.tagName === "INPUT" || activeElem.tagName === "BUTTON");
        
        if (isInput) {
            const loginBtn = document.querySelector("button[onclick='login()']");
            const signupBtn = document.querySelector("button[onclick='signup()']");

            if (loginBtn) {
                e.preventDefault();
                window.login();
            } else if (signupBtn) {
                e.preventDefault();
                window.signup();
            }
        }
    }
});


