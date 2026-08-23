// 记忆管理页：日记与核心记忆分栏展示、分页维护并触发巩固。
const MemoriesPage = {
  activeType: "diary",
  states: {
    diary: { page: 1, pageSize: 10, scope: "", keyword: "", date: "" },
    core: { page: 1, pageSize: 10, scope: "", keyword: "", category: "" },
  },

  async render() {
    const page = document.getElementById("page-memories");
    this.agents = (await App.api("GET", "/api/agents"))
      .filter((agent) => agent.agent_type === "react_agent");
    const consolidateOptions = this.agents
      .map((agent) => `<option value="agent:${agent.id}">${escapeHtml(agent.name)}</option>`)
      .join("");
    page.innerHTML = `
      <div class="list-page">
        <div class="list-head memory-head">
          <div><h2>${App.t("memories_title")}</h2><p class="muted">${App.t("memories_desc")}</p></div>
        </div>
        <div class="memory-tabs">
          <button class="memory-tab" data-memory-type="diary">${App.t("memory_layer_daily")}</button>
          <button class="memory-tab" data-memory-type="core">${App.t("memory_layer_core")}</button>
        </div>
        <div class="memory-consolidate-panel" id="memory-consolidate-tools">
          <div>
            <div class="memory-panel-title">${App.t("memories_consolidate_title")}</div>
            <div class="muted">${App.t("memories_consolidate_help")}</div>
          </div>
          <div class="memory-consolidate-actions">
            <label for="memory-consolidate-scope">${App.t("memories_consolidate_scope")}</label>
            <select id="memory-consolidate-scope">
              <option value="">${App.t("memories_select_scope_placeholder")}</option>
              <option value="global">${App.t("memory_scope_global")}</option>
              ${consolidateOptions}
            </select>
            <button class="btn btn-primary" id="memory-consolidate" disabled>${App.t("memories_consolidate")}</button>
          </div>
        </div>
        <div id="memory-list"></div>
      </div>`;
    page.querySelectorAll(".memory-tab").forEach((button) => {
      button.onclick = () => {
        this.activeType = button.dataset.memoryType;
        this.drawShell();
      };
    });
    page.querySelector("#memory-consolidate-scope").onchange = (event) => {
      page.querySelector("#memory-consolidate").disabled = !event.target.value;
    };
    page.querySelector("#memory-consolidate").onclick = () => this.consolidate();
    await this.drawShell();
  },

  async drawShell() {
    const page = document.getElementById("page-memories");
    const type = this.activeType;
    page.querySelectorAll(".memory-tab").forEach((button) => {
      button.classList.toggle("active", button.dataset.memoryType === type);
    });
    page.querySelector("#memory-consolidate-tools").style.display = type === "core" ? "flex" : "none";
    page.querySelector("#memory-list").innerHTML = `
      <div id="memory-table-wrap"></div>
      <div class="memory-pager" id="memory-pager"></div>`;
    await this.loadPage();
  },

  setFilter(key, value) {
    this.states[this.activeType][key] = value;
    this.states[this.activeType].page = 1;
    this.loadPage();
  },

  async loadPage() {
    const wrap = document.getElementById("memory-table-wrap");
    wrap.innerHTML = `<div class="memory-loading">${App.t("memories_loading")}</div>`;
    const state = this.states[this.activeType];
    const params = new URLSearchParams({
      type: this.activeType,
      page: state.page,
      page_size: state.pageSize,
    });
    if (state.scope === "global") params.set("scope", "global");
    if (state.scope.startsWith("agent:")) {
      params.set("scope", "agent");
      params.set("agent_config_id", state.scope.split(":")[1]);
    }
    if (state.keyword) params.set("keyword", state.keyword);
    if (this.activeType === "diary" && state.date) params.set("memory_date", state.date);
    if (this.activeType === "core" && state.category) params.set("category", state.category);
    const result = await App.api("GET", `/api/memories?${params.toString()}`);
    this.drawTable(result.items);
    this.drawPager(result);
  },

  agentName(id) {
    const agent = this.agents.find((item) => item.id === id);
    return agent ? agent.name : "—";
  },

  drawTable(items) {
    const wrap = document.getElementById("memory-table-wrap");
    const isDiary = this.activeType === "diary";
    const state = this.states[this.activeType];
    const agentOpts = this.agents
      .map((agent) => `<option value="agent:${agent.id}" ${state.scope === `agent:${agent.id}` ? "selected" : ""}>${escapeHtml(agent.name)}</option>`)
      .join("");
    const scopeFilter = `<select class="memory-filter" id="memory-scope">
      <option value="">${App.t("memories_all_scopes")}</option>
      <option value="global" ${state.scope === "global" ? "selected" : ""}>${App.t("memory_scope_global")}</option>
      ${agentOpts}
    </select>`;
    const keywordFilter = `<input class="memory-filter" id="memory-keyword" value="${escapeAttr(state.keyword)}" placeholder="${escapeAttr(App.t("memories_content_filter"))}">`;
    const categoryFilter = `<select class="memory-filter" id="memory-category">
      <option value="">${App.t("memories_all_categories")}</option>
      <option value="fact" ${state.category === "fact" ? "selected" : ""}>${App.t("memory_category_fact")}</option>
      <option value="experience" ${state.category === "experience" ? "selected" : ""}>${App.t("memory_category_experience")}</option>
    </select>`;
    const headers = isDiary
      ? `<th class="memory-head-single">${App.t("field_name")}</th>
        <th>${App.t("memories_scope")}${scopeFilter}</th>
        <th>${App.t("memories_date")}<input class="memory-filter" id="memory-date" type="date" value="${escapeAttr(state.date)}"></th>
        <th class="memory-content-head">${App.t("memories_content")}${keywordFilter}</th>
        <th class="memory-head-single">${App.t("memories_consolidation_status")}</th><th class="memory-head-single">${App.t("memories_updated")}</th>`
      : `<th class="memory-head-single">${App.t("field_name")}</th>
        <th>${App.t("memories_scope")}${scopeFilter}</th>
        <th>${App.t("memories_category")}${categoryFilter}</th>
        <th class="memory-content-head">${App.t("memories_content")}${keywordFilter}</th>
        <th class="memory-head-single">${App.t("memories_updated")}</th>`;
    const rows = items.map((item) => {
      const scopeLabel = item.scope === "global" ? App.t("memory_scope_global") : this.agentName(item.agent_config_id);
      const scope = `<span class="memory-badge scope-${item.scope}">${escapeHtml(scopeLabel)}</span>`;
      const preview = item.content.replace(/\s+/g, " ").trim();
      const shortPreview = preview.length > 72 ? `${preview.slice(0, 72)}…` : preview;
      const content = `<details class="table-content-details"><summary>${escapeHtml(shortPreview)}</summary><pre>${escapeHtml(item.content)}</pre></details>`;
      const common = `<td><div class="cell-title">${escapeHtml(item.name)}</div></td><td>${scope}</td>`;
      const isConsolidated = item.consolidated_at
        && new Date(item.updated_at) <= new Date(item.consolidated_at);
      const details = isDiary
        ? `<td>${item.diary_date}</td><td>${content}</td><td><span class="memory-badge status-${isConsolidated ? "done" : "pending"}">${isConsolidated ? App.t("memories_consolidated") : App.t("memories_pending")}</span></td><td>${this.formatTime(item.updated_at)}</td>`
        : `<td><span class="memory-badge category-${item.category}">${App.t(`memory_category_${item.category}`)}</span></td><td>${content}</td><td>${this.formatTime(item.updated_at)}</td>`;
      return `<tr>${common}${details}<td><div class="row-actions">
        <button class="btn btn-sm" data-edit="${item.id}">${App.t("action_edit")}</button>
        <button class="btn btn-sm btn-danger" data-delete="${item.id}">${App.t("action_delete")}</button>
      </div></td></tr>`;
    }).join("");
    const empty = items.length ? rows : `<tr><td colspan="${isDiary ? 7 : 6}"><div class="memory-empty"><strong>${App.t("memories_empty_title")}</strong><span>${App.t(`memories_empty_${this.activeType}`)}</span></div></td></tr>`;
    wrap.innerHTML = `<div class="memory-table-scroll"><table class="memory-table memory-table-${this.activeType}"><thead><tr>${headers}<th class="memory-head-single">${App.t("field_actions")}</th></tr></thead><tbody>${empty}</tbody></table></div>`;
    items.forEach((item) => {
      wrap.querySelector(`[data-edit="${item.id}"]`).onclick = () => this.openForm(item);
      wrap.querySelector(`[data-delete="${item.id}"]`).onclick = () => this.remove(item.id);
    });
    wrap.querySelector("#memory-scope").onchange = (event) => this.setFilter("scope", event.target.value);
    wrap.querySelector("#memory-keyword").onchange = (event) => this.setFilter("keyword", event.target.value.trim());
    if (isDiary) {
      wrap.querySelector("#memory-date").onchange = (event) => this.setFilter("date", event.target.value);
    } else {
      wrap.querySelector("#memory-category").onchange = (event) => this.setFilter("category", event.target.value);
    }
  },

  drawPager(result) {
    const pager = document.getElementById("memory-pager");
    const pageCount = Math.max(result.pages, 1);
    pager.innerHTML = `
      <span>${App.t("memories_total")}: ${result.total}</span>
      <button class="btn btn-sm" id="memory-prev" ${result.page <= 1 ? "disabled" : ""}>${App.t("action_previous")}</button>
      <span>${result.page} / ${pageCount}</span>
      <button class="btn btn-sm" id="memory-next" ${result.page >= result.pages ? "disabled" : ""}>${App.t("action_next")}</button>`;
    pager.querySelector("#memory-prev").onclick = () => this.changePage(-1);
    pager.querySelector("#memory-next").onclick = () => this.changePage(1);
  },

  changePage(delta) {
    this.states[this.activeType].page += delta;
    this.loadPage();
  },

  openForm(item) {
    const isDiary = this.activeType === "diary";
    const mask = document.createElement("div");
    mask.className = "modal-mask";
    const coreFields = isDiary ? "" : `
      <div class="field"><label>${App.t("field_name")}</label><input id="m-name" value="${escapeAttr(item.name)}"></div>
      <div class="field"><label>${App.t("memories_category")}</label><select id="m-category">
        <option value="fact">${App.t("memory_category_fact")}</option>
        <option value="experience" ${item.category === "experience" ? "selected" : ""}>${App.t("memory_category_experience")}</option>
      </select></div>`;
    mask.innerHTML = `<div class="modal"><h2>${App.t("action_edit")}</h2><div class="modal-body">
      ${coreFields}<div class="field"><label>${App.t("memories_content")}</label><textarea class="code-input" id="m-content">${escapeHtml(item.content)}</textarea></div>
      </div><div class="modal-actions"><button class="btn" id="m-cancel">${App.t("action_cancel")}</button><button class="btn btn-primary" id="m-save">${App.t("action_save")}</button></div></div>`;
    document.body.appendChild(mask);
    mask.querySelector("#m-cancel").onclick = () => mask.remove();
    mask.querySelector("#m-save").onclick = async () => {
      try {
        const payload = { content: mask.querySelector("#m-content").value };
        if (!isDiary) {
          payload.name = mask.querySelector("#m-name").value;
          payload.category = mask.querySelector("#m-category").value;
        }
        const path = isDiary ? `diaries/${item.id}` : `core/${item.id}`;
        await App.api("PUT", `/api/memories/${path}`, payload);
        mask.remove();
        this.loadPage();
      } catch (err) { alert(err.message); }
    };
  },

  async consolidate() {
    const select = document.getElementById("memory-consolidate-scope");
    const button = document.getElementById("memory-consolidate");
    const value = select.value;
    const isAgent = value.startsWith("agent:");
    try {
      button.disabled = true;
      button.textContent = App.t("memories_consolidating");
      const result = await App.api("POST", "/api/memories/consolidate", {
        scope: isAgent ? "agent" : "global",
        agent_config_id: isAgent ? parseInt(value.split(":")[1], 10) : null,
      });
      alert(result.processed
        ? `${App.t("memories_processed")}: ${result.processed}`
        : App.t("memories_no_pending"));
      this.states.core.page = 1;
      await this.loadPage();
    } catch (err) {
      alert(err.message);
    } finally {
      button.textContent = App.t("memories_consolidate");
      button.disabled = !select.value;
    }
  },

  async remove(id) {
    if (!confirm(App.t("confirm_delete"))) return;
    const path = this.activeType === "diary" ? `diaries/${id}` : `core/${id}`;
    await App.api("DELETE", `/api/memories/${path}`);
    await this.loadPage();
  },

  formatTime(value) {
    return value ? value.replace("T", " ").slice(0, 16) : "—";
  },
};
