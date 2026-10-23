# Workflow Studio

在 marimo / Molab 中运行图像工作流、LLM 对话与 Google Drive 文件传输。

LLM 使用 vLLM 0.32.0、FP8 和 MTP，默认模型为 [OrcaRouter Qwen3.8-27B Uncensored FP8](https://huggingface.co/orcarouter/Qwen3.8-27B-Uncensored-FP8)。支持图片输入、Thinking、多轮分支和流式输出。默认上下文为 32768 tokens，MTP 为 2 步。

在 RTX PRO 6000 Blackwell Server Edition 上，以关闭 Thinking 的 128-token 中文输出测试，热服务生成速度为 70.8 tokens/s，请求首字延迟为 0.082 秒。首次完整冷启动的实测阶段耗时为：环境安装 314.6 秒，服务初始化 311.9 秒，首轮请求 0.122 秒，合计 626.6 秒。已有运行库和编译缓存时，服务重新启动实测 74.8 秒。模型文件已在本地；权重从 Drive 恢复的时间另计。

## 启动

`notebook.py` 提供一个 cell 的 Git 启动入口。每次执行更新 `main` 分支，随后加载工作流面板。Molab 工作区保留自己的 `studio_config.json`、`studio_settings.json`、`workspace_saved.py` 和 Drive 授权配置。

模型存放在 `model_dir/LLM/`。公开模型目录记录下载仓库、固定版本与文件大小；notebook 的 `workspace_store` 中可保存自己的 Drive 模型清单，运行时优先使用该清单恢复权重。公开仓库保存工作流源码和前端资源。

现有 Molab 工作区通过 `persistent_drive_auth.connect_from_secrets()` 连接 Google Drive。模型与 Drive 授权由工作区管理。

## 文件

- `studio_bootstrap.py`：从 Git 源码启动面板，读取 notebook 工作区设置。
- `workflow_studio/vllm_runner.py`：GPU 服务、模型恢复、图片及流式对话。
- `studio_workflows/`：工作区使用的默认工作流。
- `workflow_studio/frontend/`：Svelte 前端；`workflow_studio/assets/` 包含已构建资源。
- `transfer_core.py`：Google Drive 传输队列。

完整界面和工作流说明见 [workflow_studio/README.md](workflow_studio/README.md)。第三方组件许可见 [THIRD_PARTY_LICENSES.txt](workflow_studio/THIRD_PARTY_LICENSES.txt)。
