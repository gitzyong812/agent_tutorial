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
    // 建立查找表：agent_config_id -> {名称, 类型, 模型名}
    const modelName = {};
    models.forEach((m) => (modelName[m.id] = m.model_name));
    this.agentInfo = {};
    agents.forEach((a) => (this.agentInfo[a.id] = {
      name: a.name,
      agent_type: a.agent_type,
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
    const typeLabel = this.typeLabel(info && info.agent_type);
    const meta = info
      ? `<span class="session-meta">${escapeHtml(info.name)}（${escapeHtml(typeLabel)} · ${escapeHtml(info.model_name)}）</span>`
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
    const typeLabel = this.typeLabel(info && info.agent_type);
    const header = info
      ? `<div class="chat-header">
          <span class="chat-header-name">${escapeHtml(info.name)}</span>
          <span class="chat-header-model">${escapeHtml(typeLabel)} · ${escapeHtml(info.model_name)}</span>
        </div>`
      : "";
    main.innerHTML = `
      ${header}
      <div class="chat-messages" id="msgs">
        ${messages.map((m) => this.bubble(m.role, m.content, m.extra?.rag_sources, m.extra?.agent_trace)).join("")}
      </div>
      <div class="chat-input-bar">
        <textarea id="chat-input" placeholder="${App.t("chat_input_placeholder")}"></textarea>
        <button class="btn btn-primary" id="chat-send">${App.t("chat_send")}</button>
      </div>`;
    const input = main.querySelector("#chat-input");
    const send = () => this.send();
    main.querySelector("#chat-send").onclick = send;
    main.querySelector("#msgs").onclick = (e) => {
      const btn = e.target.closest(".msg-copy");
      if (btn) this.copyMessage(btn);
    };
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        send();
      }
    });
    this.scrollDown();
  },

  typeLabel(type) {
    if (type === "rag_chatbot") return App.t("agent_type_rag");
    if (type === "react_agent") return App.t("agent_type_react");
    return App.t("agent_type_chatbot");
  },

  bubble(role, content, sources, trace) {
    if (role !== "assistant") {
      return `<div class="msg ${role}">${this.bubbleInner(role, content, sources, trace)}</div>`;
    }
    return `<div class="msg-wrap assistant-wrap">
      <div class="msg assistant" data-raw="${escapeAttr(content)}">${this.bubbleInner(role, content, sources, trace)}</div>
      ${this.copyActionHtml()}
    </div>`;
  },

  bubbleInner(role, content, sources, trace) {
    const body = role === "assistant" ? renderMarkdown(content) : escapeHtml(content);
    return `${this.traceHtml(trace)}<div class="msg-content">${body}</div>${this.sourcesHtml(sources)}`;
  },

  copyActionHtml() {
    return `<div class="msg-actions"><button type="button" class="msg-copy" title="${App.t("chat_copy")}">${App.t("chat_copy")}</button></div>`;
  },

  sourcesHtml(sources) {
    if (!sources || !sources.length) return "";
    return `<details class="sources"><summary>${App.t("chat_sources")}（${sources.length}）</summary>${sources
      .map((p, i) => {
        const title = p.source_title || "—";
        const docName = p.document_name || "—";
        return `<div class="src-item">
          <span class="src-label">[资料${i + 1}] ${escapeHtml(title)}</span>
          <span class="src-doc">${App.t("chat_source_document")}：${escapeHtml(docName)}</span>
          <p>${escapeHtml(p.content)}</p>
        </div>`;
      })
      .join("")}</details>`;
  },

  traceHtml(trace) {
    if (!trace || !trace.length) return "";
    const phaseByType = { thought: "thought", tool_call: "execution" };
    return `<details class="agent-trace"><summary>${App.t("chat_trace")}（${trace.length}）</summary>${trace.map((item) => {
      const isError = ["tool_error", "run_error"].includes(item.type);
      const phase = phaseByType[item.type] || "observation";
      const label = App.t(`chat_trace_${isError ? "error" : item.type === "tool_call" ? "call" : "result"}`);
      const tool = item.tool ? ` · ${escapeHtml(item.tool)}` : "";
      const detail = item.type === "thought" ? "" : `<strong>${escapeHtml(label)}${tool}</strong>`;
      const value = item.type === "thought"
        ? `<div class="trace-content">${escapeHtml(item.content || "")}</div>`
        : `<pre>${escapeHtml(JSON.stringify(item.arguments !== undefined ? item.arguments : item.result, null, 2))}</pre>`;
      return `<div class="trace-item ${phase}${isError ? " trace-error" : ""}"><div class="trace-head"><span class="trace-phase">${App.t(`chat_trace_${phase}`)}</span>${detail}</div>${value}</div>`;
    }).join("")}</details>`;
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
    const wrap = document.createElement("div");
    wrap.className = "msg-wrap assistant-wrap";
    const holder = document.createElement("div");
    holder.className = "msg assistant";
    holder.dataset.raw = "";
    holder.innerHTML = this.bubbleInner("assistant", App.t("chat_thinking"));
    wrap.appendChild(holder);
    wrap.insertAdjacentHTML("beforeend", this.copyActionHtml());
    box.appendChild(wrap);
    this.scrollDown();

    try {
      const res = await fetch(`/api/conversations/${this.currentId}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: text }),
      });
      if (!res.ok) {
        const error = await res.json().catch(() => ({}));
        throw new Error(error.detail || res.statusText);
      }
      if (!res.body) throw new Error("当前浏览器不支持流式响应");
      await this.consumeStream(res, holder);
    } catch (err) {
      holder.textContent = `⚠ ${err.message}`;
    }
    // 首轮对话后标题会更新，刷新左侧列表
    this.refreshSessionTitles();
  },

  // 解析 SSE 流，逐块渲染；处理 sources 事件（检索依据）
  async consumeStream(res, holder) {
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let answer = "";
    let sources = null;
    let trace = [];

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      buffer = buffer.replace(/\r\n/g, "\n");
      const events = buffer.split("\n\n");
      buffer = events.pop();
      for (const evt of events) {
        const parsed = parseSseEvent(evt);
        if (parsed.event === "error") {
          const data = parsed.data || "";
          holder.textContent = `⚠ ${this.decode(data)}`;
          return;
        }
        if (parsed.event === "done") {
          this.renderAssistant(holder, answer, sources, trace);
          return;
        }
        if (parsed.event === "sources") {
          try {
            sources = JSON.parse(parsed.data);
            this.renderAssistant(holder, answer || App.t("chat_thinking"), sources, trace);
          } catch (_) {
            sources = null;
          }
          continue;
        }
        if (parsed.event === "trace") {
          try {
            trace.push(JSON.parse(parsed.data));
            this.renderAssistant(holder, answer || App.t("chat_thinking"), sources, trace);
          } catch (_) {
            // 单条轨迹格式异常不应中断最终回答。
          }
          continue;
        }
        if (parsed.data !== null) {
          answer += this.decode(parsed.data);
          this.renderAssistant(holder, answer, sources, trace);
          this.scrollDown();
        }
      }
    }
    this.renderAssistant(holder, answer, sources, trace);
  },

  renderAssistant(holder, content, sources, trace) {
    const raw = content === App.t("chat_thinking") ? "" : content;
    holder.dataset.raw = raw;
    holder.innerHTML = this.bubbleInner("assistant", content, sources, trace);
  },

  // 还原后端转义的换行
  decode(s) {
    return s.replace(/\\n/g, "\n").replace(/\\\\/g, "\\");
  },

  async copyMessage(btn) {
    const wrap = btn.closest(".assistant-wrap");
    const msg = wrap ? wrap.querySelector(".msg.assistant") : null;
    const text = msg ? msg.dataset.raw || "" : "";
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
    } catch (_) {
      return;
    }
    const oldText = btn.textContent;
    btn.textContent = App.t("chat_copied");
    setTimeout(() => {
      btn.textContent = oldText;
    }, 1200);
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

// Markdown 渲染交给 marked，DOMPurify 负责清洗生成的 HTML。
function renderMarkdown(text) {
  const source = text || "";
  if (!globalThis.marked || !globalThis.marked.parse) {
    return `<p>${escapeHtml(source).replace(/\n/g, "<br>")}</p>`;
  }
  const html = globalThis.marked.parse(source, { gfm: true, breaks: true });
  return globalThis.DOMPurify ? globalThis.DOMPurify.sanitize(html) : html;
}

function parseSseEvent(evt) {
  const result = { event: "message", data: null };
  evt.split(/\r?\n/).forEach((line) => {
    if (line.startsWith("event:")) result.event = line.slice(6).trim();
    if (line.startsWith("data:")) {
      const data = line.startsWith("data: ") ? line.slice(6) : line.slice(5);
      result.data = (result.data || "") + data;
    }
  });
  return result;
}
