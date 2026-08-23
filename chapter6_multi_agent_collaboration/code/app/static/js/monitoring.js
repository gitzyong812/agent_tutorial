// Harness 系统监控：关键指标、最近运行和脱敏事件。
const MonitoringPage = {
  agentId: "",
  activeTab: "runs",
  runPage: 1,
  eventPage: 1,
  runDate: "",
  eventDate: "",
  overview: null,

  async render() {
    const page = document.getElementById("page-monitoring");
    const params = new URLSearchParams({
      run_page: String(this.runPage),
      event_page: String(this.eventPage),
    });
    if (this.agentId) params.set("agent_config_id", this.agentId);
    if (this.runDate) params.set("run_date", this.runDate);
    if (this.eventDate) params.set("event_date", this.eventDate);
    this.overview = await App.api("GET", `/api/monitoring/overview?${params.toString()}`);
    page.innerHTML = `<div class="list-page">
      <div class="list-head memory-head">
        <div><h2>${App.t("monitoring_title")}</h2><p class="muted">${App.t("monitoring_desc")}</p></div>
        <button class="btn" id="monitor-refresh">${App.t("monitoring_refresh")}</button>
      </div>
      ${this.summaryHtml()}
      <div class="monitor-toolbar">
        <div class="monitor-tabs">
          <button class="monitor-tab" data-monitor-tab="runs">${App.t("monitoring_tab_runs")}</button>
          <button class="monitor-tab" data-monitor-tab="events">${App.t("monitoring_tab_events")}</button>
        </div>
        <div class="monitor-filters">
          <label class="monitor-date-filter"><span>${App.t("monitoring_date")}</span><input id="monitor-date" type="date"></label>
          <select id="monitor-agent" class="monitor-agent-filter">
            <option value="">${App.t("monitoring_all_agents")}</option>
            ${this.overview.agent_options.map((item) => `<option value="${item.id}" ${String(item.id) === this.agentId ? "selected" : ""}>${escapeHtml(this.namedId(item.name, item.id))}</option>`).join("")}
          </select>
        </div>
      </div>
      <div id="monitor-panel"></div>
    </div>`;
    page.querySelector("#monitor-refresh").onclick = () => this.render();
    page.querySelector("#monitor-agent").onchange = (event) => {
      this.agentId = event.target.value;
      this.runPage = 1;
      this.eventPage = 1;
      this.render();
    };
    page.querySelector("#monitor-date").onchange = (event) => {
      if (this.activeTab === "events") {
        this.eventDate = event.target.value;
        this.eventPage = 1;
      } else {
        this.runDate = event.target.value;
        this.runPage = 1;
      }
      this.render();
    };
    page.querySelectorAll(".monitor-tab").forEach((button) => {
      button.onclick = () => this.showTab(button.dataset.monitorTab);
    });
    this.showTab(this.activeTab);
  },

  summaryHtml() {
    const counts = this.overview.status_counts;
    const waiting = this.overview.waiting_counts;
    const total = Object.values(counts).reduce((sum, value) => sum + value, 0);
    const attention = counts.handoff + counts.failed;
    const pendingDetail = App.t("monitoring_pending_detail")
      .replace("{human}", waiting.ask_human)
      .replace("{approval}", waiting.tool_approval);
    const attentionDetail = App.t("monitoring_attention_detail")
      .replace("{handoff}", counts.handoff)
      .replace("{failed}", counts.failed);
    return `<div class="monitor-summary">
      ${this.metric(App.t("monitoring_total"), total, total, "total")}
      ${this.metric(App.t("monitoring_running"), counts.running, total, "running")}
      ${this.metric(App.t("monitoring_pending"), counts.pending, total, "pending", pendingDetail)}
      ${this.metric(App.t("monitoring_completed"), counts.completed, total, "completed")}
      ${this.metric(App.t("monitoring_attention"), attention, total, "attention", attentionDetail)}
    </div>`;
  },

  metric(label, value, total, tone, detail = "") {
    const percent = total ? Math.round(value * 100 / total) : 0;
    return `<div class="monitor-metric ${tone}">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
      <div class="monitor-metric-bar"><i style="width:${percent}%"></i></div>
      ${detail ? `<small>${escapeHtml(detail)}</small>` : ""}
    </div>`;
  },

  showTab(type) {
    this.activeTab = type;
    const page = document.getElementById("page-monitoring");
    page.querySelectorAll(".monitor-tab").forEach((button) => {
      button.classList.toggle("active", button.dataset.monitorTab === type);
    });
    page.querySelector("#monitor-date").value = type === "events" ? this.eventDate : this.runDate;
    const panel = page.querySelector("#monitor-panel");
    if (type === "events") {
      panel.innerHTML = `<div class="monitor-table">${this.table(
        [App.t("monitoring_event_id"), App.t("monitoring_run_id"), App.t("monitoring_agent"), App.t("monitoring_event"), App.t("monitoring_channel"), App.t("monitoring_time"), App.t("monitoring_data")],
        this.overview.recent_events.map((item) => [
          item.id,
          item.run_id || "—",
          item.agent_config_id ? this.namedId(item.agent_name, item.agent_config_id) : "—",
          item.event_type,
          item.channel || "—",
          this.formatTime(item.created_at),
          { summary: JSON.stringify(item.data), details: JSON.stringify(item.data, null, 2) },
        ]),
        "monitor-events-table",
        App.t("monitoring_empty_events")
      )}</div>${this.pager(this.overview.event_pagination)}`;
      this.bindPager(panel);
      return;
    }
    panel.innerHTML = `<div class="monitor-table">${this.table(
      [App.t("monitoring_run_id"), App.t("monitoring_session"), App.t("monitoring_agent"), App.t("monitoring_channel"), App.t("field_status"), App.t("monitoring_time")],
      this.overview.recent_runs.map((item) => [
        item.id,
        this.namedId(item.session_title || App.t("monitoring_untitled_session"), item.session_id),
        this.namedId(item.agent_name, item.agent_config_id),
        item.channel,
        { badge: App.t(`monitoring_${item.status}`), tone: item.status },
        this.formatTime(item.updated_at),
      ]),
      "monitor-runs-table",
      App.t("monitoring_empty_runs")
    )}</div>${this.pager(this.overview.run_pagination)}`;
    this.bindPager(panel);
  },

  namedId(name, id) {
    return `${name} (#${id})`;
  },

  formatTime(value) {
    const locale = { zh: "zh-CN", en: "en-US", ru: "ru-RU" }[App.lang];
    return value ? new Date(value).toLocaleString(locale) : "—";
  },

  table(headers, rows, className, emptyText) {
    const body = rows.length
      ? rows.map((row) => `<tr>${row.map((value) => this.cell(value)).join("")}</tr>`).join("")
      : `<tr><td colspan="${headers.length}"><div class="memory-empty"><strong>${escapeHtml(emptyText)}</strong></div></td></tr>`;
    return `<table class="${className}"><thead><tr>${headers.map((item) => `<th>${escapeHtml(item)}</th>`).join("")}</tr></thead><tbody>${body}</tbody></table>`;
  },

  pager(pagination) {
    const pageCount = Math.max(pagination.pages, 1);
    return `<div class="memory-pager monitor-pager">
      <span>${App.t("monitoring_pagination_total").replace("{total}", pagination.total)}</span>
      <button class="btn btn-sm" id="monitor-prev" ${pagination.page <= 1 ? "disabled" : ""}>${App.t("action_previous")}</button>
      <span>${pagination.page} / ${pageCount}</span>
      <button class="btn btn-sm" id="monitor-next" ${pagination.page >= pagination.pages ? "disabled" : ""}>${App.t("action_next")}</button>
    </div>`;
  },

  bindPager(panel) {
    panel.querySelector("#monitor-prev").onclick = () => this.changePage(-1);
    panel.querySelector("#monitor-next").onclick = () => this.changePage(1);
  },

  changePage(delta) {
    if (this.activeTab === "events") this.eventPage += delta;
    else this.runPage += delta;
    this.render();
  },

  cell(value) {
    if (value && typeof value === "object" && value.details !== undefined) {
      return `<td><details class="table-content-details monitor-data-details">
        <summary>${escapeHtml(value.summary)}</summary><pre>${escapeHtml(value.details)}</pre>
      </details></td>`;
    }
    if (value && typeof value === "object" && value.badge !== undefined) {
      return `<td><span class="monitor-status status-${escapeAttr(value.tone)}">${escapeHtml(value.badge)}</span></td>`;
    }
    return `<td><span class="monitor-cell-text" title="${escapeAttr(value)}">${escapeHtml(value)}</span></td>`;
  },
};
