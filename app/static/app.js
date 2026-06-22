"use strict";

const state = {
  token: localStorage.getItem("token") || null,
  role: localStorage.getItem("role") || null,
  fullName: localStorage.getItem("fullName") || null,
  projects: [],
  categories: [],
  equipmentTypes: [],
};

// --- API helper --------------------------------------------------------------
async function api(path, { method = "GET", body } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (state.token) headers["Authorization"] = `Bearer ${state.token}`;
  const res = await fetch(path, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401) {
    logout();
    throw new Error("Session expired, please log in again.");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail || detail;
    } catch (_) {}
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.status === 204 ? null : res.json();
}

// --- Auth --------------------------------------------------------------------
function logout() {
  state.token = state.role = state.fullName = null;
  localStorage.clear();
  render();
}

document.getElementById("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const errEl = document.getElementById("login-error");
  errEl.textContent = "";
  try {
    const data = await api("/api/auth/login", {
      method: "POST",
      body: {
        username: document.getElementById("username").value,
        password: document.getElementById("password").value,
      },
    });
    state.token = data.access_token;
    state.role = data.role;
    state.fullName = data.full_name;
    localStorage.setItem("token", state.token);
    localStorage.setItem("role", state.role);
    localStorage.setItem("fullName", state.fullName);
    await render();
  } catch (err) {
    errEl.textContent = err.message;
  }
});

// --- View management ---------------------------------------------------------
function showTab(name) {
  document.querySelectorAll(".tab").forEach((t) => (t.hidden = t.id !== `tab-${name}`));
  document.querySelectorAll(".tabs button").forEach((b) =>
    b.classList.toggle("active", b.dataset.tab === name)
  );
  if (name === "dashboard") loadDashboard();
  if (name === "requests") loadRequests();
  if (name === "daily") loadDaily();
}

document.querySelectorAll(".tabs button").forEach((b) =>
  b.addEventListener("click", () => showTab(b.dataset.tab))
);

async function render() {
  const loginView = document.getElementById("login-view");
  const appView = document.getElementById("app-view");
  const sessionEl = document.getElementById("session");

  if (!state.token) {
    loginView.hidden = false;
    appView.hidden = true;
    sessionEl.innerHTML = "";
    return;
  }
  loginView.hidden = true;
  appView.hidden = false;
  sessionEl.innerHTML = `Signed in as <strong>${state.fullName}</strong> (${state.role}) <button class="small secondary" id="logout">Logout</button>`;
  document.getElementById("logout").addEventListener("click", logout);

  await loadReferenceData();
  showTab("dashboard");
}

async function loadReferenceData() {
  [state.projects, state.categories, state.equipmentTypes] = await Promise.all([
    api("/api/projects"),
    api("/api/categories"),
    api("/api/equipment/types"),
  ]);
  populateProjectSelect(document.getElementById("req-project"));
  populateProjectSelect(document.getElementById("av-project"));
  // Seed one line in each builder if empty.
  if (!document.querySelector("#req-items .item-row")) addItemRow("req-items");
  if (!document.querySelector("#req-eq-items .item-row")) addEqItemRow("req-eq-items");
  if (!document.querySelector("#av-items .item-row")) addItemRow("av-items");
  const today = new Date().toISOString().slice(0, 10);
  document.getElementById("req-date").value = today;
  document.getElementById("av-date").value = today;
  document.getElementById("daily-date").value = today;
}

function populateProjectSelect(sel) {
  sel.innerHTML = state.projects
    .map((p) => `<option value="${p.id}">${p.name}</option>`)
    .join("");
}

function categoryOptions() {
  return state.categories
    .map((c) => `<option value="${c.id}">${c.name}</option>`)
    .join("");
}

function categoryName(id) {
  const c = state.categories.find((x) => x.id === id);
  return c ? c.name : `#${id}`;
}

function equipmentTypeOptions() {
  return state.equipmentTypes
    .map((t) => `<option value="${t.id}">${t.name}</option>`)
    .join("");
}

function equipmentTypeName(id) {
  const t = state.equipmentTypes.find((x) => x.id === id);
  return t ? t.name : `#${id}`;
}

// --- Item row builders -------------------------------------------------------
function addItemRow(containerId) {
  const div = document.createElement("div");
  div.className = "item-row";
  div.innerHTML = `
    <label>Category<select class="item-cat">${categoryOptions()}</select></label>
    <label>Quantity<input class="item-qty" type="number" min="1" value="1" /></label>
    <button class="secondary small remove-row" type="button">Remove</button>`;
  div.querySelector(".remove-row").addEventListener("click", () => div.remove());
  document.getElementById(containerId).appendChild(div);
}

function collectItems(containerId) {
  return [...document.querySelectorAll(`#${containerId} .item-row`)]
    .map((row) => ({
      category_id: parseInt(row.querySelector(".item-cat").value, 10),
      quantity: parseInt(row.querySelector(".item-qty").value, 10),
    }))
    .filter((i) => i.quantity > 0);
}

function addEqItemRow(containerId) {
  const div = document.createElement("div");
  div.className = "item-row";
  div.innerHTML = `
    <label>Equipment type<select class="eq-type">${equipmentTypeOptions()}</select></label>
    <label>Quantity<input class="eq-qty" type="number" min="1" value="1" /></label>
    <button class="secondary small remove-row" type="button">Remove</button>`;
  div.querySelector(".remove-row").addEventListener("click", () => div.remove());
  document.getElementById(containerId).appendChild(div);
}

function collectEqItems(containerId) {
  return [...document.querySelectorAll(`#${containerId} .item-row`)]
    .map((row) => ({
      equipment_type_id: parseInt(row.querySelector(".eq-type").value, 10),
      quantity: parseInt(row.querySelector(".eq-qty").value, 10),
    }))
    .filter((i) => i.quantity > 0);
}

document.getElementById("add-item").addEventListener("click", () => addItemRow("req-items"));
document.getElementById("add-eq-item").addEventListener("click", () => addEqItemRow("req-eq-items"));
document.getElementById("av-add").addEventListener("click", () => addItemRow("av-items"));

// --- New request -------------------------------------------------------------
document.getElementById("submit-request").addEventListener("click", async () => {
  const msg = document.getElementById("request-msg");
  msg.className = "msg";
  msg.textContent = "";
  try {
    const req = await api("/api/requests", {
      method: "POST",
      body: {
        project_id: parseInt(document.getElementById("req-project").value, 10),
        required_date: document.getElementById("req-date").value,
        shift: document.getElementById("req-shift").value,
        remarks: document.getElementById("req-remarks").value,
        items: collectItems("req-items"),
        equipment_items: collectEqItems("req-eq-items"),
      },
    });
    msg.className = "msg ok";
    msg.textContent = `Request #${req.id} created (status: ${req.status}).`;
  } catch (err) {
    msg.className = "msg err";
    msg.textContent = err.message;
  }
});

// --- Availability check ------------------------------------------------------
document.getElementById("av-check").addEventListener("click", async () => {
  const table = document.getElementById("av-table");
  const tbody = table.querySelector("tbody");
  try {
    const lines = await api("/api/availability/check", {
      method: "POST",
      body: {
        project_id: parseInt(document.getElementById("av-project").value, 10),
        required_date: document.getElementById("av-date").value,
        items: collectItems("av-items"),
      },
    });
    tbody.innerHTML = lines
      .map(
        (l) => `<tr>
          <td>${l.category_name}</td>
          <td>${l.requested}</td>
          <td>${l.available}</td>
          <td class="${l.eligible >= l.requested ? "ok-val" : ""}">${l.eligible}</td>
          <td class="${l.shortage > 0 ? "shortage" : ""}">${l.shortage}</td>
          <td>${l.reason || "&mdash;"}</td>
        </tr>`
      )
      .join("");
    table.hidden = false;
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="6" class="error">${err.message}</td></tr>`;
    table.hidden = false;
  }
});

// --- Dashboard ---------------------------------------------------------------
async function loadDashboard() {
  const data = await api("/api/dashboard/summary");
  const metrics = [
    ["Available manpower", data.total_available_manpower],
    ["Available equipment", data.total_available_equipment],
    ["Total shortage", data.total_shortage],
    ["Pending approvals", data.pending_approvals],
    ["Expired passports", data.expired_passports],
    ["Expired inspections", data.expired_inspections],
    ["Mobilized", data.mobilized_requests],
    ["Rejected", data.rejected_requests],
  ];
  document.getElementById("dashboard-cards").innerHTML = metrics
    .map(
      ([label, value]) =>
        `<div class="metric"><div class="value">${value}</div><div class="label">${label}</div></div>`
    )
    .join("");
  document.querySelector("#dashboard-table tbody").innerHTML = data.projects
    .map(
      (p) => `<tr>
        <td>${p.project}</td>
        <td>${p.requested}</td>
        <td>${p.eligible}</td>
        <td class="${p.shortage > 0 ? "shortage" : ""}">${p.shortage}</td>
        <td>${p.open_requests}</td>
      </tr>`
    )
    .join("");
}

// --- Daily status board ------------------------------------------------------
async function loadDaily() {
  const dateEl = document.getElementById("daily-date");
  if (!dateEl.value) dateEl.value = new Date().toISOString().slice(0, 10);
  const board = document.getElementById("daily-board");
  let data;
  try {
    data = await api(`/api/dashboard/daily?on_date=${dateEl.value}`);
  } catch (err) {
    board.innerHTML = `<p class="error">${err.message}</p>`;
    return;
  }
  if (!data.projects.length) {
    board.innerHTML = `<p class="hint">No active requests for ${data.date}.</p>`;
    return;
  }
  const section = (title, lines) =>
    lines.length
      ? `<h4>${title}</h4><table><thead><tr><th>Item</th><th>Requested</th><th>In place</th><th>Shortage</th><th>Status</th></tr></thead><tbody>${lines
          .map(
            (l) => `<tr>
              <td>${l.name}</td><td>${l.requested}</td><td>${l.in_place}</td>
              <td class="${l.shortage > 0 ? "shortage" : ""}">${l.shortage}</td>
              <td><span class="badge ${l.status === "shortage" ? "rejected" : "confirmed"}">${l.status}</span></td>
            </tr>`
          )
          .join("")}</tbody></table>`
      : "";
  board.innerHTML = data.projects
    .map(
      (p) => `<div class="req">
        <div class="req-head">
          <strong>${p.project}</strong>
          <span class="badge ${p.status === "shortage" ? "rejected" : "confirmed"}">${p.status}</span>
        </div>
        <div class="hint">Client supervisor: ${p.client_supervisor || "&mdash;"} &middot; Our supervisor: ${p.company_supervisor || "&mdash;"}</div>
        ${section("Manpower", p.manpower)}
        ${section("Equipment", p.equipment)}
      </div>`
    )
    .join("");
}

document.getElementById("daily-load").addEventListener("click", loadDaily);

// --- Requests list + workflow ------------------------------------------------
const TRANSITION_BUTTONS = {
  draft: [["submitted", "Submit"]],
  submitted: [["supervisor_review", "Start review"]],
  supervisor_review: [
    ["operations_approval", "Confirm manpower"],
    ["rejected", "Reject"],
  ],
  operations_approval: [
    ["confirmed", "Approve"],
    ["rejected", "Reject"],
  ],
  confirmed: [["mobilized", "Mobilize"]],
  mobilized: [["closed", "Close"]],
};

// Roles allowed to confirm in-place quantities.
const CAN_CONFIRM = ["supervisor", "admin"];

async function loadRequests() {
  const list = document.getElementById("requests-list");
  const requests = await api("/api/requests");
  if (!requests.length) {
    list.innerHTML = "<p class='hint'>No requests yet.</p>";
    return;
  }
  const canConfirm = CAN_CONFIRM.includes(state.role);
  const projName = (id) => (state.projects.find((p) => p.id === id) || {}).name || `#${id}`;
  // Editable in-place cell for supervisors/admins, plain number otherwise.
  const inPlaceCell = (kind, it) =>
    canConfirm
      ? `<input class="ip-input" data-kind="${kind}" data-item="${it.id}" type="number" min="0" max="${it.quantity}" value="${it.in_place_qty}" style="width:70px" />`
      : it.in_place_qty;

  list.innerHTML = requests
    .map((r) => {
      const items = r.items
        .map(
          (it) =>
            `<tr><td>${categoryName(it.category_id)}</td><td>${it.quantity}</td><td>${it.eligible_qty}</td><td>${inPlaceCell("man", it)}</td><td class="${it.shortage_qty > 0 ? "shortage" : ""}">${it.shortage_qty}</td><td>${it.reason || "&mdash;"}</td></tr>`
        )
        .join("");
      const manTable = r.items.length
        ? `<h4>Manpower</h4><table><thead><tr><th>Category</th><th>Qty</th><th>Eligible</th><th>In place</th><th>Shortage</th><th>Reason</th></tr></thead><tbody>${items}</tbody></table>`
        : "";
      const eqItems = r.equipment_items
        .map(
          (it) =>
            `<tr><td>${equipmentTypeName(it.equipment_type_id)}</td><td>${it.quantity}</td><td>${it.available_qty}</td><td>${inPlaceCell("eq", it)}</td><td class="${it.shortage_qty > 0 ? "shortage" : ""}">${it.shortage_qty}</td><td>${it.reason || "&mdash;"}</td></tr>`
        )
        .join("");
      const eqTable = r.equipment_items.length
        ? `<h4>Equipment</h4><table><thead><tr><th>Type</th><th>Qty</th><th>Avail.</th><th>In place</th><th>Shortage</th><th>Reason</th></tr></thead><tbody>${eqItems}</tbody></table>`
        : "";
      const buttons = (TRANSITION_BUTTONS[r.status] || [])
        .map(
          ([target, label]) =>
            `<button class="small" data-req="${r.id}" data-target="${target}">${label}</button>`
        )
        .join("");
      const confirmBtn = canConfirm
        ? `<button class="small" data-confirm="${r.id}">Confirm in place</button>`
        : "";
      return `<div class="req" data-req-card="${r.id}">
        <div class="req-head">
          <strong>Request #${r.id} &middot; ${projName(r.project_id)}</strong>
          <span class="badge ${r.status}">${r.status.replace(/_/g, " ")}</span>
        </div>
        <div class="hint">Date: ${r.required_date} &middot; Shift: ${r.shift} ${r.remarks ? "&middot; " + r.remarks : ""}</div>
        ${manTable}
        ${eqTable}
        <div class="req-actions">
          <button class="small secondary" data-recheck="${r.id}">Recheck</button>
          ${confirmBtn}
          ${buttons}
        </div>
      </div>`;
    })
    .join("");

  list.querySelectorAll("[data-target]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      try {
        await api(`/api/requests/${btn.dataset.req}/transition/${btn.dataset.target}`, {
          method: "POST",
          body: { remarks: "" },
        });
        loadRequests();
      } catch (err) {
        alert(err.message);
      }
    })
  );
  list.querySelectorAll("[data-recheck]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      try {
        await api(`/api/requests/${btn.dataset.recheck}/recheck`, { method: "POST" });
        loadRequests();
      } catch (err) {
        alert(err.message);
      }
    })
  );
  list.querySelectorAll("[data-confirm]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      const rid = btn.dataset.confirm;
      const card = list.querySelector(`[data-req-card="${rid}"]`);
      const manpower = [];
      const equipment = [];
      card.querySelectorAll(".ip-input").forEach((inp) => {
        const line = { item_id: parseInt(inp.dataset.item, 10), in_place: parseInt(inp.value || "0", 10) };
        (inp.dataset.kind === "man" ? manpower : equipment).push(line);
      });
      try {
        await api(`/api/requests/${rid}/confirm`, {
          method: "POST",
          body: { manpower, equipment },
        });
        loadRequests();
      } catch (err) {
        alert(err.message);
      }
    })
  );
}

document.getElementById("refresh-requests").addEventListener("click", loadRequests);

// --- Init --------------------------------------------------------------------
render();
