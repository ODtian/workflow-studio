# Workflow Studio

一个使用 Gradio 官方前端组件的 marimo 面板，加载多个 Python 工作流。每个工作流自行声明参数和执行代码，面板动态生成表单并显示进度、预览、结果。

## 组合工作台

启动时加载 MOSS、MiniMax H3 与 Pi 对话。顶部标签页切换工作流，每个标签页拥有完整宽度的参数区和输出区。切换时页面保持挂载，各自保留输入、输出和运行状态。“工作流管理”展开添加、导入和刷新操作，同一个工作流可以添加多份。手机端精简顶部工具区、折叠模型选择并扩大主要输入及正文区域。

文本工作流的输出区域可以选择其他工作流的文本参数，点击“填入参数”后继续编辑和生成。GPU 推理任务依次执行，等待中的任务和执行中的任务均可单独停止。

## 设置保存

模型选择、LoRA 参数、采样与加载参数、提示词、H3 时间轴分段与布局、工作流标签页组合及当前标签页在修改后通过 `workspace_store` 自动保存到 Notebook 持久缓存，格式为标准 gzip。保存期间显示提示，完成后收起。重新打开面板时恢复配置，同一工作流的多个标签页分别保留参数。

页面中的参数和提示词属于配置；上传图片、视频、音频属于临时内容。生成媒体、历史索引和会话文件使用 `/tmp/workflow-studio-runtime/`，随运行容器回收。页面运行内容经 widget 消息通道传递，模型目录恢复期间下拉框保留所选文件名。源码通过 Git 更新。

## llama.cpp

LLM 对话通过 llama-cpp-python 在 notebook 进程内直接调用 libllama。默认模型为 OrcaRouter Qwen3.8-27B Uncensored Q8_0，配套独立 MTP 草稿头与 BF16 mmproj 图像投影器。主模型、投影器和草稿头分别选择，并通过 GGUF 元数据识别文件用途。

模型放在 model_dir/LLM/ 下。llm_models.json 保存公开下载来源与固定版本，运行时恢复所选权重。官方预编译 CUDA wheel 在首次使用时安装。MTP 调度器通过本地函数和线程队列执行，生成结果通过 Python 迭代器返回。

默认上下文 32768 tokens、GPU 层数 999、输入批处理 2048 tokens、MTP 2 步。对话设置提供 Thinking、推理强度、采样参数与模型驻留控制。生图与对话交替时复用各自的模型缓存；选择“生成后释放显存”时释放 LLM。

对话层使用 Pi coding agent SDK 1.4.0，通过 JSONL 标准输入输出管道调用 notebook 内驻留的 llama.cpp。Pi SessionManager 接收当前聊天分支，管理上下文并发布流式事件。前端显示会话、生成状态、Thinking、完整对话链路首字时间及模型生成速度。

## Pi 工作流工具

Pi 提供两个填写页面参数的工具，调用完成后可继续在对应工作流编辑并点击生成。

- `set_image_workflow(workflow, prompt, aspect_ratio)`：按面板 ID 或唯一的工作流文件名选择生图工作流，填写提示词与画面比例。比例采用 `16:9`、`1:1` 等格式；宽高沿用页面的像素总量与对齐步长，采样设置继续使用页面当前值。
- `set_h3_timeline(segments, workflow?)`：按 `segments` 数组重建 H3 片段。每段时长读取 H3 页面“自动分段时长”对应的 `segment_seconds`，总时长自动更新为片段数乘每段时长。存在多个 H3 面板时使用 `workflow` 指定面板 ID。

每个 H3 片段以 `prompt` 指定提示词，可设置 `name`、`references`、`loras`、`anchors`、`audio` 与衔接参数 `method`、`context_frames`、`audio_context_frames`、`blend_frames`。参考素材使用已有素材 `id`，或提供本地临时文件的 `path`、`kind`（`image`、`video`、`audio`）。LoRA 使用文件列表中的 `name` 和 `strength`。锚点由片段内的相对秒数 `time` 与素材 `source` 组成，工具将其换算为整条时间轴的时间。片段省略参考、LoRA 或锚点时，对应作用范围为空；已有素材池、LoRA 列表和时间轴布局继续保留。

以下为调用示例；示例中的面板、素材 ID 和 LoRA 名称由实际页面目录替换：

```json
{
  "workflow": "image-panel-id",
  "prompt": "清晨的山间湖泊，柔和自然光",
  "aspect_ratio": "16:9"
}
```

```json
{
  "workflow": "h3-panel-id",
  "segments": [
    {
      "prompt": "一位成年人走进咖啡店",
      "references": [{"id": "reference-id"}],
      "loras": [{"name": "style.safetensors", "strength": 0.6}],
      "anchors": [{"time": 0, "source": {"id": "reference-id"}}]
    },
    {
      "prompt": "镜头转向窗边的咖啡杯",
      "anchors": [{"time": 1, "source": {"path": "/tmp/window.png", "kind": "image"}}]
    }
  ]
}
```

此 H3 示例在页面每段设为 5 秒时得到两个 5 秒片段，总长 10 秒；第二段锚点位于整条时间轴第 6 秒。

调用链：`worker.mjs` 注册工具与当前工作流目录 → 通过现有 JSONL 管道发出 `workflow_request` → `pi_runner.py` 调用 `workflow_tools.py` → 复用 `save_settings`、`publish` 保存并发布参数 → 前端收到 `workflow_parameters` 后更新对应工作流的表单。H3 资源作用范围沿用 `h3_timeline.plan_timeline` 的数据结构和校验。提示词与参数通过已有配置保存链路写入 gzip；素材继续使用临时引用。

## 文件传输

“文件”标签页使用 Gradio 的下拉框、多选框、文本框和按钮，同时展示 Google Drive 与 Molab 两栏。文件夹直接列在列表中，点击进入；可多选文件，复制到另一栏当前目录。两栏分别浏览、刷新和显示复制进度，手机端也保持两栏。原有 `transfer_core` 队列继续处理文件；`files_bridge.py` 将队列和持久复制清单接入工作台。

首次连接使用 Drive 栏的“连接 Google Drive”按钮，在 Google 页面授权后将一次性授权码填回工作台。“完成连接”将授权配置保存到本 Notebook 的 Secrets 并读取 Drive 根目录；后续启动自动重连，授权更新使用同一入口。授权码只用于当前连接流程。

手机端将全选和刷新合并到标题行，目录栏显示当前文件夹名，文件名以两行展示。列表随屏幕高度展开、两侧分别滚动；底部保留 44 像素复制按钮，并显示选中文件数量、总大小和目标目录。

“快捷复制”保存可重复执行的“源文件 → 目标目录”操作。双栏复制时自动保存，使用 Drive 文件 ID 和 Molab 路径持久定位；下次打开工作台即可从对应行一键复制到保存的目录。支持搜索、新增、管理、删除和撤销删除；编辑时分别标明源文件与目标目录。Drive → Molab 的目标目录会在执行时创建。传输历史折叠展示，完成的传输记录可单独删除及恢复。

## MOSS-Image

启动时建立 Comfy 模型目录，molab 默认位置是 `/tmp/molab-comfy-runtime/models`：

```text
models/
├── diffusion_models/  # MOSS Base / SFT 的 .safetensors
├── text_encoders/     # 配套 Qwen3.5-9B 的 .safetensors
├── vae/               # FLUX.2 VAE 的 .safetensors
├── loras/
├── embeddings/
├── LLM/               # GGUF 主模型、mmproj 与 MTP 权重
└── vae_approx/
```

把文件放入目录，模型列表会在工作台可见时每 5 秒自动检查目录变化，更新 DiT、TE、VAE 和 LoRA 选项，首次可用的模型自动选中。已有模型选择、LoRA 权重和采样参数继续保留；模型区的“刷新模型”按钮可立即更新。从三个下拉框选择 DiT、TE、VAE 后点击“生成图片”。加载器读取权重结构和量化元数据，自动选择对应实现。目录位置由环境变量 `WORKFLOW_MODELS_DIR` 指定。

MOSS 工作流复用 Comfy 的 `load_diffusion_model`、`load_clip`、`VAE` 和采样模块，在 notebook 的后台线程执行。首次运行会准备自己的 Comfy 核心代码及依赖。`WORKFLOW_COMFY_ROOT` 可指定现有的 Comfy 代码目录，版本应包含 MOSS-Image 支持。

共享核心固定为 Comfy 0.42.0。MOSS 默认启用 Spectrum Adaptive，预热步数、误差容忍度和特征缓存设备可在高级设置调整；采样结束后运行信息显示实际计算和特征预测次数。

H3 的注意力选择提供 Spark-H3，自动模式在 CUDA 13 的 SM86、SM89、SM120 GPU 上优先使用。选择自动或 Spark-H3 时，`h3_spark.py` 在 Comfy 首次导入前调用上游安装器准备匹配的内核；安装器以 `python -m comfyui.install` 运行，显式指定源码导入路径，沿用 Molab 的安全导入设置。安装日志保存在临时运行目录，错误原因进入运行信息。LoRA、Sigma Shift 之后调用上游原生模型补丁，沿用当前图片、视频和分段采样路径。保真模式使用 20% 预热，速度模式使用 0% 预热，自定义模式读取页面预热比例；精确计算比例默认 20%，可选仅生成视频或参考视频与生成视频联合稀疏。短序列沿用上游的精确计算路径。源码、内核及运行缓存使用临时目录，控制参数通过 Notebook gzip 配置保存。

MOSS 的 Base / SFT、BF16、INT8 ConvRot，以及 Qwen3.5-9B 的 BF16、INT8 ConvRot、W4A8 GPTQ 使用这些原生加载器。预览使用采样中的 Latent2RGB；最终结果由所选 FLUX.2 VAE 解码。默认采用 50 步、CFG 3、Euler / simple、Shift 5 和负分支跳过第 22 层。

Diffusers 工作流按其模型目录中的配置识别预量化权重；MOSS 的 Comfy 文件格式由本工作流的原生文件加载器处理。

采样器和调度器读取已加载的 Comfy 核心完整列表；核心初始化前使用随包的 `sampling_options.json` 完整目录。长列表支持搜索。默认 Euler / simple。

`beta57` 使用 Comfy 原生 beta 调度函数的 `alpha=0.5, beta=0.7`，与 RES4LYF 对应定义一致，通过采样函数的 `sigmas` 参数传入。

LoRA 从 `loras/` 扫描，点击“添加 LoRA”后逐项选择文件和权重；按列表顺序调用 Comfy 原生 LoRA 加载器叠加。基础模型与 LoRA 组合分别缓存，调整 LoRA 权重后重建组合。提示词和负面提示词文本框的“粘贴”按钮用剪贴板文本替换当前内容。

图片预览和最终展示通过 widget 二进制缓冲区传递 JPEG，浏览器生成 Blob URL 展示，原图 PNG 保存在输出目录。

点击结果图片或右上角放大按钮，使用 PhotoSwipe 查看细节：电脑滚轮缩放、鼠标拖动；手机双指缩放、单指拖动，支持双击缩放。查看器先展示已有预览，再通过 widget 二进制通道按需读取原始 PNG，并保持当前缩放位置；点击关闭或按 Esc 返回参数页面。

尺寸可直接输入 MP（百万像素），按 Enter 或移开焦点后自动按照当前宽高比换算。提供 0.5、1、2、4 MP 快捷选择，以及 1:1、4:3、3:4、3:2、2:3、16:9、9:16、21:9 比例按钮；切换比例时保持接近当前像素总量。宽高按工作流的尺寸步长对齐，仍可手动编辑。自定义工作流通过 `SPEC["size_presets"]` 声明该区域、宽高参数名和 `step`。

## 模型初始化

切换到工作流或选择模型后，后台线程会准备当前模型，界面保持可编辑；运行任务与模型准备共用推理锁。短时间连续选择时合并待准备的参数。模型读取进度显示在模型选择附近，阶段耗时记录在“运行信息”。

Comfy 运行库与 llama.cpp 绑定各自在本次内核中准备一次。MOSS 的 DiT、TE、VAE 分别复用，改变其中一项时保留其余组件；已编码的提示词保留最近四项，后台准备时也会编码当前负面提示词。llama.cpp 保留当前 GGUF 模型实例；上下文、批大小、投影器或 MTP 参数改变时重建对应实例。

## 运行

当前 GitHub 入口使用 `workflow-studio` 启动包：在 Notebook 包管理器添加 `workflow-studio @ git+https://github.com/ODtian/workflow-studio.git@main`，随后通过 `from studio_entry import load_studio` 导入。`notebook.py` 的脚本依赖已包含这一配置，启动单元格调用 `load_studio()` 并显示 widget，源码更新和临时运行目录由启动模块准备。

molab：上传标准源码包 `workflow_studio.zip`、`studio_bootstrap.py`、`studio_config.json` 到 notebook 工作目录（当前实例为 `/marimo`），再将 `molab_cell.py` 放入一个 Python 单元格运行。ZIP 采用二进制文件上传；也可先上传 Google Drive，再使用现有文件复制工具复制到 `/marimo`。入口优先解压 ZIP 中的源文件和资源，配置文件与可编辑工作流沿用现有内容。

更新时覆盖同名 `workflow_studio.zip`，重新运行启动单元格。增量包沿用相同目录结构，只放入需要更新的文件；入口将其覆盖到对应目录。开发机通过 `python work/make_bundle.py workflow_studio/llama_runner.py` 构建单文件更新包，通过 `python work/make_bundle.py` 构建完整包。Python 改动只传 Python 文件；前端改动传编译后的 `assets/view.js` 与 `assets/components.css`。

`studio_config.json` 的 `source_drive_id` 指向 Drive 中的完整源码 ZIP。本地源码包缺失时，启动入口通过 notebook 已保存的 Drive 连接自动下载并解压。更新 Drive 中同一个文件可保留文件 ID；完整包用于新实例恢复，增量包用于当前实例更新。

目录结构如下：

```text
/marimo/
├── notebook.py
├── workflow_studio.zip   # 二进制上传的源码与资源包
├── studio_bootstrap.py
├── studio_config.json
├── workflow_studio/       # Python 模块、工作流模板、assets 前端文件
└── studio_workflows/      # 启动时建立，可编辑的工作流
```

notebook 单元格只负责导入和启动：

```python
import marimo as _studio_mo
from studio_bootstrap import get_studio as _get_studio

studio_panel = _get_studio()
_studio_mo.ui.anywidget(studio_panel)
```

`studio_config.json` 配置模型目录、Comfy 核心目录、工作流目录和结果目录。前端资源从 `workflow_studio/assets/` 加载，工作流从 `studio_workflows/` 加载。新增工作流放入该目录，再点击“刷新”。

资源恢复负责界面和工作流代码；模型沿用 `model_dir` 中的文件及现有的复制工具。Molab 启动并执行 notebook 后会显示面板。模型目录结构随工作流加载建立，模型文件由用户放入。

当前 notebook 的 `/marimo/pyproject.toml` 已通过 Files 保存以下启动设置，下次启动时自动执行入口：

```toml
[tool.marimo.runtime]
auto_instantiate = true
```

本地：

```sh
pip install -r requirements.txt
marimo edit notebook.py
```

在现有 notebook 中新增一个单元格：

```python
import marimo as studio_mo
from panel import get_panel
studio_mo.ui.anywidget(get_panel())
```

界面使用 Gradio 的 Textbox、Number、Dropdown、Button、Image 组件及 Soft 主题。参数、图片和执行状态通过 anywidget 与 marimo notebook 通信，Python 工作流在内核的后台线程执行。编译后的前端随源码包提供，运行时加载 `assets/` 中的资源。

修改前端时，在 `frontend/` 目录执行 `npm ci` 和 `npm run build`。Gradio 组件版本记录在 `package.json`，依赖版本记录在 `package-lock.json`；`theme.css` 使用 Gradio 6.30.0 的 Default 主题、orange 主色和系统字体。

本地使用扩散示例时，安装 `requirements-diffusers.txt`。molab 中的扩散示例会在首次执行时准备自己的 Diffusers 依赖；面板加载时只初始化界面与工作流声明。

## 添加工作流

将 `.py` 文件放入 `workflows/`，点击“刷新”；也可点击“加载工作流”导入代码。

下面是一个最小工作流示例，用于说明参数声明和执行接口：

```python
SPEC = {
    "name": "我的工作流",
    "description": "本工作流的用途",
    "fields": [
        {"key": "text", "label": "文字", "type": "textarea", "default": "hello"},
        {"key": "size", "label": "尺寸", "type": "number", "default": 512},
        {"key": "mode", "label": "模式", "type": "select",
         "default": "a", "options": ["a", "b"]},
    ],
}

def run(params, ctx):
    # 在这里组织自己的模型、算法或 API 调用。
    # 每完成一步，用 ctx.progress(step, total, preview=PIL图像) 推送预览。
    # 用 ctx.status("加载模型…") 更新状态。
    # 用 ctx.check_cancelled() 响应停止。
    # 用 ctx.metadata(引擎="自己的后端") 显示额外状态。
    from PIL import Image
    image = Image.new("RGB", (params["size"], params["size"]), "#e5eddc")
    ctx.progress(1, 1, image)
    return image  # 支持 PIL.Image、图片文件路径，或这些对象的列表。
```

字段类型：`text`、`textarea`、`number`、`select`、`image`。`section` 指定分组；数值字段可设 `min`、`max`、`step`；图片字段支持文件上传和容器 / Drive 内的路径，可用 `ctx.image(params["image"])` 读取为 PIL 图像。每个工作流可以使用完全不同的字段。

`SPEC` 可设 `run_label` 定义运行按钮文字。参数由各工作流读取、解释和执行；提示词、随机种子与采样设置属于具体的扩散工作流。

文本工作流设置 `SPEC["output"] = "text"`，`run(params, ctx)` 返回字符串；生成过程中调用 `ctx.text(当前完整文本)` 推送增量显示，结束时可用 `ctx.text(完整文本, final=True)` 立即刷新。文本结果保存为 UTF-8 TXT。现有图片返回值接口继续用于图片工作流。

## 随包示例工作流

- `moss_image.py`：从 Comfy 模型目录选择 MOSS-Image Base / SFT、TE、VAE。
- `llama_cpp.py`：选择 LLM 目录中的 GGUF，进程内流式文本推理。
- `sdxl.py`：Diffusers SDXL 文生图 / 图生图。
- `sd15.py`：Diffusers SD 1.5 文生图 / 图生图。
- `image_grade.py`：Pillow 图片调色，自有参数与执行过程。

扩散工作流支持模型 ID、Diffusers 目录或对应架构的单文件 checkpoint；单文件模型的配置与文本编码器由 Diffusers 加载。支持 Euler、DPM++ 2M、DPM++ 2M SDE，normal / Karras 调度、CFG、种子、步数、尺寸、批量和图生图重绘幅度。实时预览来自采样中的 VAE 解码。

预览与成品共用单一图片区。实时预览以 512px JPEG、最高每秒两帧发送；成品先发送一份最长边 1536px、质量 92 的 JPEG 展示图。完整 PNG 保存到结果目录，点击“下载原图 PNG”时通过 widget 二进制缓冲区传输。结果列表只同步文件名、尺寸和大小。PNG 的 `workflow_studio` 元数据包含工作流和参数；错误详情在结果目录的 `last_error.log`。输出目录在 `studio_config.json` 配置。

工作流 `.py` 是可执行的 Python 代码，按自己的项目代码管理。工作流决定推理后端与依赖；`panel.py` 负责界面通信和任务生命周期。

