// 知识库管理页：文档列表（搜索/标签筛选）+ 文档表单 + 检索调试 + 标签管理。
const KnowledgePage = {
  filterTagId: null,
  keyword: "",

  async render() {
    const page = document.getElementById("page-knowledge");
    const [docs, tags] = await Promise.all([
      App.api("GET", this.listUrl()),
      App.api("GET", "/api/tags"),
    ]);
    this.tags = tags;
    page.innerHTML = `
      <div class="list-page">
        <div class="list-head">
          <h2>${App.t("knowledge_title")}</h2>
          <div class="row-actions">
            <button class="btn" id="k-search-debug">${App.t("knowledge_search_debug")}</button>
            <button class="btn" id="k-upload">${App.t("knowledge_upload")}</button>
            <button class="btn btn-primary" id="k-new">${App.t("knowledge_new")}</button>
          </div>
        </div>
        <div class="k-toolbar">
          <input id="k-keyword" placeholder="${App.t("knowledge_search_ph")}" value="${escapeHtml(this.keyword)}">
          <select id="k-tag-filter">
            <option value="">${App.t("knowledge_all_tags")}</option>
            ${tags.map((t) => `<option value="${t.id}" ${t.id === this.filterTagId ? "selected" : ""}>${escapeHtml(t.name)}</option>`).join("")}
          </select>
          <button class="btn btn-sm" id="k-clear-filter">${App.t("knowledge_clear_filter")}</button>
          <button class="btn btn-sm" id="k-tags-manage">${App.t("knowledge_manage_tags")}</button>
        </div>
        <table>
          <thead><tr>
            <th>${App.t("field_name")}</th>
            <th>${App.t("knowledge_tags")}</th>
            <th>${App.t("knowledge_chunks")}</th>
            <th>${App.t("field_status")}</th>
            <th>${App.t("knowledge_expires")}</th>
            <th>${App.t("field_actions")}</th>
          </tr></thead>
          <tbody>${docs.length ? docs.map((d) => this.row(d)).join("") : this.emptyRow()}</tbody>
        </table>
      </div>`;

    page.querySelector("#k-new").onclick = () => this.openForm();
    page.querySelector("#k-upload").onclick = (e) => this.upload(e.currentTarget);
    page.querySelector("#k-search-debug").onclick = () => this.openSearchDebug();
    page.querySelector("#k-tags-manage").onclick = () => this.openTagManager();
    page.querySelector("#k-clear-filter").onclick = () => {
      this.keyword = "";
      this.filterTagId = null;
      this.render();
    };
    const kw = page.querySelector("#k-keyword");
    kw.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        this.keyword = kw.value.trim();
        this.render();
      }
    });
    page.querySelector("#k-tag-filter").onchange = (e) => {
      this.filterTagId = e.target.value ? parseInt(e.target.value, 10) : null;
      this.render();
    };
    docs.forEach((d) => {
      page.querySelector(`#k-edit-${d.id}`).onclick = () => this.openForm(d.id);
      page.querySelector(`#k-del-${d.id}`).onclick = () => this.remove(d.id);
      page.querySelector(`#k-reidx-${d.id}`).onclick = (e) => this.reindex(d.id, e.currentTarget);
    });
  },

  listUrl() {
    const params = new URLSearchParams();
    if (this.filterTagId) params.set("tag_id", this.filterTagId);
    if (this.keyword) params.set("keyword", this.keyword);
    const qs = params.toString();
    return qs ? `/api/documents?${qs}` : "/api/documents";
  },

  statusTag(status) {
    const map = {
      indexed: ["tag-published", "status_indexed"],
      failed: ["tag-danger", "status_failed"],
      pending: ["tag-draft", "status_pending"],
    };
    const [cls, key] = map[status] || map.pending;
    return `<span class="tag ${cls}">${App.t(key)}</span>`;
  },

  row(d) {
    const tagNames = (d.tags || [])
      .map((t) => `<span class="tag tag-soft">${escapeHtml(t.name)}</span>`)
      .join("") || `<span class="muted">—</span>`;
    const expires = d.expires_at ? d.expires_at.slice(0, 10) : App.t("knowledge_forever");
    const source = d.source ? `<div class="cell-sub">${escapeHtml(d.source)}</div>` : "";
    return `<tr>
      <td><div class="cell-title">${escapeHtml(d.name)}</div>${source}</td>
      <td><div class="tag-list">${tagNames}</div></td>
      <td>${d.chunk_count}</td>
      <td>${this.statusTag(d.status)}</td>
      <td>${expires}</td>
      <td><div class="row-actions">
        <button class="btn btn-sm" id="k-reidx-${d.id}">${App.t("knowledge_reindex")}</button>
        <button class="btn btn-sm" id="k-edit-${d.id}">${App.t("action_edit")}</button>
        <button class="btn btn-sm btn-danger" id="k-del-${d.id}">${App.t("action_delete")}</button>
      </div></td>
    </tr>`;
  },

  emptyRow() {
    return `<tr><td colspan="6">
      <div class="k-empty">
        <div class="k-empty-title">${App.t("knowledge_empty_title")}</div>
        <div class="muted">${App.t("knowledge_empty_desc")}</div>
      </div>
    </td></tr>`;
  },

  // PLACEHOLDER_FORM

  async openForm(id = null, initial = null) {
    const doc = id ? await App.api("GET", `/api/documents/${id}`) : null;
    const d = doc || initial || { name: "", source: "", version: "", content: "", file_type: "markdown", expires_at: null, tags: [] };
    const selectedTagIds = new Set((d.tags || []).map((t) => t.id));
    const tagSelect = this.renderTagSelect(selectedTagIds);
    const expiresVal = d.expires_at ? d.expires_at.slice(0, 10) : "";
    const chunksPreview = doc && doc.chunks && doc.chunks.length
      ? `<div class="field"><label>${App.t("knowledge_chunks_preview")}（${doc.chunks.length}）</label>
          <div class="chunk-list">${doc.chunks
            .map((c) => `<div class="chunk-item"><span class="chunk-title">${escapeHtml(c.source_title || "—")}</span>${escapeHtml(c.content)}</div>`)
            .join("")}</div></div>`
      : "";

    const mask = document.createElement("div");
    mask.className = "modal-mask";
    mask.innerHTML = `
      <div class="modal">
        <h2>${id ? App.t("action_edit") : App.t("knowledge_new")}</h2>
        <div class="modal-body">
          <div class="form-grid">
            <div class="field"><label>${App.t("field_name")}</label><input id="f-name" value="${escapeHtml(d.name)}"></div>
            <div class="form-grid cols-2">
              <div class="field"><label>${App.t("knowledge_source")}</label><input id="f-source" value="${escapeHtml(d.source)}"></div>
              <div class="field"><label>${App.t("knowledge_version")}</label><input id="f-version" value="${escapeHtml(d.version)}"></div>
            </div>
            <div class="field"><label>${App.t("knowledge_expires")}（${App.t("knowledge_expires_hint")}）</label><input id="f-expires" type="date" value="${expiresVal}"></div>
            <div class="field"><label>${App.t("knowledge_tags")}</label>${tagSelect}</div>
            <div class="field"><label>${App.t("knowledge_content")}</label><textarea id="f-content" rows="12">${escapeHtml(d.content)}</textarea></div>
            ${chunksPreview}
            <div id="f-error" class="form-error" hidden></div>
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn" id="f-cancel">${App.t("action_cancel")}</button>
          <button class="btn btn-primary" id="f-save">${App.t("action_save")}</button>
        </div>
      </div>`;
    document.body.appendChild(mask);
    mask.querySelector("#f-cancel").onclick = () => mask.remove();
    mask.onclick = (e) => {
      if (e.target === mask) mask.remove();
    };
    this.bindTagSelect(mask);
    mask.querySelector("#f-save").onclick = async (e) => {
      const error = mask.querySelector("#f-error");
      const expires = mask.querySelector("#f-expires").value;
      const payload = {
        name: mask.querySelector("#f-name").value.trim(),
        source: mask.querySelector("#f-source").value.trim(),
        version: mask.querySelector("#f-version").value.trim(),
        content: mask.querySelector("#f-content").value,
        file_type: d.file_type || "markdown",
        expires_at: expires ? `${expires}T00:00:00` : null,
        tag_ids: [...mask.querySelectorAll("#f-tags input:checked")].map((el) => parseInt(el.value, 10)),
      };
      if (!payload.name || !payload.content.trim()) {
        error.textContent = App.t("knowledge_required");
        error.hidden = false;
        return;
      }
      error.hidden = true;
      await this.withButtonLoading(e.currentTarget, App.t("action_save"), async () => {
        if (id) await App.api("PUT", `/api/documents/${id}`, payload);
        else await App.api("POST", "/api/documents", payload);
        mask.remove();
        this.render();
      });
    };
  },

  renderTagSelect(selectedTagIds) {
    if (!this.tags.length) return `<div class="muted">${App.t("knowledge_no_tags")}</div>`;
    const selectedNames = this.tags
      .filter((t) => selectedTagIds.has(t.id))
      .map((t) => t.name);
    const summary = selectedNames.length
      ? selectedNames.join("、")
      : App.t("knowledge_tag_select_placeholder");
    const options = this.tags
      .map(
        (t) => `<label class="multi-option"><input type="checkbox" value="${t.id}" data-name="${escapeHtml(t.name)}" ${selectedTagIds.has(t.id) ? "checked" : ""}> ${escapeHtml(t.name)}</label>`
      )
      .join("");
    return `<div class="tag-multiselect" id="f-tags">
      <button type="button" class="multi-trigger"><span>${escapeHtml(summary)}</span></button>
      <div class="multi-menu">${options}</div>
    </div>`;
  },

  bindTagSelect(root) {
    const box = root.querySelector("#f-tags");
    if (!box) return;
    const trigger = box.querySelector(".multi-trigger");
    const summary = trigger.querySelector("span");
    const update = () => {
      const names = [...box.querySelectorAll("input:checked")].map((el) => el.dataset.name);
      summary.textContent = names.length ? names.join("、") : App.t("knowledge_tag_select_placeholder");
    };
    trigger.onclick = () => box.classList.toggle("open");
    box.querySelectorAll("input").forEach((input) => input.addEventListener("change", update));
    root.querySelector(".modal-body").addEventListener("click", (e) => {
      if (!box.contains(e.target)) box.classList.remove("open");
    });
  },

  // PLACEHOLDER_ACTIONS

  upload(button) {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".txt,.md,.markdown";
    input.onchange = async () => {
      const file = input.files[0];
      if (!file) return;
      await this.withButtonLoading(button, App.t("knowledge_uploading"), async () => {
        const content = await file.text();
        this.openForm(null, {
          name: file.name,
          source: file.name,
          version: "",
          content,
          file_type: this.detectFileType(file.name),
          expires_at: null,
          tags: [],
        });
      });
    };
    input.click();
  },

  detectFileType(filename) {
    const name = (filename || "").toLowerCase();
    if (name.endsWith(".txt")) return "txt";
    return "markdown";
  },

  async reindex(id, button) {
    await this.withButtonLoading(button, App.t("knowledge_reindexing"), async () => {
      await App.api("POST", `/api/documents/${id}/reindex`);
      this.render();
    });
  },

  async remove(id) {
    if (!confirm(App.t("confirm_delete"))) return;
    await App.api("DELETE", `/api/documents/${id}`);
    this.render();
  },

  // PLACEHOLDER_DEBUG

  openSearchDebug() {
    const tagOpts = this.tags
      .map((t) => `<option value="${t.id}">${escapeHtml(t.name)}</option>`)
      .join("");
    const mask = document.createElement("div");
    mask.className = "modal-mask";
    mask.innerHTML = `
      <div class="modal">
        <h2>${App.t("knowledge_search_debug")}</h2>
        <div class="modal-body">
          <div class="form-grid">
            <div class="field"><label>${App.t("knowledge_query")}</label><input id="s-query"></div>
            <div class="form-grid cols-2">
              <div class="field"><label>${App.t("knowledge_tag_filter")}</label>
                <select id="s-tag"><option value="">${App.t("knowledge_all_tags")}</option>${tagOpts}</select></div>
              <div class="field"><label>${App.t("knowledge_retriever")}</label>
                <select id="s-retriever">
                  <option value="vector">${App.t("retriever_vector")}</option>
                  <option value="keyword">${App.t("retriever_keyword")}</option>
                  <option value="hybrid">${App.t("retriever_hybrid")}</option>
                </select></div>
              <div class="field"><label>top_k</label><input id="s-topk" type="number" value="3"></div>
            </div>
          </div>
          <div id="s-results" class="search-results"></div>
        </div>
        <div class="modal-actions">
          <button class="btn" id="s-close">${App.t("action_close")}</button>
          <button class="btn btn-primary" id="s-run">${App.t("knowledge_run_search")}</button>
        </div>
      </div>`;
    document.body.appendChild(mask);
    mask.querySelector("#s-close").onclick = () => mask.remove();
    mask.onclick = (e) => {
      if (e.target === mask) mask.remove();
    };
    mask.querySelector("#s-run").onclick = async (e) => {
      const query = mask.querySelector("#s-query").value.trim();
      if (!query) {
        mask.querySelector("#s-results").innerHTML = `<div class="chat-empty">${App.t("knowledge_query_required")}</div>`;
        return;
      }
      const tagVal = mask.querySelector("#s-tag").value;
      await this.withButtonLoading(e.currentTarget, App.t("testing"), async () => {
        const passages = await App.api("POST", "/api/knowledge/search", {
          query,
          tag_ids: tagVal ? [parseInt(tagVal, 10)] : [],
          retriever_type: mask.querySelector("#s-retriever").value,
          top_k: parseInt(mask.querySelector("#s-topk").value, 10) || 3,
        });
        const box = mask.querySelector("#s-results");
        box.innerHTML = passages.length
          ? passages
              .map((p) => this.searchHit(p))
              .join("")
          : `<div class="chat-empty">${App.t("knowledge_no_hit")}</div>`;
      });
    };
  },

  searchHit(p) {
    const title = p.source_title || p.title || "—";
    const docName = p.document_name || "—";
    const embeddingModel = p.embedding_model_name || "—";
    return `<div class="search-hit">
      <div class="hit-head">
        <div class="hit-title">
          <span>${escapeHtml(title)}</span>
          <small>${App.t("knowledge_document_name")}：${escapeHtml(docName)}</small>
          <small>${App.t("knowledge_embedding_model")}：${escapeHtml(embeddingModel)}</small>
        </div>
        <span class="hit-score">${Number(p.score).toFixed(4)}</span>
      </div>
      <div class="hit-body">${escapeHtml(p.content)}</div>
    </div>`;
  },

  // PLACEHOLDER_TAGS

  openTagManager() {
    const mask = document.createElement("div");
    mask.className = "modal-mask";
    const renderList = () =>
      this.tags
        .map(
          (t) => `<div class="tag-row"><span>${escapeHtml(t.name)}</span><button class="btn btn-sm btn-danger" data-del="${t.id}">${App.t("action_delete")}</button></div>`
        )
        .join("") || `<div class="chat-empty">${App.t("knowledge_no_tags")}</div>`;
    mask.innerHTML = `
      <div class="modal" style="width:420px">
        <h2>${App.t("knowledge_manage_tags")}</h2>
        <div class="modal-body">
          <div id="t-error" class="form-error" hidden></div>
          <div class="field"><label>${App.t("knowledge_new_tag")}</label>
            <div class="row-actions"><input id="t-name" style="flex:1"><button class="btn btn-primary" id="t-add">${App.t("knowledge_add_tag")}</button></div></div>
          <div id="t-list" class="tag-manage-list">${renderList()}</div>
        </div>
        <div class="modal-actions">
          <button class="btn btn-primary" id="t-close">${App.t("action_close")}</button>
        </div>
      </div>`;
    document.body.appendChild(mask);
    const refresh = async () => {
      this.tags = await App.api("GET", "/api/tags");
      mask.querySelector("#t-list").innerHTML = renderList();
      bind();
    };
    const bind = () => {
      mask.querySelectorAll("[data-del]").forEach((btn) => {
        btn.onclick = async () => {
          if (!confirm(App.t("confirm_delete"))) return;
          await App.api("DELETE", `/api/tags/${btn.dataset.del}`);
          await refresh();
        };
      });
    };
    const addTag = async () => {
      const name = mask.querySelector("#t-name").value.trim();
      if (!name) return;
      const error = mask.querySelector("#t-error");
      try {
        await App.api("POST", "/api/tags", { name });
      } catch (e) {
        error.textContent = e.message;
        error.hidden = false;
        return;
      }
      error.hidden = true;
      mask.querySelector("#t-name").value = "";
      await refresh();
    };
    mask.querySelector("#t-add").onclick = addTag;
    mask.querySelector("#t-name").addEventListener("keydown", (e) => {
      if (e.key === "Enter") addTag();
    });
    mask.querySelector("#t-close").onclick = () => {
      mask.remove();
      this.render();
    };
    bind();
  },

  async withButtonLoading(button, text, fn) {
    if (!button) return fn();
    const oldText = button.textContent;
    button.disabled = true;
    button.textContent = text;
    try {
      return await fn();
    } catch (e) {
      alert(e.message);
    } finally {
      button.disabled = false;
      button.textContent = oldText;
    }
  },
};
