# VibeVoice-Docker

将 VibeVoice 打包成可部署的 TTS 服务：OpenAI 兼容接口 + Web 页面 + 音色管理（内置示例音色 & 支持语音克隆）。

## 功能

- 生成语音：`POST /v1/audio/speech`（`wav` / `mp3`）
- 音色管理：`GET/POST/DELETE /v1/voices`（创建自定义克隆音色）
- 模型信息：`GET /v1/models`
- 健康检查：`GET /healthz`、`GET /ping`
- Web UI：`GET /`

## 模型与镜像

默认镜像地址：`ghcr.io/dale0525/vibevoice-docker`（如你 fork 了，请替换为自己的 `<owner>`）。

两个 tag（一个镜像固定一个模型）：
- `:1.5b`：1.5B（更省显存/更快）
- `:7b`：7B（更慢/更吃显存）

## 快速开始

### 1) 本地部署（推荐：直接拉 GHCR 镜像）

启动（默认 1.5B）：

```bash
docker compose -f docker-compose.prod.yml up -d
```

数据持久化：
- 宿主机 `./data` → 容器 `/data`
- 自定义音色会写入 `./data/voices`

切换到 7B：

```bash
docker compose -f docker-compose.prod.7b.yml up -d
```

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
4. Endpoint Type 选 **Load Balancer**
5. 建议环境变量：
   - `VIBEVOICE_API_KEY=<your-key>`（推荐：防止公开 endpoint 被盗用；设置后要求请求头 `Authorization: Bearer <key>`，Web UI 支持填写）
   - `VIBEVOICE_WARMUP_ON_PRELOAD=false`
   - `VIBEVOICE_EXIT_ON_IDLE_SECONDS=30`（更快退出以便 scale-to-zero）
   - （可选）`VIBEVOICE_PRELOAD_MODEL=1`（更快首包，代价是启动更慢）
6. Deploy

更新方式：
- RunPod 不会自动跟随提交更新；需要创建新的 GitHub Release 触发重新构建（参考官方文档 “Update your endpoint”；本仓库 push `vX.Y.Z` tag 时会自动创建对应 Release）

## 使用（Web UI）

打开 `http://<host>:8000/`：
- 选择音色（内置示例音色 / 你上传的自定义音色）
- 输入文本并生成音频（支持 wav/mp3 下载）
- 可在页面里上传参考音频创建自定义克隆音色

## 使用（API，可选）

列出模型：

```bash
curl http://localhost:8000/v1/models
```

列出音色：

```bash
curl http://localhost:8000/v1/voices
```

创建自定义克隆音色：

```bash
curl -F "name=my-voice" -F "file=@sample.wav" http://localhost:8000/v1/voices
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
- `vibevoice_cfg_scale`：高级参数，默认 3.0

## 文本输入规则（重要）

- 普通文本会自动包装成 `Speaker 0: ...`
- 支持单一说话人脚本：`Speaker 0:` / `Speaker0:`（大小写不敏感）
- 不支持多说话人：脚本里出现多个 `Speaker` 编号会返回 400
- 默认对包含中文的文本做标点归一化，可用 `VIBEVOICE_ENABLE_CN_PUNCT_NORMALIZE=false` 关闭

## 其他配置（可选）

常用：
- `VIBEVOICE_API_KEY`：可选；设置后要求请求头 `Authorization: Bearer <key>`
- `VIBEVOICE_PRELOAD_MODEL=1`：启动时预加载模型（更快首包）
- `VIBEVOICE_WARMUP_ON_PRELOAD=false`：关闭预热（启动更快）
- `VIBEVOICE_EXIT_ON_IDLE_SECONDS=30`：空闲自动退出（Serverless 常用）
- `VIBEVOICE_ENABLE_CN_PUNCT_NORMALIZE=false`：关闭中文标点归一化

目录（一般不需要改）：
- `VIBEVOICE_DATA_DIR`：默认 `/data`
- `VIBEVOICE_VOICES_DIR`：默认 `/data/voices`
- `VIBEVOICE_MODELS_DIR`：默认 `/models`

## 本地开发（简要）

```bash
pixi install
pixi run dev
```

7B：

```bash
pixi run dev-7b
```

## 镜像 Tag 规则（简要）

自动构建配置见 `.github/workflows/vibevoice-docker.yml`：
- Push 到 `main`：更新 `:1.5b` / `:7b`（不带版本号，始终指向最新）
- Push `vX.Y.Z` tag：额外生成 `:vX.Y.Z-1.5b` / `:vX.Y.Z-7b`（并自动创建对应 GitHub Release）
