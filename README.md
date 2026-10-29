# Workflow Studio

在 marimo / Molab 中运行图像工作流、LLM 对话与 Google Drive 文件传输。

LLM 通过 llama-cpp-python 0.3.36 在 notebook 进程内直接调用 libllama。默认模型为 OrcaRouter Qwen3.8-27B Uncensored Q8_0，配套独立 MTP 草稿头和 BF16 图像投影器。支持图片输入、Thinking、多轮分支与流式输出。默认上下文 32768 tokens、MTP 2 步。

对话层使用 Pi coding agent SDK 1.4.0。Python 通过 JSONL 标准输入输出管道连接常驻 Node 子进程，Pi 的自定义 provider 调回 notebook 内的 llama.cpp 实例。前端显示 Pi 会话、生成状态、Thinking 和首字时间。当前分支的聊天记录由 Pi SessionManager 重建为模型上下文。

生图与对话交替时复用各自的模型缓存。LLM 的“生成后释放显存”设置用于主动释放；默认使用“保留模型”。

运行库使用官方预编译 CUDA wheel。MTP 使用本地函数、线程队列和 Python 迭代器；模型驻留时复用已加载实例。

MOSS 默认启用 Spectrum 自适应特征预测，高级设置提供预热步数、误差容忍度与特征缓存设备。H3 的注意力选择提供 Spark-H3；自动模式在 CUDA 13 的 SM86、SM89、SM120 GPU 上优先使用 Spark-H3，可调整保真／速度／自定义预热、精确计算比例、参考视频稀疏范围和 QKV 分块。页面配置继续使用 Notebook 的 gzip 存储。

共享 Comfy 核心固定为 0.42.0，首次加载前使用 [Spark-H3 官方安装器](https://github.com/zechengtang/Spark-H3/blob/main/comfyui/install.py)准备对应 GPU 的 comfy-kitchen CUDA 内核。Spark-H3 源码固定在 `2eb2dc1be261490f86a57c93904551a5bf456af7`，源码与推理缓存位于临时运行目录。H3 每个分段的 LoRA 和 Sigma Shift 应用后，经 Spark 模型补丁进入现有采样器，结果仍由原有 VAE 与媒体输出流程处理。

## 启动

`notebook.py` 在脚本依赖中声明 GitHub 上的 `workflow-studio` 启动包，由 Notebook 包管理器安装。包中提供现有的 `studio_entry.load_studio()`，启动单元格保留 4 行普通 Python：

```python
import marimo as mo
from studio_entry import load_studio
studio_panel = load_studio()
mo.ui.anywidget(studio_panel)
```

Git 更新和初始化由 `studio_entry.py` 执行，每次调用更新临时目录中的 `main` 源码后加载 MOSS、MiniMax H3 和 Pi 面板。Notebook 的持久缓存保存页面配置，Secrets 保存 Drive 授权配置。

模型存放在 `model_dir/LLM/`。公开模型目录记录下载仓库、固定版本与文件大小；notebook 的 `workspace_store` 中可保存自己的 Drive 模型清单，运行时优先使用该清单恢复权重。公开仓库保存工作流源码和前端资源。

首次使用时，在“文件与传输”点击“连接 Google Drive”，打开 Google 授权页，将返回的一次性授权码填入工作台并点击“完成连接”。授权保存在本 Notebook 的 Secrets 中。后续启动通过 `persistent_drive_auth.connect_from_secrets()` 自动连接，授权失效时从页面重新连接。

## 内容存储

Notebook 持久保存页面中的模型选择、采样参数、提示词、H3 分段与时间轴布局、LoRA 配置、文件快捷操作以及页面编辑保存的 Skill，格式统一为标准 gzip。恢复面板时加载这些配置。

上传的参考图片、视频与音频保留在运行内存；生成媒体、缩略图、索引、Pi 会话、工具运行文件和工作流副本存放在 `/tmp/workflow-studio-runtime/`。模型、依赖和推理内核同样使用 `/tmp`。这些内容随运行容器回收。临时媒体与 Pi 会话也沿用 gzip 读写。

marimo 输出缓存与会话快照交由平台正常管理。

## 文件

- `studio_bootstrap.py`：从 Git 源码启动面板，准备临时运行目录并加载 Notebook 配置。
- `workspace_store.py`：Notebook 页面配置的 gzip 读写。
- `persistent_drive_auth.py`：通过 Notebook Secrets 恢复 Drive 连接。
- `workflow_studio/llama_runner.py`：进程内 GGUF 加载、模型恢复、图片及流式对话。
- `workflow_studio/pi_runner.py`、`pi_bridge/`：Pi 会话与本地推理的管道适配。
- `studio_workflows/`：工作区使用的默认工作流。
- `workflow_studio/frontend/`：Svelte 前端；`workflow_studio/assets/` 包含已构建资源。
- `transfer_core.py`：Google Drive 传输队列。

完整界面和工作流说明见 [workflow_studio/README.md](workflow_studio/README.md)。第三方组件许可见 [THIRD_PARTY_LICENSES.txt](workflow_studio/THIRD_PARTY_LICENSES.txt)。
