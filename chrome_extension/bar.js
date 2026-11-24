// EV command bar: press Ctrl+Shift+Space on any page. Type a question about the page (or the text you selected) and
// EV AI on this computer answers here. It only reads the page when you press Enter, and nothing leaves this computer.
(() => {
  if (window.__evBar) { window.__evBar.toggle(); return; }

  const host = document.createElement("div");
  host.style.cssText = "all:initial;position:fixed;top:14px;left:50%;transform:translateX(-50%);z-index:2147483647;";
  const root = host.attachShadow({ mode: "closed" });
  root.innerHTML = `
    <style>
      .wrap { width: min(640px, calc(100vw - 32px)); font: 14px/1.45 "Segoe UI", system-ui, sans-serif; color: #e6f6ff; }
      .glass { background: rgba(9, 16, 28, .86); -webkit-backdrop-filter: blur(14px); backdrop-filter: blur(14px);
        border: 1px solid rgba(76, 201, 240, .55); border-radius: 14px;
        box-shadow: 0 10px 40px rgba(0, 0, 0, .5), 0 0 22px rgba(76, 201, 240, .16); }
      .bar { display: flex; align-items: center; gap: 10px; padding: 10px 14px; }
      .dot { width: 10px; height: 10px; border-radius: 50%; background: #4cc9f0; box-shadow: 0 0 10px #4cc9f0; flex: none;
        animation: pulse 2.2s ease-in-out infinite; }
      .dot.off { background: #ff7b7b; box-shadow: 0 0 10px #ff7b7b; animation: none; }
      @keyframes pulse { 50% { opacity: .35; } }
      input { flex: 1; min-width: 0; background: transparent; border: 0; outline: 0; color: inherit; font: inherit; }
      input::placeholder { color: #7a93a3; }
      .x { all: unset; cursor: pointer; color: #7a93a3; padding: 2px 6px; border-radius: 6px; }
      .x:hover { color: #fff; background: rgba(255, 255, 255, .08); }
      .chips { display: flex; flex-wrap: wrap; gap: 6px; padding: 0 14px 10px; }
      .chip { all: unset; cursor: pointer; font-size: 12px; color: #4cc9f0; padding: 4px 10px; border-radius: 999px;
        border: 1px solid rgba(76, 201, 240, .4); }
      .chip:hover { background: rgba(76, 201, 240, .15); color: #fff; }
      .panel { margin-top: 8px; padding: 12px 14px; max-height: 50vh; overflow: auto; white-space: pre-wrap; }
      .panel[hidden], .chips[hidden] { display: none; }
      .tag { font-size: 11px; letter-spacing: 2px; color: #4cc9f0; margin-bottom: 6px; }
      .row { display: flex; gap: 8px; margin-top: 10px; }
    </style>
    <div class="wrap">
      <div class="glass bar"><span class="dot" id="dot"></span><input id="q" placeholder="Ask EV about this page…  (Esc closes)" autocomplete="off" spellcheck="false"><button class="x" id="close" title="Close">✕</button></div>
      <div class="glass chips" id="chips" style="margin-top:8px;padding-top:10px"></div>
      <div class="glass panel" id="panel" hidden><div class="tag">EV</div><div id="text"></div><div class="row"><button class="chip" id="copy">Copy</button></div></div>
    </div>`;
  const $ = (id) => root.getElementById(id);
  let open = false, paused = false, picked = "";      // `picked`: the text selected on the page when the bar opened

  const stop = (e) => e.stopPropagation();           // keep page shortcuts (YouTube, Gmail ...) from reacting to typing
  for (const t of ["keydown", "keyup", "keypress"]) $("q").addEventListener(t, stop);

  function selection() { return picked; }
  function page() { return { title: document.title, url: location.href, text: (document.body ? document.body.innerText : "").slice(0, 12000) }; }

  function chips() {
    const box = $("chips");
    box.textContent = "";
    const items = [["Summarize this page", "Summarize this page in a few short points."],
                   ["Key facts", "List the key facts and numbers on this page."]];
    if (selection()) items.unshift(["Explain the selection", "Explain this in simple words: " + selection()]);
    items.push([paused ? "Resume EV control" : "Pause EV control", paused ? "/resume" : "/pause"]);
    for (const [label, q] of items) {
      const b = document.createElement("button");
      b.className = "chip"; b.textContent = label;
      b.onclick = () => { $("q").value = q; submit(); };
      box.appendChild(b);
    }
  }

  async function submit() {
    const q = $("q").value.trim();
    if (!q) return;
    if (q === "/pause" || q === "/resume") {
      const r = await chrome.runtime.sendMessage({ type: "pause", on: q === "/pause" });
      paused = !!(r && r.paused);
      $("dot").className = "dot" + (paused ? " off" : "");
      show(paused ? "EV control of this browser is PAUSED. EV AI cannot click, switch tabs or open pages until you resume. You can still ask questions here."
                  : "EV control is back on.");
      $("q").value = ""; chips();
      return;
    }
    const sel = selection();
    show("EV is reading the page…");
    try {
      const r = await chrome.runtime.sendMessage({ type: "ask", question: sel && !q.includes(sel) ? q + "\n\nSelected text: " + sel : q, page: page() });
      show((r && (r.answer || r.error)) || "No answer. Is EV AI running?");
    } catch (e) { show("Couldn't reach EV AI. Is it running and paired?"); }
  }

  function show(text) {
    $("panel").hidden = false;
    $("text").textContent = text;
  }

  async function openBar() {
    picked = (window.getSelection() || "").toString().trim().slice(0, 4000);   // read it before the input takes the focus
    document.documentElement.appendChild(host);
    open = true;
    try { const r = await chrome.runtime.sendMessage({ type: "state" }); paused = !!(r && r.paused); } catch (e) {}
    $("dot").className = "dot" + (paused ? " off" : "");
    chips();
    $("panel").hidden = true;
    $("q").value = "";
    $("q").focus();
  }
  function closeBar() { open = false; host.remove(); }

  $("q").addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); submit(); }
    else if (e.key === "Escape") { e.preventDefault(); closeBar(); }
  });
  $("close").onclick = closeBar;
  $("copy").onclick = async () => { try { await navigator.clipboard.writeText($("text").textContent); $("copy").textContent = "Copied"; } catch (e) { $("copy").textContent = "Can't copy"; } };

  window.__evBar = { toggle: () => (open ? closeBar() : openBar()) };
  openBar();
})();
