const REFERENCE_VOICE_ID = "__reference_audio__";

const statusEl = document.getElementById("status");
const apiKeyEl = document.getElementById("apiKey");

const modelDisplay = document.getElementById("modelDisplay");
const voiceSelect = document.getElementById("voiceSelect");
const formatSelect = document.getElementById("formatSelect");
const textInput = document.getElementById("textInput");
const generateBtn = document.getElementById("generate");

const referenceInputsEl = document.getElementById("referenceInputs");
const referenceVoiceFileEl = document.getElementById("referenceVoiceFile");
const referenceVoicePromptTextEl = document.getElementById("referenceVoicePromptText");

const voiceNameEl = document.getElementById("voiceName");
const saveReferenceVoiceBtn = document.getElementById("saveReferenceVoice");

const manageVoiceSelect = document.getElementById("manageVoiceSelect");
const manageVoicePromptTextEl = document.getElementById("manageVoicePromptText");
const previewVoiceSampleBtn = document.getElementById("previewVoiceSample");
const saveVoicePromptTextBtn = document.getElementById("saveVoicePromptText");
const deleteVoiceBtn = document.getElementById("deleteVoice");
const voiceSamplePlayer = document.getElementById("voiceSamplePlayer");

const audioPlayer = document.getElementById("audioPlayer");
const downloadLink = document.getElementById("downloadLink");
const refreshBtn = document.getElementById("refresh");
const saveApiKeyBtn = document.getElementById("saveApiKey");
const clearApiKeyBtn = document.getElementById("clearApiKey");
const originalGenerateBtnText = generateBtn.textContent || "生成";

let currentAudioUrl = null;
let currentVoiceSampleUrl = null;
let currentModelId = "";
let lastReferenceGenerationKey = "";
let voicesById = {};
let managePromptSaving = false;

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

function bindClick(el, handler) {
  if (!el) return;
  el.addEventListener("click", handler);
}

function isReferenceMode() {
  return voiceSelect.value === REFERENCE_VOICE_ID;
}

function getReferenceFile() {
  return referenceVoiceFileEl.files && referenceVoiceFileEl.files[0];
}

function getReferenceGenerationKey() {
  const file = getReferenceFile();
  if (!file) return "";
  const promptText = referenceVoicePromptTextEl.value.trim();
  return `${file.name}|${file.size}|${file.lastModified}|${promptText}`;
}

function getSelectedManagedVoice() {
  const voiceId = manageVoiceSelect.value;
  return voiceId ? voicesById[voiceId] || null : null;
}

function normalizePromptText(value) {
  return (value || "").trim();
}

function revokeAudioUrls() {
  if (currentAudioUrl) {
    URL.revokeObjectURL(currentAudioUrl);
    currentAudioUrl = null;
  }
  if (currentVoiceSampleUrl) {
    URL.revokeObjectURL(currentVoiceSampleUrl);
    currentVoiceSampleUrl = null;
  }
}

function updateSaveReferenceState() {
  const hasVoiceName = !!voiceNameEl.value.trim();
  const currentRefKey = getReferenceGenerationKey();
  const canSave = isReferenceMode() && hasVoiceName && currentRefKey && currentRefKey === lastReferenceGenerationKey;
  saveReferenceVoiceBtn.disabled = !canSave;
}

function resetReferenceGenerationState() {
  lastReferenceGenerationKey = "";
  updateSaveReferenceState();
}

function updateReferenceModeUI() {
  const enabled = isReferenceMode();
  referenceInputsEl.style.display = enabled ? "grid" : "none";
  if (!enabled) {
    resetReferenceGenerationState();
  } else {
    updateSaveReferenceState();
  }
}

function updateManageVoiceUI() {
  const voice = getSelectedManagedVoice();
  if (!voice) {
    manageVoicePromptTextEl.value = "";
    manageVoicePromptTextEl.placeholder = "暂无已保存音色";
    manageVoicePromptTextEl.readOnly = true;
    previewVoiceSampleBtn.disabled = true;
    saveVoicePromptTextBtn.disabled = true;
    deleteVoiceBtn.disabled = true;
    return;
  }

  manageVoicePromptTextEl.value = voice.prompt_text || "";
  if (voice.type === "builtin") {
    manageVoicePromptTextEl.placeholder = "内置音色不支持编辑";
    manageVoicePromptTextEl.readOnly = true;
    saveVoicePromptTextBtn.disabled = true;
    deleteVoiceBtn.disabled = true;
  } else {
    manageVoicePromptTextEl.placeholder = "失焦自动保存，也可手动点击“保存参考文本”";
    manageVoicePromptTextEl.readOnly = false;
    saveVoicePromptTextBtn.disabled = false;
    deleteVoiceBtn.disabled = false;
  }
  previewVoiceSampleBtn.disabled = false;
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

async function refreshLists(preferredVoiceId = "", preferredManageVoiceId = "") {
  setStatus("正在刷新...");
  try {
    const models = await fetchJson("/v1/models");
    const firstModel = (models.data || [])[0];
    currentModelId = (firstModel && firstModel.id) || "";
    modelDisplay.value = currentModelId || "(unknown)";

    const voicesResp = await fetchJson("/v1/voices");
    const voices = voicesResp.data || [];
    voicesById = {};
    for (const v of voices) {
      voicesById[v.id] = v;
    }

    const prevVoiceId = preferredVoiceId || voiceSelect.value;
    voiceSelect.innerHTML = "";
    const refOpt = document.createElement("option");
    refOpt.value = REFERENCE_VOICE_ID;
    refOpt.textContent = "参考音频（先试听，满意后保存）";
    voiceSelect.appendChild(refOpt);
    for (const v of voices) {
      const opt = document.createElement("option");
      opt.value = v.id;
      opt.textContent = `${v.name} (${v.type})`;
      voiceSelect.appendChild(opt);
    }
    const voiceValues = new Set(Array.from(voiceSelect.options).map((x) => x.value));
    if (prevVoiceId && voiceValues.has(prevVoiceId)) {
      voiceSelect.value = prevVoiceId;
    } else if (voices.length > 0) {
      voiceSelect.value = voices[0].id;
    } else {
      voiceSelect.value = REFERENCE_VOICE_ID;
    }

    const prevManageVoiceId = preferredManageVoiceId || manageVoiceSelect.value;
    manageVoiceSelect.innerHTML = "";
    for (const v of voices) {
      const opt = document.createElement("option");
      opt.value = v.id;
      opt.textContent = `${v.name} (${v.type})`;
      manageVoiceSelect.appendChild(opt);
    }
    const manageValues = new Set(Array.from(manageVoiceSelect.options).map((x) => x.value));
    if (prevManageVoiceId && manageValues.has(prevManageVoiceId)) {
      manageVoiceSelect.value = prevManageVoiceId;
    } else if (voices.length > 0) {
      manageVoiceSelect.value = voices[0].id;
    }

    updateReferenceModeUI();
    updateManageVoiceUI();
    setStatus("刷新完成");
  } catch (e) {
    setStatus(String(e), true);
  }
}

if (!refreshBtn || !saveApiKeyBtn || !clearApiKeyBtn) {
  console.warn("[TTS-Docker] Missing toolbar controls in DOM; some button actions are not bound.");
}

bindClick(refreshBtn, () => refreshLists());

bindClick(saveApiKeyBtn, () => {
  const key = apiKeyEl.value.trim();
  if (key) {
    localStorage.setItem("vibevoice_api_key", key);
    setStatus("API Key 已保存");
  } else {
    setStatus("请输入 API Key", true);
  }
});

bindClick(clearApiKeyBtn, () => {
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
  if (isReferenceMode() && !getReferenceFile()) {
    setStatus("参考音频模式下，请先上传参考音频", true);
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
    let res;
    if (isReferenceMode()) {
      const form = new FormData();
      const refFile = getReferenceFile();
      form.append("file", refFile, refFile.name);
      form.append("input", input);
      form.append("response_format", response_format);
      const refPromptText = referenceVoicePromptTextEl.value.trim();
      if (refPromptText) {
        form.append("prompt_text", refPromptText);
      }
      res = await fetch("/v1/audio/speech/reference", {
        method: "POST",
        headers: {
          ...getAuthHeaders(),
        },
        body: form,
      });
    } else {
      const body = {
        voice,
        input,
        response_format,
      };
      if (currentModelId) {
        body.model = currentModelId;
      }
      res = await fetch("/v1/audio/speech", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...getAuthHeaders(),
        },
        body: JSON.stringify(body),
      });
    }

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

    if (isReferenceMode()) {
      lastReferenceGenerationKey = getReferenceGenerationKey();
      updateSaveReferenceState();
      setStatus("生成完成。若效果满意，可填写“新音色名称”并点击“保存当前参考音频为音色”");
    } else {
      resetReferenceGenerationState();
      setStatus("生成完成");
    }
  } catch (e) {
    setStatus(String(e), true);
  } finally {
    if (timer) clearInterval(timer);
    generateBtn.disabled = false;
    generateBtn.textContent = originalGenerateBtnText;
  }
}

generateBtn.addEventListener("click", generateSpeech);

async function saveReferenceVoice() {
  if (!isReferenceMode()) {
    setStatus('请先在音色里选择“参考音频”', true);
    return;
  }

  const name = voiceNameEl.value.trim();
  const file = getReferenceFile();
  const promptText = referenceVoicePromptTextEl.value.trim();
  const currentRefKey = getReferenceGenerationKey();

  if (!name) {
    setStatus("请输入新音色名称", true);
    return;
  }
  if (!file) {
    setStatus("请先上传参考音频", true);
    return;
  }
  if (!lastReferenceGenerationKey || currentRefKey !== lastReferenceGenerationKey) {
    setStatus("参考音频或提示词已变化，请先重新生成并确认效果再保存", true);
    return;
  }

  setStatus("保存音色中...");
  try {
    const form = new FormData();
    form.append("name", name);
    form.append("file", file, file.name);
    if (promptText) {
      form.append("prompt_text", promptText);
    }

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

    const created = await res.json();
    await refreshLists(created.id || "", created.id || "");
    voiceNameEl.value = "";
    resetReferenceGenerationState();
    setStatus(`保存成功：${created.name || created.id}`);
  } catch (e) {
    setStatus(String(e), true);
  }
}

saveReferenceVoiceBtn.addEventListener("click", saveReferenceVoice);

async function previewManagedVoiceSample() {
  const voice = getSelectedManagedVoice();
  if (!voice) {
    setStatus("请选择要试听的音色", true);
    return;
  }

  setStatus(`正在加载 ${voice.name} 的参考音频...`);
  try {
    const res = await fetch(`/v1/voices/${encodeURIComponent(voice.id)}/sample`, {
      method: "GET",
      headers: {
        ...getAuthHeaders(),
      },
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`${res.status} ${res.statusText}: ${text}`);
    }

    const blob = await res.blob();
    if (currentVoiceSampleUrl) {
      URL.revokeObjectURL(currentVoiceSampleUrl);
      currentVoiceSampleUrl = null;
    }
    const sampleUrl = URL.createObjectURL(blob);
    currentVoiceSampleUrl = sampleUrl;
    voiceSamplePlayer.src = sampleUrl;
    voiceSamplePlayer.play().catch(() => {});
    setStatus(`正在试听：${voice.name}`);
  } catch (e) {
    setStatus(String(e), true);
  }
}

previewVoiceSampleBtn.addEventListener("click", previewManagedVoiceSample);

async function saveManagedVoicePromptText(options = {}) {
  const { silent = false, skipIfUnchanged = false } = options;
  const voice = getSelectedManagedVoice();
  if (!voice) {
    if (!silent) {
      setStatus("请选择要编辑的音色", true);
    }
    return false;
  }
  if (voice.type === "builtin") {
    if (!silent) {
      setStatus("内置音色不支持编辑参考文本", true);
    }
    return false;
  }

  const nextPromptText = normalizePromptText(manageVoicePromptTextEl.value);
  const currentPromptText = normalizePromptText(voice.prompt_text || "");
  if (skipIfUnchanged && nextPromptText === currentPromptText) {
    return true;
  }

  if (managePromptSaving) {
    return false;
  }

  managePromptSaving = true;
  if (!silent) {
    setStatus("保存参考文本中...");
  }
  try {
    const body = {
      prompt_text: nextPromptText || null,
    };

    const res = await fetch(`/v1/voices/${encodeURIComponent(voice.id)}`, {
      method: "PATCH",
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

    await refreshLists(voiceSelect.value, voice.id);
    if (!silent) {
      setStatus("参考文本已保存");
    }
    return true;
  } catch (e) {
    if (silent) {
      setStatus(`自动保存失败：${String(e)}`, true);
    } else {
      setStatus(String(e), true);
    }
    return false;
  } finally {
    managePromptSaving = false;
  }
}

saveVoicePromptTextBtn.addEventListener("click", () => {
  saveManagedVoicePromptText();
});

async function deleteManagedVoice() {
  const voice = getSelectedManagedVoice();
  if (!voice) {
    setStatus("请选择要删除的音色", true);
    return;
  }
  if (voice.type === "builtin") {
    setStatus("内置音色不可删除", true);
    return;
  }
  if (!confirm(`确认删除音色：${voice.id} ?`)) return;

  setStatus("删除中...");
  try {
    const res = await fetch(`/v1/voices/${encodeURIComponent(voice.id)}`, {
      method: "DELETE",
      headers: {
        ...getAuthHeaders(),
      },
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`${res.status} ${res.statusText}: ${text}`);
    }

    if (voiceSelect.value === voice.id) {
      voiceSelect.value = REFERENCE_VOICE_ID;
    }
    await refreshLists(voiceSelect.value, "");
    setStatus("删除成功");
  } catch (e) {
    setStatus(String(e), true);
  }
}

deleteVoiceBtn.addEventListener("click", deleteManagedVoice);

voiceSelect.addEventListener("change", updateReferenceModeUI);
voiceNameEl.addEventListener("input", updateSaveReferenceState);
referenceVoiceFileEl.addEventListener("change", resetReferenceGenerationState);
referenceVoicePromptTextEl.addEventListener("input", resetReferenceGenerationState);
manageVoiceSelect.addEventListener("change", updateManageVoiceUI);
manageVoicePromptTextEl.addEventListener("blur", () => {
  saveManagedVoicePromptText({ silent: true, skipIfUnchanged: true });
});

function init() {
  const savedKey = localStorage.getItem("vibevoice_api_key") || "";
  apiKeyEl.value = savedKey;
  saveReferenceVoiceBtn.disabled = true;
  refreshLists();
}

window.addEventListener("beforeunload", revokeAudioUrls);

init();
