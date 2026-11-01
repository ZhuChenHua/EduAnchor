# 打包与部署文档

[English](DEPLOYMENT.md) | **简体中文**

本文说明如何把 EduAnchor 打包成 Windows 桌面应用、如何离线分发模型，以及如何验证安装包。

## 1. 交付物

```
EduAnchor-Setup-x.y.z-x64.exe        NSIS 安装包
EduAnchor-Portable-x.y.z-x64.exe     便携版单文件启动器
```

安装包包含：

- Electron 运行时与 Vue 渲染层（`dist/`）。
- Electron 主进程/preload 代码（`dist-electron/`）。
- PyInstaller `onedir` 形式的 Python 引擎，位于 `resources/engine/`
  （`eduanchor-engine.exe` + `_internal/`）。

安装包**不包含**语言模型与 BGE-M3 权重。Qwen3-8B 通过本地
OpenAI 兼容端点（Ollama 或 llama.cpp）提供。没有模型时，引擎运行
抽取式解读器；没有 BGE-M3 时，使用确定性哈希向量。两个降级路径都是
有意设计的，安装包体积约 120 MB。

## 2. 环境要求

| 工具 | 版本 | 说明 |
| --- | --- | --- |
| Windows | 10/11 x64 | 构建与目标平台 |
| Node.js | 20+ | 渲染层与 Electron 工具链 |
| uv | 0.8+ | Python 引擎，基于锁文件 |
| Python | 3.11+ | uv 可自动安装 |
| Ollama / llama.cpp / vLLM | 可选 | 本地 Qwen3-8B 端点（GGUF 或 AWQ） |

## 3. 开发运行

```powershell
cd code/engine
uv sync
uv run eduanchor seed
uv run eduanchor doctor

cd ../desktop
npm install
npm run dev
```

若 `.venv\Scripts\eduanchor-rpc.exe` 存在，Electron 直接启动它；
否则执行 `uv run eduanchor-rpc`。

## 4. 构建 Python 引擎

```powershell
cd code
pwsh ./scripts/build-engine.ps1
```

等价命令：

```powershell
cd code/engine
uv sync
uv run --with pyinstaller pyinstaller packaging/eduanchor-engine.spec --noconfirm --clean
```

输出：`code/engine/dist/eduanchor-engine/`。

spec 会打包 `src/eduanchor/data`（示例教材与试点评测集），并排除
`torch`、`FlagEmbedding`、`onnxruntime` 等可选重依赖。可脱离 Electron 验证（以下命令在仓库根目录执行）：

```powershell
$env:EDUANCHOR_DATA_DIR = "$env:TEMP\eduanchor-engine-smoke"
'{"jsonrpc":"2.0","id":1,"method":"system.ping"}' |
  .\code\engine\dist\eduanchor-engine\eduanchor-engine.exe
```

### 可选：启用 BGE-M3 向量

默认安装包使用哈希向量。若要随包提供 BGE-M3：

1. 安装模型依赖：`cd code/engine && uv sync --extra models`。
2. 把 `BAAI/bge-m3` 下载到本地缓存，并在目标机设置 `HF_HOME`。
3. 重新构建引擎，**移除** `packaging/eduanchor-engine.spec` 中对
   `FlagEmbedding`、`torch` 的排除。
4. 设置 `EDUANCHOR_EMBED_BACKEND=bge`（或 `auto`）。

体积会显著增大（PyTorch + 模型权重）。轻量演示建议保留哈希降级，
并在文档中如实说明配置。

## 5. 构建桌面安装包

```powershell
cd code/desktop
npm install
npm run build          # Vite 渲染层 + tsc 主进程/preload
npm run dist           # electron-builder
```

若 GitHub 下载受阻，使用镜像：

```powershell
$env:ELECTRON_MIRROR = "https://npmmirror.com/mirrors/electron/"
$env:ELECTRON_BUILDER_BINARIES_MIRROR = "https://npmmirror.com/mirrors/electron-builder-binaries/"
npm run dist
```

`build.win.signAndEditExecutable` 已设为 `false`，因此无需证书，也不要求
Windows 符号链接权限。正式签名发布时移除该配置并设置：

```powershell
$env:CSC_LINK = "C:\path\to\certificate.pfx"
$env:CSC_KEY_PASSWORD = "***"
npm run dist
```

产物：

```
code/desktop/release/EduAnchor-Setup-0.1.0-x64.exe
code/desktop/release/EduAnchor-Portable-0.1.0-x64.exe
```

## 6. 验证安装包

内置冒烟模式会检查完整链路：Electron 主进程 → preload 客户端 →
Python 引擎 → 导入示例教材 → 锚定回答。

```powershell
$env:EDUANCHOR_SMOKE = "1"
$env:EDUANCHOR_DATA_DIR = "$env:TEMP\eduanchor-smoke"
.\code\desktop\release\win-unpacked\EduAnchor.exe
```

预期：进程以退出码 0 结束，`$env:EDUANCHOR_DATA_DIR\eduanchor.sqlite3`
中存在一条会话与六张卡片。每次发版前都应运行，可发现引擎缺失、
JSON-RPC 握手失败或打包路径错误。

## 7. 离线模型分发

EduAnchor 自身不下载模型。可选三种部署方式：

### A. 预装 Ollama / vLLM（最简单）

在目标机联网一次：

```powershell
ollama pull qwen3:8b
ollama serve
```

国内网络建议从 ModelScope 下载官方量化版：

```powershell
uv tool install modelscope
modelscope download --model Qwen/Qwen3-8B-GGUF --local_dir .\models\Qwen3-8B-GGUF
```

然后用 Q4_K_M 的 GGUF 导入 Ollama（文件名按实际下载结果调整）：

```powershell
@"
FROM ./models/Qwen3-8B-GGUF/Qwen3-8B-Q4_K_M.gguf
PARAMETER num_ctx 8192
"@ | Set-Content Modelfile
ollama create qwen3:8b -f Modelfile
ollama serve
```

AWQ 版本可从 ModelScope 下载，并在 Linux/WSL2 上用 vLLM 启动：

```powershell
modelscope download --model Qwen/Qwen3-8B-AWQ --local_dir .\models\Qwen3-8B-AWQ
vllm serve .\models\Qwen3-8B-AWQ --port 8000 --served-model-name Qwen/Qwen3-8B-AWQ
$env:EDUANCHOR_LLM_BASE_URL = "http://127.0.0.1:8000/v1"
$env:EDUANCHOR_LLM_MODEL = "Qwen/Qwen3-8B-AWQ"
```

若需要完全离线的机房镜像，可预填充 Ollama 模型目录，或把模型烘焙进系统镜像。

### B. 随包分发 llama.cpp 服务

分发 `llama-server.exe` 与 Qwen3-8B GGUF（Q4_K_M），先启动服务：

```powershell
llama-server -m qwen3-8b-q4_k_m.gguf --port 8080
$env:EDUANCHOR_LLM_BASE_URL = "http://127.0.0.1:8080/v1"
```

模型放在安装包外，避免多 GB 的安装体积。

### C. 远程厂商 API

**模型设置**对话框同样支持任意 OpenAI 兼容端点，内置 OpenAI、DeepSeek、
阿里云百炼（Qwen）、Moonshot、硅基流动等预设。当前配置保存在
`%LOCALAPPDATA%\EduAnchor\model.json`（或 `EDUANCHOR_DATA_DIR/model.json`），
环境变量优先。

远程服务商会收到检索到的教材片段，仅在课程与版权政策允许时使用。API Key
不会返回给渲染层或写入日志，但会以明文保存在 `model.json`；公共电脑建议用
环境变量或独立系统账户。

### D. 哈希降级（无模型）

适合界面评审、结题验收与离线演示。回答为抽取式且严格引用原文；
C1 不可用，因为它需要生成模型。

## 8. 首次运行与数据目录

默认数据目录：

```
%LOCALAPPDATA%\EduAnchor\
  eduanchor.sqlite3      文档、块、卡片、会话
  index\*.npz            块向量，按向量后端区分
  sessions\              预留
```

可用 `EDUANCHOR_DATA_DIR` 覆盖。该目录可直接备份；删除只会移除已导入
教材与会话历史。

## 9. 故障排查

| 现象 | 原因 / 处理 |
| --- | --- |
| `engine start timeout` | 引擎可执行文件缺失或崩溃。手动运行 `eduanchor-engine.exe` 查看 stderr。 |
| 应用能打开但所有调用失败 | `resources/engine` 未复制。检查 `package.json` 的 `extraResources`。 |
| 下载 Electron 时报 `ERR_ELECTRON_BUILDER_CANNOT_EXECUTE` | 设置 `ELECTRON_MIRROR` 与 `ELECTRON_BUILDER_BINARIES_MIRROR`。 |
| 7-Zip 报“无法创建符号链接” | 解压 winCodeSign 需要符号链接权限。保持 `signAndEditExecutable=false`，或以管理员身份打包。 |
| 安装包超过 500 MB | 可选模型依赖被误打包。检查 PyInstaller 的 `excludes`。 |
| 回答总是拒答 | 问题超出教材，或当前向量后端的覆盖度阈值过高。调整 `EDUANCHOR_COVERAGE_THRESHOLD`（哈希默认 0.15；BGE-M3 0.36）。 |
| 大模型从不启用 | 检查 `curl http://127.0.0.1:11434/v1/models`，并设置 `EDUANCHOR_LLM_BASE_URL` / `EDUANCHOR_LLM_MODEL`。 |
| PDF 导入失败 | PDF 没有文本层（扫描版）。OCR 不在范围内。 |

## 10. 发版检查清单

- [ ] `uv run pytest -q` 与 `uv run ruff check src tests` 通过。
- [ ] `npm run typecheck` 通过。
- [ ] 构建后的引擎冒烟测试通过。
- [ ] `EDUANCHOR_SMOKE=1` 的安装包冒烟测试通过。
- [ ] 升级 `code/desktop/package.json` 与 `code/engine/pyproject.toml` 版本号。
- [ ] 同时生成安装版与便携版。
- [ ] 可选：使用有效证书完成代码签名。
- [ ] 随版本发布 SHA-256 校验和。

## 11. 已知限制

- 以 Windows 为主；macOS/Linux 需要调整打包与路径。
- 不支持 OCR、插图、公式与表格。
- 默认安装包使用哈希向量；BGE-M3 需要可选构建。
- 不内置 Qwen3-8B；应用期望本地 OpenAI 兼容端点。
- 主实验表在完整 Qwen 实验完成前保持占位。
