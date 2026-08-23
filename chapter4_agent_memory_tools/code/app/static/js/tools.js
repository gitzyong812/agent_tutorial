// 工具管理页：预设工具只读，自定义 HTTP 工具可维护。
const ToolsPage = {
  async render() {
    const page = document.getElementById("page-tools");
    const tools = await App.api("GET", "/api/tools");
    this.tools = tools;
    page.innerHTML = `
      <div class="list-page">
        <div class="list-head">
          <div>
            <h2>${App.t("tools_title")}</h2>
            <p class="muted">${App.t("tools_security_note")}</p>
          </div>
          <button class="btn btn-primary" id="tool-new">${App.t("tools_new")}</button>
        </div>
        <table class="tool-table">
          <thead><tr>
            <th>${App.t("field_name")}</th>
            <th>${App.t("tools_source")}</th>
            <th>${App.t("tools_description")}</th>
            <th>${App.t("tools_schema")}</th>
            <th>${App.t("tools_endpoint")}</th>
            <th>${App.t("field_actions")}</th>
          </tr></thead>
          <tbody>${tools.map((tool) => this.row(tool)).join("")}</tbody>
        </table>
      </div>`;
    page.querySelector("#tool-new").onclick = () => this.openForm();
    tools.filter((tool) => tool.editable).forEach((tool) => {
      page.querySelector(`#tool-edit-${tool.id}`).onclick = () => this.openForm(tool);
      page.querySelector(`#tool-del-${tool.id}`).onclick = () => this.remove(tool.id);
    });
  },

  row(tool) {
    const sourceLabel = tool.source === "builtin" ? App.t("tools_builtin") : App.t("tools_custom");
    const source = `<span class="tool-source-badge source-${tool.source}">${sourceLabel}</span>`;
    const endpoint = tool.source === "builtin" ? "—" : `${tool.method} ${escapeHtml(tool.url)}`;
    const actions = tool.editable
      ? `<button class="btn btn-sm" id="tool-edit-${tool.id}">${App.t("action_edit")}</button>
         <button class="btn btn-sm btn-danger" id="tool-del-${tool.id}">${App.t("action_delete")}</button>`
      : `<span class="muted">${App.t("tools_readonly")}</span>`;
    const schemaText = JSON.stringify(tool.parameters_schema, null, 2);
    const schemaPreviewText = JSON.stringify(tool.parameters_schema);
    const schemaPreview = schemaPreviewText.length > 72
      ? `${schemaPreviewText.slice(0, 72)}…`
      : schemaPreviewText;
    const schema = `<details class="table-content-details"><summary>${escapeHtml(schemaPreview)}</summary><pre>${escapeHtml(schemaText)}</pre></details>`;
    return `<tr>
      <td><strong>${escapeHtml(tool.name)}</strong></td>
      <td>${source}</td>
      <td>${escapeHtml(tool.description)}</td>
      <td>${schema}</td>
      <td>${endpoint}</td>
      <td><div class="row-actions">${actions}</div></td>
    </tr>`;
  },

  openForm(tool = null) {
    const d = tool || {
      name: "",
      description: "",
      method: "GET",
      url: "",
      headers: {},
      is_enabled: true,
      parameters_schema: { type: "object", properties: {}, additionalProperties: false },
    };
    const mask = document.createElement("div");
    mask.className = "modal-mask";
    mask.innerHTML = `
      <div class="modal">
        <h2>${tool ? App.t("action_edit") : App.t("tools_new")}</h2>
        <div class="modal-body"><div class="form-grid">
          <div class="field"><label>${App.t("field_name")}</label><input id="t-name" value="${escapeAttr(d.name)}"></div>
          <div class="field"><label>${App.t("tools_description")}</label><textarea id="t-desc">${escapeHtml(d.description)}</textarea></div>
          <div class="form-grid cols-2">
            <div class="field"><label>Method</label><select id="t-method"><option>GET</option><option ${d.method === "POST" ? "selected" : ""}>POST</option></select></div>
            <div class="field"><label>URL</label><input id="t-url" value="${escapeAttr(d.url)}"></div>
          </div>
          <div class="field"><label>JSON Schema</label><textarea id="t-schema" class="code-input">${escapeHtml(JSON.stringify(d.parameters_schema, null, 2))}</textarea></div>
          <div class="field"><label>${App.t("tools_headers")}</label><textarea id="t-headers" class="code-input">${escapeHtml(JSON.stringify(d.headers || {}, null, 2))}</textarea></div>
          <label class="chk"><input id="t-enabled" type="checkbox" ${d.is_enabled ? "checked" : ""}> ${App.t("tools_enabled")}</label>
        </div></div>
        <div class="modal-actions">
          <button class="btn" id="t-cancel">${App.t("action_cancel")}</button>
          <button class="btn btn-primary" id="t-save">${App.t("action_save")}</button>
        </div>
      </div>`;
    document.body.appendChild(mask);
    mask.querySelector("#t-cancel").onclick = () => mask.remove();
    mask.querySelector("#t-save").onclick = async () => {
      try {
        const payload = {
          name: mask.querySelector("#t-name").value.trim(),
          description: mask.querySelector("#t-desc").value,
          method: mask.querySelector("#t-method").value,
          url: mask.querySelector("#t-url").value.trim(),
          parameters_schema: JSON.parse(mask.querySelector("#t-schema").value),
          headers: JSON.parse(mask.querySelector("#t-headers").value),
          is_enabled: mask.querySelector("#t-enabled").checked,
        };
        await App.api(tool ? "PUT" : "POST", tool ? `/api/tools/${tool.id}` : "/api/tools", payload);
        mask.remove();
        this.render();
      } catch (err) {
        alert(err.message);
      }
    };
  },

  async remove(id) {
    if (!confirm(App.t("confirm_delete"))) return;
    await App.api("DELETE", `/api/tools/${id}`);
    this.render();
  },
};
