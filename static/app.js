const SCRAPE_INTERVAL_MS = 60_000;
const POLL_BUFFER_MS = 5_000;
const MIN_POLL_DELAY_MS = 5_000;

const state = { registered: false, token: null, pollTimer: null, telegramPollTimer: null, knownSlotKeys: new Set() };

// ── Toast ─────────────────────────────────────────────────────────────────────

function showToast(msg) {
    const toast = document.createElement("div");
    toast.className = "toast";
    toast.textContent = msg;
    document.body.appendChild(toast);
    requestAnimationFrame(() => requestAnimationFrame(() => toast.classList.add("toast-visible")));
    setTimeout(() => {
        toast.classList.remove("toast-visible");
        setTimeout(() => toast.remove(), 300);
    }, 6000);
}

// ── Slots card ────────────────────────────────────────────────────────────────

function formatSlotDate(dateStr) {
    const [y, m, d] = dateStr.split("-");
    return new Date(y, m - 1, d).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

function slotKey(n) {
    return `${n.slot_date}|${n.slot_time}|${n.clinic}`;
}

function scheduleNextPoll(lastScrapedAt) {
    clearTimeout(state.pollTimer);
    let delay = MIN_POLL_DELAY_MS;
    if (lastScrapedAt) {
        const nextScrape = new Date(lastScrapedAt).getTime() + SCRAPE_INTERVAL_MS;
        delay = Math.max(MIN_POLL_DELAY_MS, nextScrape + POLL_BUFFER_MS - Date.now());
    }
    state.pollTimer = setTimeout(() => refreshSlots(true), delay);
}

async function refreshSlots(notify) {
    try {
        const res = await fetch(`/slots/${state.token}`);
        if (!res.ok) return;
        const { slots, last_scraped_at, telegram_linked } = await res.json();
        setTelegramState(telegram_linked);
        const list = document.getElementById("slots-list");

        if (slots.length === 0) {
            list.innerHTML = '<li id="no-slots" class="no-alerts">No matching slots right now — checking every minute.</li>';
            state.knownSlotKeys.clear();
        } else {
            if (notify) {
                slots.forEach((n) => {
                    if (!state.knownSlotKeys.has(slotKey(n))) {
                        showToast(`Slot available: ${formatSlotDate(n.slot_date)} at ${n.slot_time} — ${n.clinic}`);
                    }
                });
            }
            state.knownSlotKeys = new Set(slots.map(slotKey));
            list.innerHTML = slots.map((n) =>
                `<li class="notif-item">`
                + `<span class="notif-body">${formatSlotDate(n.slot_date)} at ${n.slot_time} — ${n.clinic}</span>`
                + `<a href="${n.booking_url || n.area_url}" target="_blank" rel="noopener" class="notif-link">Book now →</a>`
                + `</li>`
            ).join("");
        }

        scheduleNextPoll(last_scraped_at);
    } catch {
        scheduleNextPoll(null);
    }
}

// ── Telegram UI ───────────────────────────────────────────────────────────────

function setTelegramState(linked) {
    if (!TELEGRAM_BOT) return;
    const btn = document.getElementById("telegram-link-btn");
    const share = document.getElementById("telegram-share");
    if (btn) btn.hidden = linked;
    if (share) share.hidden = !linked;
    if (linked) stopTelegramLinkPoll();
}

function startTelegramLinkPoll() {
    if (state.telegramPollTimer) return;
    state.telegramPollTimer = setInterval(async () => {
        try {
            const res = await fetch(`/registration/${state.token}`);
            if (!res.ok) return;
            const data = await res.json();
            if (data.telegram_linked) setTelegramState(true);
        } catch {}
    }, 3000);
}

function stopTelegramLinkPoll() {
    clearInterval(state.telegramPollTimer);
    state.telegramPollTimer = null;
}

function copyTelegramLink() {
    const input = document.getElementById("telegram-share-url");
    if (!input) return;
    navigator.clipboard.writeText(input.value).then(() => {
        const btn = document.getElementById("telegram-copy-btn");
        const original = btn.textContent;
        btn.textContent = "Copied!";
        setTimeout(() => { btn.textContent = original; }, 2000);
    });
}

// ── State transitions ─────────────────────────────────────────────────────────

function showError(msg) {
    const el = document.getElementById("error-msg");
    el.textContent = msg;
    el.hidden = false;
}

function clearError() {
    const el = document.getElementById("error-msg");
    el.hidden = true;
    el.textContent = "";
}

function showRegisteredState(token, areaName, targetDate) {
    state.registered = true;
    state.token = token;
    localStorage.setItem("swiftqueue_token", token);

    document.getElementById("form-fields").hidden = true;
    document.getElementById("registered-state").hidden = false;

    const [y, m, d] = targetDate.split("-");
    const friendly = new Date(y, m - 1, d).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
    document.getElementById("registered-detail").textContent =
        `You're watching ${areaName} for slots on or before ${friendly}.`;

    const btn = document.getElementById("submit-btn");
    btn.textContent = "Unsubscribe";
    btn.className = "btn-danger";
    btn.disabled = false;

    const telegramUrl = TELEGRAM_BOT ? `https://t.me/${TELEGRAM_BOT}?start=${token}` : null;
    const shareInput = document.getElementById("telegram-share-url");
    if (shareInput && telegramUrl) shareInput.value = telegramUrl;
    const linkBtn = document.getElementById("telegram-link-btn");
    if (linkBtn && telegramUrl) linkBtn.href = telegramUrl;

    refreshSlots(false);
    clearError();
}

function showUnregisteredState() {
    state.registered = false;
    state.token = null;
    state.knownSlotKeys.clear();
    clearTimeout(state.pollTimer);
    state.pollTimer = null;
    stopTelegramLinkPoll();
    localStorage.removeItem("swiftqueue_token");

    document.getElementById("form-fields").hidden = false;
    document.getElementById("registered-state").hidden = true;

    const btn = document.getElementById("submit-btn");
    btn.textContent = "Get Notified";
    btn.className = "btn-primary";
    btn.disabled = false;

    const telegramBtn = document.getElementById("telegram-link");
    if (telegramBtn) telegramBtn.hidden = true;

    document.getElementById("slots-list").innerHTML =
        '<li id="no-slots" class="no-alerts">No matching slots right now — checking every minute.</li>';
    clearError();
}

// ── Form handlers ─────────────────────────────────────────────────────────────

async function handleRegister(form) {
    const btn = document.getElementById("submit-btn");
    btn.disabled = true;
    btn.textContent = "Setting up…";

    try {
        const res = await fetch("/register", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                area_url: form.area_url.value,
                target_date: form.target_date.value,
            }),
        });

        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "Registration failed.");

        const areaSelect = form.area_url;
        const areaName = areaSelect.options[areaSelect.selectedIndex].text;
        showRegisteredState(data.token, areaName, form.target_date.value);
    } catch (err) {
        console.error("Registration error:", err);
        btn.disabled = false;
        btn.textContent = "Get Notified";
        showError(err.message || String(err));
    }
}

async function handleUnsubscribe() {
    const btn = document.getElementById("submit-btn");
    btn.disabled = true;
    btn.textContent = "Unsubscribing…";

    try {
        const res = await fetch(`/unsubscribe/${state.token}`, {
            method: "POST",
            headers: { "Accept": "application/json" },
        });
        if (!res.ok) throw new Error("Unsubscribe failed.");
        showUnregisteredState();
    } catch (err) {
        console.error("Unsubscribe error:", err);
        btn.disabled = false;
        btn.textContent = "Unsubscribe";
        showError(err.message || String(err));
    }
}

document.getElementById("register-form").addEventListener("submit", (e) => {
    e.preventDefault();
    clearError();
    if (state.registered) {
        handleUnsubscribe();
    } else {
        handleRegister(e.target);
    }
});

// ── Restore state on page load ────────────────────────────────────────────────

const existingToken = localStorage.getItem("swiftqueue_token");
if (existingToken) {
    fetch(`/registration/${existingToken}`)
        .then((r) => r.ok ? r.json() : null)
        .then((data) => {
            if (data) {
                showRegisteredState(existingToken, data.area_name, data.target_date);
                setTelegramState(data.telegram_linked);
            } else {
                localStorage.removeItem("swiftqueue_token");
            }
        })
        .catch(() => localStorage.removeItem("swiftqueue_token"));
}
