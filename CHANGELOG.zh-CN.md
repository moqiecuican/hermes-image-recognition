# 更新日志

本项目所有重要变更均记录在本文件。
格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循[语义化版本（Semantic Versioning）](https://semver.org/lang/zh-CN/)。

> 🌏 [English (CHANGELOG.md)](CHANGELOG.md)

## [0.5.0] - 2026-10-10

### 新增
- `check_vision_path.py` 会话运行时模型解析 —— /model 热切换大坑从"文档
  警告"升级为"已解决的工具能力"：
  - `--session <id>`：权威运行时模型对，来自
    `<hermes-home>/state.db` → `session_model_usage`（task='' 为主对话；
    只读连接 + schema 校验；上游 schema 漂移时明确报 "schema mismatch"，
    绝不静默输出错误结论）。
  - `--anchor '<消息前缀>'`：用消息前缀 grep `agent.log` turn_context
    行，再经 session_model_usage 确认；日志与库不一致时打印
    DISCREPANCY 并自动采用更新的一对。
  - 无参双视角：config 主模型 + 最近活跃会话并排展示；MISMATCH 块主动
    揭示热切换（展示用启发式；多个并发 TUI 窗口 = 多个会话）。
  - 鲁棒性：state.db 只读打开（WAL 安全）、每个失败形态（未知会话、
    锚点未命中、坏 flag）都有明确报错 + 降级建议、按实测日志限制实现
    （msg= 截断 ~90 字符 / 仅首行 / ~5 MB 轮转）。
- 两条新 Pitfall，来自 2026-10-10 实战事故（config override 把纯文本
  模型误声明为多模态）：
  - "'native 首行'是声明，不是交付证明"：运行时工具门禁同样读 CONFIG
    模型对，热切换会话里它可能给看不见图的的原模型包一层原生信封——
    首行照样说 `Image loaded`，发送路径却静默丢掉像素。会话内证据才算
    数：回答须反映像素，且下一次 API 调用的入参须增长图片量级的 token
    （0.2 MB 真图 +数千 vs 剥离注记 +数百）。
  - "`supports_vision` override 是假设——先实测再信任"：写错方向的
    `true` 是过时 veto 的镜像（xiaomi 案例）：过时 veto 只是诚实地挡路，
    假 `true` 会主动误路由。要求端点限定命名——同一模型家族可在不同
    端点多模态/纯文本并存（deepseek-flash @ deepseek vs 聚合端点的
    deepseek-v4-flash-0731 / glm-5.3 类）。
- Registry：intern-inkstone/glm-5.3 的 NEGATIVE 条目（10-10 两次真图
  实测失败后移除 override；models.dev 30+ provider 一致 text-only）与
  intern-inkstone/deepseek-v4-flash-vision 的 UNVERIFIED 条目（已声明，
  但该模型无法发出有效工具调用、验证未完成）。
- `probe_tool_media.py`：非标准环境变量名兜底（如 intern-inkstone 对应
  `INTER_INKSTONE_API_KEY`）+ intern-inkstone base-url 默认值。

### 变更
- 发布前从 0.4.1 升到 0.5.0：本版范围（新 CLI 模式、新文档章节、新
  验证方法论）是 minor bump，不是 patch。

## [0.4.0] - 2026-10-10

### 新增
- `scripts/probe_tool_media.py`：决定性双请求端点探针（1×1 红色 PNG，
  tool-result 与 user-message 双通道），用实测**仲裁** profile 否决声明，
  而不是相信声明——声明只是关于端点的假设，探针才是地面真值。内置判定
  规则：仅 200 不够（模型必须说出探针颜色——接受 ≠ 能看见）；400 区分
  内容/格式错误（声明仍准确）与型号错误（型号已下线，非通道证据）。
  密钥进程内读取、绝不打印。
- Pitfalls 新增"声明过时"修正流程：当探针与
  `supports_vision_tool_messages=False` 矛盾时，直接改正插件 profile——
  备份 + 哈希清单 → 普查该 provider 下所有在用型号 → 翻转标志位 →
  重启进程 → 分层验证 → 登记 registry。config 解不开否决，插件 profile 可以。
- 未知模型门禁新增分支：FALLBACK + `model vision: True` + 否决注释
  （"能力有、渠道被否"形态），先跑探针仲裁再做任何决定。
- `references/vision-channels-and-vetoes.md` 新增案例研究：一条过时否决把
  完全多模态的模型按在有损回退路径上，直到探针证伪声明（探测章节并挂上
  脚本引用）。
- `references/confirmed-vision-models.md` 新增登记条目：完整记录
  探针 → 修复 → 重启后验收的证据链。
- 操作层面的实例补强，让 agent 无需自行探索：agent 宿主进程重启操作卡
  （TUI `/exit` + `hermes --tui`、dashboard 停启、外部重启网关；多窗口
  说明；mtime 对 `ps` 的陈旧性检查）、翻转前型号普查的具体枚举步骤
  （config 搜索 + `GET /models` + 逐一探针）、门禁分支挂上实例指针。

### 变更
- 小字错读是路径中立的：两条路径都会自信地看错（实案：421×249 小图上
  原生把"80"读成"8"，而 aux 转述读对了）。单次小字读数不得作为路径质量
  论证的证据——先用 `region=` 裁剪复核，把两条路径的意见都当假设。
- 插件 profile 改动只在 agent 宿主进程重启后生效（provider 加载器的
  `sys.modules` 模块级缓存）：仅重启网关不够，同一 TUI/dashboard 进程内
  开新会话也不会重载插件 Python。checker（新起子进程）可立即验证磁盘
  状态；真图验收只在重启后的进程内才算数。
- "veto 是原因"的处置指引：先用探针仲裁声明是否仍准确，确认准确后才
  回退到用户消息通道 / aux 转述。

## [0.3.1] - 2026-10-09

### 修复
- `check_vision_path.py` 两参数分支改为调用上游门禁
  `_native_tool_result_images(provider, model, cfg)`，不再本地重算判定
  （issue #1）。旧公式跳过 profile 硬否决（`_profile_rejects_tool_media`），
  对"工具结果图像会被 HTTP 400 拒绝"的 provider（xiaomi/MiMo）误报
  NATIVE——用户信了判定，拿到的是报错而不是像素。缺少该带参门禁的旧
  安装回退为显式否决检查。
- 两份 README：决策树按上游顺序展示三层（路由 → profile 否决 →
  静态表/能力查询），写明 `_TOOL_RESULT_MEDIA_PROVIDERS` 的 13 个显式 id
  （"聚合器"不是表项字面值）与 `_GEMINI_PROVIDERS` 的 gemini-3 标签判定。
- SKILL.md：`_describe_image_for_anthropic_fallback` 的路径更正为
  `agent/vision_message_prep.py`（旧的 `run_agent.py` 位置已无法解析）。

### 新增
- 诊断脚本在 profile 否决导致 FALLBACK 时输出说明，避免把"会被 400 的
  provider"误认成能力缺失。

## [0.3.0] - 2026-09-10

### 新增
- SKILL.md 新增"会话首图未知模型门禁（unknown-model gate）"与
  "Quick verdict"两节：每会话/换模型后先门禁一次。当判定为 FALLBACK
  且能力查询返回 None（未知模型）时，先询问用户该模型是否为多模态并
  完成登记，再信任视觉输出——催生本版本的会话曾因静默的有损旁路损失
  约 13 轮验收。
- `references/confirmed-vision-models.md` —— 用户已确认视觉模型的追加式
  登记表（每条含证据与配置记录）。
- `check_vision_path.py` 新增 provider 别名缺口检测
  （`PROVIDER_TO_MODELS_DEV` 缺别名、而磁盘缓存里其实有视觉记录时），
  并输出含转义点的 `model_overrides.<provider>.<model>.supports_vision`
  修复命令。

### 说明
- 优先用精确登记 `model_overrides.<provider>.<model>.supports_vision`，
  而非全局 `model.supports_vision`（全局标志在切换模型后会错误声明纯文本
  模型）。含点模型 ID 在 `hermes config set` 中需 `\.` 转义；models.dev
  的磁盘缓存不可手改（TTL 刷新会丢弃手写条目）。

## [0.2.1] - 2026-09-04

### 修复
- 文档（SKILL.md 与两份 README）引用了脚本从未输出过的错误字符串
  （`Cannot locate Hermes installation`）；故障排查现已给出真实输出
  （`Could not import Hermes internals (...)`），并按可能性顺序列出两个
  成因（解释器用错 / Hermes 数据目录未找到）
- SKILL.md 引用了 Hermes 上游不存在的 `run_agent._prepare_messages_for_api`；
  现已改为指向真实的 API 期预处理符号
  （`_preprocess_anthropic_content` / `_strip_images_from_messages`）

### 新增
- `check_vision_path.py` 在 `$HERMES_HOME` 已设置但路径不存在时打印警告：
  Hermes 核心会照用该路径（得到空配置），而本脚本会回落 `~/.hermes`——
  警告让这种不对称可见，便于把诊断结论与运行时行为对照；两份 README 的
  故障排查章节同步记录了该症状

## [0.2.0] - 2026-09-04

### 新增
- 首次公开发布：双语 README（英文 + 中文）、MIT 许可证
- 便携式 `HERMES_HOME` 探测（`HERMES_HOME` 环境变量 → `~/.hermes` 回落）
  与友好的导入错误提示（可操作的指引，替代裸 traceback）
- 初装引导：五步决策树，覆盖所有配置组合，包括 `auto` 模式 + 显式
  `auxiliary.vision` 压制原生视觉的大坑与全新安装缓存缺失
- 换模型自检流程，以及明确的"Hermes Agent 专用"范围声明

### 变更
- 文档以功能性描述工具结果承载机制（把图像本体而非文字转述带回主模型
  上下文），首次出现处保留源码术语（`_multimodal` envelope）作为可追溯
  别名，而非裸术语

## [0.1.0] - 2026-09-03

- 内部首版（中文正文、机器本地路径、单语言）；部署前曾进行小范围内部测试；
  已被 0.2.0 取代，从未公开发布
