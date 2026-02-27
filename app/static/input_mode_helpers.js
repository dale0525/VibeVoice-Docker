function escapeHtml(value) {
  return (value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function isKnownVoiceId(voiceId) {
  return !!voiceId && !!voicesById[voiceId];
}

function getVisualFallbackVoiceId() {
  if (voiceSelect.value && voiceSelect.value !== REFERENCE_VOICE_ID && isKnownVoiceId(voiceSelect.value)) {
    return voiceSelect.value;
  }
  return getFirstRegularVoiceId();
}

function createEmptySegment(preferredVoiceId = "") {
  const fallbackVoiceId = preferredVoiceId || getVisualFallbackVoiceId() || "";
  return {
    sourceType: "voice",
    voiceId: fallbackVoiceId,
    text: "",
    referenceFile: null,
    referencePromptText: "",
  };
}

function serializeSegmentsToScript(options = {}) {
  const { includeEmpty = false, voiceIdResolver = null } = options;
  const fallbackVoiceId = getVisualFallbackVoiceId();
  const lines = [];

  for (let index = 0; index < visualSegments.length; index += 1) {
    const segment = visualSegments[index];
    const text = (segment.text || "").trim();
    const preferredVoiceId = (segment.voiceId || "").trim() || fallbackVoiceId;
    const resolvedVoiceId = voiceIdResolver ? voiceIdResolver(segment, index) : preferredVoiceId;
    const voiceId = (resolvedVoiceId || "").trim();

    if (!voiceId) {
      continue;
    }
    if (!text && !includeEmpty) {
      continue;
    }
    lines.push(text ? `[${voiceId}]${text}` : `[${voiceId}]`);
  }

  return lines.join("\n");
}

function parseInputToSegments(rawInput, fallbackVoiceId) {
  const lines = (rawInput || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line);

  let currentVoiceId = (fallbackVoiceId || "").trim();
  const segments = [];
  let hasVoiceTags = false;

  for (const line of lines) {
    let text = line;

    const voiceTagMatch = line.match(VOICE_TAG_LINE_RE);
    if (voiceTagMatch) {
      hasVoiceTags = true;
      const nextVoiceId = (voiceTagMatch[1] || "").trim();
      if (nextVoiceId) {
        currentVoiceId = nextVoiceId;
      }
      text = (voiceTagMatch[2] || "").trim();
    } else {
      const speakerMatch = line.match(SPEAKER_LINE_RE);
      if (speakerMatch) {
        text = (speakerMatch[1] || "").trim();
      }
    }

    const cleaned = (text || "").trim();
    if (!cleaned) {
      continue;
    }

    segments.push({
      voiceId: currentVoiceId || (fallbackVoiceId || ""),
      sourceType: "voice",
      text: cleaned,
      referenceFile: null,
      referencePromptText: "",
    });
  }

  return {
    segments,
    hasVoiceTags,
  };
}

function collectUnknownVoiceIds(segments, options = {}) {
  const { allowReferenceFallback = false } = options;
  const unknown = new Set();

  for (const seg of segments) {
    const voiceId = (seg.voiceId || "").trim();
    if (!voiceId) {
      unknown.add("(empty)");
      continue;
    }
    if (voiceId === REFERENCE_VOICE_ID && allowReferenceFallback) {
      continue;
    }
    if (!isKnownVoiceId(voiceId)) {
      unknown.add(voiceId);
    }
  }

  return Array.from(unknown);
}

function analyzeScriptInput(rawInput, selectedVoiceId) {
  const input = (rawInput || "").trim();
  const fallbackVoiceId = (selectedVoiceId || "").trim();

  if (!input) {
    return {
      ok: false,
      reason: "empty_input",
      parsed: { segments: [], hasVoiceTags: false },
      unknownVoiceIds: [],
    };
  }

  if (!fallbackVoiceId) {
    return {
      ok: false,
      reason: "missing_default_voice",
      parsed: { segments: [], hasVoiceTags: false },
      unknownVoiceIds: [],
    };
  }

  const parsed = parseInputToSegments(input, fallbackVoiceId);
  if (!parsed.segments.length) {
    return {
      ok: false,
      reason: "no_effective_content",
      parsed,
      unknownVoiceIds: [],
    };
  }

  if (selectedVoiceId === REFERENCE_VOICE_ID && parsed.hasVoiceTags) {
    return {
      ok: false,
      reason: "reference_mode_voice_tags",
      parsed,
      unknownVoiceIds: [],
    };
  }

  const allowReferenceFallback = selectedVoiceId === REFERENCE_VOICE_ID && !parsed.hasVoiceTags;
  const unknownVoiceIds = collectUnknownVoiceIds(parsed.segments, {
    allowReferenceFallback,
  });

  if (unknownVoiceIds.length > 0) {
    return {
      ok: false,
      reason: "unknown_voice_id",
      parsed,
      unknownVoiceIds,
    };
  }

  return {
    ok: true,
    reason: "ok",
    parsed,
    unknownVoiceIds: [],
  };
}

function formatAnalysisError(analysis) {
  if (!analysis || analysis.ok) {
    return "";
  }

  if (analysis.reason === "empty_input") {
    return "请输入文本或脚本内容";
  }
  if (analysis.reason === "missing_default_voice") {
    return "请选择默认音色";
  }
  if (analysis.reason === "no_effective_content") {
    return "输入中未找到有效内容";
  }
  if (analysis.reason === "reference_mode_voice_tags") {
    return "参考音频模式仅支持单说话人脚本，不能包含 [voice_id] 标签";
  }
  if (analysis.reason === "unknown_voice_id") {
    const ids = (analysis.unknownVoiceIds || []).join(", ");
    return `脚本中包含不存在的 voice_id: ${ids}`;
  }
  return "脚本解析失败，请检查输入格式";
}

function reconcileVisualSegmentsWithVoices() {
  const fallbackVoiceId = getVisualFallbackVoiceId();

  if (!visualSegments.length) {
    visualSegments.push(createEmptySegment(fallbackVoiceId));
  }

  for (const segment of visualSegments) {
    if (!segment.sourceType) {
      segment.sourceType = "voice";
    }
    if (typeof segment.referencePromptText !== "string") {
      segment.referencePromptText = "";
    }
    if (!("referenceFile" in segment)) {
      segment.referenceFile = null;
    }
    if (!segment.voiceId || !isKnownVoiceId(segment.voiceId)) {
      segment.voiceId = fallbackVoiceId || "";
    }
  }
}

function buildVoiceOptionsHtml(selectedVoiceId) {
  if (!voiceList.length) {
    return '<option value="">暂无音色</option>';
  }

  return voiceList
    .map((voice) => {
      const selected = voice.id === selectedVoiceId ? " selected" : "";
      return `<option value="${escapeHtml(voice.id)}"${selected}>${escapeHtml(voice.name)} (${escapeHtml(voice.type)})</option>`;
    })
    .join("");
}

function renderSegmentEditor() {
  if (!segmentEditorEl) {
    return;
  }

  reconcileVisualSegmentsWithVoices();

  if (!voiceList.length) {
    segmentEditorEl.innerHTML =
      '<div class="segment-empty">暂无可用音色。请先刷新或新增音色，或切换到脚本模式并使用参考音频。</div>';
    setSegmentSummary("当前无可用音色，无法进行可视化多人编排", true);
    if (addSegmentBtn) {
      addSegmentBtn.disabled = true;
    }
    if (clearSegmentsBtn) {
      clearSegmentsBtn.disabled = true;
    }
    if (exportSegmentsToScriptBtn) {
      exportSegmentsToScriptBtn.disabled = true;
    }
    return;
  }

  if (addSegmentBtn) {
    addSegmentBtn.disabled = false;
  }
  if (clearSegmentsBtn) {
    clearSegmentsBtn.disabled = false;
  }
  if (exportSegmentsToScriptBtn) {
    exportSegmentsToScriptBtn.disabled = false;
  }

  const cards = visualSegments.map((segment, index) => {
    const sourceType = segment.sourceType === "reference" ? "reference" : "voice";
    const text = segment.text || "";
    const charCount = text.trim().length;
    const warn = charCount > SCRIPT_LINE_HINT_MAX;
    const refMissing = sourceType === "reference" && !segment.referenceFile;
    const metaClass = warn ? "segment-meta warn" : "segment-meta";
    let metaText = warn
      ? `当前长度 ${charCount}，超过 ${SCRIPT_LINE_HINT_MAX}。后端会按 SCRIPT_LINE_MAX_CHARS 拆分。`
      : `当前长度 ${charCount}。后端按 SCRIPT_LINE_MAX_CHARS（默认 ${SCRIPT_LINE_HINT_MAX}）处理。`;
    if (sourceType === "reference") {
      const refName = segment.referenceFile ? `已选参考音频: ${segment.referenceFile.name}` : "未选择参考音频文件";
      metaText = `${metaText} · ${refName}`;
    }

    return `
      <div class="segment-item">
        <div class="segment-header">
          <div class="segment-title">说话段 ${index + 1}</div>
          <button class="secondary remove-segment" type="button" data-index="${index}">删除</button>
        </div>
        <div class="segment-grid">
          <label>
            声音来源
            <select class="segment-source" data-index="${index}">
              <option value="voice"${sourceType === "voice" ? " selected" : ""}>音色库</option>
              <option value="reference"${sourceType === "reference" ? " selected" : ""}>参考音频（本次临时）</option>
            </select>
          </label>
          ${
            sourceType === "voice"
              ? `<label>
            音色
            <select class="segment-voice" data-index="${index}">
              ${buildVoiceOptionsHtml(segment.voiceId)}
            </select>
          </label>`
              : `<label>
            参考音频（wav/mp3/flac/m4a/ogg）
            <input class="segment-ref-file" data-index="${index}" type="file" accept=".wav,.mp3,.flac,.m4a,.ogg" />
            <input
              class="segment-ref-prompt"
              data-index="${index}"
              type="text"
              placeholder="参考音频文本（可选）"
              value="${escapeHtml(segment.referencePromptText || "")}"
            />
            <div class="segment-meta ${refMissing ? "warn" : ""}">
              ${segment.referenceFile ? `当前文件：${escapeHtml(segment.referenceFile.name)}` : "请上传参考音频"}
            </div>
          </label>`
          }
        </div>
        <div class="segment-grid">
          <label>
            内容
            <textarea class="segment-text" data-index="${index}" rows="3">${escapeHtml(text)}</textarea>
          </label>
        </div>
        <div class="${metaClass}">${metaText}</div>
      </div>
    `;
  });

  segmentEditorEl.innerHTML = cards.join("");

  const nonEmptySegments = visualSegments.filter((seg) => (seg.text || "").trim());
  if (!nonEmptySegments.length) {
    setSegmentSummary("请至少填写一个说话段内容");
    return;
  }

  const usedVoiceIds = new Set(nonEmptySegments.map((seg) => seg.voiceId).filter(Boolean));
  const refSegments = nonEmptySegments.filter((seg) => seg.sourceType === "reference").length;
  setSegmentSummary(
    `已配置 ${nonEmptySegments.length} 段，使用 ${usedVoiceIds.size} 个音色，参考音频段 ${refSegments} 个`
  );
}

function updateScriptParseSummary() {
  if (inputMode !== INPUT_MODE_SCRIPT) {
    setScriptSummary("");
    return;
  }

  const script = (textInput.value || "").trim();
  if (!script) {
    setScriptSummary("脚本为空，支持 [voice_id] / Speaker N: / 普通文本");
    return;
  }

  const analysis = analyzeScriptInput(script, voiceSelect.value);
  if (!analysis.ok) {
    setScriptSummary(formatAnalysisError(analysis), true);
    return;
  }

  const segmentCount = analysis.parsed.segments.length;
  const usedVoiceIds = new Set(analysis.parsed.segments.map((seg) => seg.voiceId).filter(Boolean));
  const tagText = analysis.parsed.hasVoiceTags ? "包含 [voice_id]" : "未使用 [voice_id]，将回退默认音色";
  setScriptSummary(`解析成功：${segmentCount} 段，${usedVoiceIds.size} 个音色，${tagText}`);
}

function updateInputModeUI() {
  const isVisual = inputMode === INPUT_MODE_VISUAL;

  if (visualModePanelEl) {
    visualModePanelEl.style.display = isVisual ? "block" : "none";
  }
  if (scriptModePanelEl) {
    scriptModePanelEl.style.display = isVisual ? "none" : "block";
  }

  if (modeVisualBtn) {
    modeVisualBtn.classList.toggle("active", isVisual);
    modeVisualBtn.setAttribute("aria-selected", isVisual ? "true" : "false");
  }
  if (modeScriptBtn) {
    modeScriptBtn.classList.toggle("active", !isVisual);
    modeScriptBtn.setAttribute("aria-selected", isVisual ? "false" : "true");
  }

  if (isVisual) {
    renderSegmentEditor();
  }

  updateReferenceModeUI();
  updateSaveReferenceState();
}

function switchToVisualMode() {
  if (inputMode === INPUT_MODE_VISUAL) {
    return;
  }

  if (!voiceList.length) {
    setStatus("暂无可用音色，无法切换到可视化编排", true);
    return;
  }

  const script = (textInput.value || "").trim();
  if (script) {
    const parseFallbackVoiceId = getVisualFallbackVoiceId() || getFirstRegularVoiceId();
    const parsed = parseInputToSegments(script, parseFallbackVoiceId);
    if (!parsed.segments.length) {
      setStatus("脚本无法解析为可视化段，请继续使用脚本模式", true);
      return;
    }

    const unknownVoiceIds = collectUnknownVoiceIds(parsed.segments, {
      allowReferenceFallback: false,
    });
    if (unknownVoiceIds.length) {
      setStatus(`脚本包含不存在的 voice_id，无法切换：${unknownVoiceIds.join(", ")}`, true);
      return;
    }

    visualSegments = parsed.segments.map((seg) => ({
      voiceId: seg.voiceId,
      sourceType: "voice",
      text: seg.text,
      referenceFile: null,
      referencePromptText: "",
    }));
  }

  if (!visualSegments.length) {
    visualSegments = [createEmptySegment()];
  }

  inputMode = INPUT_MODE_VISUAL;
  persistInputMode();
  updateInputModeUI();
}

function switchToScriptMode(options = {}) {
  const { syncFromVisual = true } = options;

  if (syncFromVisual) {
    const serialized = serializeSegmentsToScript({ includeEmpty: false });
    if (serialized) {
      textInput.value = serialized;
    }
  }

  inputMode = INPUT_MODE_SCRIPT;
  persistInputMode();
  updateInputModeUI();
  updateScriptParseSummary();
}

function insertScriptTemplate() {
  const ids = getRegularVoiceIds();
  const id1 = ids[0] || "voice_id_1";
  const id2 = ids[1] || "voice_id_2";
  const id3 = ids[2] || "voice_id_3";

  textInput.value = `[${id1}]第一位说话人内容\n同一位说话人的续行\n[${id2}]第二位说话人内容\n[${id3}]第三位说话人内容`;
  updateScriptParseSummary();
  resetReferenceGenerationState();
}

function addSegment() {
  visualSegments.push(createEmptySegment());
  renderSegmentEditor();
}

function clearSegments() {
  visualSegments = [createEmptySegment()];
  renderSegmentEditor();
}

function exportSegmentsToScript() {
  const hasReferenceSegments = visualSegments.some(
    (seg) => seg.sourceType === "reference" && (seg.text || "").trim()
  );
  const serialized = serializeSegmentsToScript({ includeEmpty: false });
  if (!serialized) {
    setStatus("没有可导出的有效说话段", true);
    return;
  }

  textInput.value = serialized;
  switchToScriptMode({ syncFromVisual: false });
  if (hasReferenceSegments) {
    setStatus("已导出为脚本。注意：参考音频文件不会写入脚本，导出时仅保留音色 ID。");
  } else {
    setStatus("已导出为脚本，可在脚本模式继续编辑");
  }
}

function handleSegmentEditorChange(event) {
  const target = event.target;
  if (!(target instanceof HTMLElement)) {
    return;
  }

  if (target.classList.contains("segment-voice")) {
    const index = Number(target.dataset.index);
    if (Number.isInteger(index) && visualSegments[index]) {
      visualSegments[index].voiceId = target.value;
      renderSegmentEditor();
    }
    return;
  }

  if (target.classList.contains("segment-source")) {
    const index = Number(target.dataset.index);
    if (Number.isInteger(index) && visualSegments[index]) {
      visualSegments[index].sourceType = target.value === "reference" ? "reference" : "voice";
      if (!visualSegments[index].voiceId || !isKnownVoiceId(visualSegments[index].voiceId)) {
        visualSegments[index].voiceId = getVisualFallbackVoiceId() || "";
      }
      renderSegmentEditor();
    }
    return;
  }

  if (target.classList.contains("segment-ref-file")) {
    const index = Number(target.dataset.index);
    if (Number.isInteger(index) && visualSegments[index]) {
      const files = target.files;
      visualSegments[index].referenceFile = files && files[0] ? files[0] : null;
      renderSegmentEditor();
    }
    return;
  }

  if (target.classList.contains("segment-ref-prompt")) {
    const index = Number(target.dataset.index);
    if (Number.isInteger(index) && visualSegments[index]) {
      visualSegments[index].referencePromptText = target.value || "";
    }
  }
}

function handleSegmentEditorInput(event) {
  const target = event.target;
  if (!(target instanceof HTMLElement)) {
    return;
  }

  if (target.classList.contains("segment-text")) {
    const index = Number(target.dataset.index);
    if (Number.isInteger(index) && visualSegments[index]) {
      visualSegments[index].text = target.value;
      renderSegmentEditor();
    }
    return;
  }

  if (target.classList.contains("segment-ref-prompt")) {
    const index = Number(target.dataset.index);
    if (Number.isInteger(index) && visualSegments[index]) {
      visualSegments[index].referencePromptText = target.value || "";
    }
  }
}

function handleSegmentEditorClick(event) {
  const target = event.target;
  if (!(target instanceof HTMLElement)) {
    return;
  }

  const removeBtn = target.closest(".remove-segment");
  if (!removeBtn) {
    return;
  }

  const index = Number(removeBtn.dataset.index);
  if (!Number.isInteger(index) || !visualSegments[index]) {
    return;
  }

  visualSegments.splice(index, 1);
  if (!visualSegments.length) {
    visualSegments.push(createEmptySegment());
  }
  renderSegmentEditor();
}

