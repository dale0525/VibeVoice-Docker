# TTS-Docker

将 VibeVoice / MOSS-TTSD / CosyVoice3 打包成可部署的 TTS 服务：OpenAI 兼容接口 + Web 页面 + 音色管理（内置示例音色 & 支持语音克隆）。

## 功能

- 生成语音：`POST /v1/audio/speech`（`wav` / `mp3`）
- 参考音频试听：`POST /v1/audio/speech/reference`（上传参考音频后直接生成，不落库）
- 音色管理：`GET/POST/DELETE /v1/voices`（创建自定义克隆音色）
- 音色管理扩展：`GET /v1/voices/{id}/sample`（试听参考音频）、`PATCH /v1/voices/{id}`（编辑参考文本）
- 模型信息：`GET /v1/models`
- 健康检查：`GET /healthz`、`GET /ping`
- Web UI：`GET /`

## 模型与镜像

默认镜像地址：`ghcr.io/dale0525/tts-docker`（如你 fork 了，请替换为自己的 `<owner>`）。

四个 tag（一个镜像固定一个模型）：
- `:1.5b`：1.5B（更省显存/更快）
- `:7b`：7B（更慢/更吃显存）
- `:moss-ttsd-v1.0`：MOSS-TTSD v1.0（长对话场景更强）
- `:cosyvoice3-0.5b`：Fun-CosyVoice3 0.5B（跨语种/语音风格控制更强）

为避免“应用代码没怎么变，但更新镜像要重新拉 10GB+ 模型层”，本仓库把镜像拆成两层：
- **base 镜像（依赖 + 模型大层）**：`ghcr.io/<owner>/tts-docker-base:{1.5b|7b|moss-ttsd-v1.0|cosyvoice3-0.5b}`（尽量不频繁更新）
- **app 镜像（服务代码）**：`ghcr.io/<owner>/tts-docker:{1.5b|7b|moss-ttsd-v1.0|cosyvoice3-0.5b}`（频繁更新）

本地部署只需要拉 app 镜像；base 层会作为共享 layer 自动复用（不需要手动拉 base）。

## 快速开始

### 1) 本地部署（推荐：直接拉 GHCR 镜像）

仓库只保留一个 compose 文件：`docker-compose.yml`。

模型配置使用项目根目录 `.env`（默认已提供 `MODEL=1.5b`）。

启动（默认 1.5B）：

```bash
docker compose up -d
```

切换模型：修改项目根目录 `.env` 里的 `MODEL`，再重启：

```bash
MODEL=7b
# MODEL=moss-ttsd-v1.0
# MODEL=cosyvoice3-0.5b
```

修改后重启：

```bash
docker compose up -d
```

可选变量：
- `MODEL`：模型 tag，默认 `1.5b`
- `TTS_IMAGE_REPO`：镜像仓库，默认 `ghcr.io/dale0525/tts-docker`

数据持久化：
- 宿主机 `./data` → 容器 `/data`
- 自定义音色会写入 `./data/voices`

访问：
- Web UI：`http://localhost:8000/`
- 健康检查：`http://localhost:8000/healthz`

### 2) RunPod Serverless（GitHub Integration）

一个 endpoint 固定一个模型；需要另一个模型时，创建新的 endpoint。

官方文档：
- [https://docs.runpod.io/serverless/workers/github-integration.md](https://docs.runpod.io/serverless/workers/github-integration.md)
- [https://docs.runpod.io/serverless/load-balancing/overview](https://docs.runpod.io/serverless/load-balancing/overview)

部署流程（控制台）：
1. Settings → Connections → GitHub → Connect
2. Serverless → New Endpoint → Import Git Repository 选择本仓库
3. Branch 选 `main`，Dockerfile Path 选择模型：
   - 1.5B：`Dockerfile`
   - 7B：`Dockerfile.7b`
   - MOSS-TTSD v1.0：`Dockerfile.moss`
   - CosyVoice3 0.5B：`Dockerfile.cosy`
4. Endpoint Type 选 **Load Balancer**
5. 建议环境变量：
   - `API_KEY=<your-key>`（推荐：防止公开 endpoint 被盗用；设置后要求请求头 `Authorization: Bearer <key>`，Web UI 支持填写）
   - `WARMUP_ON_PRELOAD=false`
   - `EXIT_ON_IDLE_SECONDS=30`（更快退出以便 scale-to-zero）
   - （可选）`PRELOAD_MODEL=1`（更快首包，代价是启动更慢）
6. Deploy

更新方式：
- RunPod 不会自动跟随提交更新；需要创建新的 GitHub Release 触发重新构建（参考官方文档 “Update your endpoint”）
- 本仓库每次 push `main` 构建完成后会自动创建 Release（tag 规则见下方），用于触发 RunPod 重新构建

## 使用（Web UI）

打开 `http://<host>:8000/`：
- 选择音色（内置示例音色 / 你上传的自定义音色）
- 输入文本并生成音频（支持 wav/mp3 下载）
- 若在音色中选择“参考音频”，可先上传参考音频+prompt 文本进行试听，满意后再保存为新音色
- 在“音色管理”里可对已保存音色进行：试听参考音频、编辑参考文本（仅自定义音色）、删除（仅自定义音色）
  - 参考文本支持失焦自动保存（也可点击“保存参考文本”手动保存）

## 使用（API，可选）

列出模型：

```bash
curl http://localhost:8000/v1/models
```

列出音色：

```bash
curl http://localhost:8000/v1/voices
```

试听某个音色的参考音频：

```bash
curl http://localhost:8000/v1/voices/<voice_id>/sample --output sample.wav
```

编辑某个自定义音色的参考文本：

```bash
curl -X PATCH http://localhost:8000/v1/voices/<voice_id> \
  -H "Content-Type: application/json" \
  -d "{\"prompt_text\":\"新的参考文本\"}"
```

创建自定义克隆音色：

```bash
curl -F "name=my-voice" -F "file=@sample.wav" -F "prompt_text=这是参考音频对应文本" http://localhost:8000/v1/voices
```

用参考音频直接试听（不创建音色）：

```bash
curl -X POST http://localhost:8000/v1/audio/speech/reference \
  -F "file=@sample.wav" \
  -F "input=你好，世界！" \
  -F "prompt_text=这是参考音频对应文本（可选）" \
  -F "response_format=mp3" \
  --output out.mp3
```

生成语音（返回音频二进制）：

```bash
curl -X POST http://localhost:8000/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d "{\"voice\":\"zh-Xinran_woman\",\"input\":\"你好，世界！\",\"response_format\":\"mp3\"}" \
  --output out.mp3
```

参数提示：
- `voice`：来自 `GET /v1/voices` 的 `id`
- `input`：普通文本或单一说话人的 `Speaker N:` 脚本
- `response_format`：`wav`（默认）或 `mp3`
- `vibevoice_cfg_scale`：VibeVoice 高级参数，默认 3.0（MOSS-TTSD / CosyVoice3 会忽略该参数）

## 文本输入规则（重要）

- 普通文本会自动包装成 `Speaker 0: ...`
- 支持单一说话人脚本：`Speaker 0:` / `Speaker0:`（大小写不敏感）
- 不支持多说话人：脚本里出现多个 `Speaker` 编号会返回 400
- 默认对包含中文的文本做标点归一化，可用 `ENABLE_CN_PUNCT_NORMALIZE=false` 关闭
- 若某一段文本（冒号后的内容）超过长度阈值，会在句号 `.` 处自动拆分成多行（同一 `Speaker N:` 前缀；若窗口内没有 `.` 则回退为按长度硬切）；默认 150，可用 `SCRIPT_LINE_MAX_CHARS` 配置
- MOSS-TTSD 模式下会自动把单说话人脚本映射为 `[S1] ...`，并用音色的 `prompt_text`（若提供）增强克隆稳定性
- CosyVoice3 模式下会自动把单说话人脚本还原为普通文本，并优先使用音色的 `prompt_text` 作为参考音频文本（未提供时自动回退为目标文本首句）

## 其他配置（可选）

常用：
- `API_KEY`：可选；设置后要求请求头 `Authorization: Bearer <key>`
- `PRELOAD_MODEL=1`：启动时预加载模型（更快首包）
- `WARMUP_ON_PRELOAD=false`：关闭预热（启动更快）
- `EXIT_ON_IDLE_SECONDS=30`：空闲自动退出（Serverless 常用）
- `ENABLE_CN_PUNCT_NORMALIZE=false`：关闭中文标点归一化
- `SCRIPT_LINE_MAX_CHARS=150`：单一 Speaker 脚本的单行最大字符数（超过则优先按句号 `.` 自动拆分为多行）

目录（一般不需要改）：
- `DATA_DIR`：默认 `/data`
- `VOICES_DIR`：默认 `/data/voices`
- `MODELS_DIR`：默认 `/models`

## 本地开发（简要）

```bash
pixi install
pixi run dev
```

7B：

```bash
pixi run dev-7b
```

MOSS-TTSD：

```bash
pixi run dev-moss
```

CosyVoice3 0.5B：

```bash
pixi run dev-cosy3
```

运行 compose（使用 `.env` 当前配置）：

```bash
pixi run up
```

## 镜像 Tag 规则（简要）

自动构建配置见 `.github/workflows/tts-docker.yml`：
- Push 到 `main`：
  - 只更新本次提交受影响的模型镜像（不会再无条件全量更新 4 个模型）
  - 对于被选中的模型，会更新 `:<model_tag>`（始终指向最新）并额外生成 `:v0.0.<run_number>-<model_tag>`（便于固定部署版本）
  - 自动创建 GitHub Release：`v0.0.<run_number>`（Release 说明仅列出本次实际构建的模型镜像）
- workflow_dispatch（手动触发）：
  - 默认全量构建 4 个模型
  - 可勾选 `rebuild_base=true` 强制重建 base 镜像
- base 镜像（`ghcr.io/<owner>/tts-docker-base:{1.5b|7b|moss-ttsd-v1.0|cosyvoice3-0.5b}`）仅在依赖/模型相关文件变更时更新

文件变更与模型更新对应关系（push 到 `main`）：

| 变更文件 | 更新模型 |
| --- | --- |
| `Dockerfile` | `1.5b` |
| `Dockerfile.7b` | `7b` |
| `Dockerfile.moss` | `moss-ttsd-v1.0` |
| `Dockerfile.cosy` | `cosyvoice3-0.5b` |
| `Dockerfile.app` / `Dockerfile.base` / `requirements.txt` / `app/**` / `scripts/**` / `VibeVoice/**` | 全部模型（`1.5b`、`7b`、`moss-ttsd-v1.0`、`cosyvoice3-0.5b`） |
