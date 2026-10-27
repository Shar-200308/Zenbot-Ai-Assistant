import { initializeApp } from "https://www.gstatic.com/firebasejs/10.7.1/firebase-app.js";
import { getAuth } from "https://www.gstatic.com/firebasejs/10.7.1/firebase-auth.js";

const firebaseConfig = {
  apiKey: "AIzaSyDXn08_nWNQX7xWqyXsCCceOYMwpvLUSt0",
  authDomain: "zenbot-d958a.firebaseapp.com",
  projectId: "zenbot-d958a",
  storageBucket: "zenbot-d958a.firebasestorage.app",
  messagingSenderId: "878917196200",
  appId: "1:878917196200:web:ec7b28ea88c53b2c06a59d"
};
const app = initializeApp(firebaseConfig);

const auth = getAuth(app);

export { auth };
