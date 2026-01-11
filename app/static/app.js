const statusEl = document.getElementById("status");
const apiKeyEl = document.getElementById("apiKey");

const modelDisplay = document.getElementById("modelDisplay");
const voiceSelect = document.getElementById("voiceSelect");
const formatSelect = document.getElementById("formatSelect");
const textInput = document.getElementById("textInput");
const generateBtn = document.getElementById("generate");

const audioPlayer = document.getElementById("audioPlayer");
const downloadLink = document.getElementById("downloadLink");
const originalGenerateBtnText = generateBtn.textContent || "生成";

let currentAudioUrl = null;
let currentModelId = "";

function setStatus(msg, isError = false) {
  statusEl.textContent = msg || "";
  statusEl.classList.toggle("muted", !isError);
  statusEl.style.color = isError ? "#ff8b97" : "";
}

function getAuthHeaders() {
  const key = (localStorage.getItem("vibevoice_api_key") || "").trim();
  if (!key) return {};
  return { Authorization: `Bearer ${key}` };
}

async function fetchJson(url, opts = {}) {
  const res = await fetch(url, {
    ...opts,
    headers: {
      ...(opts.headers || {}),
      ...getAuthHeaders(),
    },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return await res.json();
}

async function refreshLists() {
  setStatus("正在刷新...");
  try {
    const models = await fetchJson("/v1/models");
    const firstModel = (models.data || [])[0];
    currentModelId = (firstModel && firstModel.id) || "";
    modelDisplay.value = currentModelId || "(unknown)";

    const voices = await fetchJson("/v1/voices");
    voiceSelect.innerHTML = "";
    for (const v of voices.data || []) {
      const opt = document.createElement("option");
      opt.value = v.id;
      opt.textContent = `${v.name} (${v.type})`;
      voiceSelect.appendChild(opt);
    }

    setStatus("刷新完成");
  } catch (e) {
    setStatus(String(e), true);
  }
}

document.getElementById("refresh").addEventListener("click", refreshLists);

document.getElementById("saveApiKey").addEventListener("click", () => {
  const key = apiKeyEl.value.trim();
  if (key) {
    localStorage.setItem("vibevoice_api_key", key);
    setStatus("API Key 已保存");
  } else {
    setStatus("请输入 API Key", true);
  }
});

document.getElementById("clearApiKey").addEventListener("click", () => {
  localStorage.removeItem("vibevoice_api_key");
  apiKeyEl.value = "";
  setStatus("API Key 已清除");
});

async function generateSpeech() {
  const voice = voiceSelect.value;
  const response_format = formatSelect.value;
  const input = textInput.value;

  if (!input.trim()) {
    setStatus("请输入文本", true);
    return;
  }
  if (!voice) {
    setStatus("请选择音色", true);
    return;
  }

  const startedAt = Date.now();
  let timer = null;
  const updateElapsed = () => {
    const elapsedSec = Math.floor((Date.now() - startedAt) / 1000);
    let msg = `生成中，请稍候...（${elapsedSec}s）`;
    if (elapsedSec >= 10) {
      msg += " 首次加载模型（尤其 7B 或 CPU）可能需要更久";
    }
    setStatus(msg);
  };

  updateElapsed();
  timer = setInterval(updateElapsed, 1000);

  generateBtn.disabled = true;
  generateBtn.textContent = "生成中...";

  downloadLink.style.display = "none";
  if (currentAudioUrl) {
    URL.revokeObjectURL(currentAudioUrl);
    currentAudioUrl = null;
  }
  audioPlayer.removeAttribute("src");

  try {
    const body = {
      voice,
      input,
      response_format,
    };
    if (currentModelId) {
      body.model = currentModelId;
    }
    const res = await fetch("/v1/audio/speech", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...getAuthHeaders(),
      },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`${res.status} ${res.statusText}: ${text}`);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    currentAudioUrl = url;
    audioPlayer.src = url;
    audioPlayer.play().catch(() => {});

    const ext = response_format === "mp3" ? "mp3" : "wav";
    downloadLink.href = url;
    downloadLink.download = `vibevoice.${ext}`;
    downloadLink.style.display = "inline-block";

    setStatus("生成完成");
  } catch (e) {
    setStatus(String(e), true);
  } finally {
    if (timer) clearInterval(timer);
    generateBtn.disabled = false;
    generateBtn.textContent = originalGenerateBtnText;
  }
}

generateBtn.addEventListener("click", generateSpeech);

async function createVoice() {
  const name = document.getElementById("voiceName").value.trim();
  const fileInput = document.getElementById("voiceFile");
  const file = fileInput.files && fileInput.files[0];

  if (!name) {
    setStatus("请输入音色名称", true);
    return;
  }
  if (!file) {
    setStatus("请选择参考音频文件", true);
    return;
  }

  setStatus("创建音色中...");
  try {
    const form = new FormData();
    form.append("name", name);
    form.append("file", file, file.name);

    const res = await fetch("/v1/voices", {
      method: "POST",
      headers: {
        ...getAuthHeaders(),
      },
      body: form,
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`${res.status} ${res.statusText}: ${text}`);
    }

    await refreshLists();
    setStatus("创建成功");
  } catch (e) {
    setStatus(String(e), true);
  }
}

document.getElementById("createVoice").addEventListener("click", createVoice);

async function deleteSelectedVoice() {
  const voiceId = voiceSelect.value;
  if (!voiceId) {
    setStatus("请选择要删除的音色", true);
    return;
  }
  if (!confirm(`确认删除音色：${voiceId} ?`)) return;

  setStatus("删除中...");
  try {
    const res = await fetch(`/v1/voices/${encodeURIComponent(voiceId)}`, {
      method: "DELETE",
      headers: {
        ...getAuthHeaders(),
      },
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`${res.status} ${res.statusText}: ${text}`);
    }
    await refreshLists();
    setStatus("删除成功");
  } catch (e) {
    setStatus(String(e), true);
  }
}

document.getElementById("deleteVoice").addEventListener("click", deleteSelectedVoice);

function init() {
  const savedKey = localStorage.getItem("vibevoice_api_key") || "";
  apiKeyEl.value = savedKey;
  refreshLists();
}

init();
