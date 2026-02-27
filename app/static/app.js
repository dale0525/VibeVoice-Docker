const REFERENCE_VOICE_ID = "__reference_audio__";
const INPUT_MODE_VISUAL = "visual";
const INPUT_MODE_SCRIPT = "script";
const INPUT_MODE_STORAGE_KEY = "vibevoice_input_mode";
const SCRIPT_LINE_HINT_MAX = 150;

const VOICE_TAG_LINE_RE = /^\s*\[([^\[\]\r\n]+)\]\s*(.*)$/;
const SPEAKER_LINE_RE = /^\s*speaker\s*\d+\s*:\s*(.*)$/i;

const statusEl = document.getElementById("status");
const apiKeyEl = document.getElementById("apiKey");

const modelDisplay = document.getElementById("modelDisplay");
const voiceSelect = document.getElementById("voiceSelect");
const formatSelect = document.getElementById("formatSelect");
const textInput = document.getElementById("textInput");
const generateBtn = document.getElementById("generate");

const modeVisualBtn = document.getElementById("modeVisual");
const modeScriptBtn = document.getElementById("modeScript");
const visualModePanelEl = document.getElementById("visualModePanel");
const scriptModePanelEl = document.getElementById("scriptModePanel");
const segmentEditorEl = document.getElementById("segmentEditor");
const addSegmentBtn = document.getElementById("addSegment");
const clearSegmentsBtn = document.getElementById("clearSegments");
const exportSegmentsToScriptBtn = document.getElementById("exportSegmentsToScript");
const segmentSummaryEl = document.getElementById("segmentSummary");
const insertScriptTemplateBtn = document.getElementById("insertScriptTemplate");
const scriptParseSummaryEl = document.getElementById("scriptParseSummary");

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
let voiceList = [];
let managePromptSaving = false;
let inputMode = INPUT_MODE_VISUAL;
let visualSegments = [];

function setStatus(msg, isError = false) {
  statusEl.textContent = msg || "";
  statusEl.classList.toggle("muted", !isError);
  statusEl.style.color = isError ? "#ff8b97" : "";
}

function setScriptSummary(msg, isError = false) {
  if (!scriptParseSummaryEl) return;
  scriptParseSummaryEl.textContent = msg || "";
  scriptParseSummaryEl.classList.toggle("muted", !isError);
  scriptParseSummaryEl.style.color = isError ? "#ff8b97" : "";
}

function setSegmentSummary(msg, isWarn = false) {
  if (!segmentSummaryEl) return;
  segmentSummaryEl.textContent = msg || "";
  segmentSummaryEl.classList.toggle("muted", !isWarn);
  segmentSummaryEl.style.color = isWarn ? "#ffb36b" : "";
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

function getRegularVoiceIds() {
  return voiceList.map((v) => v.id);
}

function getFirstRegularVoiceId() {
  return voiceList.length > 0 ? voiceList[0].id : "";
}

function normalizeInputMode(mode) {
  return mode === INPUT_MODE_SCRIPT ? INPUT_MODE_SCRIPT : INPUT_MODE_VISUAL;
}

function persistInputMode() {
  localStorage.setItem(INPUT_MODE_STORAGE_KEY, inputMode);
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
  const canSave =
    inputMode === INPUT_MODE_SCRIPT &&
    isReferenceMode() &&
    hasVoiceName &&
    currentRefKey &&
    currentRefKey === lastReferenceGenerationKey;
  saveReferenceVoiceBtn.disabled = !canSave;
}

function resetReferenceGenerationState() {
  lastReferenceGenerationKey = "";
  updateSaveReferenceState();
}

function updateReferenceModeUI() {
  const inScriptMode = inputMode === INPUT_MODE_SCRIPT;
  const referenceOption = Array.from(voiceSelect.options).find((option) => option.value === REFERENCE_VOICE_ID);
  if (referenceOption) {
    referenceOption.disabled = !inScriptMode;
  }

  if (inputMode === INPUT_MODE_VISUAL && isReferenceMode()) {
    const fallbackVoiceId = getFirstRegularVoiceId();
    if (fallbackVoiceId) {
      voiceSelect.value = fallbackVoiceId;
      setStatus("可视化编排不支持参考音频模式，已切回普通音色");
    }
  }

  const enabled = inScriptMode && isReferenceMode();
  referenceInputsEl.style.display = enabled ? "grid" : "none";
  if (!enabled) {
    resetReferenceGenerationState();
  } else {
    updateSaveReferenceState();
  }

  updateScriptParseSummary();
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
    voiceList = voicesResp.data || [];
    voicesById = {};
    for (const v of voiceList) {
      voicesById[v.id] = v;
    }

    const prevVoiceId = preferredVoiceId || voiceSelect.value;
    voiceSelect.innerHTML = "";
    const refOpt = document.createElement("option");
    refOpt.value = REFERENCE_VOICE_ID;
    refOpt.textContent = "参考音频（先试听，满意后保存）";
    voiceSelect.appendChild(refOpt);
    for (const v of voiceList) {
      const opt = document.createElement("option");
      opt.value = v.id;
      opt.textContent = `${v.name} (${v.type})`;
      voiceSelect.appendChild(opt);
    }
    const voiceValues = new Set(Array.from(voiceSelect.options).map((x) => x.value));
    if (prevVoiceId && voiceValues.has(prevVoiceId)) {
      voiceSelect.value = prevVoiceId;
    } else if (voiceList.length > 0) {
      voiceSelect.value = voiceList[0].id;
    } else {
      voiceSelect.value = REFERENCE_VOICE_ID;
    }

    const prevManageVoiceId = preferredManageVoiceId || manageVoiceSelect.value;
    manageVoiceSelect.innerHTML = "";
    for (const v of voiceList) {
      const opt = document.createElement("option");
      opt.value = v.id;
      opt.textContent = `${v.name} (${v.type})`;
      manageVoiceSelect.appendChild(opt);
    }
    const manageValues = new Set(Array.from(manageVoiceSelect.options).map((x) => x.value));
    if (prevManageVoiceId && manageValues.has(prevManageVoiceId)) {
      manageVoiceSelect.value = prevManageVoiceId;
    } else if (voiceList.length > 0) {
      manageVoiceSelect.value = voiceList[0].id;
    }

    reconcileVisualSegmentsWithVoices();
    updateInputModeUI();
    updateManageVoiceUI();
    updateScriptParseSummary();
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

function getVisualNonEmptySegments() {
  const out = [];
  for (let i = 0; i < visualSegments.length; i += 1) {
    const segment = visualSegments[i];
    if ((segment.text || "").trim()) {
      out.push({ index: i, segment });
    }
  }
  return out;
}

function buildSegmentReferenceSignature(segment) {
  if (!segment || !segment.referenceFile) {
    return "";
  }
  const file = segment.referenceFile;
  const prompt = (segment.referencePromptText || "").trim();
  return `${file.name}|${file.size}|${file.lastModified}|${prompt}`;
}

async function createTemporaryVoiceFromSegment(segment, tempIndex) {
  const file = segment.referenceFile;
  if (!file) {
    throw new Error("参考音频文件缺失");
  }

  const name = `tmp-ref-${Date.now()}-${tempIndex}`;
  const form = new FormData();
  form.append("name", name);
  form.append("file", file, file.name);
  const promptText = (segment.referencePromptText || "").trim();
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
  return await res.json();
}

async function cleanupTemporaryVoices(voiceIds) {
  const uniqueIds = Array.from(new Set((voiceIds || []).filter(Boolean)));
  if (!uniqueIds.length) {
    return;
  }

  const tasks = uniqueIds.map(async (voiceId) => {
    try {
      await fetch(`/v1/voices/${encodeURIComponent(voiceId)}`, {
        method: "DELETE",
        headers: {
          ...getAuthHeaders(),
        },
      });
    } catch {
      // best effort cleanup
    }
  });
  await Promise.allSettled(tasks);
}

async function prepareVisualInputWithTemporaryVoices() {
  const active = getVisualNonEmptySegments();
  if (!active.length) {
    throw new Error("请至少填写一个说话段内容");
  }

  const resolvedVoiceByIndex = new Map();
  const signatureToVoiceId = new Map();
  const tempVoiceIds = [];
  let tempCounter = 0;

  for (const item of active) {
    const { index, segment } = item;
    const sourceType = segment.sourceType === "reference" ? "reference" : "voice";

    if (sourceType === "voice") {
      const voiceId = (segment.voiceId || "").trim();
      if (!voiceId || !isKnownVoiceId(voiceId)) {
        throw new Error(`第 ${index + 1} 段的音色无效，请重新选择`);
      }
      resolvedVoiceByIndex.set(index, voiceId);
      continue;
    }

    if (!segment.referenceFile) {
      throw new Error(`第 ${index + 1} 段缺少参考音频文件`);
    }

    const signature = buildSegmentReferenceSignature(segment);
    if (!signature) {
      throw new Error(`第 ${index + 1} 段参考音频参数无效`);
    }

    let tempVoiceId = signatureToVoiceId.get(signature);
    if (!tempVoiceId) {
      tempCounter += 1;
      const created = await createTemporaryVoiceFromSegment(segment, tempCounter);
      tempVoiceId = (created && created.id) || "";
      if (!tempVoiceId) {
        throw new Error(`第 ${index + 1} 段创建临时音色失败`);
      }
      signatureToVoiceId.set(signature, tempVoiceId);
      tempVoiceIds.push(tempVoiceId);
    }
    resolvedVoiceByIndex.set(index, tempVoiceId);
  }

  const input = serializeSegmentsToScript({
    includeEmpty: false,
    voiceIdResolver: (_, index) => resolvedVoiceByIndex.get(index) || "",
  });

  if (!input.trim()) {
    throw new Error("没有可生成的有效内容");
  }

  return {
    input,
    tempVoiceIds,
    tempVoiceCount: tempVoiceIds.length,
  };
}

async function generateSpeech() {
  const voice = voiceSelect.value;
  const response_format = formatSelect.value;
  let input = "";
  let tempVoiceIds = [];

  if (!voice) {
    setStatus("请选择默认音色", true);
    return;
  }

  if (inputMode === INPUT_MODE_VISUAL) {
    if (isReferenceMode()) {
      setStatus("可视化编排不支持参考音频模式", true);
      return;
    }
    try {
      setStatus("正在准备可视化脚本...");
      const prepared = await prepareVisualInputWithTemporaryVoices();
      input = prepared.input;
      tempVoiceIds = prepared.tempVoiceIds;
      if (prepared.tempVoiceCount > 0) {
        setStatus(`已创建 ${prepared.tempVoiceCount} 个临时参考音色，开始生成...`);
      }
    } catch (e) {
      setStatus(String(e), true);
      if (tempVoiceIds.length) {
        await cleanupTemporaryVoices(tempVoiceIds);
      }
      return;
    }
  } else {
    input = textInput.value;
  }

  if (inputMode === INPUT_MODE_SCRIPT) {
    const analysis = analyzeScriptInput(input, voice);
    if (!analysis.ok) {
      setStatus(formatAnalysisError(analysis), true);
      return;
    }
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
    if (tempVoiceIds.length) {
      await cleanupTemporaryVoices(tempVoiceIds);
      await refreshLists(voiceSelect.value, manageVoiceSelect.value);
    }
    if (timer) clearInterval(timer);
    generateBtn.disabled = false;
    generateBtn.textContent = originalGenerateBtnText;
  }
}

generateBtn.addEventListener("click", generateSpeech);

async function saveReferenceVoice() {
  if (inputMode !== INPUT_MODE_SCRIPT || !isReferenceMode()) {
    setStatus('请先切换到“脚本模式”，并在音色里选择“参考音频”', true);
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

voiceSelect.addEventListener("change", () => {
  updateReferenceModeUI();
  reconcileVisualSegmentsWithVoices();
  if (inputMode === INPUT_MODE_VISUAL) {
    renderSegmentEditor();
  }
  updateScriptParseSummary();
});
voiceNameEl.addEventListener("input", updateSaveReferenceState);
referenceVoiceFileEl.addEventListener("change", resetReferenceGenerationState);
referenceVoicePromptTextEl.addEventListener("input", resetReferenceGenerationState);
manageVoiceSelect.addEventListener("change", updateManageVoiceUI);
manageVoicePromptTextEl.addEventListener("blur", () => {
  saveManagedVoicePromptText({ silent: true, skipIfUnchanged: true });
});

if (textInput) {
  textInput.addEventListener("input", () => {
    updateScriptParseSummary();
    resetReferenceGenerationState();
  });
}

if (segmentEditorEl) {
  segmentEditorEl.addEventListener("input", handleSegmentEditorInput);
  segmentEditorEl.addEventListener("change", handleSegmentEditorChange);
  segmentEditorEl.addEventListener("click", handleSegmentEditorClick);
}

bindClick(modeVisualBtn, switchToVisualMode);
bindClick(modeScriptBtn, () => switchToScriptMode({ syncFromVisual: true }));
bindClick(addSegmentBtn, addSegment);
bindClick(clearSegmentsBtn, clearSegments);
bindClick(exportSegmentsToScriptBtn, exportSegmentsToScript);
bindClick(insertScriptTemplateBtn, insertScriptTemplate);

function init() {
  const savedKey = localStorage.getItem("vibevoice_api_key") || "";
  apiKeyEl.value = savedKey;

  inputMode = normalizeInputMode(localStorage.getItem(INPUT_MODE_STORAGE_KEY));
  visualSegments = [createEmptySegment()];

  saveReferenceVoiceBtn.disabled = true;
  updateInputModeUI();
  refreshLists();
}

window.addEventListener("beforeunload", revokeAudioUrls);

init();
