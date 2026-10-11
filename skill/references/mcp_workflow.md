# MCP 编排与降级

本文件说明本技能如何真实调用麦当劳 MCP，以及各环节失败时的处理方式。技能的一切营养与价格数据都必须走这里的路径取得。

## 一、依赖的 MCP Server

- 名称：mcd-mcp
- 提供方：麦当劳中国（官方 MCP 服务）
- 接入地址：https://mcp.mcd.cn
- 传输协议：Streamable HTTP
- 鉴权：请求头携带 Authorization，格式为 Bearer 加空格加 MCP Token。Token 由使用者在麦当劳 MCP 开放平台自行申请，本技能不内置、不存储任何 Token。

客户端配置示例（Token 用环境变量占位，切勿提交真实值）：

```json
{
  "mcpServers": {
    "mcd-mcp": {
      "type": "streamablehttp",
      "url": "https://mcp.mcd.cn",
      "headers": {
        "Authorization": "Bearer ${MCD_MCP_TOKEN}"
      }
    }
  }
}
```

## 二、本技能调用的工具与用途

| 工具 | 用途 | 调用时机 |
|---|---|---|
| list-nutrition-foods | 取餐品营养（能量、蛋白质、脂肪、碳水、钠、钙等） | 任何营养解析或搭配之前，作为第一数据源 |
| query-meals | 取当前门店真实可售菜单（分类、餐品编码、标签） | 需要"该怎么点"或推荐组合时 |
| query-meal-detail | 取餐品详情与套餐组成、可替换选项 | 需要看清套餐包含内容时 |
| query-store-coupons | 取当前门店可用优惠券 | 需要算券后价格时 |
| available-coupons | 取麦麦省可领取券列表 | 需要提示可领券时 |
| query-my-coupons | 取账户已有券 | 需要判断已有券能否适用时 |
| calculate-price | 按选购清单算金额、优惠与应付总价 | 涉及价格展示时，作为金额唯一权威来源 |
| campaign-calendar | 取当月营销活动日历 | 用户问活动、新品、优惠周期时 |
| now-time-info | 取当前时间 | 需要判断活动是否在进行中时 |
| create-order | 创建订单 | 仅在用户显式确认订单摘要之后 |
| query-order | 查询订单状态 | 用户追问订单进度时 |

## 三、标准调用序列

### 场景 A：单餐营养解析

1. 调用 `list-nutrition-foods` 取得用户所点餐品的营养数据。
2. 将营养数据整理为 `--items` JSON，交给 `scripts/nutri_calc.py`。
3. 用脚本返回的表、占比、进度条与目标信号组织答复。

### 场景 B：目标化搭配求解

1. 调用 `query-meals` 取得当前门店真实可售餐品清单。
2. 调用 `list-nutrition-foods` 取对应营养数据，按 `id` 与 `name` 对齐后组成候选池。
3. 把候选池与用户约束交给 `scripts/combo_solver.py`，得到满足硬约束的最优组合。
4. 若用户关心价格，继续走场景 C；否则提示候选价格仅供参考。

### 场景 C：券后到手价

1. 优先调用 `query-my-coupons` 看已有券，再调用 `query-store-coupons` 看本店可用券。
2. 将选购清单与适用券传给 `calculate-price`。
3. 向用户展示的金额以 `calculate-price` 返回为准；脚本给出的金额仅用于组合筛选。

### 场景 D：活动与新品

1. 需要判断时间窗口时先调用 `now-time-info`。
2. 调用 `campaign-calendar` 取得当月活动，区分进行中、往期与未来。

### 场景 E：下单（必须二次确认）

1. 先完成场景 A 至 C，得到营养摘要、券后金额与门店信息。
2. 向用户展示订单摘要：门店与就餐方式、餐品清单与数量、券后应付金额、营养概要。
3. 明确询问是否确认下单，并等待用户显式同意。
4. 仅在用户确认后调用 `create-order`；未确认时不得调用。
5. 下单后可用 `query-order` 回显订单状态与取餐信息。

## 四、字段映射约定

把 MCP 返回值转成脚本入参时按下列对应关系整理，缺哪项就不传哪项，不要补 0：

| 脚本字段 | 来源 | 说明 |
|---|---|---|
| items[].name | list-nutrition-foods 的餐品名称 | 用于展示与去重 |
| items[].nutrients.kcal | 能量 | 必需 |
| items[].nutrients.protein_g | 蛋白质 | 必需 |
| items[].nutrients.fat_g | 脂肪 | 必需 |
| items[].nutrients.carb_g | 碳水化合物 | 必需 |
| items[].nutrients.sodium_mg | 钠 | 有则传 |
| items[].nutrients.sugar_g | 糖 | 有则传；麦当劳营养接口通常不直接给糖，缺失时保持缺失 |
| items[].nutrients.calcium_mg | 钙 | 有则传 |
| candidates[].price_cny | 餐品单价 | 来自菜单或 calculate-price 的明细 |
| source_hint | 固定标记 | 建议写清数据来自哪个工具，便于追溯 |

关于糖：多数情况下工具不返回糖含量。此时不要把碳水当作糖，也不要填 0；保持缺失，脚本会自动把糖标记为 partial 或 missing 并停止参与超标判定。

## 五、降级策略

- Token 无效或未配置（返回 401）：明确告知用户需要先在麦当劳 MCP 开放平台申请 Token 并配置到连接器，**不得**改用记忆中的营养数字继续回答。
- 触发限流（返回 429）：降低调用频率，合并同类查询，必要时分步询问用户；同一 Token 每分钟请求数有上限，不要循环重试。
- MCP 整体不可用：告知用户当前无法取得实时数据，并询问是否接受使用技能内置离线近似表。得到同意后改用 `scripts/nutri_calc.py --meals` 走兜底表，并在答复开头声明这是离线近似数据，非麦当劳实时数据。
- 单餐品查不到：直接说明该餐品无返回数据，请用户确认名称或换一个餐品；不猜、不套用相近餐品的数值。
- 门店未营业或无可用菜单：说明 `query-meals` 无返回，建议换门店或稍后再试，不要凭空生成菜单。
- 无可行组合：脚本返回无解时，向用户解释是哪些约束互相冲突，并给出放宽建议，例如提高热量上限或降低蛋白质下限。

## 六、禁止事项

- 禁止用模型记忆代替 MCP 工具返回的营养或价格数字。
- 禁止在用户未显式确认前调用 `create-order`。
- 禁止把脚本里的参考金额表述为最终应付金额。
- 禁止将麦当劳餐品与其他品牌餐品做对比。
- 禁止引导过量点餐、鼓励浪费或宣扬不健康饮食方式。
- 禁止把 Token、账号、地址等敏感信息写入技能文件或示例配置。
