#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
combo_solver.py - 麦当劳套餐组合确定性求解器（仅使用 Python 标准库）。

用途：给定候选餐品（通常来自麦当劳 MCP 工具 query-meals / list-nutrition-foods 的当前
真实可售菜单与营养数据）与一组硬约束（热量上下限、蛋白质下限、钠/脂肪/糖上限、金额上限、
件数上限、必选/排除项），穷举满足约束的组合并按目标打分排序，输出前 N 个方案。

设计原则：
  - 纯确定性：同输入 -> 同输出；无随机、无时间、无外部状态；枚举与排序全程稳定。
  - 硬约束优先：先过滤不满足约束的组合，再对可行解打分，绝不用“近似满足”糊弄。
  - 缺失即排除：候选缺少核心营养数据或价格数据（当约束涉及价格时）时不参与求解，并计入 notes。
  - 不臆造：找不到可行解时返回 NO_SOLUTION（exit 3），不返回“凑合”的方案。

打分模型（可复现，权重按目标归一）：
  每个维度先归一到 [0,1] 的满意度 s，score = 100 * Σ(w_i * s_i)。
    s_protein = min(1, protein_g / ref_protein)
    s_kcal    = min(1, ref_kcal / max(kcal, 1))            （越接近参考热量越满意）
    s_sodium  = clamp(1 - sodium_mg / ref_sodium, 0, 1)
    s_fat     = clamp(1 - fat_g / ref_fat, 0, 1)
    s_sugar   = clamp(1 - sugar_g / ref_sugar, 0, 1)
    s_price   = clamp(1 - price_cny / ref_price, 0, 1)
  参考基准取约束中的上限（若给出）或内置默认值，保证与用户给的目标区间自洽。
  并列时的稳定排序：score 降序 -> 金额升序 -> 热量升序 -> 名称序列升序。

引号：本文件全程使用 ASCII 直引号。
"""

import argparse
import itertools
import json
import sys
from math import comb

CORE_NUTRIENTS = ["kcal", "protein_g", "fat_g", "carb_g"]
# 求解过程中会被累加的可选营养素
OPTIONAL_NUTRIENTS = ["sodium_mg", "sugar_g"]

GOAL_WEIGHTS = {
    # 高蛋白优先（增肌 / 控脂期主力目标）
    "protein_first": {"protein": 0.55, "kcal": 0.25, "sodium": 0.10, "sugar": 0.10, "price": 0.00},
    # 控糖优先
    "sugar_control": {"protein": 0.20, "kcal": 0.20, "sodium": 0.15, "sugar": 0.45, "price": 0.00},
    # 轻食控卡优先
    "light_meal": {"protein": 0.20, "kcal": 0.50, "sodium": 0.20, "sugar": 0.10, "price": 0.00},
    # 省钱优先
    "value": {"protein": 0.25, "kcal": 0.15, "sodium": 0.05, "sugar": 0.05, "price": 0.50},
}

DEFAULT_REFS = {
    "protein_g": 40.0,
    "kcal": 700.0,
    "sodium_mg": 1000.0,
    "fat_g": 25.0,
    "sugar_g": 25.0,
    "price_cny": 35.0,
}

# 组合枚举规模上限，防止候选过多导致调用挂死
MAX_COMBINATIONS = 500000

DEFAULT_DISCLAIMER = "方案基于候选餐品的营养与价格数据计算得出，仅供参考；实际菜单、价格、供应与优惠以麦当劳官方渠道为准。"


def fail(code, message, extra=None):
    payload = {"ok": False, "code": code, "message": message}
    if extra:
        payload.update(extra)
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    if code == "NO_SOLUTION":
        sys.exit(3)
    sys.exit(1)


def round1(value):
    if value is None:
        return None
    return round(float(value) + 0.0, 1)


def clamp01(value):
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def read_json_arg(text, label):
    if text is None:
        fail("BAD_INPUT", label + " is required")
    if text == "-":
        raw = sys.stdin.read()
    else:
        raw = text
    raw = raw.strip()
    if raw == "":
        fail("BAD_INPUT", label + " is empty")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        fail("BAD_INPUT", label + " is not valid JSON: " + str(exc))


def as_number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        fail("BAD_INPUT", label + " must be a number")
    return float(value)


def parse_candidates(raw):
    if isinstance(raw, dict):
        raw = raw.get("candidates")
    if not isinstance(raw, list) or len(raw) == 0:
        fail("BAD_INPUT", "candidates must be a non-empty list or {\"candidates\": [...]}")
    out = []
    seen_ids = set()
    for idx, entry in enumerate(raw):
        label = "candidates[" + str(idx) + "]"
        if not isinstance(entry, dict):
            fail("BAD_INPUT", label + " must be an object")
        name = entry.get("name")
        if not isinstance(name, str) or name.strip() == "":
            fail("BAD_INPUT", label + " missing non-empty string 'name'")
        cid = entry.get("id")
        if not isinstance(cid, str) or cid.strip() == "":
            cid = name.strip()
        if cid in seen_ids:
            fail("BAD_INPUT", label + " duplicate candidate id: " + cid)
        seen_ids.add(cid)
        nutrients_raw = entry.get("nutrients")
        if not isinstance(nutrients_raw, dict):
            fail("BAD_INPUT", label + " missing object 'nutrients'")
        nutrients = {}
        for key in CORE_NUTRIENTS:
            if key not in nutrients_raw or nutrients_raw[key] is None:
                fail("BAD_INPUT", label + " missing required nutrient: " + key)
            nutrients[key] = as_number(nutrients_raw[key], label + "." + key)
        for key in OPTIONAL_NUTRIENTS:
            if key in nutrients_raw and nutrients_raw[key] is not None:
                nutrients[key] = as_number(nutrients_raw[key], label + "." + key)
        price = entry.get("price_cny")
        if price is not None:
            price = as_number(price, label + ".price_cny")
            if price < 0:
                fail("BAD_INPUT", label + ".price_cny must be >= 0")
        out.append({
            "id": cid,
            "name": name.strip(),
            "category": entry.get("category", ""),
            "nutrients": nutrients,
            "price_cny": price,
        })
    return out


def parse_constraints(raw):
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        fail("BAD_INPUT", "constraints must be an object")
    allowed = [
        "kcal_min", "kcal_max", "protein_g_min", "fat_g_max", "carb_g_max",
        "sodium_mg_max", "sugar_g_max", "price_cny_max",
        "min_items", "max_items", "must_include", "exclude",
    ]
    unknown = [k for k in raw.keys() if k not in allowed]
    if unknown:
        fail("BAD_INPUT", "unknown constraint keys: " + ", ".join(sorted(unknown))
             + " (allowed: " + ", ".join(allowed) + ")")
    out = {}
    for key in allowed:
        if key not in raw or raw[key] is None:
            continue
        if key in ("must_include", "exclude"):
            value = raw[key]
            if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
                fail("BAD_INPUT", "constraints." + key + " must be a list of strings")
            out[key] = list(value)
        elif key in ("min_items", "max_items"):
            value = as_number(raw[key], "constraints." + key)
            if value != int(value) or value < 1:
                fail("BAD_INPUT", "constraints." + key + " must be a positive integer")
            out[key] = int(value)
        else:
            out[key] = as_number(raw[key], "constraints." + key)
    return out


def build_pool(candidates, constraints):
    """按 exclude / 数据完整性过滤候选池，返回 (pool, notes)。"""
    notes = []
    excluded = set(constraints.get("exclude", []))
    known_ids = {c["id"] for c in candidates}
    unknown_excluded = sorted(excluded - known_ids)
    if unknown_excluded:
        fail("BAD_INPUT", "constraints.exclude refers to unknown candidate ids: "
             + ", ".join(unknown_excluded))

    need_price = "price_cny_max" in constraints
    need_sodium = "sodium_mg_max" in constraints
    need_sugar = "sugar_g_max" in constraints

    pool = []
    dropped = []
    for cand in candidates:
        if cand["id"] in excluded:
            continue
        if need_price and cand["price_cny"] is None:
            dropped.append(cand["id"] + "(缺少价格)")
            continue
        if need_sodium and "sodium_mg" not in cand["nutrients"]:
            dropped.append(cand["id"] + "(缺少钠)")
            continue
        if need_sugar and "sugar_g" not in cand["nutrients"]:
            dropped.append(cand["id"] + "(缺少糖)")
            continue
        pool.append(cand)
    if dropped:
        notes.append("以下候选因缺少求解所需数据被排除（未做任何估算）：" + "、".join(dropped))
    return pool, notes


def score_combo(combo, totals, price_total, goal, refs):
    weights = GOAL_WEIGHTS[goal]
    s = {}
    s["protein"] = clamp01(totals["protein_g"] / refs["protein_g"])
    s["kcal"] = clamp01(refs["kcal"] / max(totals["kcal"], 1.0))
    if totals.get("sodium_mg") is None:
        s["sodium"] = 1.0
    else:
        s["sodium"] = clamp01(1.0 - totals["sodium_mg"] / refs["sodium_mg"])
    if totals.get("sugar_g") is None:
        s["sugar"] = 1.0
    else:
        s["sugar"] = clamp01(1.0 - totals["sugar_g"] / refs["sugar_g"])
    if price_total is None:
        s["price"] = 1.0
    else:
        s["price"] = clamp01(1.0 - price_total / refs["price_cny"])
    score = 0.0
    for key, weight in weights.items():
        score += weight * s[key]
    return round(score * 100.0, 2), {k: round1(v * 100.0) for k, v in s.items()}


def sum_combo(combo):
    totals = {k: 0.0 for k in CORE_NUTRIENTS}
    for key in OPTIONAL_NUTRIENTS:
        totals[key] = 0.0
    price_total = 0.0
    price_known = True
    for cand in combo:
        for key in CORE_NUTRIENTS:
            totals[key] += cand["nutrients"][key]
        for key in OPTIONAL_NUTRIENTS:
            totals[key] += cand["nutrients"].get(key, 0.0)
        if cand["price_cny"] is None:
            price_known = False
        else:
            price_total += cand["price_cny"]
    return totals, (price_total if price_known else None)


def violates(totals, price_total, item_count, constraints):
    if "kcal_min" in constraints and totals["kcal"] < constraints["kcal_min"]:
        return True
    if "kcal_max" in constraints and totals["kcal"] > constraints["kcal_max"]:
        return True
    if "protein_g_min" in constraints and totals["protein_g"] < constraints["protein_g_min"]:
        return True
    if "fat_g_max" in constraints and totals["fat_g"] > constraints["fat_g_max"]:
        return True
    if "carb_g_max" in constraints and totals["carb_g"] > constraints["carb_g_max"]:
        return True
    if "sodium_mg_max" in constraints and totals["sodium_mg"] > constraints["sodium_mg_max"]:
        return True
    if "sugar_g_max" in constraints and totals["sugar_g"] > constraints["sugar_g_max"]:
        return True
    if "price_cny_max" in constraints:
        if price_total is None or price_total > constraints["price_cny_max"]:
            return True
    if item_count < constraints.get("min_items", 1):
        return True
    if item_count > constraints.get("max_items", 4):
        return True
    return False


def explain(totals, price_total, item_count, constraints, goal):
    reasons = []
    reasons.append("热量 %s kcal" % round1(totals["kcal"]))
    reasons.append("蛋白质 %s g" % round1(totals["protein_g"]))
    if totals.get("sodium_mg"):
        reasons.append("钠 %s mg" % round1(totals["sodium_mg"]))
    if totals.get("sugar_g") is not None and totals.get("sugar_g") > 0:
        reasons.append("糖 %s g" % round1(totals["sugar_g"]))
    if price_total is not None:
        reasons.append("合计约 %s 元（未含优惠券）" % round1(price_total))
    reasons.append("共 %d 件" % item_count)
    targets = {
        "protein_first": "以蛋白质最大化为主、兼顾热量与钠",
        "sugar_control": "以控糖为主、兼顾热量与蛋白质",
        "light_meal": "以控制热量为主、兼顾蛋白质与钠",
        "value": "以控制金额为主、兼顾蛋白质与热量",
    }
    return {"goal_note": targets[goal], "metrics": reasons}


def emit_text(result):
    out = []
    out.append("求解目标: " + result["goal"])
    out.append("候选池: %d 项，评估组合: %d 个，可行解: %d 个"
               % (result["pool_size"], result["combinations_evaluated"], result["feasible_count"]))
    out.append("")
    if not result["solutions"]:
        out.append("未找到满足全部硬约束的组合。")
    for sol in result["solutions"]:
        names = " + ".join(
            (it["name"] + (" x%d" % it["qty"] if it["qty"] > 1 else "")) for it in sol["items"])
        out.append("第 %d 名  得分 %s" % (sol["rank"], sol["score"]))
        out.append("  组合: " + names)
        out.append("  指标: " + "；".join(sol["rationale"]["metrics"]))
        out.append("")
    for note in result["notes"]:
        out.append("提示：" + note)
    out.append("")
    out.append("免责声明：" + result["disclaimer"])
    sys.stdout.write("\n".join(out) + "\n")


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="McDonald's meal combo deterministic solver")
    parser.add_argument("--candidates", default=None,
                        help="JSON list of candidates or {\"candidates\": [...]}; use '-' for stdin")
    parser.add_argument("--constraints", default=None, help="JSON object of hard constraints")
    parser.add_argument("--goal", default="protein_first",
                        choices=sorted(GOAL_WEIGHTS.keys()), help="scoring objective")
    parser.add_argument("--top", type=int, default=5, help="number of solutions to return, default 5")
    parser.add_argument("--format", default="json", choices=["json", "text"], help="output format")
    args = parser.parse_args(argv)

    top = args.top
    if top < 1 or top > 50:
        fail("BAD_INPUT", "--top must be between 1 and 50")

    candidates = parse_candidates(read_json_arg(args.candidates, "--candidates"))
    constraints = parse_constraints(read_json_arg(args.constraints, "--constraints")
                                    if args.constraints else None)

    max_items = constraints.get("max_items", 4)
    must_include = constraints.get("must_include", [])
    known_ids = {c["id"] for c in candidates}
    unknown_must = sorted(set(must_include) - known_ids)
    if unknown_must:
        fail("BAD_INPUT", "constraints.must_include refers to unknown candidate ids: "
             + ", ".join(unknown_must))

    pool, notes = build_pool(candidates, constraints)
    pool_by_id = {c["id"]: c for c in pool}
    missing_must = [mid for mid in must_include if mid not in pool_by_id]
    if missing_must:
        fail("BAD_INPUT", "must_include items were excluded by filters or missing data: "
             + ", ".join(missing_must))

    base = [pool_by_id[mid] for mid in must_include]
    if len(base) > max_items:
        fail("BAD_INPUT", "must_include has %d items but max_items is %d" % (len(base), max_items))

    free_pool = [c for c in pool if c["id"] not in set(must_include)]
    slots = max_items - len(base)

    # 预估枚举规模（可重复组合数 C(n+k-1, k)），避免调用挂死
    est = 0
    for k in range(0, slots + 1):
        est += comb(len(free_pool) + k - 1, k)
    if est > MAX_COMBINATIONS:
        fail("BAD_INPUT", "combination space too large (%d > %d); narrow the candidate list or lower max_items"
             % (est, MAX_COMBINATIONS))

    refs = dict(DEFAULT_REFS)
    refs["protein_g"] = max(30.0, constraints.get("protein_g_min", DEFAULT_REFS["protein_g"]))
    refs["kcal"] = max(200.0, constraints.get("kcal_max", DEFAULT_REFS["kcal"]))
    refs["sodium_mg"] = max(300.0, constraints.get("sodium_mg_max", DEFAULT_REFS["sodium_mg"]))
    refs["fat_g"] = max(10.0, constraints.get("fat_g_max", DEFAULT_REFS["fat_g"]))
    refs["sugar_g"] = max(10.0, constraints.get("sugar_g_max", DEFAULT_REFS["sugar_g"]))
    refs["price_cny"] = max(15.0, constraints.get("price_cny_max", DEFAULT_REFS["price_cny"]))

    evaluated = 0
    feasible = []
    for k in range(0, slots + 1):
        for extra in itertools.combinations_with_replacement(free_pool, k):
            combo = list(base) + list(extra)
            if not combo:
                continue
            evaluated += 1
            totals, price_total = sum_combo(combo)
            if violates(totals, price_total, len(combo), constraints):
                continue
            score, breakdown = score_combo(combo, totals, price_total, args.goal, refs)
            key = (
                -score,
                price_total if price_total is not None else float("inf"),
                totals["kcal"],
                tuple(sorted(c["name"] for c in combo)),
            )
            feasible.append((key, combo, totals, price_total, score, breakdown))

    if not feasible:
        fail("NO_SOLUTION",
             "没有任何组合同时满足全部硬约束。建议放宽其中一项（例如提高热量上限、降低蛋白质下限或增加预算）后重试。",
             {"constraints": constraints, "pool_size": len(pool),
              "combinations_evaluated": evaluated})

    feasible.sort(key=lambda row: row[0])

    solutions = []
    for idx, (_, combo, totals, price_total, score, breakdown) in enumerate(feasible[:top], start=1):
        grouped = {}
        for cand in combo:
            grouped[cand["id"]] = grouped.get(cand["id"], 0) + 1
        items = []
        for cid, qty in sorted(grouped.items()):
            cand = pool_by_id[cid]
            items.append({
                "id": cid,
                "name": cand["name"],
                "category": cand["category"],
                "qty": qty,
                "price_cny": cand["price_cny"],
            })
        totals_out = {key: round1(totals[key]) for key in CORE_NUTRIENTS + OPTIONAL_NUTRIENTS}
        solutions.append({
            "rank": idx,
            "score": score,
            "score_breakdown_pct": breakdown,
            "items": items,
            "totals": totals_out,
            "price_cny_total": round1(price_total) if price_total is not None else None,
            "rationale": explain(totals, price_total, len(combo), constraints, args.goal),
        })

    result = {
        "ok": True,
        "goal": args.goal,
        "constraints": constraints,
        "reference_baseline": {k: round1(v) for k, v in sorted(refs.items())},
        "pool_size": len(pool),
        "combinations_evaluated": evaluated,
        "feasible_count": len(feasible),
        "solutions": solutions,
        "notes": notes,
        "disclaimer": DEFAULT_DISCLAIMER,
    }

    if args.format == "text":
        emit_text(result)
    else:
        sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
    sys.exit(0)


if __name__ == "__main__":
    main()
