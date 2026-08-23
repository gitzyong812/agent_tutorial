// 数字员工配置页：列表 + 弹窗表单（提示词要素 + 模型参数）。
const AgentsPage = {
  async render() {
    const page = document.getElementById("page-agents");
    const [agents, models, tags, tools, skills, defaults] = await Promise.all([
      App.api("GET", "/api/agents"),
      App.api("GET", "/api/model-configs?config_type=chat"),
      App.api("GET", "/api/tags"),
      App.api("GET", "/api/tools"),
      App.api("GET", "/api/skills"),
      App.api("GET", "/api/agents/defaults"),
    ]);
    this.models = models;
    this.tags = tags;
    this.tools = tools;
    this.skills = skills.items || [];
    this.defaults = defaults;
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
    const typeLabel = this.typeLabel(a.agent_type);
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

  typeLabel(type) {
    if (type === "rag_chatbot") return App.t("agent_type_rag");
    if (type === "react_agent") return App.t("agent_type_react");
    return App.t("agent_type_chatbot");
  },

  openForm(a = null) {
    const defaults = this.defaults;
    const d = a || {
      name: "", agent_type: "chatbot", model_config_id: this.models[0] ? this.models[0].id : null,
      role: "", service_goal: "", business_context: "", constraints: "", output_instruction: "",
      temperature: 0.2, top_p: 1.0, max_tokens: defaults.max_tokens, frequency_penalty: 0, presence_penalty: 0,
      history_turns: 5, status: "draft",
      knowledge_tag_ids: [], retrieval_top_k: 3, retriever_type: "vector",
      tool_bindings: (this.tools || [])
        .filter((tool) => ["memory_search", "calculator"].includes(tool.name))
        .map((tool) => ({
          tool_config_id: tool.id,
          extra: tool.name === "memory_search" ? { top_k: 5 } : {},
        })),
      max_steps: defaults.max_steps, memory_enabled: true,
      skill_names: ["skill-creator"], extensions: {},
    };
    const opts = this.models
      .map((m) => `<option value="${m.id}" ${m.id === d.model_config_id ? "selected" : ""}>${escapeHtml(m.name)}</option>`)
      .join("");
    const selectedTags = new Set(d.knowledge_tag_ids || []);
    const tagChecks = (this.tags || [])
      .map((t) => `<label class="chk"><input type="checkbox" value="${t.id}" ${selectedTags.has(t.id) ? "checked" : ""}> ${escapeHtml(t.name)}</label>`)
      .join("") || App.t("knowledge_no_tags");
    const bindingExtras = new Map(
      (d.tool_bindings || []).map((binding) => [binding.tool_config_id, { ...(binding.extra || {}) }])
    );
    const toolRows = (this.tools || [])
      .map((tool) => {
        const configurable = ["knowledge_search", "memory_search"].includes(tool.name);
        return `<div class="tool-binding-row">
          <input class="tool-toggle" id="tool-bind-${tool.id}" type="checkbox" data-tool-id="${tool.id}"
            ${bindingExtras.has(tool.id) ? "checked" : ""} ${tool.is_enabled ? "" : "disabled"}>
          <label class="tool-binding-main" for="tool-bind-${tool.id}" title="${escapeAttr(`${tool.name}：${tool.description}`)}">
            <strong>${escapeHtml(tool.name)}</strong><small>${escapeHtml(tool.description)}</small>
          </label>
          ${configurable ? `<button type="button" class="btn btn-sm" data-config-tool="${tool.id}" ${tool.is_enabled ? "" : "disabled"}>${App.t("tools_configure")}</button>` : ""}
        </div>`;
      })
      .join("");
    const selectedSkills = new Set(d.skill_names || []);
    const skillRows = (this.skills || []).map((skill) => `
      <label class="skill-binding-row">
        <input type="checkbox" value="${escapeAttr(skill.name)}" ${selectedSkills.has(skill.name) ? "checked" : ""}>
        <span><strong>${escapeHtml(skill.name)}</strong><small>${escapeHtml(skill.description)}</small></span>
      </label>
    `).join("") || `<span class="muted">${App.t("skills_empty")}</span>`;

    const mask = document.createElement("div");
    mask.className = "modal-mask";
    mask.innerHTML = `
      <div class="modal agent-config-modal">
        <h2>${a ? App.t("action_edit") : App.t("agents_new")}</h2>
        <div class="modal-body">
          <div class="form-grid">
            <div class="field"><label>${App.t("field_name")}</label><input id="f-name" value="${escapeAttr(d.name)}"></div>
            <div class="form-grid cols-2">
              <div class="field"><label>${App.t("field_agent_type")}</label>
                <select id="f-type">
                  <option value="chatbot" ${d.agent_type === "chatbot" ? "selected" : ""}>${App.t("agent_type_chatbot")}</option>
                  <option value="rag_chatbot" ${d.agent_type === "rag_chatbot" ? "selected" : ""}>${App.t("agent_type_rag")}</option>
                  <option value="react_agent" ${d.agent_type === "react_agent" ? "selected" : ""}>${App.t("agent_type_react")}</option>
                </select></div>
              <div class="field"><label>${App.t("field_model")}</label><select id="f-model">${opts}</select></div>
            </div>
            <div id="f-agent-section" class="rag-section">
              <div class="agent-binding-panel agent-tool-panel">
                <div class="agent-binding-title">${App.t("field_tools")}</div>
                <div class="tool-binding-list" id="f-tools">${toolRows}</div>
              </div>
              <div class="agent-binding-panel agent-skill-panel">
                <div class="agent-binding-title">${App.t("field_skills")}</div>
                <div class="skill-binding-list" id="f-skills">${skillRows}</div>
              </div>
              <div class="agent-run-settings">
                <div class="field"><label>${App.t("field_max_steps")}</label><input id="f-steps" type="number" min="1" max="${defaults.max_steps_limit}" value="${d.max_steps || defaults.max_steps}"></div>
                <label class="agent-memory-toggle"><input id="f-memory" type="checkbox" ${d.memory_enabled !== false ? "checked" : ""}> <span>${App.t("field_memory_enabled")}</span></label>
              </div>
            </div>
            <div class="field"><label>${App.t("field_role")}</label><textarea id="f-role">${escapeHtml(d.role)}</textarea></div>
            <div class="field"><label>${App.t("field_service_goal")}</label><textarea id="f-goal">${escapeHtml(d.service_goal)}</textarea></div>
            <div class="field" id="f-ctx-field"><label>${App.t("field_business_context")}</label><textarea id="f-ctx">${escapeHtml(d.business_context)}</textarea></div>
            <div id="f-rag-section" class="rag-section">
              <div class="field"><div class="field-label-actions"><label>${App.t("field_knowledge_tags")}</label><div>
                <button type="button" class="text-btn" data-tag-action="all" data-tag-target="f-tags">${App.t("action_select_all")}</button>
                <button type="button" class="text-btn" data-tag-action="none" data-tag-target="f-tags">${App.t("action_select_none")}</button>
              </div></div><div class="chk-group" id="f-tags">${tagChecks}</div></div>
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
      const type = mask.querySelector("#f-type").value;
      mask.querySelector("#f-rag-section").style.display = type === "rag_chatbot" ? "" : "none";
      mask.querySelector("#f-agent-section").style.display = type === "react_agent" ? "" : "none";
      mask.querySelector("#f-ctx-field").style.display = type === "rag_chatbot" ? "none" : "";
    };
    toggleRag();
    mask.querySelector("#f-type").addEventListener("change", (event) => {
      if (event.target.value === "react_agent" && d.agent_type !== "react_agent") {
        const creator = [...mask.querySelectorAll("#f-skills input")]
          .find((input) => input.value === "skill-creator");
        if (creator) creator.checked = true;
      }
      toggleRag();
    });
    mask.querySelectorAll("[data-config-tool]").forEach((button) => {
      button.onclick = () => {
        const toolId = parseInt(button.dataset.configTool, 10);
        const checkbox = mask.querySelector(`[data-tool-id="${toolId}"]`);
        const wasChecked = checkbox.checked;
        checkbox.checked = true;
        this.openToolConfig(toolId, bindingExtras.get(toolId) || {}, (extra) => {
          bindingExtras.set(toolId, extra);
        }, () => {
          checkbox.checked = wasChecked;
        });
      };
    });
    mask.querySelectorAll("[data-tool-id]").forEach((checkbox) => {
      checkbox.onchange = () => {
        const toolId = parseInt(checkbox.dataset.toolId, 10);
        const tool = this.tools.find((item) => item.id === toolId);
        if (!checkbox.checked) {
          bindingExtras.delete(toolId);
        } else if (["knowledge_search", "memory_search"].includes(tool.name)) {
          this.openToolConfig(toolId, bindingExtras.get(toolId) || {}, (extra) => {
            bindingExtras.set(toolId, extra);
          }, () => {
            checkbox.checked = false;
          });
        } else {
          bindingExtras.set(toolId, {});
        }
      };
    });
    this.bindTagActions(mask);
    mask.querySelector("#f-cancel").onclick = () => mask.remove();
    mask.querySelector("#f-save").onclick = async () => {
      const agentType = mask.querySelector("#f-type").value;
      const payload = {
        name: mask.querySelector("#f-name").value.trim(),
        agent_type: agentType,
        model_config_id: parseInt(mask.querySelector("#f-model").value, 10),
        role: mask.querySelector("#f-role").value,
        service_goal: mask.querySelector("#f-goal").value,
        business_context: agentType === "rag_chatbot" ? "" : mask.querySelector("#f-ctx").value,
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
        tool_bindings: [...mask.querySelectorAll("#f-tools input:checked")].map((el) => ({
          tool_config_id: parseInt(el.dataset.toolId, 10),
          extra: bindingExtras.get(parseInt(el.dataset.toolId, 10)) || {},
        })),
        skill_names: [...mask.querySelectorAll("#f-skills input:checked")].map((el) => el.value),
        max_steps: parseInt(mask.querySelector("#f-steps").value, 10) || defaults.max_steps,
        memory_enabled: mask.querySelector("#f-memory").checked,
        extensions: d.extensions || {},
        status: d.status,
      };
      if (a) await App.api("PUT", `/api/agents/${a.id}`, payload);
      else await App.api("POST", "/api/agents", payload);
      mask.remove();
      this.render();
    };
  },

  openToolConfig(toolId, extra, onSave, onCancel = null) {
    const tool = this.tools.find((item) => item.id === toolId);
    const isKnowledge = tool.name === "knowledge_search";
    const selectedTags = new Set(extra.knowledge_tag_ids || []);
    const tagChecks = (this.tags || []).map((tag) => `
      <label class="chk"><input type="checkbox" value="${tag.id}" ${selectedTags.has(tag.id) ? "checked" : ""}> ${escapeHtml(tag.name)}</label>
    `).join("") || App.t("knowledge_no_tags");
    const dialog = document.createElement("div");
    dialog.className = "modal-mask";
    dialog.innerHTML = `<div class="modal tool-config-modal">
      <h2>${App.t("tools_configure")} · ${escapeHtml(tool.name)}</h2>
      <div class="modal-body"><div class="form-grid">
        ${isKnowledge ? `<div class="field"><div class="field-label-actions"><label>${App.t("field_knowledge_tags")}</label><div>
          <button type="button" class="text-btn" data-tag-action="all" data-tag-target="tc-tags">${App.t("action_select_all")}</button>
          <button type="button" class="text-btn" data-tag-action="none" data-tag-target="tc-tags">${App.t("action_select_none")}</button>
        </div></div><div class="chk-group" id="tc-tags">${tagChecks}</div></div>
        <div class="field"><label>${App.t("field_retriever_type")}</label><select id="tc-retriever">
          <option value="vector" ${extra.retriever_type === "vector" ? "selected" : ""}>${App.t("retriever_vector")}</option>
          <option value="keyword" ${extra.retriever_type === "keyword" ? "selected" : ""}>${App.t("retriever_keyword")}</option>
          <option value="hybrid" ${extra.retriever_type === "hybrid" ? "selected" : ""}>${App.t("retriever_hybrid")}</option>
        </select></div>` : ""}
        <div class="field"><label>${App.t("field_retrieval_top_k")}</label>
          <input id="tc-topk" type="number" min="1" max="${isKnowledge ? 20 : 10}" value="${isKnowledge ? (extra.retrieval_top_k || 3) : (extra.top_k || 5)}">
        </div>
      </div></div>
      <div class="modal-actions"><button class="btn" id="tc-cancel">${App.t("action_cancel")}</button><button class="btn btn-primary" id="tc-save">${App.t("action_save")}</button></div>
    </div>`;
    document.body.appendChild(dialog);
    this.bindTagActions(dialog);
    dialog.querySelector("#tc-cancel").onclick = () => {
      dialog.remove();
      if (onCancel) onCancel();
    };
    dialog.querySelector("#tc-save").onclick = () => {
      const topK = parseInt(dialog.querySelector("#tc-topk").value, 10);
      const value = isKnowledge ? {
        knowledge_tag_ids: [...dialog.querySelectorAll("#tc-tags input:checked")].map((el) => parseInt(el.value, 10)),
        retrieval_top_k: topK,
        retriever_type: dialog.querySelector("#tc-retriever").value,
      } : { top_k: topK };
      onSave(value);
      dialog.remove();
    };
  },

  bindTagActions(root) {
    root.querySelectorAll("[data-tag-action]").forEach((button) => {
      button.onclick = () => {
        const checked = button.dataset.tagAction === "all";
        root.querySelectorAll(`#${button.dataset.tagTarget} input[type="checkbox"]`).forEach((input) => {
          input.checked = checked;
        });
      };
    });
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
