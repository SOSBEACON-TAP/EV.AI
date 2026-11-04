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
        const { command } = await r.json();
        if (command) { try { await run(command); } catch (e) { console.warn("EV command failed", e); } }
      } catch (e) {
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
