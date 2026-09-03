# 更新日志

本项目所有重要变更均记录在本文件。
格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循[语义化版本（Semantic Versioning）](https://semver.org/lang/zh-CN/)。

> 🌏 [English (CHANGELOG.md)](CHANGELOG.md)

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

- 内部首版（中文正文、机器本地路径、单语言）；已被 0.2.0 取代，从未公开发布
