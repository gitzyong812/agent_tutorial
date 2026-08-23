// 对话页：会话列表 + 流式对话。
const ChatPage = {
  currentId: null,

  async render() {
    const page = document.getElementById("page-chat");
    const [sessions, published, agents, models] = await Promise.all([
      App.api("GET", "/api/conversations"),
      App.api("GET", "/api/agents?status=published"),
      App.api("GET", "/api/agents"),
      App.api("GET", "/api/model-configs"),
    ]);
    this.published = published;
    this.sessions = sessions;
    // 建立查找表：agent_config_id -> {名称, 模型名}
    const modelName = {};
    models.forEach((m) => (modelName[m.id] = m.model_name));
    this.agentInfo = {};
    agents.forEach((a) => (this.agentInfo[a.id] = {
      name: a.name,
      model_name: modelName[a.model_config_id] || "",
    }));
    page.innerHTML = `
      <div class="chat-page">
        <div class="chat-sessions">
          <div class="sessions-head">
            <button class="btn btn-primary" id="c-new" style="width:100%">${App.t("chat_new")}</button>
          </div>
          <div class="session-list" id="session-list">
            ${sessions.map((s) => this.sessionItem(s)).join("")}
          </div>
        </div>
        <div class="chat-main" id="chat-main"></div>
      </div>`;

    page.querySelector("#c-new").onclick = () => this.openNewSession();
    sessions.forEach((s) => {
      page.querySelector(`#s-${s.id}`).onclick = () => this.openSession(s.id);
      page.querySelector(`#sd-${s.id}`).onclick = (e) => {
        e.stopPropagation();
        this.removeSession(s.id);
      };
    });

    if (this.currentId && sessions.some((s) => s.id === this.currentId)) {
      this.openSession(this.currentId);
    } else {
      this.currentId = null;
      this.renderEmpty();
    }
  },

  sessionItem(s) {
    const active = s.id === this.currentId ? "active" : "";
    const info = (this.agentInfo || {})[s.agent_config_id];
    const meta = info
      ? `<span class="session-meta">${escapeHtml(info.name)}（${escapeHtml(info.model_name)}）</span>`
      : "";
    return `<div class="session-item ${active}" id="s-${s.id}">
      <div class="session-info">
        ${meta}
        <span class="title">${escapeHtml(s.title || App.t("chat_new"))}</span>
      </div>
      <button class="del" id="sd-${s.id}">×</button>
    </div>`;
  },

  renderEmpty() {
    document.getElementById("chat-main").innerHTML =
      `<div class="chat-empty">${App.t("chat_empty")}</div>`;
  },

  openNewSession() {
    const main = document.getElementById("chat-main");
    if (!this.published.length) {
      main.innerHTML = `<div class="chat-empty">${App.t("chat_no_published")}</div>`;
      return;
    }
    const opts = this.published
      .map((a) => `<option value="${a.id}">${escapeHtml(a.name)}</option>`)
      .join("");
    main.innerHTML = `
      <div class="new-session-form">
        <h2>${App.t("chat_new")}</h2>
        <div class="field"><label>${App.t("chat_select_agent")}</label>
          <select id="ns-agent">${opts}</select></div>
        <div class="field"><label>${App.t("chat_answer_lang")}</label>
          <select id="ns-lang">
            <option value="zh">中文</option>
            <option value="en">English</option>
            <option value="ru">Русский</option>
          </select></div>
        <button class="btn btn-primary" id="ns-start">${App.t("chat_start")}</button>
      </div>`;
    main.querySelector("#ns-lang").value = App.lang;
    main.querySelector("#ns-start").onclick = async () => {
      const session = await App.api("POST", "/api/conversations", {
        agent_config_id: parseInt(main.querySelector("#ns-agent").value, 10),
        language: main.querySelector("#ns-lang").value,
      });
      this.currentId = session.id;
      await this.render();
    };
  },

  async openSession(id) {
    this.currentId = id;
    document.querySelectorAll(".session-item").forEach((el) =>
      el.classList.toggle("active", el.id === `s-${id}`)
    );
    const messages = await App.api("GET", `/api/conversations/${id}/messages`);
    const main = document.getElementById("chat-main");
    const session = (this.sessions || []).find((s) => s.id === id);
    const info = session && (this.agentInfo || {})[session.agent_config_id];
    const header = info
      ? `<div class="chat-header">
          <span class="chat-header-name">${escapeHtml(info.name)}</span>
          <span class="chat-header-model">${escapeHtml(info.model_name)}</span>
        </div>`
      : "";
    main.innerHTML = `
      ${header}
      <div class="chat-messages" id="msgs">
        ${messages.map((m) => this.bubble(m.role, m.content)).join("")}
      </div>
      <div class="chat-input-bar">
        <textarea id="chat-input" placeholder="${App.t("chat_input_placeholder")}"></textarea>
        <button class="btn btn-primary" id="chat-send">${App.t("chat_send")}</button>
      </div>`;
    const input = main.querySelector("#chat-input");
    const send = () => this.send();
    main.querySelector("#chat-send").onclick = send;
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        send();
      }
    });
    this.scrollDown();
  },

  bubble(role, content) {
    return `<div class="msg ${role}">${escapeHtml(content)}</div>`;
  },

  scrollDown() {
    const box = document.getElementById("msgs");
    if (box) box.scrollTop = box.scrollHeight;
  },

  async send() {
    const input = document.getElementById("chat-input");
    const text = input.value.trim();
    if (!text) return;
    input.value = "";

    const box = document.getElementById("msgs");
    box.insertAdjacentHTML("beforeend", this.bubble("user", text));
    // 助手气泡，边接收边填充
    const holder = document.createElement("div");
    holder.className = "msg assistant";
    holder.textContent = App.t("chat_thinking");
    box.appendChild(holder);
    this.scrollDown();

    try {
      const res = await fetch(`/api/conversations/${this.currentId}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: text }),
      });
      await this.consumeStream(res, holder);
    } catch (err) {
      holder.textContent = `⚠ ${err.message}`;
    }
    // 首轮对话后标题会更新，刷新左侧列表
    this.refreshSessionTitles();
  },

  // 解析 SSE 流，逐块渲染
  async consumeStream(res, holder) {
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let answer = "";
    let started = false;

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split("\n\n");
      buffer = events.pop();
      for (const evt of events) {
        if (evt.startsWith("event: error")) {
          const data = evt.split("data: ")[1] || "";
          holder.textContent = `⚠ ${this.decode(data)}`;
          return;
        }
        if (evt.startsWith("event: done")) return;
        if (evt.startsWith("data: ")) {
          if (!started) {
            holder.textContent = "";
            started = true;
          }
          answer += this.decode(evt.slice(6));
          holder.textContent = answer;
          this.scrollDown();
        }
      }
    }
  },

  // 还原后端转义的换行
  decode(s) {
    return s.replace(/\\n/g, "\n").replace(/\\\\/g, "\\");
  },

  async refreshSessionTitles() {
    const sessions = await App.api("GET", "/api/conversations");
    this.sessions = sessions;
    const list = document.getElementById("session-list");
    if (!list) return;
    list.innerHTML = sessions.map((s) => this.sessionItem(s)).join("");
    sessions.forEach((s) => {
      list.querySelector(`#s-${s.id}`).onclick = () => this.openSession(s.id);
      list.querySelector(`#sd-${s.id}`).onclick = (e) => {
        e.stopPropagation();
        this.removeSession(s.id);
      };
    });
  },

  async removeSession(id) {
    if (!confirm(App.t("confirm_delete"))) return;
    await App.api("DELETE", `/api/conversations/${id}`);
    if (this.currentId === id) this.currentId = null;
    this.render();
  },
};
