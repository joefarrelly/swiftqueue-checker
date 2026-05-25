// ── Area combobox ─────────────────────────────────────────────────────────────

function initCombobox() {
    const input = document.getElementById("area-search");
    const listbox = document.getElementById("area-listbox");
    const select = document.getElementById("area_url");

    const options = Array.from(select.options)
        .filter(o => o.value)
        .map(o => ({ value: o.value, label: o.text }));

    let activeIndex = -1;

    function renderOptions(filter) {
        const q = filter.trim().toLowerCase();
        const matches = q ? options.filter(o => o.label.toLowerCase().includes(q)) : options;
        if (matches.length === 0) {
            listbox.innerHTML = '<li class="no-results">No areas found</li>';
        } else {
            listbox.innerHTML = matches.map((o, i) =>
                `<li data-value="${o.value}" data-index="${i}">${o.label}</li>`
            ).join("");
        }
        activeIndex = -1;
        listbox.hidden = false;
    }

    function selectOption(value, label) {
        select.value = value;
        input.value = label;
        input.dataset.selected = "1";
        listbox.hidden = true;
        activeIndex = -1;
    }

    function close() {
        listbox.hidden = true;
        activeIndex = -1;
    }

    input.addEventListener("focus", () => renderOptions(input.dataset.selected ? "" : input.value));

    input.addEventListener("input", () => {
        if (!input.value) {
            select.value = "";
            delete input.dataset.selected;
        } else {
            delete input.dataset.selected;
        }
        renderOptions(input.value);
    });

    input.addEventListener("keydown", (e) => {
        const items = listbox.querySelectorAll("li:not(.no-results)");
        if (e.key === "ArrowDown") {
            e.preventDefault();
            activeIndex = Math.min(activeIndex + 1, items.length - 1);
        } else if (e.key === "ArrowUp") {
            e.preventDefault();
            activeIndex = Math.max(activeIndex - 1, 0);
        } else if (e.key === "Enter") {
            e.preventDefault();
            if (activeIndex >= 0 && items[activeIndex]) {
                const item = items[activeIndex];
                selectOption(item.dataset.value, item.textContent);
            }
            return;
        } else if (e.key === "Escape") {
            close();
            return;
        } else {
            return;
        }
        items.forEach((item, i) => item.classList.toggle("active", i === activeIndex));
        if (activeIndex >= 0) items[activeIndex].scrollIntoView({ block: "nearest" });
    });

    listbox.addEventListener("mousedown", (e) => {
        const item = e.target.closest("li[data-value]");
        if (!item) return;
        e.preventDefault();
        selectOption(item.dataset.value, item.textContent);
    });

    document.addEventListener("click", (e) => {
        if (!input.contains(e.target) && !listbox.contains(e.target)) {
            if (!input.dataset.selected) {
                input.value = "";
                select.value = "";
            }
            close();
        }
    });

    return {
        reset() {
            input.value = "";
            select.value = "";
            delete input.dataset.selected;
            close();
        }
    };
}

const combobox = initCombobox();

// ── Tabs ──────────────────────────────────────────────────────────────────────

function switchTab(name) {
    document.querySelectorAll('.tab-btn').forEach(btn => {
        const active = btn.dataset.tab === name;
        btn.classList.toggle('tab-btn--active', active);
        btn.setAttribute('aria-selected', String(active));
    });
    document.getElementById('tab-register').hidden = name !== 'register';
    document.getElementById('tab-how').hidden = name !== 'how';
}

document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
});

const SCRAPE_INTERVAL_MS = 60_000;
const POLL_BUFFER_MS = 5_000;
const MIN_POLL_DELAY_MS = 5_000;

const state = {
    registered: false, token: null, pollTimer: null, telegramPollTimer: null,
    knownSlotKeys: new Set(), lastCheckedAt: null, refreshStatusTimer: null,
};

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

function updateRefreshStatus() {
    const el = document.getElementById("slots-refresh-status");
    if (!el || !state.lastCheckedAt) return;
    const secs = Math.floor((Date.now() - state.lastCheckedAt) / 1000);
    if (secs < 5) {
        el.textContent = "Just checked";
    } else if (secs < 60) {
        el.textContent = `Checked ${secs}s ago`;
    } else {
        const m = Math.floor(secs / 60);
        const s = secs % 60;
        el.textContent = `Checked ${m}m ${s}s ago`;
    }
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

        state.lastCheckedAt = Date.now();
        updateRefreshStatus();
        if (!state.refreshStatusTimer) {
            state.refreshStatusTimer = setInterval(updateRefreshStatus, 1000);
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
    state.lastCheckedAt = null;
    clearTimeout(state.pollTimer);
    state.pollTimer = null;
    clearInterval(state.refreshStatusTimer);
    state.refreshStatusTimer = null;
    stopTelegramLinkPoll();
    localStorage.removeItem("swiftqueue_token");

    document.getElementById("form-fields").hidden = false;
    document.getElementById("registered-state").hidden = true;
    combobox.reset();

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
    if (!form.area_url.value) {
        showError("Please select an area.");
        return;
    }

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
