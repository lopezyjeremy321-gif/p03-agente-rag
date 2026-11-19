/* Widget de chat P03. Sin dependencias, sin claves. Todo texto de servidor/usuario entra por textContent (nunca innerHTML). */
(function () {
  "use strict";
  var script = document.currentScript;
  var cfg = {
    api: (script && script.dataset.api) || "",
    tenant: (script && script.dataset.tenant) || "mirlo",
    name: (script && script.dataset.name) || "el negocio",
    mode: (script && script.dataset.mode) || "live",
    replay: (script && script.dataset.replay) || "replay.json",
    chips: ((script && script.dataset.chips) || "").split("|").filter(Boolean),
  };
  var MAXLEN = 500;
  var sid = null;
  try { sid = sessionStorage.getItem("p03sid-" + cfg.tenant); } catch (e) { /* sin almacenamiento: sigue funcionando */ }
  var replayData = null;
  var busy = false;
  var lastText = "";

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  function norm(s) { return s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9 ]/g, " ").replace(/\s+/g, " ").trim(); }
  function safeUrl(u) {
    try { var x = new URL(u, location.href); return (x.protocol === "https:" || x.protocol === "http:") ? x.href : null; } catch (e) { return null; }
  }

  /* ---------- estructura ---------- */
  var root = el("div", "p03w");
  var launcher = el("button", "p03w-launcher");
  launcher.type = "button";
  launcher.setAttribute("aria-expanded", "false");
  launcher.setAttribute("aria-controls", "p03w-panel");
  launcher.setAttribute("aria-label", "Preguntar al asistente: abrir chat");
  launcher.innerHTML = '<svg aria-hidden="true" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/></svg>';
  launcher.appendChild(el("span", "p03w-launcher-text", "Preguntar"));

  var panel = el("section", "p03w-panel");
  panel.id = "p03w-panel";
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-label", "Asistente de " + cfg.name);
  panel.hidden = true;

  var head = el("header", "p03w-head");
  var titleBox = el("div", "p03w-title");
  titleBox.appendChild(el("strong", null, "Asistente de " + cfg.name));
  titleBox.appendChild(el("span", "p03w-sub", cfg.mode === "replay" ? "Respuestas pregrabadas de demostración" : "Responde solo con los documentos del negocio"));
  var human = el("button", "p03w-btn p03w-btn-quiet", "Pasar a humano");
  human.type = "button";
  var close = el("button", "p03w-iconbtn");
  close.type = "button";
  close.setAttribute("aria-label", "Cerrar chat");
  close.innerHTML = '<svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>';
  head.appendChild(titleBox);
  head.appendChild(human);
  head.appendChild(close);

  var log = el("div", "p03w-log");
  log.setAttribute("role", "log");
  log.setAttribute("aria-live", "polite");
  log.setAttribute("aria-relevant", "additions");
  log.setAttribute("aria-label", "Conversación");
  log.tabIndex = 0;

  var chipsBox = el("div", "p03w-chips");
  chipsBox.setAttribute("role", "group");
  chipsBox.setAttribute("aria-label", "Preguntas sugeridas");

  var status = el("div", "p03w-status");
  status.setAttribute("role", "status");

  var form = el("form", "p03w-form");
  form.setAttribute("novalidate", "");
  var label = el("label", "p03w-sr", "Escribe tu pregunta");
  label.htmlFor = "p03w-input";
  var input = el("textarea", "p03w-input");
  input.id = "p03w-input";
  input.rows = 1;
  input.maxLength = MAXLEN;
  input.placeholder = "Ej.: ¿Cuánto cuesta un corte?";
  input.setAttribute("enterkeyhint", "send");
  var send = el("button", "p03w-btn p03w-btn-primary", "Enviar pregunta");
  send.type = "submit";
  var privacy = el("p", "p03w-privacy", "No escribas datos personales. Esta es una demostración con un negocio ficticio.");
  form.appendChild(label);
  form.appendChild(input);
  form.appendChild(send);

  panel.appendChild(head);
  panel.appendChild(log);
  panel.appendChild(chipsBox);
  panel.appendChild(status);
  panel.appendChild(form);
  panel.appendChild(privacy);
  root.appendChild(panel);
  root.appendChild(launcher);
  document.body.appendChild(root);

  /* ---------- abrir / cerrar ---------- */
  function openPanel() {
    panel.hidden = false;
    requestAnimationFrame(function () { panel.classList.add("is-open"); });
    launcher.setAttribute("aria-expanded", "true");
    launcher.setAttribute("aria-label", "Preguntar al asistente: cerrar chat");
    if (!log.children.length) welcome();
    input.focus();
  }
  function closePanel() {
    panel.classList.remove("is-open");
    launcher.setAttribute("aria-expanded", "false");
    launcher.setAttribute("aria-label", "Preguntar al asistente: abrir chat");
    setTimeout(function () { if (!panel.classList.contains("is-open")) panel.hidden = true; }, 200);
    launcher.focus();
  }
  launcher.addEventListener("click", function () { if (panel.hidden) { openPanel(); } else { closePanel(); } });
  close.addEventListener("click", closePanel);
  panel.addEventListener("keydown", function (e) { if (e.key === "Escape") { e.stopPropagation(); closePanel(); } });
  window.p03Open = openPanel;

  /* ---------- mensajes ---------- */
  function addMsg(role, text) {
    var m = el("div", "p03w-msg p03w-" + role);
    m.appendChild(el("p", "p03w-text", text));
    log.appendChild(m);
    log.scrollTop = log.scrollHeight;
    return m;
  }
  function welcome() {
    addMsg("agent", "Hola, soy el asistente de " + cfg.name + ". Respondo con lo que dicen sus documentos y cito la fuente. Si no lo encuentro, te lo digo y puedes pasar con una persona.");
    var qs = cfg.chips.length ? cfg.chips : ["¿Cuánto cuesta un corte de mujer?", "¿Qué horario tienen los sábados?", "¿Hasta cuándo puedo cancelar sin costo?"];
    qs.forEach(function (q) {
      var b = el("button", "p03w-chip", q);
      b.type = "button";
      b.addEventListener("click", function () { ask(q); });
      chipsBox.appendChild(b);
    });
  }
  function renderCitations(m, cits) {
    if (!cits || !cits.length) return;
    var wrap = el("div", "p03w-cites");
    cits.forEach(function (c, i) {
      var b = el("button", "p03w-cite", "Fuente: " + c.title + ", p. " + c.page);
      b.type = "button";
      b.setAttribute("aria-expanded", "false");
      var pid = "p03w-snip-" + Date.now() + "-" + i;
      b.setAttribute("aria-controls", pid);
      var s = el("blockquote", "p03w-snippet", c.snippet || "");
      s.id = pid;
      s.hidden = true;
      b.addEventListener("click", function () {
        var open = b.getAttribute("aria-expanded") === "true";
        b.setAttribute("aria-expanded", String(!open));
        s.hidden = open;
      });
      wrap.appendChild(b);
      wrap.appendChild(s);
    });
    m.appendChild(wrap);
  }
  function renderBooking(m, bk) {
    if (!bk) return;
    var href = safeUrl(bk.url);
    if (!href) return;
    var a = el("a", "p03w-btn p03w-btn-primary p03w-book", bk.label + (bk.demo ? " (enlace de demostración)" : ""));
    a.href = href;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    m.appendChild(a);
  }
  function renderResponse(r) {
    var m = addMsg("agent", r.answer);
    renderCitations(m, r.citations);
    renderBooking(m, r.booking);
    if (r.handoff) {
      var h = el("button", "p03w-btn p03w-btn-secondary", "Hablar con una persona");
      h.type = "button";
      h.addEventListener("click", doHandoff);
      m.appendChild(h);
    }
    log.scrollTop = log.scrollHeight;
  }

  /* ---------- red ---------- */
  function setBusy(on, msg) {
    busy = on;
    send.disabled = on;
    log.setAttribute("aria-busy", String(on));
    status.textContent = on ? "Escribiendo…" : (msg || "");
  }
  function errorMsg(text, retry) {
    var m = addMsg("agent p03w-error", text);
    if (retry) {
      var b = el("button", "p03w-btn p03w-btn-secondary", "Reintentar pregunta");
      b.type = "button";
      b.addEventListener("click", function () { m.remove(); ask(lastText, true); });
      m.appendChild(b);
    }
  }
  function getReplay() {
    if (replayData) return Promise.resolve(replayData);
    return fetch(cfg.replay).then(function (r) { return r.json(); }).then(function (d) { replayData = d; return d; });
  }
  function ask(text, isRetry) {
    text = (text || "").trim();
    if (!text || busy) return;
    if (text.length > MAXLEN) { status.textContent = "La pregunta supera " + MAXLEN + " caracteres. Acórtala y vuelve a enviar."; return; }
    lastText = text;
    chipsBox.hidden = true;
    if (!isRetry) addMsg("user", text);
    input.value = "";
    autosize();
    setBusy(true);
    var p;
    if (cfg.mode === "replay") {
      p = getReplay().then(function (d) {
        var k = norm(text);
        var hit = d.items.filter(function (i) { return norm(i.q) === k; })[0];
        return new Promise(function (res) { setTimeout(function () { res(hit ? hit : d.fallback); }, 350); });
      });
    } else {
      p = fetch(cfg.api + "/api/chat", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tenant: cfg.tenant, session_id: sid || undefined, message: text }),
      }).then(function (r) {
        return r.json().then(function (j) { return { status: r.status, body: j, retry: r.headers.get("Retry-After") }; });
      });
    }
    p.then(function (res) {
      setBusy(false);
      if (cfg.mode === "replay") return renderResponse(res);
      if (res.status === 200) {
        if (res.body.session_id) { sid = res.body.session_id; try { sessionStorage.setItem("p03sid-" + cfg.tenant, sid); } catch (e) { /* ok */ } }
        return renderResponse(res.body);
      }
      if (res.status === 429) return errorMsg("Estás escribiendo muy rápido. Espera " + (res.retry || "unos") + " segundos y reintenta.", true);
      if (res.status === 403 && res.body.error === "sesion_no_valida") { sid = null; try { sessionStorage.removeItem("p03sid-" + cfg.tenant); } catch (e) { /* ok */ } return errorMsg("La sesión caducó. Reintenta para empezar una nueva.", true); }
      if (res.status === 413) return errorMsg("El mensaje es demasiado largo. Acórtalo a menos de " + MAXLEN + " caracteres.", false);
      return errorMsg("No pude procesar la pregunta. Reintenta; si sigue fallando, pasa con una persona.", true);
    }).catch(function () {
      setBusy(false);
      errorMsg("No hay conexión con el asistente. Revisa tu red y reintenta; tu pregunta se conserva.", true);
    });
  }
  function doHandoff() {
    if (cfg.mode === "replay") { addMsg("agent", "En la demostración estática no se contacta a nadie. En la versión real, una persona del negocio recibe tu conversación."); return; }
    if (!sid) { addMsg("agent", "Escribe primero una pregunta para abrir la conversación y luego pasa con una persona."); return; }
    fetch(cfg.api + "/api/handoff", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ tenant: cfg.tenant, session_id: sid }) })
      .then(function (r) { return r.json(); })
      .then(function (j) { addMsg("agent", j.message || "Una persona te escribirá pronto."); })
      .catch(function () { errorMsg("No pude avisar a una persona. Reintenta en un momento.", false); });
  }
  human.addEventListener("click", doHandoff);

  function autosize() { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 120) + "px"; }
  input.addEventListener("input", autosize);
  input.addEventListener("keydown", function (e) { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); } });
  form.addEventListener("submit", function (e) { e.preventDefault(); ask(input.value); });
})();
