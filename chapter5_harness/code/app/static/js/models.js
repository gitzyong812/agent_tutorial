// 模型配置页：列表 + 弹窗表单。
const ModelsPage = {
  async render() {
    const page = document.getElementById("page-models");
    const items = await App.api("GET", "/api/model-configs");
    page.innerHTML = `
      <div class="list-page">
        <div class="list-head">
          <h2>${App.t("models_title")}</h2>
          <button class="btn btn-primary" id="model-new">${App.t("models_new")}</button>
        </div>
        <table>
          <thead><tr>
            <th>${App.t("field_name")}</th>
            <th>${App.t("field_provider")}</th>
            <th>${App.t("field_model_name")}</th>
            <th>${App.t("field_api_key")}</th>
            <th>${App.t("field_active")}</th>
            <th>${App.t("field_actions")}</th>
          </tr></thead>
          <tbody>
            ${items.map((m) => this.row(m)).join("")}
          </tbody>
        </table>
      </div>`;

    page.querySelector("#model-new").onclick = () => this.openForm();
    items.forEach((m) => {
      page.querySelector(`#m-test-${m.id}`).onclick = (e) => this.test(m.id, e.target);
      page.querySelector(`#m-edit-${m.id}`).onclick = () => this.openForm(m);
      page.querySelector(`#m-del-${m.id}`).onclick = () => this.remove(m.id);
      page.querySelector(`#m-act-${m.id}`).onclick = () => this.toggle(m);
    });
  },

  row(m) {
    const keyTag = m.api_key
      ? `<span class="tag tag-published">${App.t("api_key_set")}</span>`
      : `<span class="tag tag-draft">${App.t("api_key_empty")}</span>`;
    const actLabel = m.is_active ? App.t("action_disable") : App.t("action_enable");
    return `<tr>
      <td>${escapeHtml(m.name)}</td>
      <td>${escapeHtml(m.provider)}</td>
      <td>${escapeHtml(m.model_name)}</td>
      <td>${keyTag}</td>
      <td>${m.is_active ? "✓" : "—"}</td>
      <td><div class="row-actions">
        <button class="btn btn-sm" id="m-test-${m.id}">${App.t("action_test")}</button>
        <button class="btn btn-sm" id="m-act-${m.id}">${actLabel}</button>
        <button class="btn btn-sm" id="m-edit-${m.id}">${App.t("action_edit")}</button>
        <button class="btn btn-sm btn-danger" id="m-del-${m.id}">${App.t("action_delete")}</button>
      </div></td>
    </tr>`;
  },

  openForm(m = null) {
    const f = m || { name: "", provider: "openai", base_url: "", model_name: "", api_key: "", is_active: true };
    const mask = document.createElement("div");
    mask.className = "modal-mask";
    mask.innerHTML = `
      <div class="modal">
        <h2>${m ? App.t("action_edit") : App.t("models_new")}</h2>
        <div class="modal-body">
          <div class="form-grid">
            <div class="field"><label>${App.t("field_name")}</label><input id="f-name" value="${escapeAttr(f.name)}"></div>
            <div class="form-grid cols-2">
              <div class="field"><label>${App.t("field_provider")}</label><input id="f-provider" value="${escapeAttr(f.provider)}"></div>
              <div class="field"><label>${App.t("field_model_name")}</label><input id="f-model" value="${escapeAttr(f.model_name)}"></div>
            </div>
            <div class="field"><label>${App.t("field_base_url")}</label><input id="f-url" value="${escapeAttr(f.base_url)}"></div>
            <div class="field"><label>${App.t("field_api_key")}</label><input id="f-key" value="${escapeAttr(f.api_key)}"></div>
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn" id="f-cancel">${App.t("action_cancel")}</button>
          <button class="btn btn-primary" id="f-save">${App.t("action_save")}</button>
        </div>
      </div>`;
    document.body.appendChild(mask);
    mask.querySelector("#f-cancel").onclick = () => mask.remove();
    mask.querySelector("#f-save").onclick = async () => {
      const payload = {
        name: mask.querySelector("#f-name").value.trim(),
        provider: mask.querySelector("#f-provider").value.trim(),
        model_name: mask.querySelector("#f-model").value.trim(),
        base_url: mask.querySelector("#f-url").value.trim(),
        api_key: mask.querySelector("#f-key").value,
        config_type: "chat",
        dimensions: null,
        is_active: f.is_active,
      };
      if (m) await App.api("PUT", `/api/model-configs/${m.id}`, payload);
      else await App.api("POST", "/api/model-configs", payload);
      mask.remove();
      this.render();
    };
  },

  async test(id, btn) {
    const original = btn.textContent;
    btn.disabled = true;
    btn.textContent = App.t("testing");
    try {
      const res = await App.api("POST", `/api/model-configs/${id}/test`);
      this.showResult(res.ok, res.message);
    } catch (err) {
      this.showResult(false, err.message);
    } finally {
      btn.disabled = false;
      btn.textContent = original;
    }
  },

  showResult(ok, message) {
    const mask = document.createElement("div");
    mask.className = "modal-mask";
    const title = ok ? App.t("test_ok") : App.t("test_fail");
    mask.innerHTML = `
      <div class="modal" style="width:420px">
        <h2 style="color:${ok ? "#1a9e5a" : "#e5484d"}">${ok ? "✓" : "✕"} ${title}</h2>
        <div class="modal-body">
          <p style="font-size:13px;line-height:1.6;word-break:break-word">${escapeHtml(message)}</p>
        </div>
        <div class="modal-actions">
          <button class="btn btn-primary" id="r-ok">${App.t("action_close")}</button>
        </div>
      </div>`;
    document.body.appendChild(mask);
    mask.querySelector("#r-ok").onclick = () => mask.remove();
  },

  async toggle(m) {
    await App.api("PATCH", `/api/model-configs/${m.id}/active`, { is_active: !m.is_active });
    this.render();
  },

  async remove(id) {
    if (!confirm(App.t("confirm_delete"))) return;
    await App.api("DELETE", `/api/model-configs/${id}`);
    this.render();
  },
};
