// Counts the short videos you scroll through (YouTube Shorts, Instagram Reels, TikTok).
// It only looks at the address of the page, never at what is in the video, and sends just "one more short".
const host = location.hostname;
const site = host.includes("youtube") ? "youtube" : host.includes("instagram") ? "instagram" : host.includes("tiktok") ? "tiktok" : "";

function shortId() {
  const p = location.pathname;
  let m;
  if (site === "youtube" && (m = p.match(/^\/shorts\/([\w-]+)/))) return m[1];
  if (site === "instagram" && (m = p.match(/^\/(?:reels?)\/([\w-]+)/))) return m[1];
  if (site === "tiktok" && (m = p.match(/\/video\/(\d+)/))) return m[1];
  return null;
}

if (site) {
  let last = null;
  setInterval(() => {
    if (document.visibilityState !== "visible") return;
    const id = shortId();
    if (id && id !== last) chrome.runtime.sendMessage({ type: "short", site }).catch(() => {});
    last = id;
  }, 400);
}

// Regular YouTube videos: a video counts as "watched" once it has really played for 20 seconds (once per video).
if (site === "youtube") {
  let counted = null, played = 0, lastT = null;
  setInterval(() => {
    const id = new URLSearchParams(location.search).get("v");
    const v = document.querySelector("video");
    if (location.pathname !== "/watch" || !id || !v) { lastT = null; return; }
    if (id !== counted && !v.paused && !v.ended && v.readyState > 2) {
      if (lastT !== null && Math.abs(v.currentTime - lastT) < 3) played += 1;
      lastT = v.currentTime;
      if (played >= 20) { counted = id; played = 0; chrome.runtime.sendMessage({ type: "video", seconds: Math.round(v.duration) || 0 }).catch(() => {}); }
    } else lastT = v.paused ? null : v.currentTime;
    if (id !== counted && id !== (window.__evId || id)) played = 0;
    window.__evId = id;
  }, 1000);
}
