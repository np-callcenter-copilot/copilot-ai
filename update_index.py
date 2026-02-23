#!/usr/bin/env python3
"""
Script to convert new_data.csv to index.html for AI Copilot provider analysis.
Parses CSV data with provider scores and generates an interactive HTML dashboard.
"""

import csv
import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from pathlib import Path


@dataclass
class Criterion:
    """Represents a single evaluation criterion."""
    priority: str  # Must, Should, Could
    weight: float
    description: str
    scores: Dict[str, float] = field(default_factory=dict)


@dataclass
class Category:
    """Represents a category of criteria (e.g., Copilot, ACW, etc.)."""
    name: str
    weight_percent: float
    criteria: List[Criterion] = field(default_factory=list)
    subtotals: Dict[str, str] = field(default_factory=dict)  # Provider subtotals


PROVIDERS = [
    "Google Cloud CCAI",
    "Ender Turing",
    "NICE",
    "Microsoft Copilot",
    "Genesys Cloud CX",
    "NICE Cognigy",
    "Live Person",
    "Ringo stat",
    "Deca gon",
    "Eleven Labs",
    "Poly AI",
    "Get Vocal"
]

PROVIDER_DISPLAY_NAMES = {
    "Google Cloud CCAI": "Google<br><br>Cloud<br>CCAI",
    "Ender Turing": "Ender<br>Turing",
    "NICE": "NICE",
    "Microsoft Copilot": "Microsoft<br>Copilot",
    "Genesys Cloud CX": "Genesys<br><br>Cloud<br>CX",
    "NICE Cognigy": "NICECognigy",
    "Live Person": "Live<br>Person",
    "Ringo stat": "Ringo<br>stat",
    "Deca gon": "Deca<br>gon",
    "Eleven Labs": "Eleven<br>Labs",
    "Poly AI": "Poly<br>AI",
    "Get Vocal": "Get<br>Vocal"
}

CATEGORY_MAP = {
    "COPILOT": ("copilot", "Copilot", 15),
    "ПОСТОБРОБКА (ACW)": ("acw", "Постобробка", 25),
    "АНАЛІТИКА ТА QA": ("analytics", "Аналітика & QA", 15),
    "PRE-CALL AI, як повноцінний IVR-замінник": ("precall", "PreCall AI", 5),
    "IT, ENTERPRISE & SECURITY": ("it", "IT & Security", 30),
    "БІЗНЕС ТА ВПРОВАДЖЕННЯ": ("business", "Бізнес", 10),
}


def parse_csv(filepath: str) -> tuple:
    """Parse the CSV file and extract categories, criteria, and scores."""
    categories = {}
    final_scores = {}
    tco_values = {}
    current_category = None

    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        rows = list(reader)

    # Find the header row with providers
    header_row_idx = None
    for i, row in enumerate(rows):
        if len(row) > 3 and row[0] == "MSCW" and row[1] == "Weight %":
            header_row_idx = i
            break

    if header_row_idx is None:
        raise ValueError("Could not find header row")

    # Process rows after header
    for i in range(header_row_idx + 1, len(rows)):
        row = rows[i]
        if len(row) < 3:
            continue

        mscw = row[0].strip()
        weight_str = row[1].strip()
        description = row[2].strip() if len(row) > 2 else ""

        # Check if this is a category header
        if description in CATEGORY_MAP:
            cat_id, cat_name, cat_weight = CATEGORY_MAP[description]
            current_category = Category(name=cat_name, weight_percent=cat_weight)
            categories[cat_id] = current_category
            continue

        # Check for category markers (rows with just category name)
        for cat_key, (cat_id, cat_name, cat_weight) in CATEGORY_MAP.items():
            if mscw == cat_key or description == cat_key:
                current_category = Category(name=cat_name, weight_percent=cat_weight)
                categories[cat_id] = current_category
                break

        # Check for final score row (weight=100% and description contains "Загальна оцінка")
        if weight_str == "100%" and "Загальна оцінка" in description:
            for j, provider in enumerate(PROVIDERS):
                if len(row) > j + 3:
                    final_scores[provider] = row[j + 3].strip()
            continue

        # Check for TCO row (contains dollar amounts like "150 - 200 000")
        if len(row) > 3:
            # Check if row has values like "150 - 200 000" pattern
            has_tco = False
            for cell in row[3:15]:
                cell_str = str(cell).strip()
                if cell_str and re.match(r'^\d+\s*-\s*\d+\s*000$', cell_str):
                    has_tco = True
                    break
            if has_tco:
                for j, provider in enumerate(PROVIDERS):
                    if len(row) > j + 3:
                        val = row[j + 3].strip()
                        if val and re.match(r'^\d+\s*-\s*\d+\s*000$', val):
                            tco_values[provider] = val
                continue

        # Check if this is a subtotal row (contains % in weight column, no MSCW)
        if weight_str and '%' in weight_str and not mscw:
            if current_category:
                for j, provider in enumerate(PROVIDERS):
                    if len(row) > j + 3:
                        current_category.subtotals[provider] = row[j + 3].strip()
            continue

        # Parse criterion row
        if mscw in ['Must', 'Should', 'Could'] and current_category:
            try:
                weight = float(weight_str.replace(',', '.')) if weight_str else 0
            except ValueError:
                weight = 0

            criterion = Criterion(
                priority=mscw,
                weight=weight,
                description=description
            )

            # Extract scores for each provider
            for j, provider in enumerate(PROVIDERS):
                if len(row) > j + 3:
                    score_str = row[j + 3].strip()
                    try:
                        score = float(score_str.replace(',', '.'))
                        criterion.scores[provider] = score
                    except (ValueError, AttributeError):
                        criterion.scores[provider] = 0

            current_category.criteria.append(criterion)

    return categories, final_scores, tco_values


def get_score_class(score: float) -> str:
    """Get CSS class based on score value."""
    if score >= 5:
        return "s5"
    elif score >= 4:
        return "s4"
    elif score >= 3:
        return "s3"
    elif score >= 2:
        return "s2"
    else:
        return "s1"


def get_priority_badge(priority: str) -> str:
    """Get priority badge class and letter."""
    if priority == "Must":
        return "must", "M"
    elif priority == "Should":
        return "should", "S"
    else:
        return "could", "C"


def truncate_text(text: str, max_len: int = 50) -> str:
    """Truncate text for display."""
    if len(text) > max_len:
        return text[:max_len] + "..."
    return text


def generate_provider_card(provider: str, rank: int, score: str, tco: str,
                          category_scores: Dict[str, str], max_weights: Dict[str, float]) -> str:
    """Generate HTML for a provider score card."""
    rank_badge = ""
    extra_classes = ""

    if rank == 1:
        rank_badge = "🥇 #1"
        extra_classes = " top top-1"
    elif rank == 2:
        rank_badge = "🥈 #2"
        extra_classes = " top top-2"
    elif rank == 3:
        rank_badge = "🥉 #3"
        extra_classes = " top top-3"
    else:
        rank_badge = f"#{rank}"

    # Calculate breakdown percentages
    breakdowns = []
    category_labels = [
        ("copilot", "Copilot", 15),
        ("acw", "ACW", 25),
        ("analytics", "Analytics", 15),
        ("precall", "PreCall", 5),
        ("it", "IT/Sec", 30),
        ("business", "Бізнес", 10),
    ]

    for cat_id, label, max_weight in category_labels:
        cat_score = category_scores.get(cat_id, "0%")
        try:
            score_val = float(cat_score.replace('%', '').replace(',', '.'))
            fill_pct = (score_val / max_weight) * 100 if max_weight > 0 else 0
        except (ValueError, AttributeError):
            score_val = 0
            fill_pct = 0

        breakdowns.append(f'''                            <div class="breakdown-item">
                                <span class="breakdown-label">{label}</span>
                                <div class="breakdown-bar"><div class="breakdown-fill {cat_id}" style="width: {fill_pct:.1f}%;"></div></div>
                                <span class="breakdown-value">{cat_score}</span>
                            </div>''')

    score_display = score.replace('%', '')
    rank_style = ' style="opacity: 0.5;"' if rank > 3 else ''

    return f'''                    <div class="provider-score-card{extra_classes}">
                        <div class="rank-badge"{rank_style}>{rank_badge}</div>
                        <h4>{provider}</h4>
                        <div class="tco">~${tco}</div>
                        <div class="score-value">{score_display}<span style="font-size: 24px;">%</span></div>
                        <div class="score-label">Підсумковий бал</div>
                        <div class="breakdown">
{chr(10).join(breakdowns)}
                        </div>
                    </div>'''


def generate_criteria_row(criterion: Criterion, providers: List[str]) -> str:
    """Generate HTML for a criteria row."""
    priority_class, priority_letter = get_priority_badge(criterion.priority)

    score_cells = []
    for provider in providers:
        score = criterion.scores.get(provider, 0)
        score_class = get_score_class(score)
        # Display as integer if it's a whole number, otherwise show decimal
        if score == int(score):
            score_display = str(int(score))
        else:
            score_display = str(score)
        score_cells.append(f'                        <div class="score-cell"><div class="score {score_class}">{score_display}</div></div>')

    # Clean description for display
    desc_short = truncate_text(criterion.description, 50)
    desc_full = criterion.description.replace('\n', ' ').replace('"', "'")

    return f'''                    <div class="criteria-row" onclick="toggleExpand(this)" style="grid-template-columns: 250px repeat(12, 1fr);">
                        <div class="criteria-name">
                            <span class="priority-badge {priority_class}">{priority_letter}</span>
                            {desc_short}
                        </div>
{chr(10).join(score_cells)}
                        <div class="expand-details">
                            <h4>Деталі оцінки</h4>
                            <p>{desc_full}</p>
                        </div>
                    </div>'''


def generate_category_tab(cat_id: str, category: Category, providers: List[str]) -> str:
    """Generate HTML for a category tab content."""
    rows = []
    for criterion in category.criteria:
        rows.append(generate_criteria_row(criterion, providers))

    summary_cards = []
    for provider in providers:
        subtotal = category.subtotals.get(provider, "0%")
        summary_cards.append(f'''                    <div class="summary-card">
                        <h5>{provider}</h5>
                        <div class="value">{subtotal}</div>
                    </div>''')

    header_cols = []
    for provider in providers:
        header_cols.append(f'                        <div class="provider-column">{PROVIDER_DISPLAY_NAMES.get(provider, provider)}</div>')

    return f'''        <div class="tab-content" data-content="{cat_id}">
            <div class="summary-section">
                <h3 class="summary-title">{category.name} ({category.weight_percent}%) - Оцінка провайдерів</h3>
                <div class="comparison-table">
                    <div class="table-header" style="grid-template-columns: 250px repeat(12, 1fr);">
                        <div>Критерій</div>
{chr(10).join(header_cols)}
                    </div>

{chr(10).join(rows)}

                </div>
                <div class="summary-grid">
{chr(10).join(summary_cards)}
                </div>
            </div>
        </div>'''


def generate_html(categories: Dict[str, Category], final_scores: Dict[str, str],
                  tco_values: Dict[str, str]) -> str:
    """Generate the complete HTML document."""

    # Sort providers by final score for ranking
    def parse_score(s):
        try:
            return float(s.replace('%', '').replace(',', '.'))
        except (ValueError, AttributeError):
            return 0

    sorted_providers = sorted(PROVIDERS, key=lambda p: parse_score(final_scores.get(p, "0")), reverse=True)

    # Build category scores for each provider
    category_scores = {}
    for provider in PROVIDERS:
        category_scores[provider] = {}
        for cat_id, category in categories.items():
            category_scores[provider][cat_id] = category.subtotals.get(provider, "0%")

    # Generate provider cards for overall tab
    provider_cards = []
    for rank, provider in enumerate(sorted_providers, 1):
        score = final_scores.get(provider, "0%")
        tco = tco_values.get(provider, "N/A")
        card = generate_provider_card(provider, rank, score, tco, category_scores[provider],
                                     {cat_id: cat.weight_percent for cat_id, cat in categories.items()})
        provider_cards.append(card)

    # Generate category tabs
    category_tabs = []
    for cat_id in ["copilot", "acw", "analytics", "precall", "it", "business"]:
        if cat_id in categories:
            category_tabs.append(generate_category_tab(cat_id, categories[cat_id], PROVIDERS))

    # Get winner info
    winner = sorted_providers[0] if sorted_providers else "N/A"
    winner_score = final_scores.get(winner, "0%")

    html = f'''<!DOCTYPE html>
<html lang="uk">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Copilot - Аналіз провайдерів</title>
    <style>

        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #0a0e27 0%, #1a1f3a 100%);
            color: #e0e6ed;
            line-height: 1.6;
            min-height: 100vh;
            padding: 20px;
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}

        header {{
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 16px;
            padding: 40px;
            margin-bottom: 40px;
            backdrop-filter: blur(10px);
        }}

        .header-tag {{
            display: inline-block;
            background: rgba(59, 130, 246, 0.2);
            color: #60a5fa;
            padding: 6px 16px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 16px;
        }}

        h1 {{
            font-size: 48px;
            font-weight: 700;
            margin-bottom: 12px;
            background: linear-gradient(135deg, #ffffff 0%, #60a5fa 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }}

        .subtitle {{
            font-size: 18px;
            color: #9ca3af;
            line-height: 1.8;
            max-width: 800px;
        }}

        .legend {{
            display: flex;
            flex-wrap: wrap;
            gap: 16px;
            margin: 30px 0;
        }}

        .legend-item {{
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 13px;
        }}

        .legend-dot {{
            width: 12px;
            height: 12px;
            border-radius: 50%;
        }}

        .legend-dot.enterprise {{ background: #10b981; }}
        .legend-dot.needs-config {{ background: #f59e0b; }}
        .legend-dot.incomplete {{ background: #ef4444; }}
        .legend-dot.must {{ background: #ef4444; }}
        .legend-dot.should {{ background: #f59e0b; }}
        .legend-dot.could {{ background: #60a5fa; }}

        .winner-card {{
            background: linear-gradient(135deg, rgba(16, 185, 129, 0.1) 0%, rgba(59, 130, 246, 0.1) 100%);
            border: 2px solid rgba(16, 185, 129, 0.3);
            border-radius: 20px;
            padding: 32px;
            margin-bottom: 40px;
            position: relative;
            overflow: hidden;
        }}

        .winner-card::before {{
            content: '🏆';
            position: absolute;
            top: 20px;
            right: 20px;
            font-size: 48px;
            opacity: 0.3;
        }}

        .winner-badge {{
            display: inline-block;
            background: rgba(16, 185, 129, 0.2);
            color: #10b981;
            padding: 8px 20px;
            border-radius: 24px;
            font-size: 13px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.8px;
            margin-bottom: 16px;
        }}

        .winner-name {{
            font-size: 36px;
            font-weight: 700;
            margin-bottom: 8px;
        }}

        .winner-score {{
            font-size: 64px;
            font-weight: 800;
            color: #10b981;
            margin: 16px 0;
        }}

        .winner-description {{
            font-size: 15px;
            color: #d1d5db;
            line-height: 1.7;
        }}

        .tabs {{
            display: flex;
            gap: 12px;
            margin-bottom: 32px;
            background: rgba(255, 255, 255, 0.03);
            padding: 12px;
            border-radius: 12px;
            overflow-x: auto;
        }}

        .tab {{
            padding: 12px 24px;
            background: transparent;
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            color: #9ca3af;
            cursor: pointer;
            transition: all 0.3s ease;
            font-size: 14px;
            font-weight: 600;
            white-space: nowrap;
        }}

        .tab:hover {{
            background: rgba(255, 255, 255, 0.05);
            border-color: rgba(255, 255, 255, 0.2);
        }}

        .tab.active {{
            background: rgba(59, 130, 246, 0.2);
            border-color: #60a5fa;
            color: #60a5fa;
        }}

        .tab-content {{
            display: none;
        }}

        .tab-content.active {{
            display: block;
        }}

        .comparison-table {{
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 16px;
            overflow: hidden;
            margin-bottom: 32px;
        }}

        .table-header {{
            display: grid;
            grid-template-columns: 250px repeat(8, 1fr);
            gap: 1px;
            background: rgba(255, 255, 255, 0.05);
            padding: 16px;
            font-weight: 600;
            font-size: 12px;
            text-align: center;
        }}

        .provider-column {{
            line-height: 1.3;
        }}

        .criteria-row {{
            display: grid;
            grid-template-columns: 250px repeat(8, 1fr);
            gap: 1px;
            padding: 12px 16px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            align-items: center;
            cursor: pointer;
            transition: background 0.2s ease;
        }}

        .criteria-row:hover {{
            background: rgba(255, 255, 255, 0.03);
        }}

        .criteria-name {{
            font-size: 13px;
            display: flex;
            align-items: center;
            gap: 8px;
            padding-right: 8px;
        }}

        .priority-badge {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 20px;
            height: 20px;
            border-radius: 4px;
            font-size: 10px;
            font-weight: 700;
        }}

        .priority-badge.must {{
            background: rgba(239, 68, 68, 0.2);
            color: #ef4444;
        }}

        .priority-badge.should {{
            background: rgba(245, 158, 11, 0.2);
            color: #f59e0b;
        }}

        .priority-badge.could {{
            background: rgba(96, 165, 250, 0.2);
            color: #60a5fa;
        }}

        .score-cell {{
            display: flex;
            justify-content: center;
            align-items: center;
        }}

        .score {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 32px;
            height: 32px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 700;
        }}

        .score.s5 {{
            background: rgba(16, 185, 129, 0.2);
            color: #10b981;
        }}

        .score.s4, .score.s4-5 {{
            background: rgba(34, 197, 94, 0.2);
            color: #22c55e;
        }}

        .score.s3, .score.s3-5 {{
            background: rgba(245, 158, 11, 0.2);
            color: #f59e0b;
        }}

        .score.s2, .score.s2-5 {{
            background: rgba(249, 115, 22, 0.2);
            color: #f97316;
        }}

        .score.s1, .score.s1-5 {{
            background: rgba(239, 68, 68, 0.2);
            color: #ef4444;
        }}

        .expand-details {{
            display: none;
            grid-column: 1 / -1;
            padding: 16px;
            background: rgba(255, 255, 255, 0.02);
            border-radius: 8px;
            margin-top: 12px;
        }}

        .expand-details.active {{
            display: block;
        }}

        .expand-details h4 {{
            font-size: 14px;
            margin-bottom: 8px;
            color: #60a5fa;
        }}

        .expand-details p {{
            font-size: 13px;
            color: #9ca3af;
            line-height: 1.6;
        }}

        .summary-section {{
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 16px;
            padding: 32px;
            margin-bottom: 32px;
        }}

        .summary-title {{
            font-size: 24px;
            font-weight: 700;
            margin-bottom: 24px;
            color: #60a5fa;
        }}

        .summary-grid {{
            display: grid;
            grid-template-columns: repeat(6, 1fr);
            gap: 16px;
        }}

        .summary-card {{
            background: rgba(255, 255, 255, 0.03);
            border-radius: 12px;
            padding: 16px;
            text-align: center;
        }}

        .summary-card h5 {{
            font-size: 12px;
            color: #9ca3af;
            margin-bottom: 8px;
            font-weight: 600;
        }}

        .summary-card .value {{
            font-size: 24px;
            font-weight: 700;
            color: #10b981;
        }}

        .final-scores {{
            display: grid;
            grid-template-columns: repeat(6, 1fr);
            gap: 20px;
            margin-bottom: 32px;
        }}

        .provider-score-card {{
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 16px;
            padding: 24px;
            text-align: center;
        }}

        .provider-score-card:hover {{
            background: rgba(255, 255, 255, 0.05);
            border-color: rgba(255, 255, 255, 0.2);
        }}

        .provider-score-card.top {{
            border-width: 2px;
        }}

        .provider-score-card.top-1 {{
            border-color: #ffd700;
            background: linear-gradient(135deg, rgba(255, 215, 0, 0.1) 0%, rgba(255, 255, 255, 0.03) 100%);
        }}

        .provider-score-card.top-2 {{
            border-color: #c0c0c0;
            background: linear-gradient(135deg, rgba(192, 192, 192, 0.1) 0%, rgba(255, 255, 255, 0.03) 100%);
        }}

        .provider-score-card.top-3 {{
            border-color: #cd7f32;
            background: linear-gradient(135deg, rgba(205, 127, 50, 0.1) 0%, rgba(255, 255, 255, 0.03) 100%);
        }}

        .rank-badge {{
            font-size: 14px;
            font-weight: 700;
            margin-bottom: 8px;
        }}

        .provider-score-card .tco {{
            font-size: 11px;
            color: #9ca3af;
            margin-bottom: 8px;
        }}

        .provider-score-card h4 {{
            font-size: 14px;
            font-weight: 600;
            margin-bottom: 12px;
        }}

        .provider-score-card .score-value {{
            font-size: 36px;
            font-weight: 800;
            color: #10b981;
            margin-bottom: 4px;
        }}

        .provider-score-card.top .score-value {{
            font-size: 42px;
        }}

        .provider-score-card.top-1 .score-value {{
            color: #ffd700;
        }}

        .provider-score-card.top-2 .score-value {{
            color: #c0c0c0;
        }}

        .provider-score-card.top-3 .score-value {{
            color: #cd7f32;
        }}

        .score-label {{
            font-size: 11px;
            color: #9ca3af;
            margin-bottom: 16px;
        }}

        .breakdown {{
            text-align: left;
            padding-top: 16px;
            border-top: 1px solid rgba(255, 255, 255, 0.1);
        }}

        .breakdown-item {{
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 8px;
        }}

        .breakdown-label {{
            font-size: 10px;
            color: #9ca3af;
            width: 50px;
        }}

        .breakdown-bar {{
            flex: 1;
            height: 6px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 3px;
            overflow: hidden;
        }}

        .breakdown-fill {{
            height: 100%;
            border-radius: 3px;
            transition: width 0.3s ease;
        }}

        .breakdown-fill.copilot {{ background: #60a5fa; }}
        .breakdown-fill.acw {{ background: #8b5cf6; }}
        .breakdown-fill.analytics {{ background: #10b981; }}
        .breakdown-fill.precall {{ background: #f59e0b; }}
        .breakdown-fill.it {{ background: #ef4444; }}
        .breakdown-fill.business {{ background: #ec4899; }}

        .breakdown-value {{
            font-size: 10px;
            color: #e0e6ed;
            width: 35px;
            text-align: right;
        }}

        @media (max-width: 1400px) {{
            .final-scores {{
                grid-template-columns: repeat(4, 1fr);
            }}
        }}

        @media (max-width: 1024px) {{
            .final-scores {{
                grid-template-columns: repeat(3, 1fr);
            }}
        }}

        .methodology {{
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 16px;
            padding: 32px;
            margin-top: 32px;
        }}

        .methodology h3 {{
            font-size: 24px;
            font-weight: 700;
            margin-bottom: 24px;
            color: #60a5fa;
        }}

        .methodology-list {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 24px;
        }}

        .methodology-item {{
            display: flex;
            gap: 16px;
            padding: 20px;
            background: rgba(255, 255, 255, 0.02);
            border-radius: 12px;
        }}

        .methodology-item .icon {{
            font-size: 24px;
        }}

        .methodology-item .content h4 {{
            font-size: 15px;
            margin-bottom: 8px;
        }}

        .methodology-item .content p {{
            font-size: 13px;
            color: #9ca3af;
            line-height: 1.5;
        }}

        @media (max-width: 1200px) {{
            .table-header, .criteria-row {{
                grid-template-columns: 200px repeat(12, 1fr);
                font-size: 11px;
            }}
        }}

        @media (max-width: 768px) {{
            h1 {{
                font-size: 32px;
            }}
            .winner-score {{
                font-size: 48px;
            }}
            .tabs {{
                flex-wrap: wrap;
            }}
            .summary-grid {{
                grid-template-columns: repeat(3, 1fr);
            }}
        }}

    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="header-tag">НОВА ПОШТА • R&D • 2025</div>
            <h1>AI Copilot<br>Аналіз провайдерів</h1>
            <p class="subtitle">Порівняльна оцінка 12 провайдерів за методологією MSCW. Вага критеріїв відповідає пріоритетам запуску контакт-центру на 1000 операторів.</p>

            <div class="legend">
                <div class="legend-item">
                    <div class="legend-dot enterprise"></div>
                    <span>80-100% — Enterprise-ready</span>
                </div>
                <div class="legend-item">
                    <div class="legend-dot needs-config"></div>
                    <span>60-79% — Потребує налаштувань</span>
                </div>
                <div class="legend-item">
                    <div class="legend-dot incomplete"></div>
                    <span>&lt;60% — Нішевий / не повноцінний</span>
                </div>
                <div class="legend-item">
                    <div class="legend-dot must"></div>
                    <span>Must</span>
                </div>
                <div class="legend-item">
                    <div class="legend-dot should"></div>
                    <span>Should</span>
                </div>
                <div class="legend-item">
                    <div class="legend-dot could"></div>
                    <span>Could</span>
                </div>
            </div>
        </header>

        <div class="tabs">
            <button class="tab active" data-tab="overall">Загальний рейтинг</button>
            <button class="tab" data-tab="copilot">Copilot (15%)</button>
            <button class="tab" data-tab="acw">Постобробка (25%)</button>
            <button class="tab" data-tab="analytics">Аналітика & QA (15%)</button>
            <button class="tab" data-tab="precall">PreCall AI (5%)</button>
            <button class="tab" data-tab="it">IT & Security (30%)</button>
            <button class="tab" data-tab="business">Бізнес (10%)</button>
        </div>

        <div class="tab-content active" data-content="overall">
            <div class="summary-section">
                <h3 class="summary-title">Підсумкові оцінки</h3>
                <div class="final-scores">

{chr(10).join(provider_cards)}

                </div>
            </div>

            <div class="methodology">
                <h3>Методологія аналізу</h3>
                <div class="methodology-list">
                    <div class="methodology-item">
                        <div class="icon">📊</div>
                        <div class="content">
                            <h4>Пріоритезація за MSCW</h4>
                            <p>Must — обов'язкові для запуску, Should — необхідні для розвитку, Could — чудово було б мати</p>
                        </div>
                    </div>
                    <div class="methodology-item">
                        <div class="icon">⚖️</div>
                        <div class="content">
                            <h4>Розподіл пріоритетів (Weight%)</h4>
                            <p>Кожній характеристиці присвоєно вагу згідно методології MSCW залежно від її критичності</p>
                        </div>
                    </div>
                    <div class="methodology-item">
                        <div class="icon">🎯</div>
                        <div class="content">
                            <h4>Підсумковий відсоток</h4>
                            <p>Сума виконання кожної окремої вимоги відносно її ідеального втілення</p>
                        </div>
                    </div>
                    <div class="methodology-item">
                        <div class="icon">📈</div>
                        <div class="content">
                            <h4>Легенда значення оцінки</h4>
                            <p>5 — готове найкраще рішення | 4/4.5 — хороше рішення | 3/3.5 — потребує налаштувань | 1/2/2.5 — не відповідає</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>

{chr(10).join(category_tabs)}

    </div>

    <script>
        const tabs = document.querySelectorAll('.tab');
        const contents = document.querySelectorAll('.tab-content');

        tabs.forEach(tab => {{
            tab.addEventListener('click', () => {{
                const targetTab = tab.dataset.tab;

                tabs.forEach(t => t.classList.remove('active'));
                contents.forEach(c => c.classList.remove('active'));

                tab.classList.add('active');
                document.querySelector(`[data-content="${{targetTab}}"]`).classList.add('active');
            }});
        }});

        function toggleExpand(row) {{
            const expandDetails = row.querySelector('.expand-details');
            const allExpanded = document.querySelectorAll('.expand-details.active');

            allExpanded.forEach(el => {{
                if (el !== expandDetails) {{
                    el.classList.remove('active');
                }}
            }});

            if (expandDetails) {{
                expandDetails.classList.toggle('active');
            }}
        }}
    </script>
</body>
</html>'''

    return html


def main():
    """Main function to run the conversion."""
    script_dir = Path(__file__).parent
    csv_path = script_dir / "new_data.csv"
    html_path = script_dir / "index.html"
    backup_path = script_dir / "index_backup.html"

    print(f"Reading CSV from: {csv_path}")

    # Parse CSV
    categories, final_scores, tco_values = parse_csv(str(csv_path))

    print(f"Parsed {len(categories)} categories:")
    for cat_id, cat in categories.items():
        print(f"  - {cat.name}: {len(cat.criteria)} criteria")

    print(f"\nFinal scores:")
    for provider, score in sorted(final_scores.items(), key=lambda x: float(x[1].replace('%', '').replace(',', '.')) if x[1] else 0, reverse=True):
        print(f"  - {provider}: {score}")

    # Backup existing HTML
    if html_path.exists():
        import shutil
        shutil.copy(html_path, backup_path)
        print(f"\nBackup created: {backup_path}")

    # Generate HTML
    html_content = generate_html(categories, final_scores, tco_values)

    # Write HTML
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"\nGenerated HTML: {html_path}")
    print(f"File size: {len(html_content):,} bytes")


if __name__ == "__main__":
    main()
