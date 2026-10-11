# WorkBuddy 开发对话上下文（workbuddy.md）

> 本文件记录本参赛项目使用腾讯 WorkBuddy 智能体进行构思、设计、实现、测试与打包的主要对话脉络，用于核验是否符合 WorkBuddy 联动活动奖励条件。

## 一、开发背景与目标

用户希望在「麦当劳 × WorkBuddy 程序员创意开发大赛」中提交一个 Skill。初始需求是"从零构思并打磨一个 Skill，走完构思、设计、实现、测试、打包全流程"。

在读取官方活动帖与 `M-China/mcd-developer-innovation-challenge`、`M-China/mcd-mcp-server` 两份官方仓库后，确认活动的硬性要求：**必须真实使用麦当劳 MCP 能力**，仓库须包含 README.md、CONTEST_DECLARATION.md（原文不可改）、MCP_INTEGRATION.md、mcp-config.example.json（仅占位符）、workbuddy.md（参与专项奖励时需要）。

## 二、关键设计决策（在 WorkBuddy 对话中完成）

1. **MCP 优先架构**：初版仅用本地近似表，不满足"真实使用 MCP"要求，遂重构为 MCP 第一数据源，本地表仅作降级兜底。
2. **确定性计算脚本**：用纯标准库 Python 实现 `nutri_calc.py` 与 `combo_solver.py`，保证同输入同输出、可审计、不依赖外部状态，避免大模型"自由发挥"编造数字。
3. **数据完整性纪律**：引入 coverage（complete / partial / missing）状态，缺失即声明，绝不插值或把碳水当糖，超标判定只在数据完整时进行。
4. **下单二次确认**：把 `create-order` 置于显式确认之后，未确认绝不调用。
5. **差异化定位**：在已有多个"营养"类作品的情况下，叠加"目标化搭配求解 + 券后到手价 + 可选代下单"的连贯能力，形成区别度。

## 三、主要实现与自测（WorkBuddy 协助）

- 通过 WorkBuddy 编写并多轮自测两个脚本：营养求和 / 占比 / 覆盖率 / 预算评估（含 SVG 可视化）、组合约束求解（含无解退出码）。
- 生成 exemplars 输入输出样例，作为回归基准。
- 对照官方工具列表校准 `mcp_workflow.md`、`MCP_INTEGRATION.md` 中的工具名与调用序列。

## 四、合规与提交准备

- 确认 `mcp-config.example.json` 仅含 `${MCD_MCP_TOKEN}` 占位符，无真实凭证。
- 确认 `CONTEST_DECLARATION.md` 为官方原文、未改动。
- 规划以公开 GitHub 仓库 + Issue 报名，并以 Star 推广进入排行榜。

## 五、环境与工具

- 开发环境：macOS，WorkBuddy 托管 Python 3.13 与 Node 22。
- 版本管理：Git（推送至 GitHub Public 仓库）。
- 提交方式：GitHub Issue（≤1000 字，无图片）。

## 六、与 WorkBuddy 的联动说明

本项目在 WorkBuddy 中完成从需求分析、架构设计、代码实现、脚本自测到文档产出的完整链路；SKILL.md 的 `allowed-tools` 明确声明需配合 `mcp__mcd-mcp__*` 系列官方工具运行，属于真实使用腾讯 WorkBuddy 智能体开发的参赛作品，符合 WorkBuddy 专项奖励的核验条件。
