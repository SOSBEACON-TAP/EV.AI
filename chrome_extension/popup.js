const BASE = "http://127.0.0.1:47615";
const $ = (id) => document.getElementById(id);

async function token() { return (await chrome.storage.local.get("token")).token || ""; }

async function refresh() {
  const t = await token();
  $("pairBox").hidden = !!t;
  $("askBox").hidden = !t;
  let up = false;
  try { up = (await fetch(BASE + "/ping", { signal: AbortSignal.timeout(2000) })).ok; } catch (e) {}
  $("status").innerHTML = up ? '<span class="ok">EV AI is running</span>' : '<span class="bad">EV AI is not running. Open it first.</span>';
}

$("pair").onclick = async () => {
  try {
    const r = await fetch(BASE + "/pair", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: $("code").value.trim() }) });
    const d = await r.json();
    if (d.token) { await chrome.storage.local.set({ token: d.token }); $("code").value = ""; }
    else $("status").innerHTML = '<span class="bad">Wrong code (5 wrong tries lock it for a minute).</span>';
  } catch (e) { $("status").innerHTML = '<span class="bad">Cannot reach EV AI. Is it running?</span>'; }
  refresh();
};

$("unpair").onclick = async () => { await chrome.storage.local.remove("token"); refresh(); };

$("ask").onclick = async () => {
  $("answer").textContent = "EV is reading the page…";
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!/^https?:/.test(tab.url || "")) { $("answer").textContent = "Open a normal web page first."; return; }
    const [res] = await chrome.scripting.executeScript({ target: { tabId: tab.id },
      func: () => ({ title: document.title, url: location.href, text: (document.body ? document.body.innerText : "").slice(0, 12000) }) });
    const r = await fetch(BASE + "/ask", { method: "POST",
      headers: { "Content-Type": "application/json", "X-EV-Token": await token() },
      body: JSON.stringify({ question: $("q").value.trim() || "What is this page about?", page: res.result }) });
    if (r.status === 401) { await chrome.storage.local.remove("token"); refresh(); return; }
    $("answer").textContent = (await r.json()).answer;
  } catch (e) { $("answer").textContent = "Couldn't reach EV AI. Is it running?"; }
};

refresh();
