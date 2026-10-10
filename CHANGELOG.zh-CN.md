# 更新日志

本项目所有重要变更均记录在本文件。
格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循[语义化版本（Semantic Versioning）](https://semver.org/lang/zh-CN/)。

> 🌏 [English (CHANGELOG.md)](CHANGELOG.md)

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
