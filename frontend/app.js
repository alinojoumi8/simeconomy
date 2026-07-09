const $ = (sel) => document.querySelector(sel);
let lastState = null;

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
    ["Agents", m.agent_count ?? "—"],
    ["Policy rate", `${(m.policy_rate_bps / 100).toFixed(2)}%`],
    ["Agent cash", money(m.agent_cash_cents)],
    ["Company cash", money(m.company_cash_cents)],
    ["Loans out", money(m.loans_outstanding_cents)],
    ["Companies", m.companies],
    ["VC funded", m.vc_funded ?? 0],
    ["Listings", m.listings ?? 0],
    ["Equity idx", money(m.equity_index_cents ?? 0)],
    ["Trades today", m.trades_today ?? 0],
    ["Employed", m.employed_workers],
    ["Unemployed", m.unemployed_workers],
    ["Sick", m.sick_agents],
    ["Opinion", m.avg_opinion_economy ?? 0],
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
      return `<tr data-id="${a.id}" style="cursor:pointer">
        <td>${a.name}</td>
        <td>${a.role}</td>
        <td><span class="badge ${healthClass}">${a.health}</span></td>
        <td>${(a.opinion_economy ?? 0).toFixed(2)}</td>
        <td>${money(a.cash_cents)}</td>
      </tr>`;
    })
    .join("");
  $("#agentCount").textContent = `(${agents.length})`;
  const sel = $("#agentSelect");
  const cur = sel.value;
  sel.innerHTML = agents.map((a) => `<option value="${a.id}">${a.name} (${a.role})</option>`).join("");
  if (cur) sel.value = cur;
  tbody.querySelectorAll("tr").forEach((tr) => {
    tr.onclick = () => {
      sel.value = tr.dataset.id;
      showAgent(tr.dataset.id);
    };
  });
}

async function showAgent(id) {
  const a = await api(`/agents/${id}`);
  if (a.error) {
    $("#agentDetail").textContent = "Not found";
    return;
  }
  const mem = (a.memories || []).slice(-6).reverse();
  $("#agentDetail").innerHTML = `
    <div class="title">${a.name} · ${a.role}</div>
    <div class="meta">cash ${money(a.cash_cents)} · opinion ${(a.opinion_economy ?? 0).toFixed(2)} · reflections ${a.reflection_count || 0}</div>
    <div class="muted">Goals: ${(a.goals || []).join("; ")}</div>
    <div class="muted" style="margin-top:6px"><strong>Latest reflection:</strong> ${a.latest_reflection || "—"}</div>
    <div style="margin-top:8px">${mem.map((m) => `<div class="meta">d${m.tick} [${m.kind}] ${m.content}</div>`).join("")}</div>
  `;
}

function renderCompanies(state) {
  const cos = state.companies || [];
  const jobs = (state.jobs || []).filter((j) => j.open);
  const deals = state.vc_deals || [];
  $("#companies").innerHTML = cos.length
    ? cos
        .map(
          (c) =>
            `<div class="item"><div class="title">${c.name} <span class="badge">${c.stage}</span></div>
             <div class="meta">${c.sector} · founder ${c.founder_id} · cash ${money(c.cash_cents)} · inv ${c.inventory_units}
             · VC raised ${money(c.vc_raised_cents || 0)} · symbol ${c.listed_symbol || "—"}</div></div>`
        )
        .join("")
    : `<div class="muted">No companies yet.</div>`;
  $("#vcDeals").innerHTML = deals.length
    ? deals
        .map(
          (d) =>
            `<div class="item"><div class="title">${d.status.toUpperCase()} · ${money(d.amount_cents)}</div>
             <div class="meta">co ${d.company_id} · vc ${d.vc_agent_id} · shares ${d.equity_shares}</div>
             <div class="muted">${d.pitch_note || ""}</div></div>`
        )
        .join("")
    : `<div class="muted">No VC deals yet.</div>`;
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

function renderMarket(state) {
  const m = state.market || {};
  const listings = m.listings || [];
  const trades = m.recent_trades || [];
  const orders = m.open_orders || [];
  if (!listings.length) {
    $("#market").innerHTML = `<div class="muted">No listings yet. Founders can IPO after VC.</div>`;
    return;
  }
  $("#market").innerHTML = `
    ${listings
      .map(
        (L) =>
          `<div class="item"><div class="title">${L.symbol} · last ${money(L.last_price_cents)}</div>
           <div class="meta">mkt cap ${money(L.market_cap_cents)} · float ${L.float_shares} · co ${L.company_id}</div></div>`
      )
      .join("")}
    <h3>Open orders (${orders.length})</h3>
    ${
      orders.length
        ? orders
            .slice(0, 12)
            .map(
              (o) =>
                `<div class="meta">${o.side} ${o.qty} ${o.symbol} @ ${money(o.price_cents)} · ${o.agent_id}</div>`
            )
            .join("")
        : `<div class="muted">None</div>`
    }
    <h3>Recent trades</h3>
    ${
      trades.length
        ? trades
            .slice()
            .reverse()
            .slice(0, 12)
            .map(
              (t) =>
                `<div class="meta">d${t.tick} ${t.qty} ${t.symbol} @ ${money(t.price_cents)} ${t.buyer_id}←${t.seller_id}</div>`
            )
            .join("")
        : `<div class="muted">No trades yet</div>`
    }
  `;
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
  const list = [...(events || [])].reverse().slice(0, 100);
  $("#events").innerHTML = list
    .map(
      (e) =>
        `<div class="item"><div class="meta">Day ${e.tick} · ${e.kind}</div><div>${e.message}</div></div>`
    )
    .join("");
}

async function refresh() {
  const state = await api("/state");
  lastState = state;
  const m = state.metrics || {};
  $("#statusPill").textContent = `Day ${state.tick} · ${state.paused ? "paused" : "running"} · phase ${state.phase || "1"}`;
  renderCards(m);
  renderAgents(state.agents || []);
  renderCompanies(state);
  renderMarket(state);
  renderNews(state.news || []);
  renderEvents(state.events || []);
  if ($("#agentSelect").value) showAgent($("#agentSelect").value);
}

$("#btnStep1").onclick = async () => {
  await api("/step", { method: "POST", body: JSON.stringify({ n: 1 }) });
  await refresh();
};
$("#btnStep7").onclick = async () => {
  await api("/step", { method: "POST", body: JSON.stringify({ n: 7 }) });
  await refresh();
};
$("#btnStep30").onclick = async () => {
  await api("/step", { method: "POST", body: JSON.stringify({ n: 30 }) });
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
  const params =
    type === "illness_wave" ? { rate: 0.6, days: 2 } : type === "rate_hike" ? { bps: 50 } : { bps: 25 };
  await api("/shock", { method: "POST", body: JSON.stringify({ type, params }) });
  await refresh();
};
$("#agentSelect").onchange = () => showAgent($("#agentSelect").value);

setInterval(() => {
  refresh().catch(() => {});
}, 2500);

refresh().catch((e) => {
  $("#statusPill").textContent = `API error: ${e.message}`;
});
