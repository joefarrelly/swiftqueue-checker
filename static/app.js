function urlBase64ToUint8Array(base64String) {
    const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
    const raw = atob(base64);
    return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}

async function getPushSubscription() {
    const reg = await navigator.serviceWorker.register("/static/sw.js");
    await navigator.serviceWorker.ready;
    const existing = await reg.pushManager.getSubscription();
    if (existing) return existing;
    return reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC_KEY),
    });
}

function showError(msg) {
    const el = document.getElementById("error-msg");
    el.textContent = msg;
    el.hidden = false;
}

function showSuccess(token) {
    document.getElementById("form-section").hidden = true;
    const success = document.getElementById("success-section");
    success.hidden = false;

    const telegramBtn = document.getElementById("telegram-link");
    if (telegramBtn && TELEGRAM_BOT) {
        telegramBtn.href = `https://t.me/${TELEGRAM_BOT}?start=${token}`;
        telegramBtn.closest(".telegram-row").hidden = false;
    }

    document.getElementById("unsubscribe-link").href = `/unsubscribe/${token}`;
    localStorage.setItem("swiftqueue_token", token);
}

document.getElementById("register-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.target;
    const btn = form.querySelector("button[type=submit]");
    const errorEl = document.getElementById("error-msg");

    errorEl.hidden = true;
    btn.disabled = true;
    btn.textContent = "Setting up…";

    try {
        if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
            throw new Error("Push notifications are not supported in this browser.");
        }

        const permission = await Notification.requestPermission();
        if (permission !== "granted") {
            throw new Error("Notification permission denied. Please allow notifications and try again.");
        }

        const subscription = await getPushSubscription();

        const res = await fetch("/register", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                area_url: form.area_url.value,
                target_date: form.target_date.value,
                push_subscription: subscription.toJSON(),
            }),
        });

        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "Registration failed.");

        showSuccess(data.token);
    } catch (err) {
        btn.disabled = false;
        btn.textContent = "Get Notified";
        showError(err.message);
    }
});

// Re-surface unsubscribe link if already registered
const existingToken = localStorage.getItem("swiftqueue_token");
if (existingToken) {
    const hint = document.getElementById("existing-hint");
    if (hint) {
        hint.querySelector("a").href = `/unsubscribe/${existingToken}`;
        hint.hidden = false;
    }
}
