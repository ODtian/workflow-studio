# Workflow Studio 私密工作流最小验证

入口为 `privacy_probe_notebook.py`，验证分支为 `codex/private-notebook-probe`。

密码层现在复用仓库原有的完整 `WorkflowPanel` / `FilesBridge` 后端，恢复 MOSS、MiniMax H3、Pi、SD 1.5、SDXL 和图片调色，并保留运行时导入的私密工作流。公开仓库中的界面与运行框架作为公共基座。已经完成的私密性验证范围是单文件 Python 文本工作流、提示词、一张图片输入、Python 标准输出与错误输出、文本结果，观察入口为项目文件、持久缓存、widget 状态和 notebook 快照。

## 调用与数据链路

1. Notebook 保留四行入口，调用现有 `studio_entry.load_studio(privacy_probe=True)`；启动包更新公开源码后，仓库中的 `get_private_studio` 创建密码界面并衔接原有加密数据。界面继续由 `mo.ui.anywidget` 承载，浏览器解锁后加载已有 `assets/view.js` 的 Studio 界面。
2. 用户首次在浏览器设置密码，之后输入密码解锁。浏览器以随机盐和 600,000 次 PBKDF2-HMAC-SHA256 派生密码密钥，生成独立的消息密钥，以 RSA-OAEP 封装后通过现有 widget 自定义消息发送。密码保留在浏览器内存；实际内容密钥以密码密钥加密封装，公开元数据保存盐、迭代次数及封装密文。
3. 浏览器适配器以 AES-256-GCM 加密工作流源码、参数、图片和控件操作，继续使用原来的 widget 通道。服务端解密后用 `compile` / `exec` 加载单文件模块，通过原有 `WorkflowSession` / `RunContext` 执行。
4. `PrivateStudioProbe.send` 加密界面状态和结果，浏览器解密后交给原来的 Studio 组件。同步到 notebook 的 widget 属性为公开资源、协议名称和公钥。
5. `EncryptedStore.write(name, value)` 为每次写入生成独立随机 nonce，并将相对路径作为认证数据。源码、参数、日志和结果以密文写入验证目录；持久缓存保存相同的密文字节。
6. 文本结果保存继续走原有 `WorkflowSession.execute`，其写入点委托 `owner.write_text_result`。普通 Studio 的实现沿用原有内容存储，私密验证实现使用 `EncryptedStore`。

## 运行

在 molab 导入本分支的 `privacy_probe_notebook.py`。运行单元格，首次在浏览器填写并确认工作台密码，之后使用同一密码解锁。通过“导入私密工作流”提交源码，再在原有参数控件中填写输入并交互执行。

```python
import marimo as mo
from studio_entry import load_studio
studio_panel = load_studio(privacy_probe=True)
mo.ui.anywidget(studio_panel)
```

Notebook 的脚本依赖声明负责安装本分支的启动包。源码更新、密码派生配置和已有存储衔接均由仓库代码处理。

解锁后，原工作台顶部工具栏提供“修改密码”，工作流导入沿用原有“工作流管理”。输入当前密码、新密码并确认后，浏览器为新密码生成随机盐并派生新的封装密钥，通过已有加密 widget 通道提交。服务端验证当前密码后，更新内容密钥的加密封装与持久缓存，已有工作流和结果继续沿用原来的内容密钥。后续解锁使用新密码。

`EncryptedWorkflowPanel` 继承原有后端并把命令交回 `WorkflowPanel._message`。原来的预览队列、生成器、文件队列和 OAuth 流程继续使用；widget 的消息出口经外层加密。Drive 授权使用原有 `DriveAuthorization` / `connect_from_secrets` 的缓存接口，凭据存入密码保护的 notebook 缓存。OAuth 同意和授权码提交由用户在原页面完成。

私密工作流使用 `SPEC` 和 `run(params, ctx)` 这一现有接口。图片通过 `ctx.image` 从内存读取，文本结果通过返回值交给运行器加密保存。GPU 运算在原有 notebook 内核中执行。

## 验证入口

`python -m unittest discover -s tests -p test_private_probe.py -v`

该检查实际导入并执行带随机探针的私密工作流，检查 widget 状态、传输记录及生成文件，同时确认正确密码能读回结果、错误密码保持锁定，并验证原密钥版本的数据可在已解锁会话中转为密码保护。

GPU 验证以 `torch.cuda` 的实际运算结果为依据。图片/视频生成器、Pi 子进程会话和 Drive 凭据的完整迁移，分别需要接入同一加密边界。

## 本次云端实测

2026-10-31，在 molab 的 RTX PRO 6000 Blackwell Server Edition / CUDA 13.0 上执行了私密工作流，CUDA 求和结果为 523776。原有 Studio 控件展示解密后的提示词、参考图和文本结果。

只读扫描覆盖 `/marimo` 和验证本子使用的公开源码目录，共 182 个文件，并检查了 widget 同步状态与实际 session 快照。源码、提示词、输入、结果、日志的五类随机探针以及解锁密钥的原始/十六进制/Base64 表示均通过检查。错误密钥被拒绝，已有结果保留。匿名访问普通 notebook 链接时显示公共启动代码及运行态 widget 占位；重新分配容器后的静态预览呈现旧 widget 模型引用。所有者的运行会话通过密钥显示完整界面。容器重新分配后，使用原密钥恢复了加密保存的工作流和提示词。
