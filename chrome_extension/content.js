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
