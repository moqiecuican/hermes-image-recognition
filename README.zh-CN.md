# image-recognition — Hermes Agent 视觉识别技能

**一个 [Hermes Agent](https://github.com/NousResearch/hermes-agent)（Nous
Research）技能：让原生多模态主模型直接"看到"图像（像素直入上下文），并内置
原生/兜底双视觉路径的诊断工具。**

> 🌏 [English README (README.md)](README.md)

---

## 它解决什么问题

Hermes 的视觉有两条通道：

1. **原生快速路径** —— 图像以携带图像本体的结构化工具结果从 `vision_analyze`
   回到主模型上下文（Hermes 源码中称 `_multimodal` envelope），主模型
   **亲自看像素**。无辅助模型参与、无信息损失。
2. **辅助转述路径（兜底）** —— 由独立的 `auxiliary.vision` 模型看图后返回
   **文字转述**，像素从不进入主模型上下文。有损：布局、小字、精确颜色都会
   退化。

坑在于：Hermes 默认的 `auto` 模式下，**只要配置过显式的
`auxiliary.vision`，原生路径就会被压制**——即使主模型本身完全是多模态的。
很多用户因此一直在拿"隔着毛玻璃"的转述看图而不自知。本技能就是为了用一条
命令修好它，并让你随时能可靠地确认当前走的是哪条路径。

## 兼容性

| Agent | 是否支持 |
|---|---|
| **Hermes Agent**（Nous Research） | ✅ 本技能专为它构建 |
| Claude Code、Codex、OpenClaw 及其他 agent 框架 | ❌ 不兼容 |

本技能挂钩 Hermes 内部 API（`tools/vision_tools.py`、
`agent/image_routing.py`、`agent/auxiliary_client.py`、
`hermes_cli.config`）与 Hermes 管理的状态（`config.yaml`、models.dev
磁盘缓存）。已在 Hermes Agent v0.21.x 上验证；内部 API 可能随版本漂移，
升级后请重跑诊断脚本。

## 路径判定原理

`vision_analyze` 在以下条件**全部满足**时选择原生快速路径（见
`tools/vision_tools.py::_should_use_native_vision_fast_path()`）：

```
agent.image_input_mode == native
且二者其一：
     provider 在"工具结果可携带图像"静态白名单
     （anthropic / openai / openai-codex / gemini-3 / 聚合器；
      很多直连 provider 并不在名单里）
     或
     models.dev 元数据判定该模型支持视觉
     （落盘缓存于 <hermes-home>/models_dev_cache.json；
      运行时判定永不依赖网络）
```

白名单设计上是保守的——zai 这类 provider **不在名单内**，其模型靠
models.dev 分支通过（如 `glm-5.3-flash`）。库里没有的模型可用配置覆盖
手动声明，覆盖优先级高于缓存。

## 功能特性

- **一条命令诊断** —— `check_vision_path.py` 输出四行判定（附图路由 /
  工具结果图像 / 模型视觉判定 / 最终路径），可查当前模型，也可查任意
  provider+model 组合
- **初装引导** —— 覆盖所有错误配置组合的决策树，包括辅助压制大坑与
  全新安装缓存缺失
- **换模型自检** —— 更换 provider/model 后，先确认视觉仍走原生再依赖它
- **跨平台** —— Linux、macOS、Windows（便携 `HERMES_HOME` 探测；导入
  失败时输出可操作的指引而非裸报错）
- **纯只读** —— 诊断脚本绝不修改任何配置

## 安装

把本目录克隆到 Hermes 技能目录：

```bash
# 默认 Hermes home
git clone https://github.com/moqiecuican/hermes-image-recognition.git \
  ~/.hermes/skills/autonomous-ai-agents/image-recognition

# 自定义 Hermes home
git clone https://github.com/moqiecuican/hermes-image-recognition.git \
  "$HERMES_HOME/skills/autonomous-ai-agents/image-recognition"
```

新会话中技能即可见（会话技能加载器在启动时缓存）。

## 快速开始

用你 Hermes 安装自带的 venv 运行诊断脚本：

```bash
# Linux / macOS
~/.hermes/hermes-agent/venv/bin/python \
  ~/.hermes/skills/autonomous-ai-agents/image-recognition/scripts/check_vision_path.py

# Windows
%USERPROFILE%\.hermes\hermes-agent\venv\Scripts\python.exe ^
  %USERPROFILE%\.hermes\skills\autonomous-ai-agents\image-recognition\scripts\check_vision_path.py
```

不带参数检查**当前**主 provider/model；带两个参数检查任意组合：

```bash
check_vision_path.py zai glm-5.3-flash
```

### 判定读法 —— 决策矩阵

| 附图路由 | 模型视觉判定 | 含义 | 行动 |
|---|---|---|---|
| `native` | `True` | ✅ 原生路径已生效 | 无需动作——用真图验收一次 |
| `native` | `None` | ⚠️ 全新安装（无缓存）或未知模型 | 正常启动一次 Hermes 建缓存，或显式声明（见下） |
| `native` | `False` | 模型被归类为纯文本 | 确实纯文本 → 保留兜底；实际多模态 → 显式声明（见下） |
| `auto` + 显式 `auxiliary.vision` | 任意 | ❌ **原生视觉被压制**（最常见大坑） | `hermes config set agent.image_input_mode native` |
| `auto`（无 aux 配置） | `True` | ✅ 原生路径已生效 | 无需动作 |
| `text` | 任意 | 有意强制走兜底 | 保持即可，除非是误设 |
| 任意 | 声明后 provider 报 400 | 声明与实际不符 | `hermes config unset model.supports_vision` |

### 两条最关键的修复命令

```bash
# 大坑：auto 模式下显式 auxiliary.vision 压制原生视觉
hermes config set agent.image_input_mode native

# models.dev 无记录的自部署/新发布多模态模型
hermes config set model.supports_vision true
```

两者都是每轮重读配置即时生效——无需重启。回滚用
`hermes config unset <键名>`。

### 验收测试

调用 `vision_analyze(image_url=<本地图片>, question=...)`，看工具结果
首行：

- `Image loaded into your context — you can see it natively now.` → 原生
- `{"success": true, "analysis": "..."}` → 仍在兜底路径

## 常见问题排查

- **脚本报 `Could not import Hermes internals (ModuleNotFoundError: ...)`**
  → 脚本无法加载 Hermes API：要么用错了解释器（请用 Hermes 安装自带的
  venv：Linux/macOS `venv/bin/python`；Windows `venv\Scripts\python.exe`），
  要么没找到 Hermes 数据目录（设置 `HERMES_HOME=/path/to/.hermes` 后重试；
  变量指向不存在的路径时脚本会回落 `~/.hermes`）。
- **`HERMES_HOME does not exist - falling back to ~/.hermes`** → 你设置的
  `HERMES_HOME` 指向不存在的路径。注意行为差异：Hermes 核心会照用该路径
  （空配置），而本脚本会回落 `~/.hermes` 继续诊断——请修正变量取值，使
  判定与运行时一致。
- **已知多模态模型判定为 `None`** → 全新安装：正常启动一次 Hermes 以生成
  `models_dev_cache.json`；仍无记录：用 `model.supports_vision true`
  覆盖（不依赖缓存）。
- **声明 `supports_vision` 后 provider 报 HTTP 400** → 声明与模型实际不符，
  用 `hermes config unset model.supports_vision` 撤销。
- **修复后仍看到转述风格结果** → 重跑诊断；若显示 NATIVE，那是改动前的
  旧输出，重新截图/重新调用即可。
- **Agent 的文件工具拒绝编辑 config.yaml** → 这是设计行为（安全守卫）。
  改用 `hermes config set/unset`；手动编辑请先备份。
- **多 profile** → 每个 profile 有独立 `config.yaml`，按需逐个设置。
- **长会话 token 消耗上升** → 原生图片每轮重发是设计代价；对精度要求不高
  的场景可降级用兜底路径。

## FAQ

**初装引导每次看图都会跑一遍吗？**
不会。技能文本只在相关任务时加载一次；脚本是手动工具（安装后、换模型后、
排障时）。运行时 Hermes 每次调用都会自行毫秒级重新选路——纯本地、不联网、
无额外 token。引导是一次性的 setup 过程，不是每次看图的税。

**中途换模型，视觉会自动适配吗？**
会。路径判定无状态，每轮都按当前主模型重算：多模态→原生，纯文本→兜底，
历史里已有的图片也会被安全转换/剥离以适配纯文本模型。唯一需要动手的
情况：models.dev 无记录的模型，加一行 `supports_vision` 覆盖即可。

**为什么要保留 `auxiliary.vision` 配置？**
它是降级保险而非冗余：纯文本模型的兜底转述、快速路径未触发时的 legacy
路径、历史图片的自动转述全靠它。删掉就失去了整条降级链。

**`native` 模式下用纯文本模型会崩吗？**
不会——API 调用前有最后机会文本兜底，会转换/剥离图像部件。

## 参与贡献

欢迎 Issue 与 PR。提交改动前后请各跑一次诊断脚本并附上输出。

## 开源协议

[MIT](LICENSE) © moqiecuican

## 致谢

- 双路径视觉机制、快速路径开关，以及把图像本体（而非文字转述）带回主模型
  上下文的工具结果机制，均为
  [Hermes Agent](https://github.com/NousResearch/hermes-agent)（Nous
  Research）的组成部分——本技能只是围绕它们打包了诊断与配置引导，自身
  不含私有逻辑。
- [models.dev](https://models.dev) —— 社区维护的模型能力数据库，Hermes
  集成它做视觉能力判定。
