// EV AI for Chrome: waits for commands from EV AI running on this computer (127.0.0.1 only)
// and carries them out in the browser. It never reads a page unless you ask.
const BASE = "http://127.0.0.1:47615";
let running = false;

async function token() {
  return (await chrome.storage.local.get("token")).token || "";
}

function grabPage() {   // runs inside the page
  return { title: document.title, url: location.href, text: (document.body ? document.body.innerText : "").slice(0, 12000) };
}

function clickText(text) {   // runs inside the page
  const want = text.toLowerCase();
  const els = [...document.querySelectorAll("a, button, [role=button], input[type=submit], input[type=button], summary")];
  const label = (e) => (e.innerText || e.value || e.getAttribute("aria-label") || e.title || "").trim().toLowerCase();
  const hit = els.find((e) => label(e) === want) || els.find((e) => label(e).includes(want));
  if (!hit) return false;
  hit.scrollIntoView({ block: "center" });
  hit.click();
  return true;
}

function scrollPage(dir) {   // runs inside the page
  const h = Math.max(200, window.innerHeight * 0.8);
  if (dir === "down") window.scrollBy({ top: h, behavior: "smooth" });
  else if (dir === "up") window.scrollBy({ top: -h, behavior: "smooth" });
  else if (dir === "top") window.scrollTo({ top: 0, behavior: "smooth" });
  else window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
}

async function activeTab() {
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  return tab;
}

async function run(cmd) {
  const tab = await activeTab();
  const inTab = (func, args = []) => chrome.scripting.executeScript({ target: { tabId: tab.id }, func, args });
  switch (cmd.action) {
    case "open_url": return chrome.tabs.create({ url: cmd.url });
    case "new_tab": return chrome.tabs.create({});
    case "close_tab": return tab && chrome.tabs.remove(tab.id);
    case "back": return tab && chrome.tabs.goBack(tab.id);
    case "forward": return tab && chrome.tabs.goForward(tab.id);
    case "reload": return tab && chrome.tabs.reload(tab.id);
    case "scroll": return tab && inTab(scrollPage, [cmd.dir]);
    case "click": return tab && inTab(clickText, [cmd.text]);
    case "next_tab":
    case "prev_tab": {
      const tabs = await chrome.tabs.query({ lastFocusedWindow: true });
      const i = tabs.findIndex((t) => t.id === tab.id);
      const j = (i + (cmd.action === "next_tab" ? 1 : tabs.length - 1)) % tabs.length;
      return chrome.tabs.update(tabs[j].id, { active: true });
    }
    case "switch_tab": {
      const want = cmd.text.toLowerCase();
      const hit = (await chrome.tabs.query({})).find((t) => (t.title + " " + t.url).toLowerCase().includes(want));
      if (hit) { await chrome.tabs.update(hit.id, { active: true }); return chrome.windows.update(hit.windowId, { focused: true }); }
      return;
    }
    case "page_text": {   // EV asked about the page: send it back to EV on this PC
      if (!tab || !/^https?:/.test(tab.url || "")) return;
      const [res] = await inTab(grabPage);
      return fetch(BASE + "/page", {
        method: "POST", headers: { "Content-Type": "application/json", "X-EV-Token": await token() },
        body: JSON.stringify({ page: res.result }),
      });
    }
  }
}

// ---- short-video counter: the totals are kept here and sent to EV AI on this PC
const today = () => new Date().toISOString().slice(0, 10);

async function countShort(site) {
  const day = today();
  const { counts = {}, pending = {} } = await chrome.storage.local.get(["counts", "pending"]);
  counts[day] = counts[day] || {};
  counts[day][site] = (counts[day][site] || 0) + 1;
  pending[site] = (pending[site] || 0) + 1;
  for (const d of Object.keys(counts).sort().slice(0, -14)) delete counts[d];
  await chrome.storage.local.set({ counts, pending });
  flush();
}

async function flush() {   // tell EV AI about shorts it has not heard of yet
  const t = await token();
  if (!t) return;
  const { pending = {} } = await chrome.storage.local.get("pending");
  for (const [site, n] of Object.entries(pending)) {
    if (!n) continue;
    try {
      const r = await fetch(BASE + "/count", { method: "POST", headers: { "Content-Type": "application/json", "X-EV-Token": t },
        body: JSON.stringify({ site, n: Math.min(n, 50) }) });
      if (!r.ok) return;
      pending[site] = n - Math.min(n, 50);
      await chrome.storage.local.set({ pending });
    } catch (e) { return; }
  }
}

chrome.runtime.onMessage.addListener((msg) => { if (msg && msg.type === "short") countShort(msg.site); });

async function syncRules() {   // Karen mode: block the websites EV AI lists (rules stay even if EV AI is closed)
  try {
    const r = await fetch(BASE + "/rules", { headers: { "X-EV-Token": await token() }, signal: AbortSignal.timeout(5000) });
    if (!r.ok) return;
    const { blocked_sites, allow_only, allowed_sites } = await r.json();
    const redirect = { type: "redirect", redirect: { extensionPath: "/blocked.html" } };
    let rules = blocked_sites.slice(0, 100).map((d, i) => ({
      id: i + 1, priority: 1, action: redirect,
      condition: { requestDomains: [d], resourceTypes: ["main_frame"] },
    }));
    if (allow_only) {   // allow-list: everything is blocked except the listed sites (and EV AI itself)
      const ok = ["127.0.0.1", "localhost", ...(allowed_sites || []).slice(0, 100)];
      rules = [
        { id: 1, priority: 1, action: redirect, condition: { regexFilter: "^https?://", resourceTypes: ["main_frame"] } },
        { id: 2, priority: 2, action: { type: "allow" }, condition: { requestDomains: ok, resourceTypes: ["main_frame"] } },
      ];
    }
    const old = await chrome.declarativeNetRequest.getDynamicRules();
    await chrome.declarativeNetRequest.updateDynamicRules({ removeRuleIds: old.map((x) => x.id), addRules: rules });
  } catch (e) { /* EV AI not running: keep the last rules */ }
}

// EV AI is not running: ask Chrome to start it quietly (hidden, in the tray). At most once a minute.
let lastWake = 0;
function wakeEV() {
  if (Date.now() - lastWake < 60000) return;
  lastWake = Date.now();
  try {
    const port = chrome.runtime.connectNative("com.sosbeacon.evai");
    port.onDisconnect.addListener(() => { void chrome.runtime.lastError; });
  } catch (e) { /* the helper is not registered yet: open EV AI once */ }
}

async function loop() {
  if (running) return;
  running = true;
  try {
    for (;;) {
      const t = await token();
      if (!t) break;
      try {
        const r = await fetch(BASE + "/poll", { headers: { "X-EV-Token": t }, signal: AbortSignal.timeout(30000) });
        if (r.status === 401) { await chrome.storage.local.remove("token"); break; }
        flush();
        syncRules();
        const { command } = await r.json();
        if (command) { try { await run(command); } catch (e) { console.warn("EV command failed", e); } }
      } catch (e) {
        wakeEV();
        await new Promise((ok) => setTimeout(ok, 5000));   // EV AI isn't running: try again soon
      }
    }
  } finally { running = false; }
}

chrome.alarms.create("keepalive", { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener(loop);
chrome.runtime.onStartup.addListener(loop);
chrome.runtime.onInstalled.addListener(loop);
chrome.storage.onChanged.addListener((c) => { if (c.token) loop(); });
loop();
