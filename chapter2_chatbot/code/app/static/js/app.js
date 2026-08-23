// 全局：i18n、导航切换、通用 fetch 封装。
const App = {
  lang: localStorage.getItem("ui_lang") || "zh",
  dict: {},

  // 翻译取值
  t(key) {
    return this.dict[key] || key;
  },

  // 加载语言包并刷新带 data-i18n 的静态文案
  async loadLocale() {
    const res = await fetch(`/locales/${this.lang}.json`);
    this.dict = await res.json();
    document.querySelectorAll("[data-i18n]").forEach((el) => {
      el.textContent = this.t(el.getAttribute("data-i18n"));
    });
    document.title = this.t("app_title");
  },

  // 通用 JSON 请求
  async api(method, url, body) {
    const opt = { method, headers: { "Content-Type": "application/json" } };
    if (body !== undefined) opt.body = JSON.stringify(body);
    const res = await fetch(url, opt);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || res.statusText);
    }
    return res.status === 200 ? res.json() : null;
  },

  switchTab(tab) {
    document.querySelectorAll(".nav-item").forEach((b) =>
      b.classList.toggle("active", b.dataset.tab === tab)
    );
    document.querySelectorAll(".page").forEach((p) =>
      p.classList.toggle("active", p.id === `page-${tab}`)
    );
    // 切换到某页时重新渲染，保证数据最新
    if (tab === "chat") ChatPage.render();
    if (tab === "models") ModelsPage.render();
    if (tab === "agents") AgentsPage.render();
  },

  async setLang(lang) {
    this.lang = lang;
    localStorage.setItem("ui_lang", lang);
    await this.loadLocale();
    // 重新渲染当前激活页
    const active = document.querySelector(".nav-item.active").dataset.tab;
    this.switchTab(active);
  },
};

// 简单的转义，避免把模型输出当作 HTML 解析
function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

window.addEventListener("DOMContentLoaded", async () => {
  document.querySelectorAll(".nav-item").forEach((btn) =>
    btn.addEventListener("click", () => App.switchTab(btn.dataset.tab))
  );
  const langSel = document.getElementById("ui-lang");
  langSel.value = App.lang;
  langSel.addEventListener("change", (e) => App.setLang(e.target.value));

  await App.loadLocale();
  App.switchTab("chat");
});
