// 对话页：会话列表 + 流式对话。
const ChatPage = {
  currentId: null,
  channelPollTimer: null,
  channelQrImage: "",

  async render() {
    this.stopChannelPoll();
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
    this.stopChannelPoll();
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
    this.stopChannelPoll();
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
          <div class="chat-header-info">
            <span class="chat-header-name">${escapeHtml(info.name)}</span>
            <span class="chat-header-model">${escapeHtml(typeLabel)} · ${escapeHtml(info.model_name)}</span>
          </div>
          <button class="btn btn-sm chat-channel-button" id="chat-channels">🔗 ${App.t("chat_channels")}</button>
        </div>`
      : "";
    main.innerHTML = `
      ${header}
      <div class="chat-messages" id="msgs">
        ${messages.map((m) => this.bubble(m.role, m.content, m.extra?.rag_sources, m.extra?.agent_trace, m.extra?.human_request)).join("")}
      </div>
      <div class="chat-input-bar">
        <textarea id="chat-input" placeholder="${App.t("chat_input_placeholder")}"></textarea>
        <button class="btn btn-primary" id="chat-send">${App.t("chat_send")}</button>
      </div>`;
    const input = main.querySelector("#chat-input");
    const send = () => this.send();
    main.querySelector("#chat-send").onclick = send;
    const channelButton = main.querySelector("#chat-channels");
    if (channelButton) {
      channelButton.onclick = () => this.openChannelModal(session, info);
      this.refreshChannelHeader(id);
    }
    main.querySelector("#msgs").onclick = (e) => {
      const response = e.target.closest("[data-human-answer]");
      if (response) {
        this.answerHumanRequest(response);
        return;
      }
      const btn = e.target.closest(".msg-copy");
      if (btn) this.copyMessage(btn);
    };
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        send();
      }
    });
    const lastMessage = messages[messages.length - 1];
    this.setComposerDisabled(lastMessage?.extra?.execution_status === "pending");
    this.scrollDown();
  },

  typeLabel(type) {
    if (type === "rag_chatbot") return App.t("agent_type_rag");
    if (type === "react_agent") return App.t("agent_type_react");
    return App.t("agent_type_chatbot");
  },

  bubble(role, content, sources, trace, humanRequest) {
    if (role !== "assistant") {
      return `<div class="msg ${role}">${this.bubbleInner(role, content, sources, trace, humanRequest)}</div>`;
    }
    return `<div class="msg-wrap assistant-wrap">
      <div class="msg assistant" data-raw="${escapeAttr(content)}">${this.bubbleInner(role, content, sources, trace, humanRequest)}</div>
      ${this.copyActionHtml()}
    </div>`;
  },

  bubbleInner(role, content, sources, trace, humanRequest) {
    const body = role === "assistant" ? renderMarkdown(content) : escapeHtml(content);
    return `${this.traceHtml(trace)}<div class="msg-content">${body}</div>${this.humanRequestHtml(humanRequest)}${this.sourcesHtml(sources)}`;
  },

  humanRequestHtml(request) {
    if (!request || request.status !== "pending") return "";
    const prompt = `<p>${escapeHtml(request.prompt || "")}</p>`;
    if (request.kind === "tool_approval") {
      return `<div class="approval-card" data-request-kind="tool_approval" data-request-id="${request.request_id}">
        <strong>${App.t("approval_title")}</strong>${prompt}
        <pre>${escapeHtml(JSON.stringify(request.arguments || {}, null, 2))}</pre>
        <div class="row-actions">
          <button class="btn btn-sm btn-primary" data-human-answer="approve">${App.t("approval_approve")}</button>
          <button class="btn btn-sm" data-human-answer="reject">${App.t("approval_reject")}</button>
        </div>
      </div>`;
    }
    if (request.input_type === "confirm") {
      return `<div class="approval-card" data-request-kind="ask_human" data-request-id="${request.request_id}">
        <strong>${App.t("human_input_title")}</strong>${prompt}
        <div class="row-actions">
          <button class="btn btn-sm btn-primary" data-human-answer="yes">${App.t("human_yes")}</button>
          <button class="btn btn-sm" data-human-answer="no">${App.t("human_no")}</button>
        </div>
      </div>`;
    }
    return `<div class="approval-card" data-request-kind="ask_human" data-request-id="${request.request_id}">
      <strong>${App.t("human_input_title")}</strong>${prompt}
      <textarea class="human-text-input" rows="3"></textarea>
      <div class="row-actions"><button class="btn btn-sm btn-primary" data-human-answer="text">${App.t("human_submit")}</button></div>
    </div>`;
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
    const hiddenTypes = new Set([
      "human_requested", "human_answer", "approval_requested", "approval_decision",
    ]);
    const visibleTrace = trace.filter((item) => !hiddenTypes.has(item.type));
    if (!visibleTrace.length) return "";
    const phaseByType = { thought: "thought", tool_call: "execution", skill_activated: "execution" };
    return `<details class="agent-trace"><summary>${App.t("chat_trace")}（${visibleTrace.length}）</summary>${visibleTrace.map((item) => {
      const isError = ["tool_error", "run_error"].includes(item.type);
      const phase = phaseByType[item.type] || "observation";
      const labelKey = item.type === "skill_activated"
        ? "skill_activated"
        : isError ? "error" : item.type === "tool_call" ? "call" : "result";
      const label = App.t(`chat_trace_${labelKey}`);
      const subject = item.tool || (item.type === "skill_activated" ? item.skill : "");
      const tool = subject ? ` · ${escapeHtml(subject)}` : "";
      const detail = item.type === "thought" ? "" : `<strong>${escapeHtml(label)}${tool}</strong>`;
      const payload = item.arguments !== undefined ? item.arguments : item.result;
      let value = "";
      if (item.type === "thought") {
        value = `<div class="trace-content">${escapeHtml(item.content || "")}</div>`;
      } else if (item.type === "tool_call" && item.tool === "create_skill" && item.arguments?.document_chars !== undefined) {
        const summary = App.t("chat_trace_skill_document_hidden")
          .replace("{count}", String(item.arguments.document_chars));
        value = `<div class="trace-content">${escapeHtml(summary)}</div>`;
      } else if (payload !== undefined) {
        value = `<pre>${escapeHtml(JSON.stringify(payload, null, 2))}</pre>`;
      }
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
    holder._answer = "";
    holder._sources = null;
    holder._trace = [];
    holder._humanRequest = null;
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
      this.setComposerDisabled(false);
    }
    // 首轮对话后标题会更新，刷新左侧列表
    this.refreshSessionTitles();
  },

  // 解析 SSE 流，逐块渲染；处理 sources 事件（检索依据）
  async consumeStream(res, holder) {
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let answer = holder._answer || "";
    let sources = holder._sources || null;
    let trace = holder._trace || [];
    let humanRequest = holder._humanRequest || null;

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      buffer = buffer.replace(/\r\n/g, "\n");
      const events = buffer.split("\n\n");
      buffer = events.pop();
      for (const evt of events) {
        const message = parseSseEvent(evt);
        if (!message) continue;
        if (message.type === "error") {
          holder.textContent = `⚠ ${message.payload?.message || ""}`;
          this.setComposerDisabled(false);
          return;
        }
        if (message.type === "done") {
          this.renderAssistant(holder, answer, sources, trace, humanRequest);
          this.setComposerDisabled(message.payload?.status === "pending");
          return;
        }
        if (message.type === "sources") {
          sources = message.payload?.items || [];
          this.renderAssistant(holder, answer || App.t("chat_thinking"), sources, trace, humanRequest);
          continue;
        }
        if (message.type === "trace") {
          if (message.payload?.item) trace.push(message.payload.item);
          this.renderAssistant(holder, answer || App.t("chat_thinking"), sources, trace, humanRequest);
          continue;
        }
        if (message.type === "human_required") {
          humanRequest = message.payload;
          this.renderAssistant(holder, answer || App.t("approval_waiting"), sources, trace, humanRequest);
          this.setComposerDisabled(true);
          continue;
        }
        if (message.type === "text_delta") {
          answer += message.payload?.content || "";
          this.renderAssistant(holder, answer, sources, trace, humanRequest);
          this.scrollDown();
        }
      }
    }
    this.renderAssistant(holder, answer, sources, trace, humanRequest);
  },

  renderAssistant(holder, content, sources, trace, humanRequest) {
    const raw = content === App.t("chat_thinking") ? "" : content;
    holder.dataset.raw = raw;
    holder._answer = raw;
    holder._sources = sources;
    holder._trace = trace;
    holder._humanRequest = humanRequest;
    holder.innerHTML = this.bubbleInner("assistant", content, sources, trace, humanRequest);
  },

  async answerHumanRequest(button) {
    const card = button.closest(".approval-card");
    const holder = button.closest(".msg.assistant");
    if (!card || !holder) return;
    card.querySelectorAll("button").forEach((item) => (item.disabled = true));
    try {
      const kind = card.dataset.requestKind;
      let answer = button.dataset.humanAnswer;
      let url = `/api/human-requests/${card.dataset.requestId}/answer`;
      let body = { answer, channel: "web", sender_id: "browser-user" };
      if (kind === "tool_approval") {
        url = `/api/approvals/${card.dataset.requestId}/decision`;
        body = { decision: answer, channel: "web", sender_id: "browser-user" };
      } else if (answer === "text") {
        answer = card.querySelector(".human-text-input").value.trim();
        if (!answer) throw new Error(App.t("human_text_required"));
        body.answer = answer;
      }
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const error = await res.json().catch(() => ({}));
        throw new Error(error.detail || res.statusText);
      }
      holder._answer = "";
      holder._humanRequest = null;
      await this.consumeStream(res, holder);
      await this.openSession(this.currentId);
    } catch (err) {
      alert(err.message);
      card.querySelectorAll("button").forEach((item) => (item.disabled = false));
    }
  },

  setComposerDisabled(disabled) {
    const input = document.getElementById("chat-input");
    const send = document.getElementById("chat-send");
    if (input) input.disabled = disabled;
    if (send) send.disabled = disabled;
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

  stopChannelPoll() {
    if (this.channelPollTimer) {
      clearTimeout(this.channelPollTimer);
      this.channelPollTimer = null;
    }
  },

  async refreshChannelHeader(sessionId) {
    const button = document.getElementById("chat-channels");
    if (!button || this.currentId !== sessionId) return;
    try {
      const channels = await App.api("GET", `/api/conversations/${sessionId}/channels`);
      if (!button.isConnected || this.currentId !== sessionId) return;
      const weixin = channels.find((item) => item.channel === "weixin");
      const connected = weixin?.status === "connected";
      button.classList.toggle("connected", connected);
      button.textContent = connected
        ? `✓ ${App.t("chat_channels")}`
        : `🔗 ${App.t("chat_channels")}`;
    } catch (_) {
      // 通道状态不影响网页对话。
    }
  },

  async openChannelModal(session, info) {
    this.stopChannelPoll();
    this.channelQrImage = "";
    const mask = document.createElement("div");
    mask.className = "modal-mask";
    const description = App.t("chat_channels_desc").replace("{agent}", info?.name || "");
    const cliCommand = `python -m app.cli --session-id ${session.id} --base-url ${window.location.origin}`;
    mask.innerHTML = `<div class="modal channel-modal">
      <h2>${App.t("chat_channels_title")}</h2>
      <div class="modal-body">
        <p class="channel-dialog-desc">${escapeHtml(description)}</p>
        <div class="channel-card">
          <div class="channel-card-head">
            <div class="channel-logo cli">CLI</div>
            <div><strong>${App.t("channel_cli")}</strong><p>${App.t("channel_cli_desc")}</p></div>
            <button class="btn btn-sm channel-card-action" id="channel-cli-show">${App.t("channel_cli_show")}</button>
          </div>
          <div id="cli-channel-panel" class="channel-panel channel-cli-panel" hidden>
            <p>${App.t("channel_cli_command")}</p>
            <div class="channel-command">
              <code>${escapeHtml(cliCommand)}</code>
              <button class="btn btn-sm" id="channel-cli-copy" data-command="${escapeAttr(cliCommand)}">${App.t("channel_cli_copy")}</button>
            </div>
            <p class="muted">${App.t("channel_cli_note")}</p>
          </div>
        </div>
        <div class="channel-card">
          <div class="channel-card-head">
            <div class="channel-logo">微</div>
            <div><strong>${App.t("channel_weixin")}</strong><p>${App.t("channel_weixin_desc")}</p></div>
          </div>
          <div id="weixin-channel-panel" class="channel-panel"></div>
        </div>
      </div>
      <div class="modal-actions"><button class="btn" id="channel-close">${App.t("action_close")}</button></div>
    </div>`;
    document.body.appendChild(mask);
    const close = () => {
      this.stopChannelPoll();
      mask.remove();
    };
    mask.querySelector("#channel-close").onclick = close;
    mask.addEventListener("click", (event) => {
      if (event.target === mask) close();
    });
    mask.querySelector("#channel-cli-show").onclick = () => {
      mask.querySelector("#cli-channel-panel").hidden = false;
      mask.querySelector("#channel-cli-show").hidden = true;
    };
    mask.querySelector("#channel-cli-copy").onclick = (event) => this.copyCliCommand(event.currentTarget);

    this.renderChannelLoading(mask);
    try {
      const channels = await App.api("GET", `/api/conversations/${session.id}/channels`);
      if (!mask.isConnected) return;
      const weixin = channels.find((item) => item.channel === "weixin");
      if (!weixin) {
        this.renderWeixinDisconnected(mask, session.id);
      } else {
        this.renderWeixinState(mask, session.id, weixin);
      }
    } catch (err) {
      this.renderWeixinError(mask, session.id, err.message);
    }
  },

  renderChannelLoading(mask) {
    const panel = mask.querySelector("#weixin-channel-panel");
    if (panel) panel.innerHTML = `<p class="channel-status muted">${App.t("channel_loading")}</p>`;
  },

  renderWeixinDisconnected(mask, sessionId, message = App.t("channel_weixin_desc")) {
    const panel = mask.querySelector("#weixin-channel-panel");
    if (!panel) return;
    panel.innerHTML = `<div class="channel-disconnected">
      <p>${escapeHtml(message)}</p>
      <button class="btn btn-sm btn-primary" id="channel-connect">${App.t("channel_connect")}</button>
    </div>`;
    panel.querySelector("#channel-connect").onclick = () => this.startWeixinQr(mask, sessionId);
  },

  async copyCliCommand(button) {
    try {
      await navigator.clipboard.writeText(button.dataset.command);
    } catch (_) {
      return;
    }
    button.textContent = App.t("channel_cli_copied");
  },

  async startWeixinQr(mask, sessionId) {
    this.stopChannelPoll();
    this.renderChannelLoading(mask);
    try {
      const state = await App.api("POST", `/api/conversations/${sessionId}/channels/weixin/qr`);
      if (mask.isConnected) this.renderWeixinState(mask, sessionId, state);
    } catch (err) {
      this.renderWeixinError(mask, sessionId, err.message);
    }
  },

  renderWeixinState(mask, sessionId, state) {
    if (!mask.isConnected) return;
    const panel = mask.querySelector("#weixin-channel-panel");
    if (!panel) return;
    if (state.qr_image) this.channelQrImage = state.qr_image;
    if (state.status === "connected") {
      this.stopChannelPoll();
      panel.innerHTML = `<div class="channel-connected">
        <span class="channel-success-icon">✓</span>
        <strong>${App.t("channel_weixin_connected")}</strong>
        <p>${App.t("channel_weixin_connected_desc")}</p>
        <div class="row-actions">
          <button class="btn btn-sm" id="channel-reconnect">${App.t("channel_reconnect")}</button>
          <button class="btn btn-sm btn-danger" id="channel-disconnect">${App.t("channel_disconnect")}</button>
        </div>
      </div>`;
      panel.querySelector("#channel-reconnect").onclick = () => this.startWeixinQr(mask, sessionId);
      panel.querySelector("#channel-disconnect").onclick = () => this.disconnectWeixin(mask, sessionId);
      this.refreshChannelHeader(sessionId);
      return;
    }
    if (["reauth_required", "error"].includes(state.status)) {
      this.renderWeixinError(mask, sessionId, state.last_error || App.t("channel_error"));
      return;
    }

    const statusText = state.status === "scanned"
      ? App.t("channel_scanned")
      : App.t("channel_waiting_scan");
    panel.innerHTML = `<div class="channel-qr">
      <p class="channel-scan-desc">${App.t("channel_scan_desc")}</p>
      ${this.channelQrImage ? `<div class="channel-qr-frame"><img src="${escapeAttr(this.channelQrImage)}" alt="QR Code" /></div>` : ""}
      <strong class="channel-status ${state.status === "scanned" ? "scanned" : ""}">${statusText}</strong>
      <p class="muted">${App.t("channel_qr_tip")}</p>
    </div>`;
    this.scheduleWeixinPoll(mask, sessionId);
  },

  scheduleWeixinPoll(mask, sessionId) {
    this.stopChannelPoll();
    this.channelPollTimer = setTimeout(async () => {
      this.channelPollTimer = null;
      if (!mask.isConnected || this.currentId !== sessionId) return;
      try {
        const state = await App.api("POST", `/api/conversations/${sessionId}/channels/weixin/qr/poll`);
        this.renderWeixinState(mask, sessionId, state);
      } catch (err) {
        this.renderWeixinError(mask, sessionId, err.message);
      }
    }, 600);
  },

  renderWeixinError(mask, sessionId, message) {
    this.stopChannelPoll();
    const panel = mask.querySelector("#weixin-channel-panel");
    if (!panel) return;
    panel.innerHTML = `<div class="channel-error">
      <strong>${App.t("channel_error")}</strong>
      <p>${escapeHtml(message || App.t("channel_error_desc"))}</p>
      <button class="btn btn-sm btn-primary" id="channel-retry">${App.t("channel_reconnect")}</button>
    </div>`;
    panel.querySelector("#channel-retry").onclick = () => this.startWeixinQr(mask, sessionId);
  },

  async disconnectWeixin(mask, sessionId) {
    if (!confirm(App.t("channel_disconnect_confirm"))) return;
    await App.api("DELETE", `/api/conversations/${sessionId}/channels/weixin`);
    this.stopChannelPoll();
    this.channelQrImage = "";
    this.refreshChannelHeader(sessionId);
    if (mask.isConnected) {
      this.renderWeixinDisconnected(mask, sessionId, App.t("channel_disconnected"));
    }
  },

  async removeSession(id) {
    if (!confirm(App.t("confirm_delete"))) return;
    await App.api("DELETE", `/api/conversations/${id}`);
    if (this.currentId === id) {
      this.stopChannelPoll();
      this.currentId = null;
    }
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
  let data = "";
  evt.split(/\r?\n/).forEach((line) => {
    if (line.startsWith("data:")) {
      data += line.startsWith("data: ") ? line.slice(6) : line.slice(5);
    }
  });
  if (!data) return null;
  try { return JSON.parse(data); } catch (_) { return null; }
}
