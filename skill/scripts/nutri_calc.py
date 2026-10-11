#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
nutri_calc.py - 麦当劳营养确定性计算引擎（仅使用 Python 标准库）。

设计原则（确定性、幂等、可复现、不臆造）：
  - 数据可来自麦当劳 MCP 工具 list-nutrition-foods 的真实返回（由 LLM 整理为 --items JSON），
    也可来自本技能内置的离线兜底近似表 references/menu_nutrition.json（--meals 按 key 查表）。
  - 只做求和、占比、可视化与阈值判定；不推断、不插值、不补全缺失营养素。
  - 任一营养素若只有部分餐品提供数据，则标记 coverage=partial，
    合计值标注为“部分值”，并且不参与超标判定（避免用残缺数据下结论）。

输入（二选一）：
  --items '<json>' / --items -      显式营养数据（MCP 或用户提供）
  --meals '<json>'                  按 key 查离线兜底表

输出：成功 exit 0 输出 JSON；畸形输入 BAD_INPUT exit 1；查表未命中 ITEM_NOT_FOUND exit 2。
引号：本文件全程使用 ASCII 直引号。
"""

import argparse
import json
import os
import sys

FALLBACK_REL_PATH = os.path.join("..", "references", "menu_nutrition.json")

# 核心营养素（缺失即视为输入不完整）
CORE_NUTRIENTS = ["kcal", "protein_g", "fat_g", "carb_g"]
# 全部营养素（可选者允许缺失，会以 coverage 标注）
ALL_NUTRIENTS = ["kcal", "protein_g", "fat_g", "carb_g", "sodium_mg", "sugar_g", "calcium_mg"]

NUTRIENT_LABELS = {
    "kcal": "热量",
    "protein_g": "蛋白质",
    "fat_g": "脂肪",
    "carb_g": "碳水",
    "sodium_mg": "钠",
    "sugar_g": "糖",
    "calcium_mg": "钙",
}

UNITS = {
    "kcal": "kcal",
    "protein_g": "g",
    "fat_g": "g",
    "carb_g": "g",
    "sodium_mg": "mg",
    "sugar_g": "g",
    "calcium_mg": "mg",
}

# 百分比输出键（与外部契约一致：kcal_pct / protein_pct / ...）
PCT_KEY = {
    "kcal": "kcal_pct",
    "protein_g": "protein_pct",
    "fat_g": "fat_pct",
    "carb_g": "carb_pct",
    "sodium_mg": "sodium_pct",
    "sugar_g": "sugar_pct",
    "calcium_mg": "calcium_pct",
}

VALID_GOALS = ["fat_loss", "muscle_gain", "sugar_control", "high_protein", "general"]

DEFAULT_DRI_PROFILE = "adult_general"

# 进度条宽度（字符数），filled = round(clamp(pct/100, 0, 1) * BAR_WIDTH)
BAR_WIDTH = 20

# 目标信号阈值（确定性，供 LLM 转写为自然语言建议；仅在全覆盖时判定）
THRESHOLDS = {
    "sugar_pct_high": 50,
    "sodium_pct_high": 50,
    "fat_pct_high": 50,
    "kcal_pct_high": 50,
    "sugar_pct_watch": 25,
    "protein_g_low_fat_loss": 30,
    "protein_g_low_muscle_gain": 40,
    "protein_g_low_high_protein": 40,
}

DEFAULT_DISCLAIMER = "营养数据来自麦当劳 MCP 服务或本技能离线兜底近似表，仅供参考，请以麦当劳官方渠道实时信息为准。"


def fail(code, message, extra=None):
    """以非 0 退出码输出错误 JSON；任何失败路径都不以 0 退出夹带编造数字。"""
    payload = {"ok": False, "code": code, "message": message}
    if extra:
        payload.update(extra)
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    if code == "ITEM_NOT_FOUND":
        sys.exit(2)
    sys.exit(1)


def round1(value):
    """保留 1 位小数，规避二进制浮点抖动，保证幂等。"""
    if value is None:
        return None
    return round(float(value) + 0.0, 1)


def load_fallback_data():
    here = os.path.dirname(os.path.abspath(__file__))
    data_path = os.path.normpath(os.path.join(here, FALLBACK_REL_PATH))
    try:
        with open(data_path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        fail("BAD_INPUT", "fallback data file not found: " + data_path)
    except json.JSONDecodeError as exc:
        fail("BAD_INPUT", "fallback data file is not valid JSON: " + str(exc))


def read_json_arg(text, label):
    if text is None:
        return None
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


def parse_nutrients(raw, label, core_required):
    """解析营养素字典。core_required=True 时核心四项必须齐全。"""
    if not isinstance(raw, dict):
        fail("BAD_INPUT", label + " nutrients must be an object")
    out = {}
    for key in ALL_NUTRIENTS:
        if key in raw and raw[key] is not None:
            out[key] = as_number(raw[key], label + "." + key)
        elif core_required and key in CORE_NUTRIENTS:
            fail("BAD_INPUT", label + " missing required nutrient: " + key)
    if core_required:
        for key in CORE_NUTRIENTS:
            if key not in out:
                fail("BAD_INPUT", label + " missing required nutrient: " + key)
    return out


def parse_override(raw, label):
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        fail("BAD_INPUT", label + " must be an object")
    out = {}
    for key in ALL_NUTRIENTS:
        if key in raw and raw[key] is not None:
            out[key] = as_number(raw[key], label + "." + key)
    return out


def build_items_from_explicit(obj, global_override):
    """MCP / 用户显式数据路径。"""
    raw = obj.get("items")
    if not isinstance(raw, list) or len(raw) == 0:
        fail("BAD_INPUT", "items must be a non-empty list")
    items = []
    for idx, entry in enumerate(raw):
        label = "items[" + str(idx) + "]"
        if not isinstance(entry, dict):
            fail("BAD_INPUT", label + " must be an object")
        name = entry.get("name")
        if not isinstance(name, str) or name.strip() == "":
            fail("BAD_INPUT", label + " missing non-empty string 'name'")
        qty = as_number(entry.get("qty", 1), label + ".qty")
        if qty <= 0:
            fail("BAD_INPUT", label + ".qty must be > 0")
        nutrients = parse_nutrients(entry.get("nutrients"), label, core_required=True)
        item_override = parse_override(entry.get("override"), label + ".override")
        merged = dict(nutrients)
        merged.update(global_override)
        merged.update(item_override)
        source = entry.get("source")
        if not isinstance(source, str) or source == "":
            source = obj.get("source_hint", "explicit")
        items.append({
            "name": name.strip(),
            "qty": qty,
            "nutrients": merged,
            "source": source,
        })
    return items


def build_items_from_meals(obj, fallback, global_override):
    """离线兜底表路径：按 canonical key 查表。"""
    raw = obj.get("meals")
    if not isinstance(raw, list) or len(raw) == 0:
        fail("BAD_INPUT", "meals must be a non-empty list")
    index = {it.get("key"): it for it in fallback.get("items", [])}
    items = []
    missing = []
    for idx, entry in enumerate(raw):
        label = "meals[" + str(idx) + "]"
        if not isinstance(entry, dict):
            fail("BAD_INPUT", label + " must be an object")
        key = entry.get("key")
        if not isinstance(key, str) or key.strip() == "":
            fail("BAD_INPUT", label + " missing non-empty string 'key'")
        record = index.get(key)
        if record is None:
            missing.append(key)
            continue
        qty = as_number(entry.get("qty", 1), label + ".qty")
        if qty <= 0:
            fail("BAD_INPUT", label + ".qty must be > 0")
        nutrients = parse_nutrients(record.get("nutrients"), label, core_required=True)
        item_override = parse_override(entry.get("override"), label + ".override")
        merged = dict(nutrients)
        merged.update(global_override)
        merged.update(item_override)
        source = "fallback-table"
        if item_override or global_override:
            source = "fallback-table+override"
        items.append({
            "name": record.get("name_zh", key),
            "qty": qty,
            "nutrients": merged,
            "source": source,
        })
    if missing:
        fail(
            "ITEM_NOT_FOUND",
            "离线兜底表中未收录以下餐品，未做任何估算："
            + ", ".join(missing)
            + "。请改用麦当劳 MCP 工具 list-nutrition-foods 获取真实数据后以 --items 传入。",
            {"items": missing, "hint": "call list-nutrition-foods then pass --items"},
        )
    return items


def compute_totals_and_coverage(items):
    totals = {}
    coverage = {}
    for key in ALL_NUTRIENTS:
        present = [it for it in items if key in it["nutrients"]]
        if not present:
            totals[key] = None
            coverage[key] = {"state": "missing", "items_with_value": 0, "items_total": len(items)}
            continue
        total = 0.0
        for it in present:
            total += it["nutrients"][key] * it["qty"]
        totals[key] = round1(total)
        state = "complete" if len(present) == len(items) else "partial"
        coverage[key] = {
            "state": state,
            "items_with_value": len(present),
            "items_total": len(items),
        }
    return totals, coverage


def compute_percentages(totals, coverage, dri_values):
    pct = {}
    for key in ALL_NUTRIENTS:
        out_key = PCT_KEY[key]
        dri = dri_values.get(key)
        if coverage[key]["state"] != "complete" or not dri:
            pct[out_key] = None
            continue
        pct[out_key] = round1(totals[key] / dri * 100)
    return pct


def compute_goal_signals(goal, totals, coverage, percentages):
    t = THRESHOLDS
    flags = []

    def full(key):
        return coverage[key]["state"] == "complete"

    if full("sugar_g") and percentages.get("sugar_pct") is not None and percentages["sugar_pct"] >= t["sugar_pct_high"]:
        flags.append("high_sugar")
    if full("sodium_mg") and percentages.get("sodium_pct") is not None and percentages["sodium_pct"] >= t["sodium_pct_high"]:
        flags.append("high_sodium")
    if full("fat_g") and percentages.get("fat_pct") is not None and percentages["fat_pct"] >= t["fat_pct_high"]:
        flags.append("high_fat")
    if full("kcal") and percentages.get("kcal_pct") is not None and percentages["kcal_pct"] >= t["kcal_pct_high"]:
        flags.append("high_calorie")

    if goal == "fat_loss" and full("protein_g") and totals["protein_g"] < t["protein_g_low_fat_loss"]:
        flags.append("low_protein")
    elif goal == "muscle_gain" and full("protein_g") and totals["protein_g"] < t["protein_g_low_muscle_gain"]:
        flags.append("low_protein_for_gain")
    elif goal == "sugar_control" and percentages.get("sugar_pct") is not None and percentages["sugar_pct"] >= t["sugar_pct_watch"]:
        flags.append("watch_sugar")
    elif goal == "high_protein" and full("protein_g") and totals["protein_g"] < t["protein_g_low_high_protein"]:
        flags.append("low_protein")

    seen = set()
    ordered = []
    for flag in flags:
        if flag not in seen:
            seen.add(flag)
            ordered.append(flag)
    return {"flags": ordered, "thresholds": t}


def compute_budget_eval(remaining, totals, coverage):
    if remaining is None:
        return None
    if not isinstance(remaining, dict):
        fail("BAD_INPUT", "--remaining must be a JSON object")
    provided = {}
    for key, value in remaining.items():
        if key not in ALL_NUTRIENTS:
            fail("BAD_INPUT", "--remaining has unknown nutrient key: " + str(key))
        provided[key] = as_number(value, "--remaining." + key)
    used = {}
    remaining_after = {}
    within = {}
    over_by = {}
    gap = {}
    for key, limit in provided.items():
        if coverage[key]["state"] != "complete":
            used[key] = None
            remaining_after[key] = None
            within[key] = None
            over_by[key] = None
            gap[key] = None
            continue
        used[key] = totals[key]
        left = round1(limit - totals[key])
        remaining_after[key] = left
        within[key] = left >= 0
        over_by[key] = round1(-left) if left < 0 else 0.0
        gap[key] = round1(-left) if left < 0 else 0.0
    return {
        "provided": provided,
        "used": used,
        "remaining_after": remaining_after,
        "within": within,
        "over_by": over_by,
        "gap": gap,
        "complete": all(v is not None for v in within.values()) if within else False,
    }


def fmt_value(value):
    if value is None:
        return "n/a"
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    return str(value)


def make_table_text(items, totals, coverage, percentages):
    lines = []
    header = "%-16s %6s %6s %6s %6s %7s %6s %6s  %s" % (
        "餐品", "数量", "热量", "蛋白", "脂肪", "碳水", "钠", "糖", "来源")
    lines.append(header)
    lines.append("-" * 78)
    for it in items:
        n = it["nutrients"]
        lines.append("%-16s %6s %6s %6s %6s %6s %7s %6s  %s" % (
            it["name"][:16],
            fmt_value(it["qty"]),
            fmt_value(n.get("kcal")),
            fmt_value(n.get("protein_g")),
            fmt_value(n.get("fat_g")),
            fmt_value(n.get("carb_g")),
            fmt_value(n.get("sodium_mg")),
            fmt_value(n.get("sugar_g")),
            it["source"],
        ))
    lines.append("-" * 78)
    lines.append("%-16s %6s %6s %6s %6s %6s %7s %6s" % (
        "合计",
        "-",
        fmt_value(totals["kcal"]),
        fmt_value(totals["protein_g"]),
        fmt_value(totals["fat_g"]),
        fmt_value(totals["carb_g"]),
        fmt_value(totals["sodium_mg"]),
        fmt_value(totals["sugar_g"]),
    ))
    lines.append("")
    lines.append("占每日参考摄入量（%）：")
    for key in ALL_NUTRIENTS:
        if coverage[key]["state"] == "missing":
            continue
        pct = percentages.get(PCT_KEY[key])
        pct_text = (fmt_value(pct) + "%") if pct is not None else "无完整数据，未计算"
        lines.append("  %-4s %s" % (NUTRIENT_LABELS[key], pct_text))
    return "\n".join(lines)


def make_bars_text(totals, coverage, percentages, dri_values):
    lines = []
    lines.append("营养素占参考值进度条（每个方块=5%，实心为已占）：")
    for key in ALL_NUTRIENTS:
        if coverage[key]["state"] == "missing":
            continue
        pct = percentages.get(PCT_KEY[key])
        if pct is None:
            lines.append("  %-4s 无完整数据，未计算" % NUTRIENT_LABELS[key])
            continue
        ratio = max(0.0, min(1.0, pct / 100.0))
        filled = max(0, min(BAR_WIDTH, int(round(ratio * BAR_WIDTH))))
        bar = "\u2588" * filled + "\u2591" * (BAR_WIDTH - filled)
        lines.append("  %-4s [%s] %5s%%  (%s/%s %s)" % (
            NUTRIENT_LABELS[key], bar, fmt_value(pct),
            fmt_value(totals[key]), fmt_value(dri_values[key]), UNITS[key]))
    return "\n".join(lines)


def make_svg(totals, coverage, percentages, dri_values):
    labels = [k for k in ALL_NUTRIENTS if coverage[k]["state"] != "missing"]
    width = 460
    row_h = 30
    top = 34
    height = top + len(labels) * row_h + 16
    parts = ['<?xml version="1.0" encoding="UTF-8"?>']
    parts.append('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">'
                 % (width, height, width, height))
    parts.append('<rect width="100%" height="100%" fill="#ffffff"/>')
    parts.append('<text x="12" y="22" font-size="14" fill="#333333">'
                 'Nutrition vs daily reference (percent of DRI)</text>')
    for i, key in enumerate(labels):
        y = top + i * row_h
        parts.append('<text x="12" y="%d" font-size="12" fill="#333333">%s</text>'
                     % (y + 14, NUTRIENT_LABELS[key]))
        pct = percentages.get(PCT_KEY[key])
        if pct is None:
            parts.append('<text x="76" y="%d" font-size="12" fill="#333333">no complete data</text>'
                         % (y + 14))
            continue
        ratio = max(0.0, min(1.0, pct / 100.0))
        bar_w = int(round(ratio * 300))
        parts.append('<rect x="76" y="%d" width="300" height="15" fill="#eeeeee"/>' % y)
        parts.append('<rect x="76" y="%d" width="%d" height="15" fill="#c8102e"/>' % (y, bar_w))
        parts.append('<text x="384" y="%d" font-size="12" fill="#333333">%s%%</text>'
                     % (y + 14, fmt_value(pct)))
    parts.append('</svg>')
    return "\n".join(parts)


def emit_text(result):
    out = []
    out.append("目标 goal: " + str(result["goal"]))
    out.append("参考摄入量档位: " + str(result["dri_profile"]))
    out.append("")
    out.append(result["viz"]["table_text"])
    out.append("")
    out.append(result["viz"]["bars_text"])
    out.append("")
    flags = result["goal_signals"]["flags"]
    out.append("目标信号: " + (", ".join(flags) if flags else "(无)"))
    if result.get("budget_eval"):
        out.append("")
        out.append("剩余额度评估: " + json.dumps(result["budget_eval"], ensure_ascii=False))
    if result.get("notes"):
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

    parser = argparse.ArgumentParser(description="McDonald's nutrition deterministic calculator")
    parser.add_argument("--items", default=None,
                        help="JSON object {goal?, dri_profile?, source_hint?, items:[{name,qty,nutrients,source?,override?}]} or a JSON array; use '-' for stdin")
    parser.add_argument("--meals", default=None,
                        help="JSON object {meals:[{key,qty,override?}]} resolved against the offline fallback table")
    parser.add_argument("--override", default=None, help="global override JSON object applied to every item")
    parser.add_argument("--remaining", default=None,
                        help="remaining daily allowance JSON, e.g. {\"kcal\":700,\"protein_g\":40}")
    parser.add_argument("--goal", default=None,
                        help="fat_loss|muscle_gain|sugar_control|high_protein|general")
    parser.add_argument("--dri", default=None, help="DRI profile name, default adult_general")
    parser.add_argument("--format", default="json", choices=["json", "text"], help="output format")
    args = parser.parse_args(argv)

    if bool(args.items) == bool(args.meals):
        fail("BAD_INPUT", "provide exactly one of --items or --meals")

    raw = read_json_arg(args.items if args.items else args.meals, "--items" if args.items else "--meals")
    if isinstance(raw, list):
        obj = {"items" if args.items else "meals": raw}
    elif isinstance(raw, dict):
        obj = raw
    else:
        fail("BAD_INPUT", "input must be a JSON object or array")

    goal = args.goal if args.goal else obj.get("goal", "general")
    if goal not in VALID_GOALS:
        fail("BAD_INPUT", "unknown goal: " + str(goal) + " (expected one of " + ",".join(VALID_GOALS) + ")")
    dri_profile = args.dri if args.dri else obj.get("dri_profile", DEFAULT_DRI_PROFILE)

    global_override = parse_override(read_json_arg(args.override, "--override"), "--override")
    fallback = load_fallback_data()
    dri_table = fallback.get("dri", {})
    if dri_profile not in dri_table:
        fail("BAD_INPUT", "unknown dri_profile: " + str(dri_profile)
             + " (available: " + ",".join(sorted(dri_table.keys())) + ")")
    dri_values = dri_table[dri_profile]

    if args.items:
        items = build_items_from_explicit(obj, global_override)
        data_source = obj.get("source_hint", "explicit")
    else:
        items = build_items_from_meals(obj, fallback, global_override)
        data_source = "fallback-table"

    totals, coverage = compute_totals_and_coverage(items)
    percentages = compute_percentages(totals, coverage, dri_values)
    signals = compute_goal_signals(goal, totals, coverage, percentages)
    remaining = read_json_arg(args.remaining, "--remaining")
    budget_eval = compute_budget_eval(remaining, totals, coverage)

    notes = []
    for key in ALL_NUTRIENTS:
        state = coverage[key]["state"]
        if state == "partial":
            notes.append(
                "%s：仅 %d/%d 项餐品提供该数据，合计为部分值，未据此判定超标，也未计入占比。"
                % (NUTRIENT_LABELS[key], coverage[key]["items_with_value"], coverage[key]["items_total"])
            )
        elif state == "missing":
            notes.append("%s：本次输入全部缺失该数据，未计算、未估算。" % NUTRIENT_LABELS[key])
    if data_source == "fallback-table":
        notes.append("当前使用的是技能内置离线兜底近似表（非麦当劳 MCP 实时数据），仅供参考。")

    disclaimer = DEFAULT_DISCLAIMER
    if data_source == "fallback-table":
        disclaimer = fallback.get("meta", {}).get("disclaimer", DEFAULT_DISCLAIMER)

    result = {
        "ok": True,
        "goal": goal,
        "dri_profile": dri_profile,
        "data_source": data_source,
        "per_item": [{
            "name": it["name"],
            "qty": it["qty"],
            "source": it["source"],
            "nutrients": {k: round1(v) for k, v in sorted(it["nutrients"].items())},
        } for it in items],
        "totals": {k: totals[k] for k in ALL_NUTRIENTS},
        "coverage": coverage,
        "dri": {"profile": dri_profile, "values": dri_values},
        "percentages": percentages,
        "goal_signals": signals,
        "budget_eval": budget_eval,
        "notes": notes,
        "viz": {
            "table_text": make_table_text(items, totals, coverage, percentages),
            "bars_text": make_bars_text(totals, coverage, percentages, dri_values),
            "svg": make_svg(totals, coverage, percentages, dri_values),
        },
        "disclaimer": disclaimer,
    }

    if args.format == "text":
        emit_text(result)
    else:
        sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
    sys.exit(0)


if __name__ == "__main__":
    main()
