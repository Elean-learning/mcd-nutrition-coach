# 报名与冲榜手册（参赛内部用）

> 本文件汇总「报名前置检查、你需要做的事、我将在你授权后执行的命令、报名 Issue 正文、Star 冲榜计划、时间线」。
> 仓库根目录的 5 个比赛文件 + `skill/` 主体均已在本地完成并提交（无真实凭证）。

## 一、报名前置检查（仓库内已满足 ✅）

- [x] `README.md`：项目介绍 / 安装方法 / 使用示例 / 目标用户
- [x] `CONTEST_DECLARATION.md`：官方原文，未改动
- [x] `MCP_INTEGRATION.md`：实际使用的 Server / Tool / 调用流程 / 业务价值
- [x] `mcp-config.example.json`：仅 `${MCD_MCP_TOKEN}` 环境变量占位符
- [x] `workbuddy.md`：WorkBuddy 联动专项奖励用
- [x] `skill/` 主体：`SKILL.md` + `scripts/`（确定性脚本）+ `references/` + `exemplars/`
- [x] 真实调用麦当劳 MCP：`list-nutrition-foods` / `query-meals` / `query-meal-detail` / `query-store-coupons` / `available-coupons` / `query-my-coupons` / `calculate-price` / `campaign-calendar` / `now-time-info` / `create-order` / `query-order`
- [x] 无真实 Token / 密钥 / 账号落入仓库
- [x] 脚本本地自测通过（营养求和、覆盖率、占比、预算；组合约束求解、无解退出码），与 exemplars 完全一致

## 二、你需要做的两件事

1. **申请麦当劳 MCP Token**
   打开 https://open.mcd.cn/mcp → 手机号登录 → 右上角「控制台」→「激活」→ 复制 Token。
   （仅在你本地 WorkBuddy 连接器里配置，不要提交到仓库。）
2. **终端完成 `gh` 授权**
   新开终端执行 `gh auth login`：选 `GitHub.com` → `HTTPS` → 用浏览器完成 OAuth 授权。
   完成后告诉我，我来建仓库、推送、提交报名 Issue。

## 三、我将在你授权后执行

```bash
# 在你的仓库目录下（已完成 git init + 首次提交）
gh repo create mcd-nutrition-coach --public \
  --description "麦当劳营养与套餐参谋 · 麦当劳xWorkBuddy程序员创意开发大赛参赛作品" \
  --source . --push

# 提交报名 Issue（≤1000 字，无图）。注意把 <USER> 替换为你的 GitHub 用户名
gh issue create \
  --repo M-China-Official/mcd-developer-innovation-challenge \
  --title "麦当劳营养与套餐参谋 mcd-nutrition-coach" \
  --body '【参赛申请】
项目名称：麦当劳营养与套餐参谋（mcd-nutrition-coach）
项目地址：https://github.com/<USER>/mcd-nutrition-coach
项目简介：基于麦当劳官方 MCP 实时餐品营养与当前可售菜单，解析热量/蛋白质/脂肪/碳水/钠/糖并对照每日参考摄入量给出占比与进度条；在热量、蛋白质、钠、糖、金额等硬约束下求解最优搭配组合；结合优惠券与 calculate-price 给出券后到手价；用户明确确认后可代下单。所有营养与价格数字均来自麦当劳 MCP 返回，缺失即声明、绝不臆造，下单前强制二次确认。真实调用 list-nutrition-foods、query-meals、calculate-price、create-order 等官方工具，配套确定性计算脚本，可审计、可复现。'
```

> Issue 提交需在 **2026-10-25 23:59（北京时间）** 前完成；正文不超过 1000 字且不含图片。

## 四、Star 冲榜计划

- **排名规则**：以 **2026-10-26 00:00** 采集的公开 Star 总数为最终依据；Star > 0 即进榜；原则上前 100 名进获奖范围；同一 GitHub 账号多个项目只取 Star 最高者进榜。
- **奖励**：进榜即得【汉堡回车键玩具 + 程序员节实体徽章】；前 100 且真实使用 WorkBuddy 并提交 `workbuddy.md` → +3000 WorkBuddy 积分；前三名额外 +10240 积分及巨无霸免费兑换券。
- **行动清单**：
  1. 自己先 Star 自己的仓库（避免 0 星不进榜）。
  2. 朋友圈 / 技术群 / 微博 / 小红书 / 知乎 / V2EX / 掘金 等分享，附仓库链接 + 一句话亮点（"吃麦当劳也能算得清热量和券后价"）。
  3. 在 WorkBuddy / 麦当劳相关开发者社群与论坛发帖。
  4. 截止前（10/25 23:59）持续回收链接与提醒；10/26 00:00 后以该时刻快照为准，不再依赖新增 Star。
- **目标**：至少进前 100（实物周边 + 3000 积分）；争取更高名次（前三另有 10240 积分 + 巨无霸券）。

## 五、时间线

| 阶段 | 时间 | 负责 |
|---|---|---|
| 代码与文档完成、本地提交 | 已完成 | 我 |
| 申请 MCP Token | 你方便时 | 你 |
| `gh auth login` 浏览器授权 | 你方便时 | 你 |
| 建仓库、推送、交 Issue | 你授权后 | 我 |
| Star 推广窗口 | 即日起至 10/25 23:59 | 共 |
| 定榜快照 | 2026-10-26 00:00 | 官方 |
| 获奖问卷 / 收货信息 | 2026-11-14 前 | 你 |
