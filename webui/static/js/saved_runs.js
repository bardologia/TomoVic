"use strict";

class SavedRunsView {
  constructor(runConsole, gridEl) {
    this.runConsole = runConsole;
    this.gridEl = gridEl;
    this.entries = [];
  }

  enter() {
    this.load();
  }

  async load() {
    const data = await Api.get("/api/saved-runs");

    if (data.error) {
      this.gridEl.innerHTML = `<p class="saved-empty">Could not load saved runs: ${SharedCharts.esc(data.error)}</p>`;
      return;
    }

    this.entries = data.saved || [];
    this._renderGrid();
  }

  _renderGrid() {
    this.gridEl.innerHTML = "";

    if (!this.entries.length) {
      this.gridEl.innerHTML = `<p class="saved-empty">No saved runs yet. Configure a script on its launch page and press &ldquo;Save for later&rdquo;.</p>`;
      return;
    }

    this.entries.forEach((entry, i) => {
      const card = this._card(entry);
      card.style.transitionDelay = `${i * 0.04}s`;
      this.gridEl.appendChild(card);
    });

    window.revealScan();
  }

  _card(entry) {
    const card = document.createElement("article");
    card.className = "saved-card reveal";

    const overrides = Object.entries(entry.overrides || {});
    const rows = overrides.map(([path, value]) =>
      `<div class="saved-card__override"><span class="saved-card__path">${SharedCharts.esc(path)}</span><b>${SharedCharts.esc(value)}</b></div>`
    ).join("");

    const facts = [entry.detach ? "detached" : "attached"];
    if (entry.follow_up) facts.push(`then ${entry.follow_up}`);
    facts.push(entry.saved_at.replace("T", " "));

    card.innerHTML =
      `<div class="saved-card__top"><span class="saved-card__script">${SharedCharts.esc(entry.title)}</span>` +
      `<button type="button" class="saved-card__delete" title="Delete this saved run">&times;</button></div>` +
      `<h3 class="saved-card__name">${SharedCharts.esc(entry.name || entry.title)}</h3>` +
      `<div class="saved-card__overrides">${rows || `<p class="saved-card__none">All defaults, no overrides.</p>`}</div>` +
      `<div class="saved-card__facts">${facts.map((f) => `<span>${SharedCharts.esc(f)}</span>`).join("")}</div>` +
      `<div class="saved-card__actions">` +
      `<button type="button" class="btn btn--primary saved-card__launch">&#9654;&nbsp; Launch now</button>` +
      `<button type="button" class="btn btn--ghost saved-card__schedule" title="Queue this saved run to launch when the currently running job (and any earlier queued runs) end">&#8627;&nbsp; Schedule</button>` +
      `</div>`;

    card.querySelector(".saved-card__launch").addEventListener("click", () => this._run(entry, false));
    card.querySelector(".saved-card__schedule").addEventListener("click", () => this._run(entry, true));
    card.querySelector(".saved-card__delete").addEventListener("click", () => this._delete(entry));
    return card;
  }

  async _run(entry, queue) {
    const label = entry.name || entry.title;
    const res = await Api.post(`/api/saved-runs/${entry.saved_id}/run`, { queue: !!queue });

    if (!res.ok) {
      Toast.show(res.error || (queue ? "Schedule failed" : "Launch failed"), "error");
      return;
    }

    Toast.show(res.queued ? `Scheduled ${label} to run after the current job` : `Launched ${label}`, "ok");
    window.router.go("console");
    await this.runConsole.refresh();
    this.runConsole.open(res.job_id);
  }

  async _delete(entry) {
    const label = entry.name || entry.title;
    if (!window.confirm(`Delete saved run "${label}"?`)) return;

    const res = await Api.post(`/api/saved-runs/${entry.saved_id}/delete`, {});
    if (!res.ok) {
      Toast.show(res.error || "Delete failed", "error");
      return;
    }

    Toast.show(`Deleted ${label}`, "ok");
    await this.load();
  }

}

window.SavedRunsView = SavedRunsView;
