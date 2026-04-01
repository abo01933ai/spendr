#!/usr/bin/env python3
"""Parse Obsidian Finance MD files → JSON for dashboard"""

import re
import json
import os
from pathlib import Path

FINANCE_DIR = Path.home() / "Obsidian/Finance"
OUTPUT_DIR = Path(__file__).parent / "data"

CATEGORY_META = {
    "餐點":   {"icon": "🍱", "color": "#FF6B6B", "group": "variable"},
    "飲料":   {"icon": "🧋", "color": "#FF8E53", "group": "variable"},
    "日常消費": {"icon": "🛒", "color": "#FFA940", "group": "variable"},
    "固定支出": {"icon": "📌", "color": "#7C83FD", "group": "fixed"},
    "娛樂":   {"icon": "🎮", "color": "#A78BFA", "group": "variable"},
    "旅遊":   {"icon": "✈️",  "color": "#34D399", "group": "variable"},
    "學習投資": {"icon": "📚", "color": "#60A5FA", "group": "variable"},
    "服飾":   {"icon": "👕", "color": "#F472B6", "group": "variable"},
    "寵物":   {"icon": "🐾", "color": "#FBBF24", "group": "variable"},
    "醫療":   {"icon": "💊", "color": "#4ADE80", "group": "variable"},
    "交通":   {"icon": "🚗", "color": "#22D3EE", "group": "variable"},
    "捐款":   {"icon": "🙏", "color": "#818CF8", "group": "variable"},
    "紅包":   {"icon": "🧧", "color": "#F87171", "group": "variable"},
    "用品":   {"icon": "📦", "color": "#FB923C", "group": "variable"},
    "工具":   {"icon": "🔧", "color": "#94A3B8", "group": "variable"},
    "玩具":   {"icon": "🪆", "color": "#E879F9", "group": "variable"},
    "伴手禮": {"icon": "🎁", "color": "#2DD4BF", "group": "variable"},
    "寶可夢": {"icon": "⚡", "color": "#FBBF24", "group": "variable"},
}

DEFAULT_META = {"icon": "💸", "color": "#94A3B8", "group": "variable"}

SKIP_KEYWORDS = ["當日合計", "小計", "合計", "累積", "固定支出小計", "本月"]
SKIP_SECTIONS = ["本月累積", "固定支出對照", "本月統計"]


def parse_amount(s):
    """Parse amount string like -NT$1,234 or -1,234 → float"""
    s = re.sub(r'[^0-9.\-]', '', s.replace(',', ''))
    try:
        v = float(s)
        return v
    except ValueError:
        return None


def parse_table_row(line):
    """Parse a single markdown table line → list of cell strings or None"""
    line = line.strip()
    if not line.startswith('|'):
        return None
    cells = [c.strip() for c in line.strip('|').split('|')]
    return cells


def parse_month_file(filepath):
    text = filepath.read_text(encoding="utf-8")

    m = re.search(r"(\d{4})-(\d{2})\.md$", filepath.name)
    if not m:
        return None
    year, month = m.group(1), m.group(2)

    transactions = []
    days = {}
    categories = {}

    # Split into lines and process state-machine style
    lines = text.splitlines()
    current_date = None
    in_skip_section = False

    for line in lines:
        stripped = line.strip()

        # Detect section headers (## or ###)
        header_m = re.match(r'^#{1,3}\s+(.+)', stripped)
        if header_m:
            header_text = header_m.group(1).strip()

            # Check if entering a skip section
            in_skip_section = any(kw in header_text for kw in SKIP_SECTIONS)
            if in_skip_section:
                current_date = None
                continue

            # Try to parse as a date header: DD-MM or MM-DD (with optional weekday suffix)
            date_m = re.match(r'^(\d{2})-(\d{2})', header_text)
            if date_m:
                a, b = date_m.group(1), date_m.group(2)
                # Format is MM-DD (month first, then day) based on file content
                full_date = f"{year}-{a}-{b}"
                current_date = full_date
            continue

        if in_skip_section:
            continue

        if not current_date:
            continue

        # Try to parse table row
        if '|' not in stripped:
            continue

        cells = parse_table_row(stripped)
        if not cells or len(cells) < 2:
            continue

        # Skip separator rows
        if all(re.match(r'^-+$', c.replace(':', '').replace(' ', '')) for c in cells if c):
            continue

        # Skip header rows
        if any(h in cells[0] for h in ['類型', '項目', '類別', '分類', '---']):
            continue

        # Skip summary rows
        if any(kw in cells[0] for kw in SKIP_KEYWORDS):
            continue

        # Handle both old (3-col: 類型|項目|金額) and new (4-col: 項目|金額|分類|備註)
        # Old format: col[0]=類型, col[1]=項目, col[2]=金額 (has NT$ or starts with -)
        # New format: col[0]=項目, col[1]=金額 (starts with - or is pure number), col[2]=分類
        # Heuristic: if col[2] looks like a currency amount → old format
        col2_has_amount = bool(re.search(r'(NT\$|-\s*\d)', cells[2])) if len(cells) > 2 else False
        col1_is_amount = bool(re.match(r'^-?\d[\d,.]*$', cells[1].replace(',', ''))) if len(cells) > 1 else False
        is_new_format = col1_is_amount and not col2_has_amount

        if is_new_format and len(cells) >= 3:
            # New format: 項目 | 金額 | 分類 [| 備註]
            item_name = cells[0].replace('**', '').strip()
            raw_amt = cells[1].replace('**', '').strip()
            category = cells[2].replace('**', '').strip() if len(cells) > 2 else "其他"
        elif not is_new_format and len(cells) >= 3:
            # Old format: 類型 | 項目 | 金額
            category = cells[0].replace('**', '').strip()
            item_name = cells[1].replace('**', '').strip()
            raw_amt = cells[2].replace('**', '').strip()
        else:
            continue

        # Skip summary rows by category/item name
        if any(kw in category for kw in SKIP_KEYWORDS) or any(kw in item_name for kw in SKIP_KEYWORDS):
            continue

        # Skip empty entries
        if not item_name or not category:
            continue

        amount = parse_amount(raw_amt)
        if amount is None or amount == 0:
            continue

        # Only allow negative amounts (expenses) — skip monthly summary positive numbers
        if amount > 0:
            continue

        meta = CATEGORY_META.get(category, DEFAULT_META)
        t = {
            "date": current_date,
            "category": category,
            "item": item_name,
            "amount": amount,
            "icon": meta["icon"],
            "group": meta["group"],
        }
        transactions.append(t)

        # Accumulate by category
        categories[category] = categories.get(category, 0) + amount

        # Accumulate by day
        if current_date not in days:
            days[current_date] = {"date": current_date, "total": 0.0, "items": []}
        days[current_date]["total"] += amount
        days[current_date]["items"].append(t)

    # Calculate totals
    total = sum(t["amount"] for t in transactions)
    fixed_total = sum(t["amount"] for t in transactions if t["group"] == "fixed")
    variable_total = sum(t["amount"] for t in transactions if t["group"] == "variable")

    # Build category summary
    category_summary = []
    for cat, amt in sorted(categories.items(), key=lambda x: x[1]):
        meta = CATEGORY_META.get(cat, DEFAULT_META)
        category_summary.append({
            "category": cat,
            "amount": amt,
            "icon": meta["icon"],
            "color": meta["color"],
            "group": meta["group"],
        })

    return {
        "month": f"{year}-{month}",
        "year": int(year),
        "monthNum": int(month),
        "total": total,
        "fixedTotal": fixed_total,
        "variableTotal": variable_total,
        "categories": category_summary,
        "days": sorted(days.values(), key=lambda d: d["date"]),
        "transactions": transactions,
    }


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)

    months = []
    for md_file in sorted(FINANCE_DIR.glob("????-??.md")):
        print(f"Parsing {md_file.name}...")
        data = parse_month_file(md_file)
        if data:
            months.append(data)
            out = OUTPUT_DIR / f"{data['month']}.json"
            out.write_text(json.dumps(data, ensure_ascii=False, indent=2))
            print(f"  → {out.name}: {len(data['transactions'])} tx, total {data['total']:,.0f}")

    index = [{
        "month": m["month"],
        "total": m["total"],
        "fixedTotal": m["fixedTotal"],
        "variableTotal": m["variableTotal"],
    } for m in months]

    (OUTPUT_DIR / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2))
    print(f"\n✅ Done. {len(months)} months parsed.")


if __name__ == "__main__":
    main()
