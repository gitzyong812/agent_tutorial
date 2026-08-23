// 数字员工配置页：列表 + 弹窗表单（提示词要素 + 模型参数）。
const AgentsPage = {
  async render() {
    const page = document.getElementById("page-agents");
    const [agents, models, tags] = await Promise.all([
      App.api("GET", "/api/agents"),
      App.api("GET", "/api/model-configs?config_type=chat"),
      App.api("GET", "/api/tags"),
    ]);
    this.models = models;
    this.tags = tags;
    page.innerHTML = `
      <div class="list-page">
        <div class="list-head">
          <h2>${App.t("agents_title")}</h2>
          <button class="btn btn-primary" id="agent-new">${App.t("agents_new")}</button>
        </div>
        <table>
          <thead><tr>
            <th>${App.t("field_name")}</th>
            <th>${App.t("field_agent_type")}</th>
            <th>${App.t("field_model")}</th>
            <th>${App.t("field_status")}</th>
            <th>${App.t("field_actions")}</th>
          </tr></thead>
          <tbody>${agents.map((a) => this.row(a)).join("")}</tbody>
        </table>
      </div>`;

    page.querySelector("#agent-new").onclick = () => this.openForm();
    agents.forEach((a) => {
      page.querySelector(`#a-edit-${a.id}`).onclick = () => this.openForm(a);
      page.querySelector(`#a-del-${a.id}`).onclick = () => this.remove(a.id);
      page.querySelector(`#a-pub-${a.id}`).onclick = () => this.togglePublish(a);
    });
  },

  modelName(id) {
    const m = (this.models || []).find((x) => x.id === id);
    return m ? m.name : "—";
  },

  row(a) {
    const tag =
      a.status === "published"
        ? `<span class="tag tag-published">${App.t("status_published")}</span>`
        : `<span class="tag tag-draft">${App.t("status_draft")}</span>`;
    const pubLabel = a.status === "published" ? App.t("action_unpublish") : App.t("action_publish");
    const typeLabel = a.agent_type === "rag_chatbot" ? App.t("agent_type_rag") : App.t("agent_type_chatbot");
    return `<tr>
      <td>${escapeHtml(a.name)}</td>
      <td>${typeLabel}</td>
      <td>${escapeHtml(this.modelName(a.model_config_id))}</td>
      <td>${tag}</td>
      <td><div class="row-actions">
        <button class="btn btn-sm" id="a-pub-${a.id}">${pubLabel}</button>
        <button class="btn btn-sm" id="a-edit-${a.id}">${App.t("action_edit")}</button>
        <button class="btn btn-sm btn-danger" id="a-del-${a.id}">${App.t("action_delete")}</button>
      </div></td>
    </tr>`;
  },

  openForm(a = null) {
    const d = a || {
      name: "", agent_type: "chatbot", model_config_id: this.models[0] ? this.models[0].id : null,
      role: "", service_goal: "", business_context: "", constraints: "", output_instruction: "",
      temperature: 0.2, top_p: 1.0, max_tokens: 500, frequency_penalty: 0, presence_penalty: 0,
      history_turns: 5, status: "draft",
      knowledge_tag_ids: [], retrieval_top_k: 3, retriever_type: "vector",
    };
    const opts = this.models
      .map((m) => `<option value="${m.id}" ${m.id === d.model_config_id ? "selected" : ""}>${escapeHtml(m.name)}</option>`)
      .join("");
    const selectedTags = new Set(d.knowledge_tag_ids || []);
    const tagChecks = (this.tags || [])
      .map((t) => `<label class="chk"><input type="checkbox" value="${t.id}" ${selectedTags.has(t.id) ? "checked" : ""}> ${escapeHtml(t.name)}</label>`)
      .join("") || App.t("knowledge_no_tags");

    const mask = document.createElement("div");
    mask.className = "modal-mask";
    mask.innerHTML = `
      <div class="modal">
        <h2>${a ? App.t("action_edit") : App.t("agents_new")}</h2>
        <div class="modal-body">
          <div class="form-grid">
            <div class="field"><label>${App.t("field_name")}</label><input id="f-name" value="${escapeHtml(d.name)}"></div>
            <div class="form-grid cols-2">
              <div class="field"><label>${App.t("field_agent_type")}</label>
                <select id="f-type">
                  <option value="chatbot" ${d.agent_type === "chatbot" ? "selected" : ""}>${App.t("agent_type_chatbot")}</option>
                  <option value="rag_chatbot" ${d.agent_type === "rag_chatbot" ? "selected" : ""}>${App.t("agent_type_rag")}</option>
                </select></div>
              <div class="field"><label>${App.t("field_model")}</label><select id="f-model">${opts}</select></div>
            </div>
            <div class="field"><label>${App.t("field_role")}</label><textarea id="f-role">${escapeHtml(d.role)}</textarea></div>
            <div class="field"><label>${App.t("field_service_goal")}</label><textarea id="f-goal">${escapeHtml(d.service_goal)}</textarea></div>
            <div class="field" id="f-ctx-field"><label>${App.t("field_business_context")}</label><textarea id="f-ctx">${escapeHtml(d.business_context)}</textarea></div>
            <div id="f-rag-section" class="rag-section">
              <div class="field"><label>${App.t("field_knowledge_tags")}</label><div class="chk-group" id="f-tags">${tagChecks}</div></div>
              <div class="form-grid cols-2">
                <div class="field"><label>${App.t("field_retrieval_top_k")}</label><input id="f-topk" type="number" value="${d.retrieval_top_k}"></div>
                <div class="field"><label>${App.t("field_retriever_type")}</label>
                  <select id="f-retriever">
                    <option value="vector" ${d.retriever_type === "vector" ? "selected" : ""}>${App.t("retriever_vector")}</option>
                    <option value="keyword" ${d.retriever_type === "keyword" ? "selected" : ""}>${App.t("retriever_keyword")}</option>
                    <option value="hybrid" ${d.retriever_type === "hybrid" ? "selected" : ""}>${App.t("retriever_hybrid")}</option>
                  </select></div>
              </div>
            </div>
            <div class="field"><label>${App.t("field_constraints")}</label><textarea id="f-cons">${escapeHtml(d.constraints)}</textarea></div>
            <div class="field"><label>${App.t("field_output_instruction")}</label><textarea id="f-out">${escapeHtml(d.output_instruction)}</textarea></div>
            <div class="form-grid cols-2">
              <div class="field"><label>${App.t("field_temperature")}</label><input id="f-temp" type="number" step="0.1" value="${d.temperature}"></div>
              <div class="field"><label>${App.t("field_top_p")}</label><input id="f-topp" type="number" step="0.1" value="${d.top_p}"></div>
              <div class="field"><label>${App.t("field_max_tokens")}</label><input id="f-max" type="number" value="${d.max_tokens}"></div>
              <div class="field"><label>${App.t("field_history_turns")}</label><input id="f-hist" type="number" value="${d.history_turns}"></div>
              <div class="field"><label>${App.t("field_frequency_penalty")}</label><input id="f-freq" type="number" step="0.1" value="${d.frequency_penalty}"></div>
              <div class="field"><label>${App.t("field_presence_penalty")}</label><input id="f-pres" type="number" step="0.1" value="${d.presence_penalty}"></div>
            </div>
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn" id="f-cancel">${App.t("action_cancel")}</button>
          <button class="btn btn-primary" id="f-save">${App.t("action_save")}</button>
        </div>
      </div>`;
    document.body.appendChild(mask);
    const toggleRag = () => {
      const isRag = mask.querySelector("#f-type").value === "rag_chatbot";
      mask.querySelector("#f-rag-section").style.display = isRag ? "" : "none";
      mask.querySelector("#f-ctx-field").style.display = isRag ? "none" : "";
    };
    toggleRag();
    mask.querySelector("#f-type").addEventListener("change", toggleRag);
    mask.querySelector("#f-cancel").onclick = () => mask.remove();
    mask.querySelector("#f-save").onclick = async () => {
      const agentType = mask.querySelector("#f-type").value;
      const payload = {
        name: mask.querySelector("#f-name").value.trim(),
        agent_type: agentType,
        model_config_id: parseInt(mask.querySelector("#f-model").value, 10),
        role: mask.querySelector("#f-role").value,
        service_goal: mask.querySelector("#f-goal").value,
        business_context: agentType === "chatbot" ? mask.querySelector("#f-ctx").value : "",
        constraints: mask.querySelector("#f-cons").value,
        output_instruction: mask.querySelector("#f-out").value,
        temperature: parseFloat(mask.querySelector("#f-temp").value),
        top_p: parseFloat(mask.querySelector("#f-topp").value),
        max_tokens: parseInt(mask.querySelector("#f-max").value, 10),
        frequency_penalty: parseFloat(mask.querySelector("#f-freq").value),
        presence_penalty: parseFloat(mask.querySelector("#f-pres").value),
        history_turns: parseInt(mask.querySelector("#f-hist").value, 10),
        knowledge_tag_ids: [...mask.querySelectorAll("#f-tags input:checked")].map((el) => parseInt(el.value, 10)),
        retrieval_top_k: parseInt(mask.querySelector("#f-topk").value, 10) || 3,
        retriever_type: mask.querySelector("#f-retriever").value,
        status: d.status,
      };
      if (a) await App.api("PUT", `/api/agents/${a.id}`, payload);
      else await App.api("POST", "/api/agents", payload);
      mask.remove();
      this.render();
    };
  },

  async togglePublish(a) {
    const next = a.status === "published" ? "draft" : "published";
    await App.api("PATCH", `/api/agents/${a.id}/status`, { status: next });
    this.render();
  },

  async remove(id) {
    if (!confirm(App.t("confirm_delete"))) return;
    await App.api("DELETE", `/api/agents/${id}`);
    this.render();
  },
};
