const form = document.getElementById("form");
const urlInput = document.getElementById("url");
const submitBtn = document.getElementById("submit");
const statusEl = document.getElementById("status");
const statusText = document.getElementById("status-text");
const statusPct = document.getElementById("status-pct");
const barFill = document.getElementById("bar-fill");
const filesEl = document.getElementById("files");
const emptyEl = document.getElementById("empty");
const visitorsEl = document.getElementById("stat-visitors");
const downloadsEl = document.getElementById("stat-downloads");

function formatNumber(n) {
  return new Intl.NumberFormat("ar-EG").format(Number(n) || 0);
}

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function setMetric(el, value) {
  const next = formatNumber(value);
  if (el.textContent === next) return;
  el.textContent = next;
  el.classList.remove("pulse");
  void el.offsetWidth;
  el.classList.add("pulse");
}

function renderStats(data) {
  if (!data) return;
  setMetric(visitorsEl, data.visitors);
  setMetric(downloadsEl, data.downloads);
}

function setStatus(visible, text, pct, state) {
  statusEl.hidden = !visible;
  statusEl.classList.remove("error", "done");
  if (state) statusEl.classList.add(state);
  statusText.textContent = text;
  statusPct.textContent = `${pct}%`;
  barFill.style.width = `${pct}%`;
}

function triggerDownload(fileId, filename) {
  const a = document.createElement("a");
  a.href = `/file/${fileId}`;
  a.download = filename || "audio.mp3";
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

async function trackVisit() {
  const res = await fetch("/api/visit", { method: "POST" });
  const data = await res.json();
  if (data.ok) renderStats(data);
}

async function loadStats() {
  const res = await fetch("/api/stats");
  const data = await res.json();
  if (data.ok) renderStats(data);
}

async function loadFiles() {
  const res = await fetch("/api/files");
  const data = await res.json();
  filesEl.innerHTML = "";

  if (!data.ok || !data.files.length) {
    emptyEl.hidden = false;
    return;
  }

  emptyEl.hidden = true;
  for (const file of data.files) {
    const li = document.createElement("li");
    const title = escapeHtml(file.title || file.name);
    const size = formatSize(file.size);
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "download-btn";
    btn.textContent = "تحميل";
    btn.addEventListener("click", () => triggerDownload(file.id, file.name));

    const meta = document.createElement("div");
    meta.className = "file-meta";
    meta.innerHTML = `<strong>${title}</strong><span>${size}</span>`;

    li.appendChild(meta);
    li.appendChild(btn);
    filesEl.appendChild(li);
  }
}

function escapeHtml(str) {
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function pollStatus(jobId) {
  while (true) {
    const res = await fetch(`/api/status/${jobId}`);
    const data = await res.json();

    if (!data.ok) {
      setStatus(true, data.error || "حدث خطأ", 0, "error");
      return null;
    }

    if (data.status === "queued") {
      setStatus(true, "في قائمة الانتظار...", data.progress || 2);
    } else if (data.status === "downloading") {
      setStatus(true, "جاري التنزيل من يوتيوب...", data.progress || 10);
    } else if (data.status === "converting") {
      setStatus(true, "جاري التحويل إلى MP3...", data.progress || 92);
    } else if (data.status === "done") {
      setStatus(true, `جاهز: ${data.filename}`, 100, "done");
      return data;
    } else if (data.status === "error") {
      setStatus(true, data.error || "فشل التنزيل", 0, "error");
      return null;
    }

    await new Promise((r) => setTimeout(r, 900));
  }
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const url = urlInput.value.trim();
  if (!url) return;

  submitBtn.disabled = true;
  setStatus(true, "بدء المهمة...", 1);

  try {
    const res = await fetch("/api/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    const data = await res.json();

    if (!data.ok) {
      setStatus(true, data.error || "تعذر بدء التنزيل", 0, "error");
      return;
    }

    const result = await pollStatus(data.job_id);
    if (result) {
      urlInput.value = "";
      triggerDownload(result.file_id || data.job_id, result.filename);
      await Promise.all([loadFiles(), loadStats()]);
    }
  } catch (err) {
    setStatus(
      true,
      "تعذر الاتصال بالخادم. لا تستخدم Netlify — شغّل start.bat أو publish-online.bat",
      0,
      "error"
    );
  } finally {
    submitBtn.disabled = false;
  }
});

trackVisit().catch(() => {
  setStatus(
    true,
    "الخادم غير متصل. شغّل start.bat محلياً أو publish-online.bat للنشر",
    0,
    "error"
  );
});
loadFiles().catch(() => {});
