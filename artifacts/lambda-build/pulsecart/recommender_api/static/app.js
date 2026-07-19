const fmt = (n, digits = 0) => {
    if (n === null || n === undefined) return "—";
    return Number(n).toLocaleString(undefined, { maximumFractionDigits: digits });
};

async function refreshSummary() {
    try {
        const r = await fetch("/summary");
        if (!r.ok) return;
        const s = await r.json();
        document.getElementById("n-events").textContent = fmt(s.n_events);
        document.getElementById("n-users").textContent = fmt(s.n_users);
        document.getElementById("n-sessions").textContent = fmt(s.n_sessions);
        document.getElementById("avg-latency").textContent = fmt(s.avg_latency_ms, 1) + " ms";
    } catch (err) {
        // silent — dashboard tolerates transient errors
    }
}

async function refreshHealth() {
    try {
        const r = await fetch("/health");
        if (!r.ok) return;
        const h = await r.json();
        document.getElementById("mode-badge").textContent = "mode: " + (h.mode || "—");
    } catch (err) { /* ignore */ }
}

async function lookup() {
    const uid = document.getElementById("user-input").value.trim();
    const target = document.getElementById("result");
    if (!uid) {
        target.innerHTML = "";
        return;
    }
    try {
        const r = await fetch(`/recommendations/${encodeURIComponent(uid)}`);
        if (r.status === 404) {
            target.innerHTML = `<div class="error">No scored events for <code>${uid}</code> yet. Emit some clicks first.</div>`;
            return;
        }
        if (!r.ok) throw new Error("HTTP " + r.status);
        const rec = await r.json();
        target.innerHTML = renderCard(rec);
    } catch (err) {
        target.innerHTML = `<div class="error">Failed to fetch: ${err.message}</div>`;
    }
}

function renderCard(rec) {
    const rows = rec.recommendations.map(r => `
        <div class="rec-row">
            <div class="rank">#${r.rank}</div>
            <div class="pid">${r.product_id}</div>
            <div class="score">score ${r.score.toFixed(3)}</div>
        </div>
    `).join("");
    return `
        <div class="rec-card">
            <div class="meta">
                <span>user <code>${rec.user_id}</code></span>
                <span>trace <code>${rec.trace_id.slice(0, 12)}…</code></span>
                <span>model <code>${rec.model_version}</code></span>
                <span>scored at ${rec.scored_at}</span>
            </div>
            <div class="rec-list">${rows}</div>
        </div>
    `;
}

document.getElementById("lookup-btn").addEventListener("click", lookup);
document.getElementById("user-input").addEventListener("keydown", e => { if (e.key === "Enter") lookup(); });

refreshHealth();
refreshSummary();
setInterval(refreshSummary, 3000);
