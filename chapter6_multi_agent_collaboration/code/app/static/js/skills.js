// 技能管理：来源筛选、本地目录导入、对话创建技能维护和渐进查看。
const SkillsPage = {
  async render() {
    const page = document.getElementById("page-skills");
    const [data, agents] = await Promise.all([
      App.api("GET", "/api/skills"),
      App.api("GET", "/api/agents"),
    ]);
    this.skills = data.items;
    this.agents = agents.filter((agent) => agent.agent_type === "react_agent");
    const agentOptions = this.agents.map((agent) =>
      `<option value="${agent.id}">${escapeHtml(agent.name)}</option>`
    ).join("");
    page.innerHTML = `<div class="list-page">
      <div class="list-head skill-page-head">
        <div><h2>${App.t("skills_title")}</h2><p class="muted">${App.t("skills_desc")}</p></div>
        <button class="btn btn-primary" id="skill-upload">${App.t("skills_upload")}</button>
        <input id="skill-folder" type="file" webkitdirectory multiple hidden>
      </div>
      <div class="skill-toolbar">
        <input id="skill-search" placeholder="${escapeAttr(App.t("skills_search"))}">
        <select id="skill-source">
          <option value="">${App.t("skills_source_all")}</option>
          <option value="builtin">${App.t("skills_source_builtin")}</option>
          <option value="imported">${App.t("skills_source_imported")}</option>
          <option value="created">${App.t("skills_source_created")}</option>
        </select>
        <select id="skill-agent">
          <option value="">${App.t("skills_agent_filter_all")}</option>
          ${agentOptions}
        </select>
      </div>
      ${data.diagnostics.length ? `<div class="form-error">${data.diagnostics.map(escapeHtml).join("<br>")}</div>` : ""}
      <div class="skill-grid" id="skill-grid"></div>
    </div>`;
    page.querySelector("#skill-upload").onclick = () => page.querySelector("#skill-folder").click();
    page.querySelector("#skill-folder").onchange = (event) => this.importFolder(event.target);
    page.querySelector("#skill-search").oninput = () => this.renderCards();
    page.querySelector("#skill-source").onchange = () => this.renderCards();
    page.querySelector("#skill-agent").onchange = () => this.renderCards();
    this.renderCards();
  },

  renderCards() {
    const page = document.getElementById("page-skills");
    const query = page.querySelector("#skill-search").value.trim().toLowerCase();
    const source = page.querySelector("#skill-source").value;
    const agentId = parseInt(page.querySelector("#skill-agent").value, 10);
    const selectedAgent = this.agents.find((agent) => agent.id === agentId);
    const skills = (this.skills || []).filter((skill) => {
      const matchesText = !query || `${skill.name} ${skill.description}`.toLowerCase().includes(query);
      const matchesAgent = !selectedAgent || selectedAgent.skill_names.includes(skill.name);
      return matchesText && matchesAgent && (!source || skill.source === source);
    });
    const grid = page.querySelector("#skill-grid");
    grid.innerHTML = skills.length ? skills.map((skill) => this.card(skill)).join("")
      : `<div class="empty">${App.t("skills_empty")}</div>`;
    grid.querySelectorAll("[data-skill-detail]").forEach((button) => {
      button.onclick = () => this.openDetail(button.dataset.skillDetail);
    });
    grid.querySelectorAll("[data-skill-bind]").forEach((button) => {
      button.onclick = () => this.openBinding(button.dataset.skillBind);
    });
    grid.querySelectorAll("[data-skill-help]").forEach((button) => {
      button.onclick = () => this.openCreatorHelp();
    });
    grid.querySelectorAll("[data-skill-edit]").forEach((button) => {
      button.onclick = () => this.openEdit(button.dataset.skillEdit);
    });
    grid.querySelectorAll("[data-skill-delete]").forEach((button) => {
      button.onclick = () => this.removeSkill(button.dataset.skillDelete);
    });
  },

  card(skill) {
    const dependencies = (skill.required_tools || []).length
      ? `<div class="skill-tools"><span>${App.t("skills_dependencies")}</span>${skill.required_tools.map((tool) => `<code>${escapeHtml(tool)}</code>`).join("")}</div>`
      : "";
    const boundAgents = (this.agents || []).filter((agent) => agent.skill_names.includes(skill.name));
    const bindingSummary = boundAgents.length
      ? boundAgents.map((agent) => `<span>${escapeHtml(agent.name)}</span>`).join("")
      : `<span class="skill-agent-empty">${App.t("skills_unbound")}</span>`;
    const deletable = ["imported", "created"].includes(skill.source)
      ? `<button class="btn btn-sm skill-delete" data-skill-delete="${escapeAttr(skill.name)}">${App.t("skills_delete")}</button>`
      : "";
    const creatorHelp = skill.source === "builtin" && skill.name === "skill-creator"
      ? `<button class="btn btn-sm" data-skill-help>${App.t("skills_creator_help")}</button>`
      : "";
    const edit = skill.source === "created"
      ? `<button class="btn btn-sm" data-skill-edit="${escapeAttr(skill.name)}">${App.t("action_edit")}</button>`
      : "";
    return `<article class="skill-card">
      <div class="skill-card-head"><strong>${escapeHtml(skill.name)}</strong><div class="skill-card-meta"><span>v${escapeHtml(skill.version)}</span></div></div>
      <div class="skill-source source-${escapeAttr(skill.source)}">${App.t(`skills_source_${skill.source}`)}</div>
      <p>${escapeHtml(skill.description)}</p>
      ${dependencies}
      <div class="skill-agent-bindings"><small>${App.t("skills_bound_agents")}</small><div>${bindingSummary}</div></div>
      <div class="skill-card-actions">
        <button class="btn btn-sm" data-skill-detail="${escapeAttr(skill.name)}">${App.t("skills_view")}</button>
        <button class="btn btn-sm" data-skill-bind="${escapeAttr(skill.name)}">${App.t("skills_bind_agents")}</button>
        ${creatorHelp}${edit}${deletable}
      </div>
    </article>`;
  },

  openBinding(skillName) {
    const rows = (this.agents || []).map((agent) => `
      <label class="skill-binding-row">
        <input type="checkbox" value="${agent.id}" ${agent.skill_names.includes(skillName) ? "checked" : ""}>
        <span><strong>${escapeHtml(agent.name)}</strong><small>${App.t("agent_type_react")}</small></span>
      </label>
    `).join("") || `<span class="muted">${App.t("skills_no_react_agents")}</span>`;
    const mask = document.createElement("div");
    mask.className = "modal-mask";
    mask.innerHTML = `<div class="modal skill-binding-modal">
      <h2>${App.t("skills_bind_title")} · ${escapeHtml(skillName)}</h2>
      <div class="modal-body">
        <div class="skill-binding-list">${rows}</div>
        <div class="form-error" id="skill-bind-error" hidden></div>
      </div>
      <div class="modal-actions">
        <button class="btn" id="skill-bind-cancel">${App.t("action_cancel")}</button>
        <button class="btn btn-primary" id="skill-bind-save" ${this.agents.length ? "" : "disabled"}>${App.t("action_save")}</button>
      </div>
    </div>`;
    document.body.appendChild(mask);
    mask.querySelector("#skill-bind-cancel").onclick = () => mask.remove();
    mask.querySelector("#skill-bind-save").onclick = () => this.saveBindings(mask, skillName);
  },

  async saveBindings(mask, skillName) {
    const selected = new Set(
      [...mask.querySelectorAll("input:checked")].map((input) => parseInt(input.value, 10))
    );
    const changed = this.agents.filter((agent) =>
      selected.has(agent.id) !== agent.skill_names.includes(skillName)
    );
    const button = mask.querySelector("#skill-bind-save");
    const errorBox = mask.querySelector("#skill-bind-error");
    button.disabled = true;
    errorBox.hidden = true;
    try {
      await Promise.all(changed.map((agent) => {
        const { id, created_at, updated_at, ...payload } = agent;
        payload.skill_names = selected.has(id)
          ? [...new Set([...agent.skill_names, skillName])]
          : agent.skill_names.filter((name) => name !== skillName);
        return App.api("PUT", `/api/agents/${id}`, payload);
      }));
      this.agents = (await App.api("GET", "/api/agents"))
        .filter((agent) => agent.agent_type === "react_agent");
      mask.remove();
      this.renderCards();
    } catch (error) {
      errorBox.textContent = error.message;
      errorBox.hidden = false;
      button.disabled = false;
    }
  },

  async importFolder(input) {
    const files = [...input.files];
    if (!files.length) return;
    try {
      let response = await this.uploadFiles(files, false);
      if (response.status === 409 && confirm(App.t("skills_overwrite_confirm"))) {
        response = await this.uploadFiles(files, true);
      }
      await this.requireOk(response);
      await this.render();
    } catch (error) {
      alert(error.message);
    } finally {
      input.value = "";
    }
  },

  uploadFiles(files, overwrite) {
    const form = new FormData();
    files.forEach((file) => {
      form.append("files", file, file.name);
      form.append("paths", file.webkitRelativePath || file.name);
    });
    form.append("overwrite", String(overwrite));
    return fetch("/api/skills/import", { method: "POST", body: form });
  },

  async openDetail(name) {
    const skill = await App.api("GET", `/api/skills/${encodeURIComponent(name)}`);
    const dependencies = (skill.required_tools || []).length
      ? `<p class="muted">${App.t("skills_dependencies")}: ${skill.required_tools.map(escapeHtml).join(", ")}</p>`
      : "";
    const mask = document.createElement("div");
    mask.className = "modal-mask";
    mask.innerHTML = `<div class="modal skill-detail-modal"><h2>${escapeHtml(skill.name)}</h2>
      <div class="modal-body">
        <div class="skill-source source-${escapeAttr(skill.source)}">${App.t(`skills_source_${skill.source}`)}</div>
        ${dependencies}<pre class="skill-content">${escapeHtml(skill.content)}</pre>
      </div>
      <div class="modal-actions"><button class="btn" id="skill-close">${App.t("action_close")}</button></div></div>`;
    document.body.appendChild(mask);
    mask.querySelector("#skill-close").onclick = () => mask.remove();
  },

  openCreatorHelp() {
    const help = escapeHtml(App.t("skills_creator_help_text")).replace(/\n/g, "<br>");
    const mask = document.createElement("div");
    mask.className = "modal-mask";
    mask.innerHTML = `<div class="modal skill-detail-modal"><h2>${App.t("skills_creator_help_title")}</h2>
      <div class="modal-body"><p class="skill-help-text">${help}</p>
        <pre class="skill-command">/skill-creator ${escapeHtml(App.t("skills_creator_example"))}</pre></div>
      <div class="modal-actions"><button class="btn" id="skill-help-close">${App.t("action_close")}</button></div></div>`;
    document.body.appendChild(mask);
    mask.querySelector("#skill-help-close").onclick = () => mask.remove();
  },

  async openEdit(name) {
    const skill = await App.api("GET", `/api/skills/${encodeURIComponent(name)}`);
    const skillDocument = `---\nname: ${skill.name}\ndescription: ${JSON.stringify(skill.description)}\nversion: ${JSON.stringify(String(skill.version))}\n---\n\n${skill.content}`;
    const mask = document.createElement("div");
    mask.className = "modal-mask";
    mask.innerHTML = `<div class="modal skill-detail-modal"><h2>${App.t("skills_edit_title")} · ${escapeHtml(name)}</h2>
      <div class="modal-body"><p class="muted">${App.t("skills_edit_help")}</p>
        <textarea id="skill-editor" class="skill-editor">${escapeHtml(skillDocument)}</textarea>
        <div class="form-error" id="skill-edit-error" hidden></div></div>
      <div class="modal-actions"><button class="btn" id="skill-edit-cancel">${App.t("action_cancel")}</button>
        <button class="btn btn-primary" id="skill-edit-save">${App.t("action_save")}</button></div></div>`;
    document.body.appendChild(mask);
    mask.querySelector("#skill-edit-cancel").onclick = () => mask.remove();
    mask.querySelector("#skill-edit-save").onclick = async () => {
      const button = mask.querySelector("#skill-edit-save");
      const errorBox = mask.querySelector("#skill-edit-error");
      button.disabled = true;
      errorBox.hidden = true;
      try {
        await App.api("PUT", `/api/skills/${encodeURIComponent(name)}`, {
          content: mask.querySelector("#skill-editor").value,
        });
        mask.remove();
        await this.render();
      } catch (error) {
        errorBox.textContent = error.message;
        errorBox.hidden = false;
        button.disabled = false;
      }
    };
  },

  async removeSkill(name) {
    const bound = (this.agents || []).filter((agent) => agent.skill_names.includes(name));
    const affected = bound.length
      ? `\n${App.t("skills_delete_bound")}: ${bound.map((agent) => agent.name).join(", ")}`
      : "";
    if (!confirm(`${App.t("skills_delete_confirm")}\n${name}${affected}`)) return;
    try {
      await App.api("DELETE", `/api/skills/${encodeURIComponent(name)}`);
      await this.render();
    } catch (error) {
      alert(error.message);
    }
  },

  async requireOk(response) {
    if (response.ok) return response.json();
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || response.statusText);
  },
};
