# Workflow Studio

在 marimo / Molab 中运行图像工作流、LLM 对话与 Google Drive 文件传输。

默认 LLM 使用 notebook 已有的 PyTorch、Transformers 和 Accelerate，直接加载 [OrcaRouter Qwen3.8-27B Uncensored FP8](https://huggingface.co/orcarouter/Qwen3.8-27B-Uncensored-FP8)。权重加载为 BF16，在当前 96 GB GPU 上运行，支持图片输入、Thinking、多轮分支和流式输出。

在 RTX PRO 6000 Blackwell Server Edition、4 CPU 的 Molab 环境中，模型文件已在本地，以关闭 Thinking、seed 42、128-token 中文输出测试：

| 运行方式 | 环境安装 | 安装开始到首字（阶段耗时合计） | 持续输出 |
| --- | ---: | ---: | ---: |
| 默认 LLM：Transformers / BF16 | 0 秒，复用 notebook 环境 | 27.7 秒 | 18.3 tokens/s |
| 可选 vLLM 0.32 / FP8 + MTP | 314.6 秒 | 626.6 秒 | 70.8 tokens/s |

默认方式优先满足 notebook 的快速启动需求。工作流管理中可添加 `vllm_chat.py`，用于需要持续吞吐量的长任务。上述时间是本次环境的实测，包含库导入、模型初始化和首轮请求；模型文件恢复过程由 Drive 清单管理。

## 启动

`notebook.py` 提供一个 cell 的 Git 启动入口。每次执行更新 `main` 分支，随后加载工作流面板。Molab 工作区保留自己的 `studio_config.json`、`studio_settings.json`、`workspace_saved.py` 和 Drive 授权配置。

模型存放在 `model_dir/LLM/`。公开模型目录记录下载仓库、固定版本与文件大小；notebook 的 `workspace_store` 中可保存自己的 Drive 模型清单，运行时优先使用该清单恢复权重。公开仓库保存工作流源码和前端资源。

现有 Molab 工作区通过 `persistent_drive_auth.connect_from_secrets()` 连接 Google Drive。模型与 Drive 授权由工作区管理。

## 文件

- `studio_bootstrap.py`：从 Git 源码启动面板，读取 notebook 工作区设置。
- `workflow_studio/vllm_runner.py`：GPU 服务、模型恢复、图片及流式对话。
- `workflow_studio/fast_runner.py`、`fast_worker.py`：复用 notebook 环境的默认快速启动后端。
- `studio_workflows/`：工作区使用的默认工作流。
- `workflow_studio/frontend/`：Svelte 前端；`workflow_studio/assets/` 包含已构建资源。
- `transfer_core.py`：Google Drive 传输队列。

完整界面和工作流说明见 [workflow_studio/README.md](workflow_studio/README.md)。第三方组件许可见 [THIRD_PARTY_LICENSES.txt](workflow_studio/THIRD_PARTY_LICENSES.txt)。
