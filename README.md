# Workflow Studio

在 Google Colab 中运行图像工作流、LLM 对话与 Google Drive 文件传输。

LLM 通过 llama-cpp-python 0.3.36 在 notebook 进程内直接调用 libllama。支持本地 GGUF、可选 MTP 草稿头与图像投影器、Thinking、多轮分支与流式输出。

对话层使用 Pi coding agent SDK 1.4.0。Python 通过 JSONL 标准输入输出管道连接常驻 Node 子进程，Pi 的自定义 provider 调回 notebook 内的 llama.cpp 实例。前端显示 Pi 会话、生成状态、Thinking 和首字时间。当前分支的聊天记录由 Pi SessionManager 重建为模型上下文。

生图与对话交替时复用各自的模型缓存。LLM 的“生成后释放显存”设置用于主动释放；默认使用“保留模型”。

运行库使用官方预编译 CUDA wheel。MTP 使用本地函数、线程队列和 Python 迭代器；模型驻留时复用已加载实例。

MOSS 默认启用 Spectrum 自适应特征预测，高级设置提供预热步数、误差容忍度与特征缓存设备。H3 的注意力选择提供 Spark-H3；自动模式在 CUDA 13 的 SM86、SM89、SM120 GPU 上优先使用 Spark-H3，可调整保真／速度／自定义预热、精确计算比例、参考视频稀疏范围和 QKV 分块。页面配置继续使用 Notebook 的 gzip 存储。

共享 Comfy 核心固定为 0.42.0。H3 选择自动或 Spark-H3 时，在首次加载前使用 [Spark-H3 官方安装器](https://github.com/zechengtang/Spark-H3/blob/main/comfyui/install.py)准备对应 GPU 的 comfy-kitchen CUDA 内核。安装器以 Python 模块方式运行，并显式添加源码导入路径。Spark-H3 源码固定在 `2eb2dc1be261490f86a57c93904551a5bf456af7`，源码与推理缓存位于临时运行目录。H3 每个分段的 LoRA 和 Sigma Shift 应用后，经 Spark 模型补丁进入现有采样器，结果仍由原有 VAE 与媒体输出流程处理。

## 在 Google Colab 启动

在 Colab 检出本仓库并把检出目录加入 Python 导入路径。依次运行：

```python
from colab_runtime import prepare, start_comfy, start_studio

prepare()
start_comfy()
start_studio()
```

ComfyUI 通过 Colab 预览打开。Studio 面板直接显示在 Colab 单元格中，工作流在当前 Python 内核执行。两者共用与仓库检出目录并列的 `ComfyUI/models`。

在 Studio 所在的单元格输出旁打开「⋮」，选择「全屏查看输出项」。

### Google Drive 和模型

在 Colab 的「文件」栏挂载云端硬盘，再在 Studio 的「文件与传输」刷新目录。也可以在 Colab 代码单元格调用 `colab_runtime.mount_drive()`。复制文件夹时保留子目录，从运行时和挂载盘两栏选择来源与目标。

模型选择来自运行时的模型目录。GGUF 放在 `LLM/`，图像和视频权重按类型放在 `diffusion_models/`、`text_encoders/`、`vae/` 等目录。通过「文件与传输 → 快捷复制 → 新增快捷复制 → HF → 本机」填写 Hugging Face 来源、文件范围和目标目录，再点击「保存并复制」。

在「文件与传输 → 传输记录」查看 Hugging Face 下载和 Drive 复制。记录保存在当前运行时，挂载可写 Drive 并刷新 Drive 目录后会同步到「Workflow Studio/transfer-history」。

### 设置与结果

工作台的参数、快捷项和资源存放在 Colab 运行时。可在启动时通过 `start_studio(state_directory=...)` 指定已挂载 Drive 下的设置目录。模型、输入和生成结果可在文件面板复制到 Drive。

## 文件

- `studio_bootstrap.py`：从 Git 源码启动面板，准备临时运行目录并加载 Notebook 配置。
- `workspace_store.py`：Colab 工作台设置的 gzip 读写。
- `colab_runtime.py`：Colab 启动、Drive 挂载与预览。
- `workflow_studio/llama_runner.py`：进程内 GGUF 加载、模型恢复、图片及流式对话。
- `workflow_studio/pi_runner.py`、`pi_bridge/`：Pi 会话与本地推理的管道适配。
- `studio_workflows/`：工作区使用的默认工作流。
- `workflow_studio/frontend/`：Svelte 前端；`workflow_studio/assets/` 包含已构建资源。
- `transfer_core.py`：运行时与已挂载 Drive 之间的传输队列。

完整界面和工作流说明见 [workflow_studio/README.md](workflow_studio/README.md)。第三方组件许可见 [THIRD_PARTY_LICENSES.txt](workflow_studio/THIRD_PARTY_LICENSES.txt)。
