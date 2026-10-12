# 麦当劳营养与套餐参谋（mcd-nutrition-coach）

> 麦当劳程序员创意开发大赛参赛作品 · 基于麦当劳官方 MCP 能力

身材管控期也想吃麦当劳？这个 Skill 会基于**麦当劳官方 MCP 实时返回的餐品营养与当前可售菜单**，帮你算清这一餐吃了多少、占每天多少额度、想达到减脂 / 增肌 / 控糖 / 高蛋白目标该怎么点，并算出券后到手价；所有数字可追溯、绝不编造，代下单前强制二次确认。

## 项目简介

`mcd-nutrition-coach` 是一个运行在 WorkBuddy 中的 Skill，核心能力如下：

1. **营养解析**：把用户点的麦当劳餐品整理后，调用 `list-nutrition-foods` 取得官方营养，再由确定性脚本 `nutri_calc.py` 做求和、对照每日参考摄入量给占比与进度条，并标注数据覆盖率（完整 / 部分 / 缺失）。
2. **目标化搭配求解**：基于 `query-meals` 的当前门店真实可售菜单，在热量、蛋白质、脂肪、碳水、钠、糖、金额等硬约束下，用 `combo_solver.py` 求解最优组合（减脂 / 增肌 / 控糖 / 高性价比等目标）。
3. **券后到手价**：结合 `query-store-coupons` / `available-coupons` 与 `calculate-price`，给出以 MCP 为准的券后应付金额。
4. **可选代下单**：先展示订单摘要，用户显式确认后才调用 `create-order`，绝不在未确认时下单。

所有营养与价格数字一律来自麦当劳 MCP 返回或用户显式提供，**缺失即声明，绝不臆造，绝不把碳水当糖，绝不插值补零**。

## 目录结构

```
.
├── README.md                      # 本文件
├── CONTEST_DECLARATION.md         # 参赛声明（官方原文，不可修改）
├── MCP_INTEGRATION.md             # 麦当劳 MCP 接入说明
├── mcp-config.example.json        # 脱敏 MCP 配置示例（仅占位符）
├── workbuddy.md                   # WorkBuddy 开发对话上下文
└── skill/                        # Skill 主体
    ├── SKILL.md
    ├── requirements.txt
    ├── scripts/                  # 确定性计算脚本（纯标准库）
    │   ├── nutri_calc.py
    │   └── combo_solver.py
    ├── references/               # MCP 编排、能力边界、事实纪律等
    └── exemplars/                # 输入输出样例
```

## 安装方法

### 1. 申请麦当劳 MCP Token

前往 [麦当劳 MCP 开放平台](https://open.mcd.cn/mcp)，用手机号登录后申请 MCP Token。

### 2. 在 WorkBuddy 接入 mcd-mcp

打开 WorkBuddy → 左侧【专家·技能·连接器】→【连接器】→ 右上角【自定义连接器】→【配置 MCP】，粘贴 `mcp-config.example.json` 中的内容，将`"Bearer YOUR_MCP_TOKEN"` 替换为你的真实 Token 后保存并启用。

### 3. 安装本 Skill

将本仓库 `skill/` 目录作为 Skill 导入 WorkBuddy 即可（SKILL.md 已含全部元数据与触发条件）。

## 使用示例

- "我吃了巨无霸 + 中杯可乐 + 薯条，帮我算一下这餐的营养" → 调用 `list-nutrition-foods`，脚本给出营养表与每日参考摄入量占比。
- "减脂期麦当劳怎么点，热量控制在 500 大卡以内、蛋白质尽量高" → 调用 `query-meals` + `list-nutrition-foods`，脚本在约束下求解最优组合。
- "刚才那套券后多少钱" → 调用 `query-store-coupons` + `calculate-price`，给出券后到手价。
- "帮我把这套下单吧"（需先确认订单摘要）→ 展示摘要，确认后调用 `create-order`。

## 目标用户

- 健身 / 减脂 / 控糖 / 增肌人群，希望在麦当劳吃得清楚、吃得有数。
- 关注性价比、想用券后价点餐的普通消费者。
- 想基于麦当劳官方实时数据做搭配决策的任何人。

## 免责声明

本项目为麦当劳程序员节创意开发大赛参赛作品，由参赛者独立开发，**非麦当劳官方产品**。输出仅供参考，不构成医疗、营养或其他专业建议；餐品信息、价格及供应状态以麦当劳官方渠道的实时结果为准。

详见 [CONTEST_DECLARATION.md](./CONTEST_DECLARATION.md)。
