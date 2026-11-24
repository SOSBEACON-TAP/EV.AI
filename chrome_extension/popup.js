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

async function showShorts() {
  const { counts = {} } = await chrome.storage.local.get("counts");
  const day = counts[new Date().toISOString().slice(0, 10)] || {};
  const n = Object.values(day).reduce((a, b) => a + b, 0);
  const names = { youtube: "YouTube", instagram: "Instagram", tiktok: "TikTok" };
  const parts = Object.entries(day).filter(([, v]) => v > 0).map(([k, v]) => `${names[k] || k} ${v}`);
  const { videos = {} } = await chrome.storage.local.get("videos");
  const v = videos[new Date().toISOString().slice(0, 10)] || 0;
  $("shorts").innerHTML = "YouTube videos watched today: <b>" + v + "</b><br>Shorts scrolled today: " + n + (parts.length ? " (" + parts.join(", ") + ")" : "");
}

refresh();
showShorts();


// Focus this page: hide sidebars, comments, recommendations and ads on the current tab. Click again to undo.
$("focus").addEventListener("click", async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || !/^https?:/.test(tab.url || "")) { $("focus").textContent = "Open a normal web page first"; return; }
  const key = "focus_" + tab.id;
  const on = !!(await chrome.storage.session.get(key))[key];
  const target = { tabId: tab.id };
  try {
    if (on) { await chrome.scripting.removeCSS({ target, files: ["focus.css"] }); await chrome.storage.session.remove(key); $("focus").textContent = "Focus this page (hide distractions)"; }
    else { await chrome.scripting.insertCSS({ target, files: ["focus.css"] }); await chrome.storage.session.set({ [key]: true }); $("focus").textContent = "Focus is ON (click to undo)"; }
  } catch (e) { $("focus").textContent = "Can't focus this page"; }
});

// Tab tools
$("mute").onclick = async () => {
  const tabs = await chrome.tabs.query({ audible: true });
  const muted = await chrome.tabs.query({ muted: true });
  if (tabs.length) tabs.forEach((t) => chrome.tabs.update(t.id, { muted: true }));
  else muted.forEach((t) => chrome.tabs.update(t.id, { muted: false }));
  $("mute").textContent = tabs.length ? "Tabs muted (click to unmute)" : "Mute all noisy tabs";
};
$("dupes").onclick = async () => {
  const seen = new Set(), drop = [];
  for (const t of await chrome.tabs.query({ currentWindow: true })) {
    const k = (t.url || "").split("#")[0];
    if (!k || t.pinned) continue;
    if (seen.has(k)) drop.push(t.id); else seen.add(k);
  }
  if (drop.length) await chrome.tabs.remove(drop);
  $("dupes").textContent = drop.length ? "Closed " + drop.length + " duplicate tab(s)" : "No duplicate tabs";
};
$("copylink").onclick = async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  try {
    const u = new URL(tab.url);
    for (const k of [...u.searchParams.keys()]) if (/^(utm_|fbclid|gclid|igshid|si$|feature$)/.test(k)) u.searchParams.delete(k);
    await navigator.clipboard.writeText(u.href);
    $("copylink").textContent = "Clean link copied";
  } catch (e) { $("copylink").textContent = "Can't copy this page's link"; }
};


// Kill switch: while paused, EV AI cannot click, switch tabs or open pages in this browser.
async function showPause() {
  const on = !!(await chrome.storage.local.get("paused")).paused;
  $("pause").textContent = on ? "EV control is PAUSED (click to resume)" : "Pause EV control of this browser";
}
$("pause").onclick = async () => {
  const on = !!(await chrome.storage.local.get("paused")).paused;
  await chrome.runtime.sendMessage({ type: "pause", on: !on });
  showPause(); showActivity();
};
showPause();

// Tab time machine: click a closed tab to open it again.
function ago(ms) {
  const m = Math.round((Date.now() - ms) / 60000);
  return m < 1 ? "just now" : m < 60 ? m + " min ago" : m < 1440 ? Math.round(m / 60) + " h ago" : Math.round(m / 1440) + " d ago";
}
async function showClosed() {
  const { closed = [] } = await chrome.storage.local.get("closed");
  const box = $("closed");
  box.textContent = "";
  if (!closed.length) { box.textContent = "Nothing closed yet."; return; }
  for (const t of closed.slice(0, 12)) {
    const b = document.createElement("button");
    b.className = "row";
    b.textContent = t.title;
    const s = document.createElement("small");
    s.textContent = new URL(t.url).hostname + " - " + ago(t.at);
    b.appendChild(s);
    b.onclick = () => chrome.tabs.create({ url: t.url });
    box.appendChild(b);
  }
}
async function showActivity() {
  const { activity = [] } = await chrome.storage.local.get("activity");
  const box = $("activity");
  box.textContent = "";
  if (!activity.length) { box.textContent = "EV has not done anything in Chrome yet."; return; }
  for (const a of activity.slice(0, 15)) {
    const d = document.createElement("div");
    d.className = "log";
    d.textContent = ago(a.at) + ": " + a.action.replace(/_/g, " ") + (a.host ? " on " + a.host : "");
    box.appendChild(d);
  }
}
showClosed();
showActivity();
