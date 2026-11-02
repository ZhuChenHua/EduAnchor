# 打包与部署文档

[English](DEPLOYMENT.md) | **简体中文**

本文说明如何把 EduAnchor 打包成 Windows 桌面应用、如何离线分发模型，以及如何验证安装包。

## 1. 产物

```
EduAnchor-Setup-x.y.z-x64.exe        NSIS 安装包
EduAnchor-Portable-x.y.z-x64.exe     便携版
```

`npm run dist` 同时生成两个产物，包含 Electron、Vue 渲染层、
`resources/engine/` 下的 PyInstaller 引擎，以及 `resources/llama/` 下的
llama.cpp 运行时。**不包含** 5.0 GB 的 Qwen 权重。

安装后首次启动会自动下载 GGUF、校验 SHA-256，并在 `127.0.0.1:8081` 拉起
`llama-server`，模型别名 `qwen3-8b`。Ollama、vLLM 与远程 API 都是可选后端。
模型准备完成前，引擎回退为抽取式解释器；没有 BGE-M3 时使用确定性哈希嵌入。

## 2. 环境要求

| 工具 | 版本 | 说明 |
| --- | --- | --- |
| Windows | 10/11 x64 | 构建与目标平台 |
| Node.js | 20+ | 渲染层与 Electron 工具链 |
| uv | 0.8+ | Python 引擎，基于锁文件 |
| Python | 3.11+ | uv 可自动安装 |
| llama.cpp + Qwen3-8B | 随完整包内置 | 轻量包可选 Ollama/vLLM |

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
code/desktop/release/EduAnchor-Setup-0.2.0-x64.exe
code/desktop/release/EduAnchor-Portable-0.2.0-x64.exe
```

## 6. 验证安装包

内置冒烟模式会检查完整链路：Electron 主进程 → preload 客户端 →
Python 引擎 → 导入示例教材 → 锚定回答。

```powershell
$env:EDUANCHOR_SMOKE = "1"
$env:EDUANCHOR_DATA_DIR = "$env:TEMP\eduanchor-smoke"

# 方式 A：用已有模型验证随包运行时
$env:EDUANCHOR_MODEL_DIR = "D:\EduAnchor\Models"

# 方式 B：不下载 5 GB 模型，仅验证回退链路
# $env:EDUANCHOR_DISABLE_MODEL_DOWNLOAD = "1"

.\code\desktop\release\win-unpacked\EduAnchor.exe
```

预期：进程以退出码 0 结束，`$env:EDUANCHOR_DATA_DIR\eduanchor.sqlite3`
中存在一条会话与六张卡片。每次发版前都应运行，可发现引擎缺失、
JSON-RPC 握手失败或打包路径错误。下载链路可另用本地 HTTP 镜像和空模型目录单独验证。

## 7. 模型分发与首次下载

### A. 内置 llama.cpp + Qwen3-8B（默认）

安装包包含 `resources/llama/` 下的 llama.cpp 运行时，但不包含权重。首次启动时，
Electron 主进程会：

1. 检查配置的模型目录；
2. 从 Hugging Face 镜像下载 `Qwen3-8B-Q4_K_M.gguf`（官方 HF 作为回退）；
3. 尽量续传 `.part` 文件，并校验 SHA-256；
4. 原子安装模型并启动 `127.0.0.1:8081` 的 `llama-server`；
5. 重启引擎，使其检测到新模型。

默认模型位置：

```text
%LOCALAPPDATA%\EduAnchor\models\Qwen3-8B-GGUF\Qwen3-8B-Q4_K_M.gguf
```

用户可在 **模型设置 → 内置模型存储** 中更改根目录。已有权重会迁移到新位置，
未完成下载会在新目录续传。环境变量覆盖：

```powershell
$env:EDUANCHOR_MODEL_DIR = "D:\EduAnchor\Models"
$env:EDUANCHOR_MODEL_URLS = "https://your-mirror/Qwen3-8B-Q4_K_M.gguf"
$env:EDUANCHOR_DISABLE_MODEL_DOWNLOAD = "1"
```

固定 SHA-256：
`D98CDCBD03E17CE47681435B5150E34C1417F50B5C0019DD560E4882C5745785`。

如需从 ModelScope 手动放入权重：

```powershell
uv tool install modelscope
modelscope download --model Qwen/Qwen3-8B-GGUF --local_dir D:\EduAnchor\Models\Qwen3-8B-GGUF
```

### B. 可选 Ollama 或 vLLM

若实验室已经管理 Ollama：

```powershell
ollama pull qwen3:8b
ollama serve
```

AWQ 版本可在 Linux/WSL2 上用 vLLM 启动：

```powershell
modelscope download --model Qwen/Qwen3-8B-AWQ --local_dir .\models\Qwen3-8B-AWQ
vllm serve .\models\Qwen3-8B-AWQ --port 8000 --served-model-name Qwen/Qwen3-8B-AWQ
$env:EDUANCHOR_LLM_BASE_URL = "http://127.0.0.1:8000/v1"
$env:EDUANCHOR_LLM_MODEL = "Qwen/Qwen3-8B-AWQ"
```

两者都是内置路径的替代项，不是运行前提。

### C. 远程厂商 API

同一个 **模型设置** 对话框接受任意 OpenAI 兼容端点，内置 OpenAI、DeepSeek、
阿里云百炼（Qwen）、Moonshot 与硅基流动预设。配置保存在
`%LOCALAPPDATA%\EduAnchor\model.json`（或 `EDUANCHOR_DATA_DIR/model.json`），
环境变量优先。

远程服务商会收到检索到的教材片段，请确认课程与版权政策允许后再使用。API Key
不会返回渲染层，也不会写入日志，但在 `model.json` 中为明文；公共电脑上建议使用
环境变量或独立系统账户。

### D. 哈希回退（无模型）

用于界面评审、评分与离线演示。回答为抽取式引用；C1 需要生成模型，因此不可用。

## 8. 首次运行与数据目录

默认数据目录：

```
%LOCALAPPDATA%\EduAnchor\
  eduanchor.sqlite3      文档、块、卡片、会话
  index\*.npz            块向量，按向量后端区分
  sessions\              预留
  models\
    Qwen3-8B-GGUF\
      Qwen3-8B-Q4_K_M.gguf
```

桌面端偏好文件 `desktop-settings.json` 位于 Electron 的 `userData` 目录，保存
用户选择的模型根目录。数据目录可用 `EDUANCHOR_DATA_DIR` 覆盖，模型目录可用
`EDUANCHOR_MODEL_DIR` 覆盖。该目录可直接备份；删除只会移除已导入教材与会话历史。
删除模型目录后，下次启动会重新下载。

## 9. 故障排查

| 现象 | 原因 / 处理 |
| --- | --- |
| `engine start timeout` | 引擎可执行文件缺失或崩溃。手动运行 `eduanchor-engine.exe` 查看 stderr。 |
| 应用能打开但所有调用失败 | `resources/engine` 未复制。检查 `package.json` 的 `extraResources`。 |
| 下载 Electron 时报 `ERR_ELECTRON_BUILDER_CANNOT_EXECUTE` | 设置 `ELECTRON_MIRROR` 与 `ELECTRON_BUILDER_BINARIES_MIRROR`。 |
| 7-Zip 报“无法创建符号链接” | 解压 winCodeSign 需要符号链接权限。保持 `signAndEditExecutable=false`，或以管理员身份打包。 |
| 安装包异常大 | 检查是否误把模型权重放进了 `resources/models`；安装包只应包含 `resources/llama` 运行时。 |
| 模型下载失败 | 检查能否访问 `hf-mirror.com`；设置 `EDUANCHOR_MODEL_URLS` 为可用镜像，或手动放入 GGUF。 |
| 模型反复下载 | 确认目标目录可写，文件大小应恰好为 5,027,783,488 字节；SHA-256 不匹配会被拒绝。 |
| 回答总是拒答 | 问题超出教材，或当前向量后端的覆盖度阈值过高。调整 `EDUANCHOR_COVERAGE_THRESHOLD`（哈希默认 0.15；BGE-M3 0.36）。 |
| 大模型从不启用 | 检查 `curl http://127.0.0.1:8081/v1/models`，或配置的 Ollama/vLLM 端点。 |
| PDF 导入失败 | PDF 没有文本层（扫描版）。OCR 不在范围内。 |

## 10. 发版检查清单

- [ ] `uv run pytest -q` 与 `uv run ruff check src tests` 通过。
- [ ] `npm run typecheck` 通过。
- [ ] 构建后的引擎冒烟测试通过。
- [ ] `EDUANCHOR_SMOKE=1` 的安装包冒烟测试通过（使用本地模型）。
- [ ] 首次下载、SHA-256 校验与更改模型目录流程测试通过。
- [ ] 升级 `code/desktop/package.json` 与 `code/engine/pyproject.toml` 版本号。
- [ ] 同时生成安装版与便携版。
- [ ] 可选：使用有效证书完成代码签名。
- [ ] 发布安装包、便携版与 SHA-256 校验和。

## 11. 已知限制

- 以 Windows 为主；macOS/Linux 需要调整打包与路径。
- 不支持 OCR、插图、公式与表格。
- 安装包不含模型权重；首次使用需要联网下载约 5.0 GB。
- 默认评测使用哈希向量；BGE-M3 需要可选构建。
- 当前结果基于一本 6 页教材与 48 道题；多教材评测与用户研究仍在进行。
