# EduAnchor

[English](README.md) | **简体中文**

**离线、教材锚定的多智能体解读平台** —— 基于 Electron 桌面应用与本地 Python RAG/智能体引擎，是一篇关于教材锚定、证据可追溯学习支持的学术论文的参考实现。

> 模型只读你给的教材。每个回答都带页码级出处；教材没有覆盖的问题，系统会明确拒答，而不是猜测。

## 为什么做成桌面应用

- **隐私**：教材与学生问题不离开本机。
- **零部署**：一个安装包（NSIS 或便携版），不需要服务器、域名或云端 GPU。
- **离线演示**：断网也能完成完整演示。
- **可复现**：演示、用户研究与论文实验使用同一个版本化产物。
- **消费级硬件**：Qwen3-8B GGUF（4-bit）通过 Ollama / llama.cpp 运行，或 AWQ 通过 vLLM 运行。

渲染层、Electron 主进程与 Python 引擎全部在本机运行。引擎是子进程，通过标准输入输出的逐行 JSON-RPC 通信，**不暴露 HTTP 端口**。

## 仓库结构

```
code/
  engine/         Python 3.11+ 引擎，使用 uv 管理
    src/eduanchor/
      pdf_parser.py chunker.py cards.py      # 解析、分块、知识点卡片
      embeddings.py bm25.py retriever.py     # 混合检索
      agents.py pipeline.py                  # 规划/解读/校验 + 边界策略
      evaluation.py rpc.py cli.py            # 评测、stdio RPC、CLI
    tests/                                   # pytest
    packaging/                               # PyInstaller 打包
  desktop/        Electron 33 + Vue 3 + Vite + TypeScript
  scripts/        开发 / 构建引擎 / 打包 的 PowerShell 脚本
docs/
  DEPLOYMENT.zh-CN.md                        # 打包与部署文档
  DEPLOYMENT.md                              # 英文版
```

## 快速运行

环境要求：**uv**、**Node.js 20+**、Windows 10/11（macOS/Linux 需要调整少量打包配置）。

```powershell
# 1) Python 引擎
cd code/engine
uv sync
uv run eduanchor seed            # 导入内置示例教材
uv run eduanchor doctor          # 查看 LLM / 向量后端 / 数据目录状态

# 2) 桌面应用
cd ../desktop
npm install
npm run dev
```

应用会自动启动引擎：开发模式使用 `uv run eduanchor-rpc`，生产模式使用随包分发的可执行文件。若本机没有可用大模型，引擎会退化为**抽取式解读 + 确定性哈希向量**，因此不下载模型也能完整体验界面。

### 导入自己的教材

在侧边栏点击 **导入教材**（PDF / Markdown / TXT）。PDF 需要文本层；扫描版不在范围内。Markdown 可用 `<!-- page: N -->` 标记保留页码。

## 选择生成模型

在侧边栏打开 **模型设置**。引擎支持任意 OpenAI 兼容的聊天端点，配置保存在本机 `%LOCALAPPDATA%\EduAnchor\model.json`，环境变量优先。

| 服务商 | Base URL | 默认模型 | API Key |
| --- | --- | --- | --- |
| Ollama（本地，GGUF） | `http://127.0.0.1:11434/v1` | `qwen3:8b` | 不需要 |
| vLLM（本地，AWQ） | `http://127.0.0.1:8000/v1` | `Qwen/Qwen3-8B-AWQ` | 不需要 |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` | 需要 |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` | 需要 |
| 阿里云百炼（Qwen） | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` | 需要 |
| Moonshot（Kimi） | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` | 需要 |
| 硅基流动 | `https://api.siliconflow.cn/v1` | `Qwen/Qwen3-8B` | 需要 |
| 自定义 | 任意 OpenAI 兼容 `/v1` | 自填 | 可选 |

**测试连接**会先发一次短对话请求再保存。API Key 不会返回给渲染层，也不会写入日志；它以明文保存在本机 `model.json` 中。

### 本地默认：Qwen3-8B 的两个量化版本

默认生成模型是 Qwen3-8B，支持 ModelScope 上的两种官方量化版本：

| 版本 | 运行方式 | 端点 | 模型名 | 说明 |
| --- | --- | --- | --- | --- |
| GGUF Q4_K_M | Ollama / llama.cpp | `http://127.0.0.1:11434/v1` | `qwen3:8b` | CPU 或消费级 GPU，配置最简单 |
| AWQ | vLLM | `http://127.0.0.1:8000/v1` | `Qwen/Qwen3-8B-AWQ` | NVIDIA GPU；vLLM 需 Linux/WSL2 |

**GGUF（Ollama）**。从官方仓库拉取：

```powershell
ollama pull qwen3:8b
ollama serve
```

或从 ModelScope 下载官方 GGUF（国内推荐）：

```powershell
uv tool install modelscope
modelscope download --model Qwen/Qwen3-8B-GGUF --local_dir .\models\Qwen3-8B-GGUF
```

用 Q4_K_M 文件创建 Ollama 模型（文件名按实际下载结果调整）：

```powershell
@"
FROM ./models/Qwen3-8B-GGUF/Qwen3-8B-Q4_K_M.gguf
PARAMETER num_ctx 8192
"@ | Set-Content Modelfile
ollama create qwen3:8b -f Modelfile
ollama serve
```

**AWQ（vLLM）**。下载 AWQ 版本并在 Linux/WSL2 上启动服务：

```powershell
modelscope download --model Qwen/Qwen3-8B-AWQ --local_dir .\models\Qwen3-8B-AWQ
vllm serve .\models\Qwen3-8B-AWQ --port 8000 --served-model-name Qwen/Qwen3-8B-AWQ
```

然后把 Base URL 设为 `http://127.0.0.1:8000/v1`，模型名设为 `Qwen/Qwen3-8B-AWQ`。GGUF 也可以用 `llama-server -m <文件> --port 8080` 启动，Base URL 设为 `http://127.0.0.1:8080/v1`。

### 远程厂商 API

选择预设、填入 API Key、测试并保存即可。**远程服务商会收到检索到的教材片段**，请确认课程与版权政策允许后再使用；界面会标注当前端点是本地还是远程。公共电脑上建议使用环境变量，或为密钥单独设置系统账户。

环境变量覆盖：

```powershell
$env:EDUANCHOR_LLM_PROVIDER = "ollama"       # ollama | openai | deepseek | dashscope | moonshot | siliconflow | custom
$env:EDUANCHOR_LLM_BASE_URL = "http://127.0.0.1:11434/v1"
$env:EDUANCHOR_LLM_MODEL = "qwen3:8b"
$env:EDUANCHOR_LLM_API_KEY = "..."           # 仅远程厂商需要
```

### 可选 BGE-M3 向量

```powershell
cd code/engine
uv sync --extra models
$env:EDUANCHOR_EMBED_BACKEND = "bge"
```

`auto` 会尝试 BGE-M3，失败则回退到哈希向量。向量索引会在后端变化时自动失效并重建（后端名称记录在索引文件中）。

## 命令行

```powershell
cd code/engine
uv run eduanchor ask "什么是机器学习？"
uv run eduanchor ask "什么是过拟合？" --mode socratic
uv run eduanchor model show               # 查看当前模型配置
uv run eduanchor model test               # 测试端点连通性
uv run eduanchor model set --provider deepseek --api-key $env:DEEPSEEK_API_KEY
uv run eduanchor cards
uv run eduanchor eval --all-conditions --out ../results.json
uv run eduanchor serve                    # stdio JSON-RPC，供 Electron 调用
```

`eval` 运行 C1–C5 消融：裸模型、稠密 RAG、混合检索、多智能体校验、完整锚定约束。它会输出逐题 JSON 与论文 LaTeX 表格。

## 测试

```powershell
cd code/engine
uv run pytest -q
uv run ruff check src tests
```

## 打包安装包

```powershell
cd code
pwsh ./scripts/build-engine.ps1     # PyInstaller -> engine/dist/eduanchor-engine
pwsh ./scripts/package.ps1          # 构建引擎 + electron-builder
```

输出：

- `code/desktop/release/EduAnchor-Setup-0.1.0-x64.exe`
- `code/desktop/release/EduAnchor-Portable-0.1.0-x64.exe`

详细步骤、离线模型分发、代码签名与故障排查见 [docs/DEPLOYMENT.zh-CN.md](docs/DEPLOYMENT.zh-CN.md)。

## 学术论文

会议论文、中文原稿、图表与投稿材料不在本仓库中维护。引擎仍保留 `eduanchor eval --latex-dir <目录>`，可在本地导出 LaTeX 表格。

## 配置项

| 环境变量 | 默认值 | 作用 |
| --- | --- | --- |
| `EDUANCHOR_DATA_DIR` | `%LOCALAPPDATA%\EduAnchor` | SQLite、索引、会话 |
| `EDUANCHOR_LLM_PROVIDER` | `ollama` | `ollama`、`openai`、`deepseek`、`dashscope`、`moonshot`、`siliconflow`、`custom` |
| `EDUANCHOR_LLM_BASE_URL` | `http://127.0.0.1:11434/v1` | OpenAI 兼容端点 |
| `EDUANCHOR_LLM_MODEL` | `qwen3:8b` | 模型名 |
| `EDUANCHOR_LLM_API_KEY` | 空 | 远程厂商密钥 |
| `EDUANCHOR_LLM_TIMEOUT` | `180` | 秒 |
| `EDUANCHOR_EMBED_BACKEND` | `auto` | `auto`、`bge` 或 `hash` |
| `EDUANCHOR_EMBED_MODEL` | `BAAI/bge-m3` | 本地/远程模型路径 |
| `EDUANCHOR_COVERAGE_THRESHOLD` | `0.15` | 哈希向量下的覆盖度阈值 |

## 范围

- 仅文本；不做 OCR、插图、公式或表格理解。
- 不做大规模训练；Qwen3-8B 以冻结调用为主，LoRA 仅作为未来可选增强。
- 不是通用助手：拒绝教材外问题是特性，不是故障。
