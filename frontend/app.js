const $ = (sel) => document.querySelector(sel);

function money(cents) {
  if (cents == null) return "—";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(cents / 100);
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) throw new Error(`${path} ${res.status}`);
  return res.json();
}

function renderCards(m) {
  const items = [
    ["Day", m.tick],
    ["Policy rate", `${(m.policy_rate_bps / 100).toFixed(2)}%`],
    ["Agent cash", money(m.agent_cash_cents)],
    ["Company cash", money(m.company_cash_cents)],
    ["Loans out", money(m.loans_outstanding_cents)],
    ["Companies", m.companies],
    ["Employed", m.employed_workers],
    ["Unemployed", m.unemployed_workers],
    ["Sick", m.sick_agents],
    ["Inventory", m.inventory_units],
    ["Sales today", m.sales_today],
    ["Total money", money(m.total_money_cents)],
  ];
  $("#cards").innerHTML = items
    .map(([label, value]) => `<div class="card"><div class="label">${label}</div><div class="value">${value}</div></div>`)
    .join("");
}

function renderAgents(agents) {
  const tbody = $("#agentsTable tbody");
  tbody.innerHTML = agents
    .map((a) => {
      const healthClass = a.health === "sick" ? "sick" : "healthy";
      return `<tr>
        <td>${a.name}</td>
        <td>${a.role}</td>
        <td><span class="badge ${healthClass}">${a.health}</span></td>
        <td class="muted">${a.employer_company_id || "—"}</td>
        <td>${money(a.cash_cents)}</td>
      </tr>`;
    })
    .join("");
}

function renderCompanies(state) {
  const cos = state.companies || [];
  const jobs = (state.jobs || []).filter((j) => j.open);
  $("#companies").innerHTML = cos.length
    ? cos
        .map(
          (c) =>
            `<div class="item"><div class="title">${c.name}</div>
             <div class="meta">Founder ${c.founder_id} · cash ${money(c.cash_cents)} · inv ${c.inventory_units}</div></div>`
        )
        .join("")
    : `<div class="muted">No companies yet.</div>`;
  $("#jobs").innerHTML = jobs.length
    ? jobs
        .map(
          (j) =>
            `<div class="item"><div class="title">${j.title}</div>
             <div class="meta">${j.company_id} · ${money(j.wage_cents_day)}/day · applicants: ${j.applicants.length}</div></div>`
        )
        .join("")
    : `<div class="muted">No open jobs.</div>`;
}

function renderNews(news) {
  const list = [...(news || [])].reverse();
  $("#news").innerHTML = list.length
    ? list
        .map(
          (n) =>
            `<div class="item"><div class="meta">Day ${n.tick} · ${n.author_id} · sent ${n.sentiment}</div>
             <div class="title">${n.headline}</div>
             <div class="muted">${n.body}</div></div>`
        )
        .join("")
    : `<div class="muted">No news yet.</div>`;
}

function renderEvents(events) {
  const list = [...(events || [])].reverse().slice(0, 80);
  $("#events").innerHTML = list
    .map(
      (e) =>
        `<div class="item"><div class="meta">Day ${e.tick} · ${e.kind}</div><div>${e.message}</div></div>`
    )
    .join("");
}

async function refresh() {
  const state = await api("/state");
  const m = state.metrics || {};
  $("#statusPill").textContent = `Day ${state.tick} · ${state.paused ? "paused" : "running"}`;
  renderCards(m);
  renderAgents(state.agents || []);
  renderCompanies(state);
  renderNews(state.news || []);
  renderEvents(state.events || []);
}

$("#btnStep1").onclick = async () => {
  await api("/step", { method: "POST", body: JSON.stringify({ n: 1 }) });
  await refresh();
};
$("#btnStep7").onclick = async () => {
  await api("/step", { method: "POST", body: JSON.stringify({ n: 7 }) });
  await refresh();
};
$("#btnAuto").onclick = async () => {
  await api("/auto/start", { method: "POST", body: JSON.stringify({ interval_sec: 1.0 }) });
  await refresh();
};
$("#btnStop").onclick = async () => {
  await api("/auto/stop", { method: "POST" });
  await api("/pause", { method: "POST" });
  await refresh();
};
$("#btnReset").onclick = async () => {
  await api("/reset", { method: "POST", body: JSON.stringify({}) });
  await refresh();
};
$("#btnShock").onclick = async () => {
  const type = $("#shockType").value;
  const params = type === "illness_wave" ? { rate: 0.6, days: 2 } : type === "rate_hike" ? { bps: 50 } : { bps: 25 };
  await api("/shock", { method: "POST", body: JSON.stringify({ type, params }) });
  await refresh();
};

// poll while auto-running
setInterval(() => {
  refresh().catch(() => {});
}, 2000);

refresh().catch((e) => {
  $("#statusPill").textContent = `API error: ${e.message}`;
});
