// 多智能体团队协作页：共享消息、记忆和文本文件，按任务图流式执行。
const GroupChatPage = {
  currentId: null,

  async render() {
    ChatPage.stopChannelPoll();
    const page = document.getElementById("page-group-chat");
    const [groups, agents] = await Promise.all([
      App.api("GET", "/api/group-conversations"),
      App.api("GET", "/api/agents?status=published"),
    ]);
    this.groups = groups;
    this.agents = agents;
    page.innerHTML = `
      <div class="group-chat-page">
        <aside class="chat-sessions group-list-panel">
          <div class="sessions-head"><button class="btn btn-primary" id="g-new" style="width:100%">${App.t("teamwork_new")}</button></div>
          <div class="session-list" id="group-list">${groups.map((item) => this.groupItem(item)).join("")}</div>
        </aside>
        <section class="group-main" id="group-main"></section>
      </div>`;
    page.querySelector("#g-new").onclick = () => this.openNewGroup();
    this.bindGroupList();
    if (this.currentId && groups.some((item) => item.id === this.currentId)) {
      await this.openGroup(this.currentId);
    } else {
      this.currentId = null;
      this.renderEmpty();
    }
  },

  groupItem(group) {
    const active = group.id === this.currentId ? "active" : "";
    const members = (group.members || []).map((item) => item.agent.name).join(App.t("teamwork_member_sep")) || App.t("teamwork_no_agent");
    return `<div class="session-item ${active}" id="g-${group.id}">
      <div class="session-info">
        <span class="title">${escapeHtml(group.title || App.t("teamwork_default_title"))}</span>
        <span class="session-meta">${escapeHtml(group.latest_message_summary || members)}</span>
      </div>
      <button class="del" id="gd-${group.id}">×</button>
    </div>`;
  },

  bindGroupList() {
    (this.groups || []).forEach((group) => {
      document.getElementById(`g-${group.id}`).onclick = () => this.openGroup(group.id);
      document.getElementById(`gd-${group.id}`).onclick = (event) => {
        event.stopPropagation();
        this.removeGroup(group.id);
      };
    });
  },

  renderEmpty() {
    document.getElementById("group-main").innerHTML = `<div class="chat-empty">${App.t("teamwork_empty")}</div>`;
  },

  openNewGroup() {
    const main = document.getElementById("group-main");
    if (!this.agents.length) {
      main.innerHTML = `<div class="chat-empty">${App.t("teamwork_no_published")}</div>`;
      return;
    }
    main.innerHTML = `
      <div class="new-session-form group-new-form">
        <h2>${App.t("teamwork_new")}</h2>
        <div class="field"><label>${App.t("teamwork_name")}</label><input id="gn-title" value="${escapeAttr(App.t("teamwork_default_title"))}"></div>
        <div class="field"><label>${App.t("teamwork_initial_agent")}</label>
          <div class="group-agent-checks">${this.agents.map((agent, index) => `<label><input type="checkbox" value="${agent.id}" ${index === 0 ? "checked" : ""}> ${escapeHtml(agent.name)}</label>`).join("")}</div>
        </div>
        <div class="field"><label>${App.t("chat_answer_lang")}</label>
          <select id="gn-lang"><option value="zh">中文</option><option value="en">English</option><option value="ru">Русский</option></select>
        </div>
        <button class="btn btn-primary" id="gn-start">${App.t("teamwork_create")}</button>
      </div>`;
    main.querySelector("#gn-lang").value = App.lang;
    main.querySelector("#gn-start").onclick = async () => {
      const ids = [...main.querySelectorAll(".group-agent-checks input:checked")].map((item) => Number(item.value));
      if (!ids.length) {
        alert(App.t("teamwork_initial_agent_required"));
        return;
      }
      const group = await App.api("POST", "/api/group-conversations", {
        title: main.querySelector("#gn-title").value.trim() || App.t("teamwork_default_title"),
        language: main.querySelector("#gn-lang").value,
        agent_config_ids: ids,
      });
      this.currentId = group.id;
      await this.render();
    };
  },

  async openGroup(id) {
    this.currentId = id;
    document.querySelectorAll("#group-list .session-item").forEach((item) => item.classList.toggle("active", item.id === `g-${id}`));
    const [messages, environment, members] = await Promise.all([
      App.api("GET", `/api/group-conversations/${id}/messages`),
      App.api("GET", `/api/group-conversations/${id}/environment`),
      App.api("GET", `/api/group-conversations/${id}/members`),
    ]);
    this.members = members.agents || [];
    const group = this.groups.find((item) => item.id === id) || {};
    document.getElementById("group-main").innerHTML = `
      <div class="group-workspace">
        <section class="group-chat-main">
          <div class="chat-header">
            <div class="chat-header-info">
              <span class="chat-header-name">${escapeHtml(group.title || App.t("teamwork_default_title"))}</span>
              <span class="chat-header-model">${this.members.map((item) => `@${escapeHtml(item.agent.name)}`).join(" ")}</span>
            </div>
          </div>
          <div class="chat-messages group-messages" id="group-msgs">${messages.map((item) => this.bubble(item)).join("")}</div>
          <div class="chat-input-bar">
            <textarea id="group-input" placeholder="${escapeAttr(App.t("teamwork_input_placeholder"))}"></textarea>
            <button class="btn btn-primary" id="group-send">${App.t("chat_send")}</button>
          </div>
        </section>
        <aside class="group-side">${this.sidePanel(environment, members)}</aside>
      </div>`;
    document.getElementById("group-send").onclick = () => this.send();
    document.getElementById("group-input").addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        this.send();
      }
    });
    this.bindSideActions();
    this.scrollDown();
  },

  bubble(message) {
    const role = message.role === "assistant" ? "assistant" : "user";
    const content = role === "assistant" ? renderMarkdown(message.content || "") : escapeHtml(message.content || "").replace(/\n/g, "<br>");
    return `<div class="group-msg-row ${role}">
      <div class="group-sender">${escapeHtml(message.sender_name || (role === "assistant" ? App.t("teamwork_sender_agent") : App.t("teamwork_sender_user")))}</div>
      <div class="msg ${role}">${role === "assistant" ? ChatPage.traceHtml(message.extra?.agent_trace || []) : ""}<div class="msg-content">${content}</div>${ChatPage.sourcesHtml(message.sources || [])}</div>
    </div>`;
  },

  sidePanel(environment, members) {
    const agentRows = (members.agents || []).map((item) => `<div class="env-row"><span>🤖 @${escapeHtml(item.agent.name)}</span><button class="btn btn-sm btn-danger" data-remove-agent="${item.agent_config_id}">${App.t("teamwork_remove")}</button></div>`).join("") || `<div class="muted">${App.t("teamwork_no_agent")}</div>`;
    const memoryRows = (environment.memories || []).map((item) => `<div class="env-card"><strong>${escapeHtml(item.key)}</strong><div>${escapeHtml(item.content)}</div></div>`).join("") || `<div class="muted">${App.t("teamwork_no_memories")}</div>`;
    const fileRows = (environment.files || []).map((item) => `<details class="env-file"><summary>${escapeHtml(item.filename)}</summary><pre>${escapeHtml(item.content || App.t("teamwork_empty_file"))}</pre></details>`).join("") || `<div class="muted">${App.t("teamwork_no_files")}</div>`;
    return `<div class="group-side-body">
      <div class="env-section"><div class="env-section-head"><h3>${App.t("teamwork_agents_section")}</h3><button class="btn btn-sm" id="ga-add-btn">+ ${App.t("teamwork_join")}</button></div>${agentRows}</div>
      <div class="env-section"><h3>${App.t("teamwork_memories_section")}</h3>${memoryRows}</div>
      <div class="env-section"><h3>${App.t("teamwork_files_section")}</h3>${fileRows}</div>
    </div>`;
  },

  bindSideActions() {
    const add = document.getElementById("ga-add-btn");
    if (add) add.onclick = () => this.openAgentPicker();
    document.querySelectorAll("[data-remove-agent]").forEach((button) => {
      button.onclick = async () => {
        await App.api("DELETE", `/api/group-conversations/${this.currentId}/agents/${button.dataset.removeAgent}`);
        await this.render();
      };
    });
  },

  async openAgentPicker() {
    const data = await App.api("GET", `/api/group-conversations/${this.currentId}/members`);
    if (!data.available_agents.length) {
      alert(App.t("teamwork_no_available_agent"));
      return;
    }
    const mask = document.createElement("div");
    mask.className = "modal-mask";
    mask.innerHTML = `<div class="modal group-agent-modal"><h2>${App.t("teamwork_join_agent")}</h2>
      <div class="modal-body group-agent-checks">${data.available_agents.map((agent) => `<label><input type="checkbox" value="${agent.id}"> ${escapeHtml(agent.name)}</label>`).join("")}</div>
      <div class="modal-actions"><button class="btn" id="gap-cancel">${App.t("action_cancel")}</button><button class="btn btn-primary" id="gap-save">${App.t("teamwork_join")}</button></div></div>`;
    document.body.appendChild(mask);
    mask.querySelector("#gap-cancel").onclick = () => mask.remove();
    mask.querySelector("#gap-save").onclick = async () => {
      const ids = [...mask.querySelectorAll("input:checked")].map((item) => Number(item.value));
      await Promise.all(ids.map((agentId) => App.api("POST", `/api/group-conversations/${this.currentId}/agents`, { agent_config_id: agentId })));
      mask.remove();
      await this.render();
    };
  },

  mentionedIds(text) {
    const normalized = text.toLowerCase();
    return (this.members || []).filter((item) => {
      const name = item.agent.name.toLowerCase();
      return normalized.includes(`@${name}`) || normalized.includes(`@${name.replace(/\s+/g, "-")}`);
    }).map((item) => item.agent_config_id);
  },

  async send() {
    const input = document.getElementById("group-input");
    const text = input.value.trim();
    if (!text) return;
    const box = document.getElementById("group-msgs");
    input.value = "";
    box.insertAdjacentHTML("beforeend", this.bubble({ role: "user", sender_name: App.t("teamwork_sender_user"), content: text }));
    this.scrollDown();
    try {
      const response = await fetch(`/api/group-conversations/${this.currentId}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: text, mentioned_agent_ids: this.mentionedIds(text), sender_name: App.t("teamwork_sender_user") }),
      });
      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(App.t(error.detail || response.statusText));
      }
      await this.consumeStream(response);
      await this.refreshGroupList();
    } catch (error) {
      box.insertAdjacentHTML("beforeend", `<div class="group-msg-row assistant"><div class="msg assistant">⚠ ${escapeHtml(error.message)}</div></div>`);
    }
    this.scrollDown();
  },

  async consumeStream(response) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    const holders = {};
    const answers = {};
    const sources = {};
    const traces = {};
    const box = document.getElementById("group-msgs");
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop();
      for (const block of blocks) {
        const parsed = parseGroupSseEvent(block);
        if (!parsed || parsed.event === "user") continue;
        if (parsed.event === "done") return;
        let data = {};
        try { data = JSON.parse(parsed.data || "{}"); } catch (_) { data = {}; }
        const key = data.task_id || data.agent_id;
        if (parsed.event === "agent_start") {
          const dependencies = (data.depends_on || []).join(", ");
          const taskMeta = `${data.task_id || "task"} · depends_on=[${dependencies}]`;
          const row = document.createElement("div");
          row.className = "group-msg-row assistant";
          row.innerHTML = `<div class="group-sender">${escapeHtml(data.name || "Agent")} · ${escapeHtml(taskMeta)} · ${App.t("teamwork_typing")}</div><div class="msg assistant"><div class="msg-content">${App.t("chat_thinking")}</div></div>`;
          box.appendChild(row);
          holders[key] = row.querySelector(".msg");
          answers[key] = "";
          traces[key] = [];
        } else if (parsed.event === "delta" && holders[key]) {
          answers[key] += this.decode(data.delta || "");
          this.renderHolder(holders[key], answers[key], sources[key], traces[key]);
        } else if (parsed.event === "sources" && holders[key]) {
          sources[key] = data.sources || [];
          this.renderHolder(holders[key], answers[key] || App.t("chat_thinking"), sources[key], traces[key]);
        } else if (parsed.event === "trace" && holders[key]) {
          traces[key] = [...(traces[key] || []), data.item];
          this.renderHolder(holders[key], answers[key] || App.t("chat_thinking"), sources[key], traces[key]);
        } else if (parsed.event === "error") {
          box.insertAdjacentHTML("beforeend", `<div class="group-msg-row assistant"><div class="msg assistant">⚠ ${escapeHtml(App.t(data.error || "teamwork_request_failed"))}</div></div>`);
        }
        this.scrollDown();
      }
    }
  },

  renderHolder(holder, content, sources, traces) {
    holder.innerHTML = `${ChatPage.traceHtml(traces || [])}<div class="msg-content">${renderMarkdown(content || "")}</div>${ChatPage.sourcesHtml(sources || [])}`;
  },

  decode(text) {
    return (text || "").replace(/\\n/g, "\n").replace(/\\\\/g, "\\");
  },

  async refreshGroupList() {
    this.groups = await App.api("GET", "/api/group-conversations");
    document.getElementById("group-list").innerHTML = this.groups.map((item) => this.groupItem(item)).join("");
    this.bindGroupList();
  },

  scrollDown() {
    const box = document.getElementById("group-msgs");
    if (box) box.scrollTop = box.scrollHeight;
  },

  async removeGroup(id) {
    if (!confirm(App.t("teamwork_delete_confirm"))) return;
    await App.api("DELETE", `/api/group-conversations/${id}`);
    if (this.currentId === id) this.currentId = null;
    await this.render();
  },
};

function parseGroupSseEvent(block) {
  let event = "";
  const data = [];
  block.split(/\r?\n/).forEach((line) => {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    if (line.startsWith("data:")) data.push(line.startsWith("data: ") ? line.slice(6) : line.slice(5));
  });
  if (!event && !data.length) return null;
  return { event: event || "message", data: data.join("\n") };
}
