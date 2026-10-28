# Workflow Studio

在 marimo / Molab 中运行图像工作流、LLM 对话与 Google Drive 文件传输。

LLM 通过 llama-cpp-python 0.3.36 在 notebook 进程内直接调用 libllama。默认模型为 OrcaRouter Qwen3.8-27B Uncensored Q8_0，配套独立 MTP 草稿头和 BF16 图像投影器。支持图片输入、Thinking、多轮分支与流式输出。默认上下文 32768 tokens、MTP 2 步。

对话层使用 Pi coding agent SDK 1.4.0。Python 通过 JSONL 标准输入输出管道连接常驻 Node 子进程，Pi 的自定义 provider 调回 notebook 内的 llama.cpp 实例。前端显示 Pi 会话、生成状态、Thinking 和首字时间。当前分支的聊天记录由 Pi SessionManager 重建为模型上下文。

生图与对话交替时复用各自的模型缓存。LLM 的“生成后释放显存”设置用于主动释放；默认使用“保留模型”。

运行库使用官方预编译 CUDA wheel。MTP 使用本地函数、线程队列和 Python 迭代器；模型驻留时复用已加载实例。原 FP8 默认模型设置在启动时迁移为 Q8_0 及配套权重。

## 启动

`notebook.py` 提供一个 cell 的 Git 启动入口。每次执行更新 `main` 分支，随后加载工作流面板。Molab 工作区保留自己的 `studio_config.json`、`studio_settings.json`、`workspace_saved.py` 和 Drive 授权配置。

模型存放在 `model_dir/LLM/`。公开模型目录记录下载仓库、固定版本与文件大小；notebook 的 `workspace_store` 中可保存自己的 Drive 模型清单，运行时优先使用该清单恢复权重。公开仓库保存工作流源码和前端资源。

现有 Molab 工作区通过 `persistent_drive_auth.connect_from_secrets()` 连接 Google Drive。模型与 Drive 授权由工作区管理。

## 内容存储

Molab 中的工作区状态、会话和媒体内容通过标准 gzip 保存，读取时还原原值供工作台显示。现有逻辑文件名和缓存键继续用于定位内容，gzip 文件头用于识别存储格式。Python 使用 `gzip`，Pi 会话使用 Node.js 的 `zlib`；`WORKFLOW_GZIP_CONTENT` 控制压缩，Molab 默认启用。

marimo 输出缓存与会话快照交由平台正常管理。

## 文件

- `studio_bootstrap.py`：从 Git 源码启动面板，读取 notebook 工作区设置。
- `workflow_studio/llama_runner.py`：进程内 GGUF 加载、模型恢复、图片及流式对话。
- `workflow_studio/pi_runner.py`、`pi_bridge/`：Pi 会话与本地推理的管道适配。
- `studio_workflows/`：工作区使用的默认工作流。
- `workflow_studio/frontend/`：Svelte 前端；`workflow_studio/assets/` 包含已构建资源。
- `transfer_core.py`：Google Drive 传输队列。

完整界面和工作流说明见 [workflow_studio/README.md](workflow_studio/README.md)。第三方组件许可见 [THIRD_PARTY_LICENSES.txt](workflow_studio/THIRD_PARTY_LICENSES.txt)。
