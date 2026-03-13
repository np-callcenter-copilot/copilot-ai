#!/usr/bin/env python3
"""
Script to convert new_data.csv to index.html for AI Copilot provider analysis.
Parses CSV data with provider scores and generates an interactive HTML dashboard.
"""

import csv
import json
import re
import shutil
from dataclasses import dataclass, field
from typing import Dict, List
from pathlib import Path


@dataclass
class Criterion:
    """Represents a single evaluation criterion."""
    priority: str  # Must, Should, Could
    weight: float
    name: str  # Short criterion name from CSV column 1
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
    "Uni Talk",
    "NICE",
    "Microsoft Copilot",
    "Genesys Cloud CX",
    "NICE Cognigy",
    "Cresta",
    "Live Person",
    "Ringostat",
    "Decagon",
    "11 Labs",
    "Poly AI",
    "Get Vocal"
]

PROVIDER_DISPLAY_NAMES = {
    "Google Cloud CCAI": "Google<br>Cloud<br>CCAI",
    "Ender Turing": "Ender<br>Turing",
    "Uni Talk": "Uni Talk",
    "NICE": "NICE",
    "Microsoft Copilot": "Microsoft<br>Copilot",
    "Genesys Cloud CX": "Genesys<br>Cloud<br>CX",
    "NICE Cognigy": "NICE Cognigy",
    "Cresta": "Cresta",
    "Live Person": "LivePerson",
    "Ringostat": "Ringostat",
    "Decagon": "Decagon",
    "11 Labs": "11 Labs",
    "Poly AI": "Poly AI",
    "Get Vocal": "Get Vocal"
}

CATEGORY_MAP = {
    "COPILOT": ("copilot", "Copilot", 15),
    "ПОСТОБРОБКА (ACW)": ("acw", "Постобробка", 25),
    "АНАЛІТИКА ТА QA": ("analytics", "Аналітика & QA", 15),
    "PRE-CALL AI, як повноцінний IVR-замінник": ("precall", "PreCall AI", 5),
    "IT, ENTERPRISE & SECURITY": ("it", "IT & Security", 30),
    "БІЗНЕС ТА ВПРОВАДЖЕННЯ": ("business", "Бізнес", 10),
}

# Short display labels for breakdown bars in provider score cards.
# Derived from CATEGORY_MAP so the two sources stay in sync.
_CATEGORY_BREAKDOWN_LABELS: Dict[str, str] = {
    "copilot": "Copilot",
    "acw": "ACW",
    "analytics": "Analytics",
    "precall": "PreCall",
    "it": "IT/Sec",
    "business": "Бізнес",
}


def _parse_score_float(score_str: str) -> float:
    """Convert a score string like '84.1%' or '84,1' to a float."""
    try:
        return float(str(score_str).replace('%', '').replace(',', '.'))
    except (ValueError, AttributeError):
        return 0.0


def parse_csv(filepath: str, delimiter: str = ';') -> tuple:
    """Parse the CSV file and extract categories, criteria, and scores.

    CSV structure (after update):
    - Column 0: MSC (Must/Should/Could)
    - Column 1: Criterion Name (short name)
    - Column 2: Weight %
    - Column 3: Description (detailed)
    - Columns 4-15: Provider scores
    """
    categories: Dict[str, Category] = {}
    final_scores: Dict[str, str] = {}
    tco_values: Dict[str, str] = {}
    current_category: Category | None = None

    with open(filepath, 'r', encoding='utf-8') as f:
        rows = list(csv.reader(f, delimiter=delimiter))

    # Find the header row with providers (has empty column 1 for criterion name)
    header_row_idx = next(
        (i for i, row in enumerate(rows)
         if len(row) > 3 and row[0] == "MSC" and row[2] == "Weight %"),
        None
    )
    if header_row_idx is None:
        raise ValueError("Could not find header row")

    for row in rows[header_row_idx + 1:]:
        if len(row) < 4:
            continue

        mscw = row[0].strip()
        criterion_name = row[1].strip()
        weight_str = row[2].strip()
        description = row[3].strip() if len(row) > 3 else ""

        # Category header row
        if mscw in CATEGORY_MAP:
            cat_id, cat_name, cat_weight = CATEGORY_MAP[mscw]
            current_category = Category(name=cat_name, weight_percent=cat_weight)
            categories[cat_id] = current_category
            continue

        # Final score row
        if weight_str == "100%" and "Загальна оцінка" in description:
            for j, provider in enumerate(PROVIDERS):
                if len(row) > j + 4:
                    final_scores[provider] = row[j + 4].strip()
            continue

        # TCO row (values match pattern like "150 - 200 000")
        if len(row) > 4:
            tco_pattern = r'^\d+\s*-\s*\d+\s*000$'
            if any(re.match(tco_pattern, str(cell).strip()) for cell in row[4:16]):
                for j, provider in enumerate(PROVIDERS):
                    if len(row) > j + 4:
                        val = row[j + 4].strip()
                        if val and re.match(tco_pattern, val):
                            tco_values[provider] = val
                continue

        # Subtotal row (has % in weight column, no MSC)
        if weight_str and '%' in weight_str and not mscw:
            if current_category:
                for j, provider in enumerate(PROVIDERS):
                    if len(row) > j + 4:
                        current_category.subtotals[provider] = row[j + 4].strip()
            continue

        # Criterion row
        if mscw in ('Must', 'Should', 'Could') and current_category:
            try:
                weight = float(weight_str.replace(',', '.')) if weight_str else 0.0
            except ValueError:
                weight = 0.0

            name = criterion_name if criterion_name else truncate_text(description, 40)
            criterion = Criterion(priority=mscw, weight=weight, name=name, description=description)

            for j, provider in enumerate(PROVIDERS):
                if len(row) > j + 4:
                    score_str = row[j + 4].strip()
                    try:
                        criterion.scores[provider] = float(score_str.replace(',', '.'))
                    except (ValueError, AttributeError):
                        criterion.scores[provider] = 0.0

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
    return "s1"


def get_priority_badge(priority: str) -> tuple:
    """Return (css_class, letter) for a priority string."""
    return {
        "Must": ("must", "M"),
        "Should": ("should", "S"),
    }.get(priority, ("could", "C"))


def truncate_text(text: str, max_len: int = 50) -> str:
    """Truncate text for display."""
    return text[:max_len] + "..." if len(text) > max_len else text


# ---------------------------------------------------------------------------
# HTML fragment builders
# ---------------------------------------------------------------------------

def _render_pros_cons(pros: List[str], cons: List[str]) -> str:
    """Render the two-column pros/cons grid shared by all strategy cards."""
    def _items(points: List[str], color: str, symbol: str) -> str:
        lines = "\n".join(
            f'                                <div style="display:flex;gap:10px;font-size:13px;color:#9ca3af;align-items:flex-start;">'
            f'<span style="color:{color};flex-shrink:0;">{symbol}</span>{point}</div>'
            for point in points
        )
        return lines

    return f'''                        <div>
                            <div style="font-size:9px;letter-spacing:.1em;text-transform:uppercase;color:#6b7280;margin-bottom:10px;">Переваги</div>
                            <div style="display:flex;flex-direction:column;gap:8px;">
{_items(pros, "#10b981", "✓")}
                            </div>
                        </div>
                        <div>
                            <div style="font-size:9px;letter-spacing:.1em;text-transform:uppercase;color:#6b7280;margin-bottom:10px;">Ризики</div>
                            <div style="display:flex;flex-direction:column;gap:8px;">
{_items(cons, "#ef4444", "✗")}
                            </div>
                        </div>'''


def _render_strategy_card(
    *,
    border_rgba: str,
    label_color: str,
    label_text: str,
    score_text: str,
    title: str,
    subtitle: str,
    pros: List[str],
    cons: List[str],
    wrapper_style: str = "",
    indent: str = "                ",
) -> str:
    """Render one provider strategy card for the recommendations tab.

    All visual values are passed as arguments so the HTML structure is
    defined exactly once — eliminating the 10-copy repetition.
    """
    pros_cons = _render_pros_cons(pros, cons)
    wrapper_open = f'{indent}<div class="strategy-card" style="border-color: {border_rgba};{wrapper_style}">'
    return f'''{wrapper_open}
                    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;">
                        <div class="strategy-label" style="color: {label_color}; margin-bottom: 0;">{label_text}</div>
                        <div style="font-family:monospace;font-size:20px;font-weight:600;color:{label_color};">{score_text}</div>
                    </div>
                    <div class="strategy-title" style="margin-bottom: 4px;">{title}</div>
                    <div style="font-size:11px;color:#6b7280;margin-bottom:16px;">{subtitle}</div>
                    <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;">
{pros_cons}
                    </div>
                </div>'''


def generate_provider_card(
    provider: str,
    rank: int,
    score: str,
    tco: str,
    category_scores: Dict[str, str],
    max_weights: Dict[str, float],
) -> str:
    """Generate HTML for a provider score card."""
    RANK_BADGES = {1: "🥇 #1", 2: "🥈 #2", 3: "🥉 #3"}
    RANK_CLASSES = {1: " top top-1", 2: " top top-2", 3: " top top-3"}

    rank_badge = RANK_BADGES.get(rank, f"#{rank}")
    extra_classes = RANK_CLASSES.get(rank, "")
    rank_style = ' style="opacity: 0.5;"' if rank > 3 else ''

    # Build breakdown bars using CATEGORY_MAP as the single source of truth
    # for cat_id ordering and max_weight; _CATEGORY_BREAKDOWN_LABELS for display names.
    breakdowns = []
    for csv_key, (cat_id, _cat_name, cat_max_weight) in CATEGORY_MAP.items():
        label = _CATEGORY_BREAKDOWN_LABELS[cat_id]
        cat_score = category_scores.get(cat_id, "0%")
        score_part = cat_score.split(' / ')[0]
        score_val = _parse_score_float(score_part)
        fill_pct = (score_val / cat_max_weight * 100) if cat_max_weight > 0 else 0.0
        breakdowns.append(
            f'                            <div class="breakdown-item">\n'
            f'                                <span class="breakdown-label">{label}</span>\n'
            f'                                <div class="breakdown-bar">'
            f'<div class="breakdown-fill {cat_id}" style="width: {fill_pct:.1f}%;"></div></div>\n'
            f'                                <span class="breakdown-value">{cat_score}</span>\n'
            f'                            </div>'
        )

    score_display = score.replace('%', '')

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
    priority_class, _ = get_priority_badge(criterion.priority)
    w = criterion.weight
    weight_label = f"{int(w)}%" if w == int(w) else f"{w}%"
    desc_full = criterion.description.replace('"', "'").replace('\n', '<br>')

    score_cells = []
    for provider in providers:
        score = criterion.scores.get(provider, 0)
        score_class = get_score_class(score)
        score_display = str(int(score)) if score == int(score) else str(score)
        score_cells.append(
            f'                        <div class="score-cell">'
            f'<div class="score {score_class}">{score_display}</div></div>'
        )

    n = len(providers)
    return f'''                    <div class="criteria-row" onclick="toggleExpand(this)" style="grid-template-columns: 250px repeat({n}, 1fr);">
                        <div class="criteria-name">
                            <span class="priority-badge {priority_class}">{weight_label}</span>
                            {criterion.name}
                        </div>
{chr(10).join(score_cells)}
                        <div class="expand-details">
                            <h4>Деталі оцінки</h4>
                            <p>{desc_full}</p>
                        </div>
                    </div>'''


def generate_category_tab(cat_id: str, category: Category, providers: List[str]) -> str:
    """Generate HTML for a category tab content."""
    rows = "\n".join(generate_criteria_row(c, providers) for c in category.criteria)

    providers_sorted_by_cat = sorted(
        providers,
        key=lambda p: _parse_score_float(category.subtotals.get(p, "0")),
        reverse=True,
    )
    summary_cards = "\n".join(
        f'                    <div class="summary-card">\n'
        f'                        <h5>{p}</h5>\n'
        f'                        <div class="value">{category.subtotals.get(p, "0%")}</div>\n'
        f'                    </div>'
        for p in providers_sorted_by_cat
    )

    header_cols = "\n".join(
        f'                        <div class="provider-column">{PROVIDER_DISPLAY_NAMES.get(p, p)}</div>'
        for p in providers
    )

    return f'''        <div class="tab-content" data-content="{cat_id}">
            <div class="summary-section">
                <h3 class="summary-title">{category.name} ({category.weight_percent}%) - Оцінка провайдерів</h3>
                <div class="comparison-table">
                    <div class="table-header" style="grid-template-columns: 250px repeat({len(providers)}, 1fr);">
                        <div>Критерій</div>
{header_cols}
                    </div>

{rows}

                </div>
                <div class="summary-grid">
{summary_cards}
                </div>
            </div>
        </div>'''


def generate_recommendations_tab() -> str:
    """Generate HTML for the recommendations tab."""

    # ------------------------------------------------------------------
    # Priority provider cards (full-width)
    # ------------------------------------------------------------------
    cresta_card = _render_strategy_card(
        border_rgba="rgba(34,211,238,.3)",
        label_color="#22d3ee",
        label_text="Real-Time Assist · Agent Copilot · #1 Score",
        score_text="85.1%",
        title="Cresta AI",
        subtitle="Real-Time Assist · Agent Copilot · Ocean-1",
        indent="                    ",
        pros=[
            "Ocean-1: власна модель від ех-співробітників OpenAI з мультимовною підтримкою",
            "Найкращий Copilot на ринку, глибока постобробка, нативна інтеграція у робоче місце оператора, висока точність аналітики",
            "Cresta має українське венчурне коріння від фонду Roosh Ventures Сергія Токарєва (раунд $80 млн у 2022)",
            "Email-підтримка як повноцінний канал комунікації",
        ],
        cons=[
            "Потребує тестування діалогів та суржику — авторезюме, заповнення тематик, полів та маркування розмов",
            "Відсутність нативної інтеграції з Binotel, Power Platform, Power BI",
            "Тривале налаштування та непрозора вартість розробки",
        ],
    )

    google_card = _render_strategy_card(
        border_rgba="rgba(245,200,66,.3)",
        label_color="#f5c842",
        label_text="Enterprise-рішення · #2 Score",
        score_text="81.5%",
        title="Google Cloud CCAI",
        subtitle="Contact Center AI · Agent Assist · Dialogflow CX · Gemini",
        indent="                    ",
        pros=[
            "Нативна підтримка української мови з кращим авторезюме. Підтримка 100+ мов через Google NLU",
            "Спеціалізована telephony-модель, навчена на аудіо телефонних ліній та IVR-систем",
            "Gemini — один з найпотужніших LLM у світі",
            "Нативна інтеграція з Cisco",
            "Повний стек із набору інструментів. Гнучка компонентна архітектура (оплата лише за необхідний функціонал)",
        ],
        cons=[
            "Потребує тестування діалогів та суржику — авторезюме, заповнення тематик, полів та маркування розмов",
            "Відсутність нативної інтеграції з Binotel, Power Platform, Power BI",
            "Складність адміністрування та дорога вартість розробки",
            "Складність налаштування повного стеку",
        ],
    )

    ender_card = _render_strategy_card(
        border_rgba="rgba(62,207,142,.25)",
        label_color="#10b981",
        label_text="Співвідношення ціна / якість",
        score_text="67.6%",
        title="Ender Turing",
        subtitle="Локальний продукт із найкращим розумінням українського говору",
        indent="                    ",
        pros=[
            "Найкраща генерація резюме розмов",
            "Модулі аналітики та якісне навчання операторів",
            "Підтверджений досвід у NovaPay",
            "100% автоматизований контроль якості. Аналітика рівня світових продуктів",
        ],
        cons=[
            "Відсутній інструмент підказок у реальному часі — не є асистентом оператора під час дзвінка",
            "Немає функцій Pre-Call AI (голосовий бот / заміна IVR)",
            "Слабші інтеграційні можливості — потрібна розробка API з усіма системами",
            "Алгоритми ACW поступаються якістю великим мовним моделям (GPT, Gemini)",
        ],
    )

    unitalk_card = _render_strategy_card(
        border_rgba="rgba(156,163,175,.25)",
        label_color="#9ca3af",
        label_text="Call Recording · Voice Bot",
        score_text="45.1%",
        title="Uni Talk",
        subtitle="Локальний продукт · Голосовий бот",
        indent="                    ",
        pros=[
            "Український продукт із функціоналом голосового бота",
            "Швидкий і безкоштовний пілот",
            "Інтуїтивне адміністрування та зручний інтерфейс для менеджерів",
            "Швидкий онбординг після підписання контракту",
        ],
        cons=[
            "Відсутній функціонал копайлота",
            "Максимум 15 API-запитів на секунду",
            "Немає авторезюме дзвінка, лише транскрибація і таймлайни",
            "Відсутня автоматична оцінка якості та аналітика",
            "Слабке тегування та маркування розмов",
            "Моноліт. Рішення передбачає свою телефонію"
        ],
    )

    # ------------------------------------------------------------------
    # Secondary provider cards (2-column grid rows)
    # ------------------------------------------------------------------
    microsoft_card = _render_strategy_card(
        border_rgba="rgba(74,158,255,.25)",
        label_color="#60a5fa",
        label_text="AI Ecosystem · Azure OpenAI",
        score_text="78.4%",
        title="Microsoft Copilot",
        subtitle="Dynamics 365 · Power Platform",
        indent="                    ",
        pros=[
            "Висока швидкість і точність Next Best Action для вирішення запитів",
            "Найкращий пошук із завантаженою базою знань із наданням прямих посилань на документи",
            "Гнучка адаптація відповідей під контекст розмови",
            "Безшовна передача даних аналітики у внутрішні системи звітності",
            "Найвищий рівень маскування чутливих даних клієнтів",
        ],
        cons=[
            "Слабше автоматичне перенесення даних саме з україномовних розмов",
            "Фокус інструментарію платформи зроблено на текстові канали зв'язку",
            "Висока вартість ліцензій та складність налаштування",
            "Обмежена автоматизація процесу у кейсах: з 7 до 4хв"
        ],
    )

    nice_card = _render_strategy_card(
        border_rgba="rgba(168,85,247,.25)",
        label_color="#a855f7",
        label_text="Enterprise Cloud Contact Center",
        score_text="74.9%",
        title="NICE",
        subtitle="Enlighten AI · Autopilot",
        indent="                    ",
        pros=[
            "Швидкість аналізу контексту у реальному часі займає до 2 секунд",
            "Copilot-функціонал для супроводу оператора (підказки, генерація скриптів)",
            "Наявність професійного вбудованого модуля WFM",
            "Розвинені інструменти автоматичного навчання операторів",
        ],
        cons=[
            "Глобальна міграція — повноцінна інфраструктурна платформа",
            "Необхідність тестування української мови для авторезюме (ACW)",
            "Слабше розпізнавання суржику порівняно з локальними продуктами",
            "Довгий та складний процес впровадження",
        ],
    )

    genesys_card = _render_strategy_card(
        border_rgba="rgba(251,146,60,.25)",
        label_color="#fb923c",
        label_text="Contact Center as a Service",
        score_text="72.7%",
        title="Genesys Cloud CX",
        subtitle="Genesys AI · Agent Assist",
        indent="                    ",
        pros=[
            "Надійний модуль Agent Assist із високою швидкістю підказок",
            "Відмінне автоматичне маскування чутливої інформації",
            "Зручне low-code налаштування без залучення ІТ",
            "Високий рівень масштабування та витривалість",
        ],
        cons=[
            "Глобальна міграція — повноцінна платформа, що потребує переїзду",
            "Низька точність STT для українського аудіо",
            "Потенційні складнощі з визначенням глибоких підтематик",
            "Відсутні інструменти для ШІ-перевірки по чек-листу",
        ],
    )

    cognigy_card = _render_strategy_card(
        border_rgba="rgba(168,85,247,.25)",
        label_color="#a855f7",
        label_text="Conversational AI · Bot-first",
        score_text="71.5%",
        title="NICE Cognigy",
        subtitle="Omnichannel",
        indent="                    ",
        pros=[
            "Потужний Pre-Call AI — лідер у створенні голосових ботів",
            "Зручні візуальні конструктори low-code",
            "Висока швидкість NBA та відмінний пошук по документації",
        ],
        cons=[
            "Немає підтверджень генерації українською авторезюме",
            "Складнощі зі швидкістю маркування та фільтрації даних",
            "Гірші можливості для передачі даних у кастомне робоче місце",
        ],
    )

    liveperson_card = _render_strategy_card(
        border_rgba="rgba(156,163,175,.25)",
        label_color="#9ca3af",
        label_text="Text-first · AI Chatbots",
        score_text="61.2%",
        title="Live Person",
        subtitle="Conversational Cloud",
        indent="                    ",
        pros=[
            "Сильний інструментарій для чатів, месенджерів та NBA у тексті",
            "Високий рівень захисту та автоматичного маскування даних",
        ],
        cons=[
            "Відсутнє підтвердження якісного розуміння українського голосу та суржику",
            "Контроль якості дзвінків відсутній по чек-листах",
            "Значне відставання у функціоналі ACW",
        ],
    )

    ringostat_card = _render_strategy_card(
        border_rgba="rgba(156,163,175,.25)",
        label_color="#9ca3af",
        label_text="Call Tracking · Cloud PBX",
        score_text="57.7%",
        title="Ringostat",
        subtitle="AI Analytics",
        indent="                    ",
        pros=[
            "Швидкий та безкоштовний запуск тестового періоду",
            "Відмінний базовий рівень розпізнавання української мови та суржику",
            "Зрозумілі дашборди та висока здатність перетравлювати великі потоки даних",
        ],
        cons=[
            "Фокус продукту на продажі, маркетинг та аналіз реклами",
            "Відсутність Copilot-функцій",
            "Слабкі можливості ACW та класифікації тематик",
            "Відсутня архітектура для глибокої взаємодії з API",
        ],
    )

    decagon_card = _render_strategy_card(
        border_rgba="rgba(156,163,175,.25)",
        label_color="#9ca3af",
        label_text="Generative AI · Text-first",
        score_text="57.3%",
        title="Decagon",
        subtitle="Customer Support Automation",
        indent="                    ",
        pros=[
            "Сильні інструменти для текстових скриптів та пошуку по документації",
            "Інтерфейс налаштувань інтуїтивно зрозумілий",
            "Швидкий старт пілотного проєкту на реальних даних",
            "Розгортають співпрацю із 11labs"
        ],
        cons=[
            "Відсутність української голосової моделі для транскрибації",
            "Слабкі модулі аналітики та автоматичного контролю якості (QA)",
        ],
    )

    polyai_card = _render_strategy_card(
        border_rgba="rgba(156,163,175,.25)",
        label_color="#9ca3af",
        label_text="Voice Assistants · Conversational IVR",
        score_text="55.7%",
        title="Poly AI",
        subtitle="Voice Assistants",
        indent="                    ",
        pros=[
            "Вузька спеціалізація у голосових асистентах (Pre-Call, заміна IVR)",
            "Здатність витримувати величезну кількість одночасних розмов",
            "Надійні протоколи захисту даних",
        ],
        cons=[
            "Менша швидкість обробки ШІ та глибина розуміння української",
            "Відсутні підказки та супровід живого оператора",
            "Немає інструментів для постобробки та аналітики",
        ],
    )

    getvocal_card = _render_strategy_card(
        border_rgba="rgba(156,163,175,.25)",
        label_color="#9ca3af",
        label_text="Local Voice · AI Provider",
        score_text="40.3%",
        title="Get Vocal",
        subtitle="Local Voice AI",
        indent="                    ",
        pros=[
            "Швидкий старт, готовність до локальної співпраці та недорогий тест",
            "Готовий функціонал безшовної ескалації розмови з бота на оператора",
        ],
        cons=[
            "Функціональне відставання швидкості роботи ШІ та поверхневе розуміння української",
            "Відсутність функціоналу пошуку Copilot, модуля ACW та аналітики",
            "Слабке розпізнавання суржику та недостатній аналіз емоцій",
            "Не вказано у документації функціонал українською та аналіз емоцій"
        ],
    )

    elevenlabs_card = _render_strategy_card(
        border_rgba="rgba(156,163,175,.25)",
        label_color="#60a5fa",
        label_text="Голосовий асистент · STT-шар",
        score_text="40%",
        title="ElevenLabs",
        subtitle="Speech-to-Text · Scribe v2 · Streaming · Pre-Call",
        indent="                    ",
        pros=[
            "Голосовий асистент та маршрутизація (Pre-Call)",
            "STT — висока точність розпізнавання мови",
            "Scribe v2 забезпечує розпізнавання суржику",
            "Стрімінгова передача тексту із затримкою ~500 мс",
            "Нативна Cisco-інтеграція",
            "Сертифікації безпеки",
        ],
        cons=[
            "Не є Copilot-рішенням — лише надає транскрибацію у систему",
            "Відсутній функціонал ACW, аналітики та не може замінити IVR",
        ],
    )

    return f'''        <div class="tab-content" data-content="recommendations">
            <div class="recommendations-section">
                <div class="rec-header">
                    <div class="rec-eyebrow">Фінальний розділ</div>
                    <h3 class="rec-title">Ключові висновки аналізу</h3>
                    <p class="rec-lead">
                        Аналіз 14 рішень за методологією MSC для AI Copilot контакт-центру на 1 000 операторів.
                        Оскільки ми вже маємо високорозвинену екосистему контакт-центру — готове робоче місце оператора,
                        дерево тематик, функціонуючу базу знань та власну систему аналітики — класичний підхід до
                        закупівлі монолітних рішень стає недоцільним.
                    </p>
                </div>

                <div class="rec-divider">
                    <span class="rec-divider-label">Аналіз Провайдерів</span>
                    <div class="rec-divider-line"></div>
                </div>

                <!-- Provider Cards Grid - Row 1 -->
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px;">
{cresta_card}

{google_card}
                </div>

                <!-- Provider Cards Grid - Row 2 -->
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px;">
{nice_card}

{microsoft_card}
                </div>

                <!-- Provider Cards Grid - Row 3 -->
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px;">
{genesys_card}

{cognigy_card}
                </div>

                <!-- Provider Cards Grid - Row 4 -->
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px;">
{ender_card}

{liveperson_card}
                </div>

                <!-- Provider Cards Grid - Row 5 -->
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px;">
{decagon_card}

{polyai_card}
                </div>

                <!-- Provider Cards Grid - Row 6 -->
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px;">
{ringostat_card}

{unitalk_card}
                </div>

                <!-- Provider Cards Grid - Row 7 -->
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px;">
{elevenlabs_card}

{getvocal_card}
                </div>

                <div class="rec-divider">
                    <span class="rec-divider-label">Ключові висновки</span>
                    <div class="rec-divider-line"></div>
                </div>

                <div class="strategy-alert-card" style="border-color: rgba(255,255,255,0.15);">

                        <div class="strategy-title">Ризики монолітних CCaaS платформ</div>
                        <div class="strategy-text">
                            Глобальні рішення формату «все-в-одному» (Genesys Cloud CX або NICE CXone), попри свою потужність,
                            вимагають міграції операторів у власні інтерфейси та використання вбудованих баз знань.
                            Для нас це означатиме <strong style="color:#f59e0b;">міграцію до вендора та відмову від власних робочих місць операторів.</strong>
                        </div>

                </div>

                <div class="strategy-card" style="border-color: rgba(255,255,255,0.15);">
                    <div class="strategy-label" style="color: #9ca3af;">Важливий висновок</div>
                    <div class="strategy-title">Жоден провайдер не закриває 100% вимог</div>
                    <div class="strategy-text">
                        Кожне з 14 проаналізованих рішень має глибокі переваги в одному домені й важливі для нас архітектурні прогалини в іншому.
                        Ідеальне рішення — це <strong style="color:#e0e6ed;">композитна архітектура з лідерів у своїх нішах</strong> або перегляд пріоритизації та ваги must-вимог.
                    </div>
                </div>

                <div class="rec-divider">
                    <span class="rec-divider-label">Приклад Технічної Архітектури TO-BE</span>
                    <div class="rec-divider-line"></div>
                </div>

                <div style="border:1px solid var(--border2);border-radius:10px;overflow:hidden;background:#080b12">
                  <svg viewBox="0 0 1360 400" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="Mulish,sans-serif">
                    <defs>
                      <marker id="a1" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto"><path d="M0,0 L10,4 L0,8 Z" fill="#5a6e90"/></marker>
                      <marker id="a2" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto"><path d="M0,0 L10,4 L0,8 Z" fill="#4a8cff"/></marker>
                      <marker id="a3" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto"><path d="M0,0 L10,4 L0,8 Z" fill="#30d890"/></marker>
                      <marker id="a5" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto"><path d="M0,0 L10,4 L0,8 Z" fill="#3a4a65"/></marker>
                    </defs>
                    <rect x="0" y="0" width="1360" height="400" fill="#080b12"/>
                    <!-- Lane backgrounds -->
                    <rect x="0"    y="0" width="185"  height="370" fill="#0a0e16"/>
                    <rect x="185"  y="0" width="185"  height="370" fill="#0c1020"/>
                    <rect x="370"  y="0" width="185"  height="370" fill="#0a0e16"/>
                    <rect x="555"  y="0" width="260"  height="370" fill="#0c1020"/>
                    <rect x="815"  y="0" width="260"  height="370" fill="#0a0e16"/>
                    <rect x="1075" y="0" width="285"  height="370" fill="#0c1020"/>
                    <!-- Lane headers -->
                    <rect x="0"    y="0" width="185"  height="28" fill="#111826"/>
                    <rect x="185"  y="0" width="185"  height="28" fill="#131a2e"/>
                    <rect x="370"  y="0" width="185"  height="28" fill="#111826"/>
                    <rect x="555"  y="0" width="260"  height="28" fill="#131a2e"/>
                    <rect x="815"  y="0" width="260"  height="28" fill="#111826"/>
                    <rect x="1075" y="0" width="285"  height="28" fill="#131a2e"/>
                    <!-- Dividers -->
                    <line x1="185"  y1="0" x2="185"  y2="370" stroke="#1e2a40" stroke-width="1.2"/>
                    <line x1="370"  y1="0" x2="370"  y2="370" stroke="#1e2a40" stroke-width="1.2"/>
                    <line x1="555"  y1="0" x2="555"  y2="370" stroke="#1e2a40" stroke-width="1.2"/>
                    <line x1="815"  y1="0" x2="815"  y2="370" stroke="#1e2a40" stroke-width="1.2"/>
                    <line x1="1075" y1="0" x2="1075" y2="370" stroke="#1e2a40" stroke-width="1.2"/>
                    <line x1="0" y1="28" x2="1360" y2="28" stroke="#1e2a40" stroke-width="1"/>
                    <line x1="0" y1="370" x2="1360" y2="370" stroke="#1e2a40" stroke-width="1"/>
                    <!-- Lane labels -->
                    <text x="93"   y="18" text-anchor="middle" font-size="8.5" fill="#4a5e80" font-family="JetBrains Mono,monospace" font-weight="700" letter-spacing="0.1em">TELEPHONY</text>
                    <text x="278"  y="18" text-anchor="middle" font-size="8.5" fill="#4a5e80" font-family="JetBrains Mono,monospace" font-weight="700" letter-spacing="0.1em">PRE AI / IVR</text>
                    <text x="463"  y="18" text-anchor="middle" font-size="8.5" fill="#4a5e80" font-family="JetBrains Mono,monospace" font-weight="700" letter-spacing="0.1em">DATA PIPELINE</text>
                    <text x="685"  y="18" text-anchor="middle" font-size="8.5" fill="#4a5e80" font-family="JetBrains Mono,monospace" font-weight="700" letter-spacing="0.1em">IN-CALL AI / COPILOT</text>
                    <text x="945"  y="18" text-anchor="middle" font-size="8.5" fill="#4a5e80" font-family="JetBrains Mono,monospace" font-weight="700" letter-spacing="0.1em">ACW</text>
                    <text x="1218" y="18" text-anchor="middle" font-size="8.5" fill="#4a5e80" font-family="JetBrains Mono,monospace" font-weight="700" letter-spacing="0.1em">DEEP ANALYSIS</text>

                    <!-- ===== TELEPHONY ===== -->
                    <circle cx="93" cy="72" r="16" fill="#0a0e16" stroke="#5a6e90" stroke-width="2.2"/>
                    <line x1="93" y1="88" x2="93" y2="112" stroke="#5a6e90" stroke-width="1.8" marker-end="url(#a1)"/>
                    <rect x="22" y="114" width="142" height="62" rx="8" fill="#060f1e" stroke="#1a3060" stroke-width="1.8"/>
                    <text x="93" y="140" text-anchor="middle" font-size="11" fill="#7aaeff" font-weight="700">Cisco &#x2192;</text>
                    <text x="93" y="155" text-anchor="middle" font-size="11" fill="#7aaeff" font-weight="700">real-time streaming</text>
                    <line x1="93" y1="176" x2="93" y2="300" stroke="#3a4a65" stroke-width="1.4" stroke-dasharray="7,5"/>
                    <line x1="93" y1="300" x2="278" y2="300" stroke="#3a4a65" stroke-width="1.4" stroke-dasharray="7,5" marker-end="url(#a5)"/>

                    <!-- ===== PRE AI / IVR ===== -->
                    <line x1="278" y1="300" x2="278" y2="208" stroke="#3a4a65" stroke-width="1.4" stroke-dasharray="7,5" marker-end="url(#a5)"/>
                    <polygon points="278,200 289,214 267,214" fill="#080b12" stroke="#3a4a65" stroke-width="1.5"/>
                    <rect x="206" y="114" width="144" height="82" rx="8" fill="#0d1f45" stroke="#4a8cff" stroke-width="2.2"/>
                    <text x="278" y="144" text-anchor="middle" font-size="11" fill="#7aaeff" font-weight="700">11labs / Google</text>
                    <text x="278" y="159" text-anchor="middle" font-size="11" fill="#7aaeff" font-weight="700">DialogflowCX</text>
                    <text x="278" y="178" text-anchor="middle" font-size="10" fill="#a0c0ff" font-weight="600">&#x2192; Intent</text>
                    <line x1="350" y1="148" x2="392" y2="148" stroke="#3a4a65" stroke-width="1.4" stroke-dasharray="7,5" marker-end="url(#a5)"/>

                    <!-- ===== DATA PIPELINE ===== -->
                    <rect x="393" y="114" width="148" height="68" rx="8" fill="#041408" stroke="#0d5030" stroke-width="1.8"/>
                    <text x="467" y="144" text-anchor="middle" font-size="11" fill="#50e8a0" font-weight="700">Ender Turing</text>
                    <text x="467" y="159" text-anchor="middle" font-size="11" fill="#50e8a0" font-weight="700">transcribes</text>
                    <text x="467" y="174" text-anchor="middle" font-size="10" fill="#30d890" font-weight="600">&#x2192; context</text>
                    <line x1="467" y1="182" x2="467" y2="300" stroke="#3a4a65" stroke-width="1.4" stroke-dasharray="7,5"/>
                    <line x1="467" y1="300" x2="625" y2="300" stroke="#3a4a65" stroke-width="1.4" stroke-dasharray="7,5" marker-end="url(#a5)"/>

                    <!-- ===== IN-CALL AI / COPILOT ===== -->
                    <!-- Ender Turing: top-right. Mapped from SVG: x=702,y=69,w=87,h=66 -->
                    <rect x="702" y="60" width="100" height="70" rx="8" fill="#041408" stroke="#0d5030" stroke-width="1.8"/>
                    <text x="752" y="88" text-anchor="middle" font-size="11" fill="#50e8a0" font-weight="700">Ender Turing</text>
                    <text x="752" y="103" text-anchor="middle" font-size="11" fill="#50e8a0" font-weight="700">transcribes</text>

                    <!-- Google Agent: left-center. Mapped from SVG: x=616,y=144,w=87,h=66 -->
                    <rect x="570" y="155" width="110" height="74" rx="8" fill="#0d1f45" stroke="#4a8cff" stroke-width="2.2"/>
                    <text x="625" y="180" text-anchor="middle" font-size="11" fill="#7aaeff" font-weight="700">Google Agent</text>
                    <text x="625" y="195" text-anchor="middle" font-size="11" fill="#7aaeff" font-weight="700">Assist &#x2192;</text>
                    <text x="625" y="210" text-anchor="middle" font-size="10" fill="#a0c0ff">NBA\RAG</text>

                    <!-- Consultation: bottom-left. Mapped from SVG: x=616,y=251,w=87,h=66 -->
                    <rect x="570" y="262" width="110" height="68" rx="8" fill="#0a0e18" stroke="#2a3a58" stroke-width="1.8"/>
                    <circle cx="596" cy="278" r="7" fill="none" stroke="#8ab0e0" stroke-width="1.4"/>
                    <path d="M587,292 Q596,286 605,292" fill="none" stroke="#8ab0e0" stroke-width="1.4"/>
                    <text x="648" y="282" text-anchor="middle" font-size="11" fill="#c0d8f0" font-weight="700">Consultation</text>

                    <!-- Flow_01k7vdu: ET left → left → down → GA top (M1230,3310 L1180,3310 L1180,3360) -->
                    <path d="M702,95 L670,95 L670,155" fill="none" stroke="#5a6e90" stroke-width="1.8" marker-end="url(#a1)"/>

                    <!-- Flow_1iyksw6: GA bottom → down → CO top (M1180,3440 L1180,3490) -->
                    <line x1="625" y1="229" x2="625" y2="262" stroke="#5a6e90" stroke-width="1.8" marker-end="url(#a1)"/>



                    <!-- ARROW 1: Consultation right → up → Ender Turing bottom -->
                    <path d="M680,296 L752,296 L752,130" fill="none" stroke="#5a6e90" stroke-width="1.8" marker-end="url(#a1)"/>
                    <!-- ARROW 2: Ender Turing right → right → down → Summary CRM left -->
                    <path d="M802,95 L840,95 L840,299 L870,299" fill="none" stroke="#5a6e90" stroke-width="1.8" marker-end="url(#a1)"/>
                    <!-- solid arrow: Summary CRM → Agents validation -->
                    <line x1="958" y1="260" x2="958" y2="116" stroke="#5a6e90" stroke-width="1.8" marker-end="url(#a1)"/>




                    <!-- ===== ACW ===== -->
                    <rect x="882" y="50" width="152" height="66" rx="8" fill="#0a0e18" stroke="#2a3a58" stroke-width="1.8"/>
                    <circle cx="908" cy="67" r="7" fill="none" stroke="#8ab0e0" stroke-width="1.4"/>
                    <path d="M899,81 Q908,75 917,81" fill="none" stroke="#8ab0e0" stroke-width="1.4"/>
                    <text x="958" y="76" text-anchor="middle" font-size="11" fill="#c0d8f0" font-weight="700">Agents</text>
                    <text x="958" y="91" text-anchor="middle" font-size="11" fill="#c0d8f0" font-weight="700">validation</text>

                    <!-- Summary CRM -->
                    <rect x="870" y="260" width="176" height="78" rx="8" fill="#041408" stroke="#0d5030" stroke-width="1.8"/>
                    <text x="958" y="285" text-anchor="middle" font-size="11" fill="#50e8a0" font-weight="700">Summary</text>
                    <text x="958" y="300" text-anchor="middle" font-size="11" fill="#50e8a0" font-weight="700">avtomation CRM</text>
                    <text x="958" y="315" text-anchor="middle" font-size="10" fill="#30d890" font-weight="600">EnderTuring</text>
                    <!-- dashed to Deep Analysis -->
                    <line x1="1034" y1="83" x2="1118" y2="83" stroke="#3a4a65" stroke-width="1.4" stroke-dasharray="7,5" marker-end="url(#a5)"/>

                    <!-- ===== DEEP ANALYSIS ===== -->
                    <line x1="1118" y1="83" x2="1188" y2="83" stroke="#3a4a65" stroke-width="1.4" stroke-dasharray="7,5"/>
                    <line x1="1188" y1="83" x2="1188" y2="112" stroke="#3a4a65" stroke-width="1.4" stroke-dasharray="7,5" marker-end="url(#a5)"/>
                    <rect x="1118" y="114" width="192" height="68" rx="8" fill="#041408" stroke="#0d5030" stroke-width="1.8"/>
                    <text x="1214" y="144" text-anchor="middle" font-size="11" fill="#50e8a0" font-weight="700">Ender Turing</text>
                    <text x="1214" y="159" text-anchor="middle" font-size="11" fill="#50e8a0" font-weight="700">Deep Analysis</text>
                    <line x1="1214" y1="182" x2="1214" y2="216" stroke="#5a6e90" stroke-width="1.8" marker-end="url(#a1)"/>
                    <circle cx="1214" cy="236" r="18" fill="#080b12" stroke="#5a6e90" stroke-width="3"/>
                    <circle cx="1214" cy="236" r="11" fill="#3a4a65"/>
                  </svg>
                </div>
            </div>
        </div>'''


def generate_asis_tab() -> str:
    """Generate HTML for the AS-IS BPMN tab."""
    return '''        <!-- ═══ AS-IS ═══ -->
    <div id="p-as" class="panel tab-content" data-content="asis">
      <div class="hero">
        <div>
          <h2 style="color:#ff7040">AS-IS &mdash; <span style="color:var(--text)">Поточний процес</span></h2>
          <p>6 учасників з BPMN: Клієнт · Cisco · EVA (Omilia) · Запис (MP3) · Оператор · Робоче місце</p>
        </div>
        <div class="chips">
          <div class="chip" style="border-color:#1a3060;color:#4a8cff">Cisco — телефонія</div>
          <div class="chip" style="border-color:#4a3000;color:#f0a030">EVA — Omilia IVR</div>
          <div class="chip" style="border-color:var(--warn-b);color:var(--warn)">Без AI</div>
          <div class="chip" style="border-color:var(--warn-b);color:var(--warn)">ACW вручну</div>
        </div>
      </div>
      <div class="diag-wrap"><svg width="100%" style="min-width:900px;display:block" viewBox="-4.0 -4.0 2888.0 1298.0" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg">
    <defs>
      <marker id="ah_s" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
        <path d="M0,0 L8,3 L0,6 Z" fill="#3a4a65"/>
      </marker>
      <marker id="ah_m" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
        <path d="M0,0 L8,3 L0,6 Z" fill="#2a5a8a"/>
      </marker>
      <marker id="ah_n" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
        <path d="M0,0 L8,3 L0,6 Z" fill="#0c4020"/>
      </marker>
    </defs>
    <rect x="0.0" y="0.0" width="2880.0" height="200.0" fill="#0d1320" stroke="#1a2540" stroke-width="0.8"/><rect x="0.0" y="0.0" width="30" height="200.0" fill="#0d1320" stroke="#1a2540" stroke-width="0.8"/><text transform="rotate(-90,15.0,100.0)" x="15.0" y="100.0" text-anchor="middle" dominant-baseline="middle" font-size="11.6" fill="#3a5888" font-family="JetBrains Mono,monospace" font-weight="600">Клієнт</text>
    <rect x="0.0" y="200.0" width="2880.0" height="140.0" fill="#060f1e" stroke="#1a2540" stroke-width="0.8"/><rect x="0.0" y="200.0" width="30" height="140.0" fill="#060f1e" stroke="#1a2540" stroke-width="0.8"/><text transform="rotate(-90,15.0,270.0)" x="15.0" y="270.0" text-anchor="middle" dominant-baseline="middle" font-size="11.6" fill="#3a7cee" font-family="JetBrains Mono,monospace" font-weight="600">Cisco</text>
    <rect x="0.0" y="340.0" width="2880.0" height="250.0" fill="#150d00" stroke="#1a2540" stroke-width="0.8"/><rect x="0.0" y="340.0" width="30" height="250.0" fill="#150d00" stroke="#1a2540" stroke-width="0.8"/><text transform="rotate(-90,15.0,465.0)" x="15.0" y="465.0" text-anchor="middle" dominant-baseline="middle" font-size="11.6" fill="#c08828" font-family="JetBrains Mono,monospace" font-weight="600">EVA</text>
    <rect x="0.0" y="590.0" width="2880.0" height="260.0" fill="#030c12" stroke="#1a2540" stroke-width="0.8"/><rect x="0.0" y="590.0" width="30" height="260.0" fill="#030c12" stroke="#1a2540" stroke-width="0.8"/><text transform="rotate(-90,15.0,720.0)" x="15.0" y="715.0" text-anchor="middle" dominant-baseline="middle" font-size="11.6" fill="#3090b8" font-family="JetBrains Mono,monospace" font-weight="600">Запис</text><text transform="rotate(-90,15.0,720.0)" x="15.0" y="725.0" text-anchor="middle" dominant-baseline="middle" font-size="11.6" fill="#3090b8" font-family="JetBrains Mono,monospace" font-weight="600">(MP3)</text>
    <rect x="0.0" y="850.0" width="2880.0" height="210.0" fill="#0e0618" stroke="#1a2540" stroke-width="0.8"/><rect x="0.0" y="850.0" width="30" height="210.0" fill="#0e0618" stroke="#1a2540" stroke-width="0.8"/><text transform="rotate(-90,15.0,955.0)" x="15.0" y="955.0" text-anchor="middle" dominant-baseline="middle" font-size="11.6" fill="#8860d0" font-family="JetBrains Mono,monospace" font-weight="600">Оператор</text>
    <rect x="0.0" y="1060.0" width="2880.0" height="230.0" fill="#0a0618" stroke="#1a2540" stroke-width="0.8"/><rect x="0.0" y="1060.0" width="30" height="230.0" fill="#0a0618" stroke="#1a2540" stroke-width="0.8"/><text transform="rotate(-90,15.0,1175.0)" x="15.0" y="1170.0" text-anchor="middle" dominant-baseline="middle" font-size="11.6" fill="#7048c0" font-family="JetBrains Mono,monospace" font-weight="600">Робоче</text><text transform="rotate(-90,15.0,1175.0)" x="15.0" y="1180.0" text-anchor="middle" dominant-baseline="middle" font-size="11.6" fill="#7048c0" font-family="JetBrains Mono,monospace" font-weight="600">місце</text>
    <path d="M88.0,120.0 L140.0,120.0" fill="none" stroke="#3a4a65" stroke-width="1.3" marker-end="url(#ah_s)"/>
    <path d="M850.0,270.0 L960.0,270.0" fill="none" stroke="#3a4a65" stroke-width="1.3" marker-end="url(#ah_s)"/>
    <path d="M390.0,520.0 L525.0,520.0" fill="none" stroke="#3a4a65" stroke-width="1.3" marker-end="url(#ah_s)"/>
    <path d="M575.0,520.0 L750.0,520.0" fill="none" stroke="#3a4a65" stroke-width="1.3" marker-end="url(#ah_s)"/><text x="665.5" y="509.0" font-size="13.0" fill="#c8a030" font-family="JetBrains Mono,monospace" font-weight="600" text-anchor="middle">Ні</text>
    <path d="M550.0,495.0 L550.0,440.0" fill="none" stroke="#3a4a65" stroke-width="1.3" marker-end="url(#ah_s)"/><text x="565.0" y="472.0" font-size="13.0" fill="#c8a030" font-family="JetBrains Mono,monospace" font-weight="600" text-anchor="middle">Так</text>
    <path d="M2080.0,670.0 L2145.0,670.0" fill="none" stroke="#3a4a65" stroke-width="1.3" marker-end="url(#ah_s)"/>
    <path d="M2195.0,670.0 L2420.0,670.0" fill="none" stroke="#3a4a65" stroke-width="1.3" marker-end="url(#ah_s)"/><text x="2320.0" y="660.0" font-size="13.0" fill="#c8a030" font-family="JetBrains Mono,monospace" font-weight="600" text-anchor="middle">EVA</text>
    <path d="M2170.0,695.0 L2170.0,750.0" fill="none" stroke="#3a4a65" stroke-width="1.3" marker-end="url(#ah_s)"/><text x="2210.0" y="720.0" font-size="13.0" fill="#c8a030" font-family="JetBrains Mono,monospace" font-weight="600" text-anchor="middle">Оператор</text>
    <path d="M2520.0,670.0 L2632.0,670.0" fill="none" stroke="#3a4a65" stroke-width="1.3" marker-end="url(#ah_s)"/>
    <path d="M1740.0,985.0 L1740.0,1040.0 L1540.0,1040.0 L1540.0,1000.0" fill="none" stroke="#3a4a65" stroke-width="1.3" marker-end="url(#ah_s)"/><text x="1641.5" y="1029.0" font-size="13.0" fill="#c8a030" font-family="JetBrains Mono,monospace" font-weight="600" text-anchor="middle">Ні</text>
    <path d="M1400.0,960.0 L1490.0,960.0" fill="none" stroke="#3a4a65" stroke-width="1.3" marker-end="url(#ah_s)"/>
    <path d="M1590.0,960.0 L1715.0,960.0" fill="none" stroke="#3a4a65" stroke-width="1.3" marker-end="url(#ah_s)"/>
    <path d="M1765.0,960.0 L1870.0,960.0" fill="none" stroke="#3a4a65" stroke-width="1.3" marker-end="url(#ah_s)"/><text x="1818.0" y="949.0" font-size="13.0" fill="#c8a030" font-family="JetBrains Mono,monospace" font-weight="600" text-anchor="middle">Так</text>
    <path d="M2360.0,960.0 L2420.0,960.0" fill="none" stroke="#3a4a65" stroke-width="1.3" marker-end="url(#ah_s)"/>
    <path d="M2520.0,960.0 L2600.0,960.0" fill="none" stroke="#3a4a65" stroke-width="1.3" marker-end="url(#ah_s)"/>
    <path d="M2700.0,1190.0 L2792.0,1190.0" fill="none" stroke="#3a4a65" stroke-width="1.3" marker-end="url(#ah_s)"/>
    <path d="M190.0,160.0 L190.0,230.0" fill="none" stroke="#2a5a8a" stroke-width="1.3" stroke-dasharray="6,3" marker-end="url(#ah_m)"/>
    <path d="M1920.0,920.0 L1920.0,160.0" fill="none" stroke="#2a5a8a" stroke-width="1.3" stroke-dasharray="6,3" marker-end="url(#ah_m)"/>
    <path d="M1970.0,120.0 L2030.0,120.0 L2030.0,630.0" fill="none" stroke="#2a5a8a" stroke-width="1.3" stroke-dasharray="6,3" marker-end="url(#ah_m)"/>
    <path d="M190.0,310.0 L190.0,630.0" fill="none" stroke="#2a5a8a" stroke-width="1.3" stroke-dasharray="6,3" marker-end="url(#ah_m)"/>
    <path d="M1060.0,270.0 L1150.0,270.0 L1150.0,920.0" fill="none" stroke="#2a5a8a" stroke-width="1.3" stroke-dasharray="6,3" marker-end="url(#ah_m)"/>
    <path d="M1350.0,1160.0 L1350.0,1000.0" fill="none" stroke="#2a5a8a" stroke-width="1.3" stroke-dasharray="6,3" marker-end="url(#ah_m)"/>
    <path d="M1350.0,1000.0 L1350.0,1160.0" fill="none" stroke="#2a5a8a" stroke-width="1.3" stroke-dasharray="6,3" marker-end="url(#ah_m)"/>
    <path d="M1190.0,920.0 L1190.0,160.0" fill="none" stroke="#2a5a8a" stroke-width="1.3" stroke-dasharray="6,3" marker-end="url(#ah_m)"/>
    <path d="M1240.0,120.0 L1350.0,120.0 L1350.0,920.0" fill="none" stroke="#2a5a8a" stroke-width="1.3" stroke-dasharray="6,3" marker-end="url(#ah_m)"/>
    <path d="M2650.0,1000.0 L2650.0,1150.0" fill="none" stroke="#2a5a8a" stroke-width="1.3" stroke-dasharray="6,3" marker-end="url(#ah_m)"/>
    <path d="M190.0,310.0 L190.0,520.0 L290.0,520.0" fill="none" stroke="#2a5a8a" stroke-width="1.3" stroke-dasharray="6,3" marker-end="url(#ah_m)"/>
    <path d="M800.0,480.0 L800.0,310.0" fill="none" stroke="#2a5a8a" stroke-width="1.3" stroke-dasharray="6,3" marker-end="url(#ah_m)"/>
    <path d="M550.0,360.0 L550.0,40.0 L1920.0,40.0 L1920.0,80.0" fill="none" stroke="#2a5a8a" stroke-width="1.3" stroke-dasharray="6,3" marker-end="url(#ah_m)"/>
    <path d="M2170.0,830.0 L2170.0,1150.0" fill="none" stroke="#2a5a8a" stroke-width="1.3" stroke-dasharray="6,3" marker-end="url(#ah_m)"/>
    <path d="M2220.0,1190.0 L2310.0,1190.0 L2310.0,1000.0" fill="none" stroke="#2a5a8a" stroke-width="1.3" stroke-dasharray="6,3" marker-end="url(#ah_m)"/>
    <circle cx="70.0" cy="120.0" r="18.0" fill="#0b0e14" stroke="#3a4a65" stroke-width="1.5"/>
    <rect x="140.0" y="80.0" width="100.0" height="80.0" rx="4" fill="#0a0e18" stroke="#252e45" stroke-width="1.3"/><text x="190.0" y="118.0" text-anchor="middle" font-size="12.3" fill="#dde6f5" font-family="Mulish,sans-serif" font-weight="700">Здійснює</text><text x="190.0" y="129.0" text-anchor="middle" font-size="12.3" fill="#dde6f5" font-family="Mulish,sans-serif" font-weight="700">дзвінок</text>
    <rect x="1140.0" y="80.0" width="100.0" height="80.0" rx="4" fill="#0a0e18" stroke="#252e45" stroke-width="1.3"/><text x="1190.0" y="123.5" text-anchor="middle" font-size="12.3" fill="#dde6f5" font-family="Mulish,sans-serif" font-weight="700">Описує запит</text>
    <rect x="1870.0" y="80.0" width="100.0" height="80.0" rx="4" fill="#0a0e18" stroke="#252e45" stroke-width="1.3"/><text x="1920.0" y="118.0" text-anchor="middle" font-size="12.3" fill="#dde6f5" font-family="Mulish,sans-serif" font-weight="700">Завершує</text><text x="1920.0" y="129.0" text-anchor="middle" font-size="12.3" fill="#dde6f5" font-family="Mulish,sans-serif" font-weight="700">дзвінок</text>
    <rect x="140.0" y="230.0" width="100.0" height="80.0" rx="4" fill="#060f1e" stroke="#1a3060" stroke-width="1.3"/><text x="190.0" y="268.0" text-anchor="middle" font-size="12.3" fill="#7aaeff" font-family="Mulish,sans-serif" font-weight="700">Маршрутизує</text><text x="190.0" y="279.0" text-anchor="middle" font-size="12.3" fill="#7aaeff" font-family="Mulish,sans-serif" font-weight="700">дзвінок</text>
    <rect x="750.0" y="230.0" width="100.0" height="80.0" rx="4" fill="#060f1e" stroke="#1a3060" stroke-width="1.3"/><text x="800.0" y="268.0" text-anchor="middle" font-size="12.3" fill="#7aaeff" font-family="Mulish,sans-serif" font-weight="700">Очікування в</text><text x="800.0" y="279.0" text-anchor="middle" font-size="12.3" fill="#7aaeff" font-family="Mulish,sans-serif" font-weight="700">черзі</text>
    <rect x="960.0" y="230.0" width="100.0" height="80.0" rx="4" fill="#0a0e18" stroke="#252e45" stroke-width="1.3"/><text x="1010.0" y="268.0" text-anchor="middle" font-size="12.3" fill="#dde6f5" font-family="Mulish,sans-serif" font-weight="700">Переадресація</text><text x="1010.0" y="279.0" text-anchor="middle" font-size="12.3" fill="#dde6f5" font-family="Mulish,sans-serif" font-weight="700">на оператора</text>
    <rect x="290.0" y="480.0" width="100.0" height="80.0" rx="4" fill="#0a0e18" stroke="#252e45" stroke-width="1.3"/><text x="340.0" y="518.0" text-anchor="middle" font-size="12.3" fill="#dde6f5" font-family="Mulish,sans-serif" font-weight="700">Первинна</text><text x="340.0" y="529.0" text-anchor="middle" font-size="12.3" fill="#dde6f5" font-family="Mulish,sans-serif" font-weight="700">консультація</text>
    <polygon points="550.0,495.0 575.0,520.0 550.0,545.0 525.0,520.0" fill="#12100a" stroke="#6a5010" stroke-width="1.5"/><line x1="544.0" y1="514.0" x2="556.0" y2="526.0" stroke="#c8a030" stroke-width="1.2"/><line x1="556.0" y1="514.0" x2="544.0" y2="526.0" stroke="#c8a030" stroke-width="1.2"/><text x="550.0" y="555.0" text-anchor="middle" font-size="10.9" fill="#c8a030" font-family="JetBrains Mono,monospace" font-weight="600">Чи вирішено</text><text x="550.0" y="565.0" text-anchor="middle" font-size="10.9" fill="#c8a030" font-family="JetBrains Mono,monospace" font-weight="600">запит клієнта?</text>
    <rect x="500.0" y="360.0" width="100.0" height="80.0" rx="4" fill="#060f1e" stroke="#1a3060" stroke-width="1.3"/><text x="550.0" y="398.0" text-anchor="middle" font-size="12.3" fill="#7aaeff" font-family="Mulish,sans-serif" font-weight="700">Очікування</text><text x="550.0" y="409.0" text-anchor="middle" font-size="12.3" fill="#7aaeff" font-family="Mulish,sans-serif" font-weight="700">інших питань</text>
    <rect x="750.0" y="480.0" width="100.0" height="80.0" rx="4" fill="#060f1e" stroke="#1a3060" stroke-width="1.3"/><text x="800.0" y="518.0" text-anchor="middle" font-size="12.3" fill="#7aaeff" font-family="Mulish,sans-serif" font-weight="700">Передати запит</text><text x="800.0" y="529.0" text-anchor="middle" font-size="12.3" fill="#7aaeff" font-family="Mulish,sans-serif" font-weight="700">оператору</text>
    <rect x="140.0" y="630.0" width="100.0" height="80.0" rx="4" fill="#060f1e" stroke="#1a3060" stroke-width="1.3"/><text x="190.0" y="668.0" text-anchor="middle" font-size="12.3" fill="#7aaeff" font-family="Mulish,sans-serif" font-weight="700">Початок запису</text><text x="190.0" y="679.0" text-anchor="middle" font-size="12.3" fill="#7aaeff" font-family="Mulish,sans-serif" font-weight="700">розмови</text>
    <rect x="1980.0" y="630.0" width="100.0" height="80.0" rx="4" fill="#060f1e" stroke="#1a3060" stroke-width="1.3"/><text x="2030.0" y="668.0" text-anchor="middle" font-size="12.3" fill="#7aaeff" font-family="Mulish,sans-serif" font-weight="700">Завершення</text><text x="2030.0" y="679.0" text-anchor="middle" font-size="12.3" fill="#7aaeff" font-family="Mulish,sans-serif" font-weight="700">запису розмови</text>
    <polygon points="2170.0,645.0 2195.0,670.0 2170.0,695.0 2145.0,670.0" fill="#12100a" stroke="#6a5010" stroke-width="1.5"/><line x1="2164.0" y1="664.0" x2="2176.0" y2="676.0" stroke="#c8a030" stroke-width="1.2"/><line x1="2176.0" y1="664.0" x2="2164.0" y2="676.0" stroke="#c8a030" stroke-width="1.2"/><text x="2170.0" y="608.0" text-anchor="middle" font-size="10.9" fill="#c8a030" font-family="JetBrains Mono,monospace" font-weight="600">Визначення</text><text x="2170.0" y="620.0" text-anchor="middle" font-size="10.9" fill="#c8a030" font-family="JetBrains Mono,monospace" font-weight="600">каналу</text><text x="2170.0" y="632.0" text-anchor="middle" font-size="10.9" fill="#c8a030" font-family="JetBrains Mono,monospace" font-weight="600">консультації</text>
    <rect x="2120.0" y="750.0" width="100.0" height="80.0" rx="4" fill="#060f1e" stroke="#1a3060" stroke-width="1.3"/><text x="2170.0" y="788.0" text-anchor="middle" font-size="12.3" fill="#7aaeff" font-family="Mulish,sans-serif" font-weight="700">Фіксація запиту</text><text x="2170.0" y="799.0" text-anchor="middle" font-size="12.3" fill="#7aaeff" font-family="Mulish,sans-serif" font-weight="700">оператором</text>
    <rect x="2420.0" y="630.0" width="100.0" height="80.0" rx="4" fill="#060f1e" stroke="#1a3060" stroke-width="1.3"/><text x="2470.0" y="668.0" text-anchor="middle" font-size="12.3" fill="#7aaeff" font-family="Mulish,sans-serif" font-weight="700">Збереження</text><text x="2470.0" y="679.0" text-anchor="middle" font-size="12.3" fill="#7aaeff" font-family="Mulish,sans-serif" font-weight="700">запису розмови</text>
    <circle cx="2650.0" cy="670.0" r="18.0" fill="#0b0e14" stroke="#3a4a65" stroke-width="3"/><circle cx="2650.0" cy="670.0" r="14.0" fill="#3a4a65"/>
    <rect x="1120.0" y="920.0" width="100.0" height="80.0" rx="4" fill="#1a0800" stroke="#8a3000" stroke-width="1.3"/><text x="1170.0" y="952.5" text-anchor="middle" font-size="12.3" fill="#ff9878" font-family="Mulish,sans-serif" font-weight="700">Приймає</text><text x="1170.0" y="963.5" text-anchor="middle" font-size="12.3" fill="#ff9878" font-family="Mulish,sans-serif" font-weight="700">дзвінок,</text><text x="1170.0" y="974.5" text-anchor="middle" font-size="12.3" fill="#ff9878" font-family="Mulish,sans-serif" font-weight="700">починає розмову</text><rect x="1124.0" y="924.0" width="34" height="8" rx="2" fill="#501800"/><text x="1141.0" y="931.0" text-anchor="middle" font-size="8.0" fill="#ff6030" font-family="JetBrains Mono,monospace" font-weight="700">MANUAL</text>
    <rect x="1300.0" y="920.0" width="100.0" height="80.0" rx="4" fill="#1a0800" stroke="#8a3000" stroke-width="1.3"/><text x="1350.0" y="947.0" text-anchor="middle" font-size="12.3" fill="#ff9878" font-family="Mulish,sans-serif" font-weight="700">Аналіз</text><text x="1350.0" y="958.0" text-anchor="middle" font-size="12.3" fill="#ff9878" font-family="Mulish,sans-serif" font-weight="700">запитань, пошук</text><text x="1350.0" y="969.0" text-anchor="middle" font-size="12.3" fill="#ff9878" font-family="Mulish,sans-serif" font-weight="700">у базі знань,</text><text x="1350.0" y="980.0" text-anchor="middle" font-size="12.3" fill="#ff9878" font-family="Mulish,sans-serif" font-weight="700">накладної</text><rect x="1304.0" y="924.0" width="34" height="8" rx="2" fill="#501800"/><text x="1321.0" y="931.0" text-anchor="middle" font-size="8.0" fill="#ff6030" font-family="JetBrains Mono,monospace" font-weight="700">MANUAL</text>
    <rect x="1490.0" y="920.0" width="100.0" height="80.0" rx="4" fill="#1a0800" stroke="#8a3000" stroke-width="1.3"/><text x="1540.0" y="958.0" text-anchor="middle" font-size="12.3" fill="#ff9878" font-family="Mulish,sans-serif" font-weight="700">Консультує та</text><text x="1540.0" y="969.0" text-anchor="middle" font-size="12.3" fill="#ff9878" font-family="Mulish,sans-serif" font-weight="700">шукає рішення</text><rect x="1494.0" y="924.0" width="34" height="8" rx="2" fill="#501800"/><text x="1511.0" y="931.0" text-anchor="middle" font-size="8.0" fill="#ff6030" font-family="JetBrains Mono,monospace" font-weight="700">MANUAL</text>
    <polygon points="1740.0,935.0 1765.0,960.0 1740.0,985.0 1715.0,960.0" fill="#12100a" stroke="#6a5010" stroke-width="1.5"/><line x1="1734.0" y1="954.0" x2="1746.0" y2="966.0" stroke="#c8a030" stroke-width="1.2"/><line x1="1746.0" y1="954.0" x2="1734.0" y2="966.0" stroke="#c8a030" stroke-width="1.2"/><text x="1740.0" y="900.0" text-anchor="middle" font-size="10.9" fill="#c8a030" font-family="JetBrains Mono,monospace" font-weight="600">Клієнт</text><text x="1740.0" y="912.0" text-anchor="middle" font-size="10.9" fill="#c8a030" font-family="JetBrains Mono,monospace" font-weight="600">задоволений</text><text x="1740.0" y="924.0" text-anchor="middle" font-size="10.9" fill="#c8a030" font-family="JetBrains Mono,monospace" font-weight="600">відповіддю?</text>
    <rect x="1870.0" y="920.0" width="100.0" height="80.0" rx="4" fill="#1a0800" stroke="#8a3000" stroke-width="1.3"/><text x="1920.0" y="947.0" text-anchor="middle" font-size="12.3" fill="#ff9878" font-family="Mulish,sans-serif" font-weight="700">Очікування</text><text x="1920.0" y="958.0" text-anchor="middle" font-size="12.3" fill="#ff9878" font-family="Mulish,sans-serif" font-weight="700">інших питань чи</text><text x="1920.0" y="969.0" text-anchor="middle" font-size="12.3" fill="#ff9878" font-family="Mulish,sans-serif" font-weight="700">завершення</text><text x="1920.0" y="980.0" text-anchor="middle" font-size="12.3" fill="#ff9878" font-family="Mulish,sans-serif" font-weight="700">дзвінка</text><rect x="1874.0" y="924.0" width="34" height="8" rx="2" fill="#501800"/><text x="1891.0" y="931.0" text-anchor="middle" font-size="8.0" fill="#ff6030" font-family="JetBrains Mono,monospace" font-weight="700">MANUAL</text>
    <rect x="2260.0" y="920.0" width="100.0" height="80.0" rx="4" fill="#1a0800" stroke="#8a3000" stroke-width="1.3"/><text x="2310.0" y="947.0" text-anchor="middle" font-size="12.3" fill="#ff9878" font-family="Mulish,sans-serif" font-weight="700">Заповнення</text><text x="2310.0" y="958.0" text-anchor="middle" font-size="12.3" fill="#ff9878" font-family="Mulish,sans-serif" font-weight="700">резюме, запиту</text><text x="2310.0" y="969.0" text-anchor="middle" font-size="12.3" fill="#ff9878" font-family="Mulish,sans-serif" font-weight="700">на інші відділи</text><text x="2310.0" y="980.0" text-anchor="middle" font-size="12.3" fill="#ff9878" font-family="Mulish,sans-serif" font-weight="700">(опціонально)</text><rect x="2264.0" y="924.0" width="34" height="8" rx="2" fill="#501800"/><text x="2281.0" y="931.0" text-anchor="middle" font-size="8.0" fill="#ff6030" font-family="JetBrains Mono,monospace" font-weight="700">MANUAL</text>
    <rect x="2420.0" y="920.0" width="100.0" height="80.0" rx="4" fill="#1a0800" stroke="#8a3000" stroke-width="1.3"/><text x="2470.0" y="952.5" text-anchor="middle" font-size="12.3" fill="#ff9878" font-family="Mulish,sans-serif" font-weight="700">Заповнення</text><text x="2470.0" y="963.5" text-anchor="middle" font-size="12.3" fill="#ff9878" font-family="Mulish,sans-serif" font-weight="700">тематик, тегів,</text><text x="2470.0" y="974.5" text-anchor="middle" font-size="12.3" fill="#ff9878" font-family="Mulish,sans-serif" font-weight="700">тону дзвінка</text><rect x="2424.0" y="924.0" width="34" height="8" rx="2" fill="#501800"/><text x="2441.0" y="931.0" text-anchor="middle" font-size="8.0" fill="#ff6030" font-family="JetBrains Mono,monospace" font-weight="700">MANUAL</text>
    <rect x="2600.0" y="920.0" width="100.0" height="80.0" rx="4" fill="#1a0800" stroke="#8a3000" stroke-width="1.3"/><text x="2650.0" y="958.0" text-anchor="middle" font-size="12.3" fill="#ff9878" font-family="Mulish,sans-serif" font-weight="700">Тегування та</text><text x="2650.0" y="969.0" text-anchor="middle" font-size="12.3" fill="#ff9878" font-family="Mulish,sans-serif" font-weight="700">маркування</text><rect x="2604.0" y="924.0" width="34" height="8" rx="2" fill="#501800"/><text x="2621.0" y="931.0" text-anchor="middle" font-size="8.0" fill="#ff6030" font-family="JetBrains Mono,monospace" font-weight="700">MANUAL</text>
    <rect x="1300.0" y="1160.0" width="100.0" height="80.0" rx="4" fill="#1a0800" stroke="#8a3000" stroke-width="1.3"/><rect x="1304.0" y="1164.0" width="34" height="8" rx="2" fill="#501800"/><text x="1321.0" y="1171.0" text-anchor="middle" font-size="8.0" fill="#ff6030" font-family="JetBrains Mono,monospace" font-weight="700">MANUAL</text><text x="1350.0" y="1198.0" text-anchor="middle" font-size="12.3" fill="#ff9878" font-family="Mulish,sans-serif" font-weight="700">Аналіз історії</text><text x="1350.0" y="1209.0" text-anchor="middle" font-size="12.3" fill="#ff9878" font-family="Mulish,sans-serif" font-weight="700">клієнта</text>
    <rect x="2120.0" y="1150.0" width="100.0" height="80.0" rx="4" fill="#1a0800" stroke="#8a3000" stroke-width="1.3"/><text x="2170.0" y="1182.5" text-anchor="middle" font-size="12.3" fill="#ff9878" font-family="Mulish,sans-serif" font-weight="700">Створення нової</text><text x="2170.0" y="1193.5" text-anchor="middle" font-size="12.3" fill="#ff9878" font-family="Mulish,sans-serif" font-weight="700">картки</text><text x="2170.0" y="1204.5" text-anchor="middle" font-size="12.3" fill="#ff9878" font-family="Mulish,sans-serif" font-weight="700">звернення</text><rect x="2124.0" y="1154.0" width="34" height="8" rx="2" fill="#501800"/><text x="2141.0" y="1161.0" text-anchor="middle" font-size="8.0" fill="#ff6030" font-family="JetBrains Mono,monospace" font-weight="700">MANUAL</text>
    <rect x="2600.0" y="1150.0" width="100.0" height="80.0" rx="4" fill="#1a0800" stroke="#8a3000" stroke-width="1.3"/><rect x="2604.0" y="1154.0" width="34" height="8" rx="2" fill="#501800"/><text x="2621.0" y="1161.0" text-anchor="middle" font-size="8.0" fill="#ff6030" font-family="JetBrains Mono,monospace" font-weight="700">MANUAL</text><text x="2650.0" y="1193.5" text-anchor="middle" font-size="12.3" fill="#ff9878" font-family="Mulish,sans-serif" font-weight="700">Закриття картки</text>
    <circle cx="2810.0" cy="1190.0" r="18.0" fill="#0b0e14" stroke="#3a4a65" stroke-width="3"/><circle cx="2810.0" cy="1190.0" r="14.0" fill="#3a4a65"/>
    </svg></div>
      <div class="sl" style="padding-top:24px">Проблеми AS-IS</div>
      <div class="pg">
        <div class="pgc w"><div class="pgc-t">Контекст губиться при ескалації</div><div class="pgc-d">EVA [Передати запит] → Cisco [Черга] → Оператор отримує дзвінок без жодного контексту.</div></div>
        <div class="pgc w"><div class="pgc-t">Оператор шукає вручну</div><div class="pgc-d">Аналіз запитань + пошук у БЗ та накладній — повністю ручний процес під час розмови.</div></div>
        <div class="pgc w"><div class="pgc-t">ACW — 3 ручних кроки</div><div class="pgc-d">Заповнення резюме → Теги + тон → Маркування. Все вручну, 3–7 хвилин на дзвінок.</div></div>
        <div class="pgc w"><div class="pgc-t">Запис не аналізується</div><div class="pgc-d">MP3 зберігається або фіксується вручну. QA — вибіркова, ручна, повільна.</div></div>
        <div class="pgc w"><div class="pgc-t">Черга без обробки</div><div class="pgc-d">Якщо оператор зайнятий — клієнт просто чекає. Немає автоматичної обробки.</div></div>
        <div class="pgc w"><div class="pgc-t">Нульова аналітика</div><div class="pgc-d">Немає BI, топ-причин звернень, тональності, compliance.</div></div>
      </div>
    </div>'''


def generate_tobe_tab() -> str:
    """Generate HTML for the TO-BE BPMN tab."""
    return '''        <!-- ═══ TO-BE ═══ -->
    <div id="p-to" class="panel tab-content" data-content="tobe">
      <div class="hero">
        <div>
          <h2 style="color:#30d890">TO-BE &mdash; <span style="color:var(--text)">Процес з AI Асистентом</span></h2>
          <p>6 учасників: Клієнт · Cisco (нова гілка) · Запис (MP3) · AI Асистент (4 транзакції) · Оператор · Робоче місце</p>
        </div>
        <div class="chips">
          <div class="chip" style="border-color:#0d4028;color:#30d890">Pre-AI: RAG + ЕН</div>
          <div class="chip" style="border-color:#0d4028;color:#30d890">Real-time Copilot</div>
          <div class="chip" style="border-color:#0d4028;color:#30d890">Post-call &le;1хв</div>
          <div class="chip" style="border-color:#0d4028;color:#30d890">Deep Analysis &le;10хв</div>
        </div>
      </div>
      <div class="diag-wrap"><svg width="100%" style="min-width:900px;display:block" viewBox="-4.0 -4.0 3148.0 1268.0" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg">
    <defs>
      <marker id="ah_s" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
        <path d="M0,0 L8,3 L0,6 Z" fill="#3a4a65"/>
      </marker>
      <marker id="ah_m" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
        <path d="M0,0 L8,3 L0,6 Z" fill="#2a5a8a"/>
      </marker>
      <marker id="ah_n" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
        <path d="M0,0 L8,3 L0,6 Z" fill="#0c4020"/>
      </marker>
    </defs>
    <rect x="0.0" y="0.0" width="3140.0" height="160.0" fill="#0d1320" stroke="#1a2540" stroke-width="0.8"/><rect x="0.0" y="0.0" width="30" height="160.0" fill="#0d1320" stroke="#1a2540" stroke-width="0.8"/><text transform="rotate(-90,15.0,80.0)" x="15.0" y="80.0" text-anchor="middle" dominant-baseline="middle" font-size="11.6" fill="#3a5888" font-family="JetBrains Mono,monospace" font-weight="600">Клієнт</text>
    <rect x="0.0" y="160.0" width="3140.0" height="230.0" fill="#060f1e" stroke="#1a2540" stroke-width="0.8"/><rect x="0.0" y="160.0" width="30" height="230.0" fill="#060f1e" stroke="#1a2540" stroke-width="0.8"/><text transform="rotate(-90,15.0,275.0)" x="15.0" y="275.0" text-anchor="middle" dominant-baseline="middle" font-size="11.6" fill="#3a7cee" font-family="JetBrains Mono,monospace" font-weight="600">Cisco</text>
    <rect x="0.0" y="390.0" width="3140.0" height="160.0" fill="#030c12" stroke="#1a2540" stroke-width="0.8"/><rect x="0.0" y="390.0" width="30" height="160.0" fill="#030c12" stroke="#1a2540" stroke-width="0.8"/><text transform="rotate(-90,15.0,470.0)" x="15.0" y="465.0" text-anchor="middle" dominant-baseline="middle" font-size="11.6" fill="#3090b8" font-family="JetBrains Mono,monospace" font-weight="600">Запис</text><text transform="rotate(-90,15.0,470.0)" x="15.0" y="475.0" text-anchor="middle" dominant-baseline="middle" font-size="11.6" fill="#3090b8" font-family="JetBrains Mono,monospace" font-weight="600">(MP3)</text>
    <rect x="0.0" y="550.0" width="3140.0" height="350.0" fill="#030f08" stroke="#1a2540" stroke-width="0.8"/><rect x="0.0" y="550.0" width="30" height="350.0" fill="#030f08" stroke="#1a2540" stroke-width="0.8"/><text transform="rotate(-90,15.0,725.0)" x="15.0" y="720.0" text-anchor="middle" dominant-baseline="middle" font-size="11.6" fill="#30d890" font-family="JetBrains Mono,monospace" font-weight="600">AI</text><text transform="rotate(-90,15.0,725.0)" x="15.0" y="730.0" text-anchor="middle" dominant-baseline="middle" font-size="11.6" fill="#30d890" font-family="JetBrains Mono,monospace" font-weight="600">Асистент</text>
    <rect x="0.0" y="900.0" width="3140.0" height="210.0" fill="#0e0618" stroke="#1a2540" stroke-width="0.8"/><rect x="0.0" y="900.0" width="30" height="210.0" fill="#0e0618" stroke="#1a2540" stroke-width="0.8"/><text transform="rotate(-90,15.0,1005.0)" x="15.0" y="1005.0" text-anchor="middle" dominant-baseline="middle" font-size="11.6" fill="#8860d0" font-family="JetBrains Mono,monospace" font-weight="600">Оператор</text>
    <rect x="0.0" y="1110.0" width="3140.0" height="150.0" fill="#0a0618" stroke="#1a2540" stroke-width="0.8"/><rect x="0.0" y="1110.0" width="30" height="150.0" fill="#0a0618" stroke="#1a2540" stroke-width="0.8"/><text transform="rotate(-90,15.0,1185.0)" x="15.0" y="1185.0" text-anchor="middle" dominant-baseline="middle" font-size="11.6" fill="#a888e8" font-family="JetBrains Mono,monospace" font-weight="600">CRM</text>
    <rect x="440.0" y="570.0" width="830.0" height="310.0" rx="6" fill="#020a04" stroke="#0c3820" stroke-width="1.5" stroke-dasharray="6,3"/>
    <text x="855.0" y="582.0" text-anchor="middle" font-size="11.6" fill="#30d890" font-family="JetBrains Mono,monospace" font-weight="600" opacity="0.8">Pre AI Assistant</text>
    <rect x="1410.0" y="570.0" width="330.0" height="310.0" rx="6" fill="#020a04" stroke="#0c3820" stroke-width="1.5" stroke-dasharray="6,3"/>
    <text x="1575.0" y="582.0" text-anchor="middle" font-size="11.6" fill="#30d890" font-family="JetBrains Mono,monospace" font-weight="600" opacity="0.8">Real-time AI</text>
    <text x="1575.0" y="593.0" text-anchor="middle" font-size="11.6" fill="#30d890" font-family="JetBrains Mono,monospace" font-weight="600" opacity="0.8">Copilot</text>
    <rect x="1990.0" y="570.0" width="480.0" height="310.0" rx="6" fill="#020a04" stroke="#0c3820" stroke-width="1.5" stroke-dasharray="6,3"/>
    <text x="2230.0" y="582.0" text-anchor="middle" font-size="11.6" fill="#30d890" font-family="JetBrains Mono,monospace" font-weight="600" opacity="0.8">Post-call AI (≤1m)</text>
    <rect x="2540.0" y="570.0" width="580.0" height="310.0" rx="6" fill="#020a04" stroke="#0c3820" stroke-width="1.5" stroke-dasharray="6,3"/>
    <text x="2830.0" y="582.0" text-anchor="middle" font-size="11.6" fill="#30d890" font-family="JetBrains Mono,monospace" font-weight="600" opacity="0.8">Deep Analysis</text>
    <text x="2830.0" y="593.0" text-anchor="middle" font-size="11.6" fill="#30d890" font-family="JetBrains Mono,monospace" font-weight="600" opacity="0.8">(≤10m)</text>
    <path d="M88.0,80.0 L140.0,80.0" fill="none" stroke="#3a4a65" stroke-width="1.3" marker-end="url(#ah_s)"/>
    <path d="M210.0,280.0 L210.0,310.0 L285.0,310.0" fill="none" stroke="#3a4a65" stroke-width="1.3" marker-end="url(#ah_s)"/>
    <path d="M335.0,310.0 L920.0,310.0" fill="none" stroke="#3a4a65" stroke-width="1.3" marker-end="url(#ah_s)"/><text x="390.0" y="299.0" font-size="13.0" fill="#c8a030" font-family="JetBrains Mono,monospace" font-weight="600" text-anchor="middle">Так</text>
    <path d="M310.0,285.0 L310.0,230.0 L420.0,230.0" fill="none" stroke="#3a4a65" stroke-width="1.3" marker-end="url(#ah_s)"/><text x="389.5" y="219.0" font-size="13.0" fill="#c8a030" font-family="JetBrains Mono,monospace" font-weight="600" text-anchor="middle">Ні</text>
    <path d="M620.0,1190.0 L920.0,1190.0" fill="none" stroke="#3a4a65" stroke-width="1.3" marker-end="url(#ah_s)"/>
    <path d="M1020.0,1190.0 L2340.0,1190.0" fill="none" stroke="#3a4a65" stroke-width="1.3" marker-end="url(#ah_s)"/>
    <path d="M2440.0,1190.0 L2570.0,1190.0" fill="none" stroke="#3a4a65" stroke-width="1.3" marker-end="url(#ah_s)"/>
    <path d="M1825.0,1010.0 L1900.0,1010.0" fill="none" stroke="#3a4a65" stroke-width="1.3" marker-end="url(#ah_s)"/><text x="1863.0" y="999.0" font-size="13.0" fill="#c8a030" font-family="JetBrains Mono,monospace" font-weight="600" text-anchor="middle">Так</text>
    <path d="M1710.0,1010.0 L1775.0,1010.0" fill="none" stroke="#3a4a65" stroke-width="1.3" marker-end="url(#ah_s)"/>
    <path d="M1800.0,1035.0 L1800.0,1090.0 L1660.0,1090.0 L1660.0,1050.0" fill="none" stroke="#3a4a65" stroke-width="1.3" marker-end="url(#ah_s)"/><text x="1730.5" y="1079.0" font-size="13.0" fill="#c8a030" font-family="JetBrains Mono,monospace" font-weight="600" text-anchor="middle">Ні</text>
    <path d="M710.0,755.0 L710.0,820.0 L920.0,820.0" fill="none" stroke="#3a4a65" stroke-width="1.3" marker-end="url(#ah_s)"/><text x="725.0" y="791.0" font-size="13.0" fill="#c8a030" font-family="JetBrains Mono,monospace" font-weight="600" text-anchor="middle">Так</text>
    <path d="M970.0,780.0 L970.0,755.0" fill="none" stroke="#3a4a65" stroke-width="1.3" marker-end="url(#ah_s)"/>
    <path d="M995.0,730.0 L1120.0,730.0" fill="none" stroke="#3a4a65" stroke-width="1.3" marker-end="url(#ah_s)"/><text x="1058.0" y="719.0" font-size="13.0" fill="#c8a030" font-family="JetBrains Mono,monospace" font-weight="600" text-anchor="middle">Так</text>
    <path d="M710.0,705.0 L710.0,630.0 L920.0,630.0" fill="none" stroke="#3a4a65" stroke-width="1.3" marker-end="url(#ah_s)"/><text x="725.5" y="672.0" font-size="13.0" fill="#c8a030" font-family="JetBrains Mono,monospace" font-weight="600" text-anchor="middle">Ні</text>
    <path d="M970.0,705.0 L970.0,670.0" fill="none" stroke="#3a4a65" stroke-width="1.3" marker-end="url(#ah_s)"/><text x="979.5" y="692.0" font-size="13.0" fill="#c8a030" font-family="JetBrains Mono,monospace" font-weight="600" text-anchor="middle">Ні</text>
    <path d="M600.0,730.0 L685.0,730.0" fill="none" stroke="#3a4a65" stroke-width="1.3" marker-end="url(#ah_s)"/>
    <path d="M1550.0,730.0 L1600.0,730.0" fill="none" stroke="#3a4a65" stroke-width="1.3" marker-end="url(#ah_s)"/>
    <path d="M2120.0,730.0 L2180.0,730.0" fill="none" stroke="#3a4a65" stroke-width="1.3" marker-end="url(#ah_s)"/>
    <path d="M2280.0,730.0 L2340.0,730.0" fill="none" stroke="#3a4a65" stroke-width="1.3" marker-end="url(#ah_s)"/>
    <path d="M2670.0,725.0 L2740.0,725.0" fill="none" stroke="#3a4a65" stroke-width="1.3" marker-end="url(#ah_s)"/>
    <path d="M2840.0,725.0 L2900.0,725.0" fill="none" stroke="#3a4a65" stroke-width="1.3" marker-end="url(#ah_s)"/>
    <path d="M3000.0,725.0 L3052.0,725.0" fill="none" stroke="#3a4a65" stroke-width="1.3" marker-end="url(#ah_s)"/>
    <path d="M190.0,120.0 L190.0,200.0" fill="none" stroke="#2a5a8a" stroke-width="1.3" stroke-dasharray="6,3" marker-end="url(#ah_m)"/>
    <path d="M210.0,280.0 L210.0,430.0" fill="none" stroke="#2a5a8a" stroke-width="1.3" stroke-dasharray="6,3" marker-end="url(#ah_m)"/>
    <path d="M470.0,190.0 L470.0,120.0" fill="none" stroke="#2a5a8a" stroke-width="1.3" stroke-dasharray="6,3" marker-end="url(#ah_m)"/>
    <path d="M1020.0,310.0 L1330.0,310.0 L1330.0,970.0" fill="none" stroke="#2a5a8a" stroke-width="1.3" stroke-dasharray="6,3" marker-end="url(#ah_m)"/>
    <path d="M970.0,590.0 L970.0,350.0" fill="none" stroke="#2a5a8a" stroke-width="1.3" stroke-dasharray="6,3" marker-end="url(#ah_m)"/>
    <path d="M1170.0,690.0 L1170.0,80.0 L1900.0,80.0" fill="none" stroke="#2a5a8a" stroke-width="1.3" stroke-dasharray="6,3" marker-end="url(#ah_m)"/>
    <path d="M1650.0,770.0 L1650.0,970.0" fill="none" stroke="#2a5a8a" stroke-width="1.3" stroke-dasharray="6,3" marker-end="url(#ah_m)"/>
    <path d="M1370.0,970.0 L1370.0,730.0 L1450.0,730.0" fill="none" stroke="#2a5a8a" stroke-width="1.3" stroke-dasharray="6,3" marker-end="url(#ah_m)"/>
    <path d="M2620.0,1150.0 L2620.0,765.0" fill="none" stroke="#2a5a8a" stroke-width="1.3" stroke-dasharray="6,3" marker-end="url(#ah_m)"/>
    <path d="M2390.0,770.0 L2390.0,1150.0" fill="none" stroke="#2a5a8a" stroke-width="1.3" stroke-dasharray="6,3" marker-end="url(#ah_m)"/>
    <path d="M2070.0,510.0 L2070.0,690.0" fill="none" stroke="#2a5a8a" stroke-width="1.3" stroke-dasharray="6,3" marker-end="url(#ah_m)"/>
    <path d="M2000.0,80.0 L2070.0,80.0 L2070.0,430.0" fill="none" stroke="#2a5a8a" stroke-width="1.3" stroke-dasharray="6,3" marker-end="url(#ah_m)"/>
    <path d="M1950.0,970.0 L1950.0,120.0" fill="none" stroke="#2a5a8a" stroke-width="1.3" stroke-dasharray="6,3" marker-end="url(#ah_m)"/>
    <path d="M1480.0,770.0 L1480.0,1090.0 L590.0,1090.0 L590.0,1150.0" fill="none" stroke="#2a5a8a" stroke-width="1.3" stroke-dasharray="6,3" marker-end="url(#ah_m)"/>
    <path d="M590.0,1150.0 L590.0,1090.0 L1480.0,1090.0 L1480.0,770.0" fill="none" stroke="#2a5a8a" stroke-width="1.3" stroke-dasharray="6,3" marker-end="url(#ah_m)"/>
    <path d="M1610.0,1010.0 L1500.0,1010.0 L1500.0,770.0" fill="none" stroke="#2a5a8a" stroke-width="1.3" stroke-dasharray="6,3" marker-end="url(#ah_m)"/>
    <path d="M550.0,770.0 L550.0,1150.0" fill="none" stroke="#2a5a8a" stroke-width="1.3" stroke-dasharray="6,3" marker-end="url(#ah_m)"/>
    <path d="M520.0,80.0 L550.0,80.0 L550.0,690.0" fill="none" stroke="#2a5a8a" stroke-width="1.3" stroke-dasharray="6,3" marker-end="url(#ah_m)"/>
    <circle cx="70.0" cy="80.0" r="18.0" fill="#0b0e14" stroke="#3a4a65" stroke-width="1.5"/>
    <rect x="140.0" y="40.0" width="100.0" height="80.0" rx="4" fill="#0a0e18" stroke="#252e45" stroke-width="1.3"/><text x="190.0" y="78.0" text-anchor="middle" font-size="12.3" fill="#dde6f5" font-family="Mulish,sans-serif" font-weight="700">Здійснює</text><text x="190.0" y="89.0" text-anchor="middle" font-size="12.3" fill="#dde6f5" font-family="Mulish,sans-serif" font-weight="700">дзвінок</text>
    <rect x="420.0" y="40.0" width="100.0" height="80.0" rx="4" fill="#0a0e18" stroke="#252e45" stroke-width="1.3"/><text x="470.0" y="83.5" text-anchor="middle" font-size="12.3" fill="#dde6f5" font-family="Mulish,sans-serif" font-weight="700">Описує запит</text>
    <rect x="1900.0" y="40.0" width="100.0" height="80.0" rx="4" fill="#0a0e18" stroke="#252e45" stroke-width="1.3"/><text x="1950.0" y="78.0" text-anchor="middle" font-size="12.3" fill="#dde6f5" font-family="Mulish,sans-serif" font-weight="700">Завершує</text><text x="1950.0" y="89.0" text-anchor="middle" font-size="12.3" fill="#dde6f5" font-family="Mulish,sans-serif" font-weight="700">дзвінок</text>
    <rect x="160.0" y="200.0" width="100.0" height="80.0" rx="4" fill="#060f1e" stroke="#1a3060" stroke-width="1.3"/><text x="210.0" y="238.0" text-anchor="middle" font-size="12.3" fill="#7aaeff" font-family="Mulish,sans-serif" font-weight="700">Маршрутизує</text><text x="210.0" y="249.0" text-anchor="middle" font-size="12.3" fill="#7aaeff" font-family="Mulish,sans-serif" font-weight="700">дзвінок</text>
    <polygon points="310.0,285.0 335.0,310.0 310.0,335.0 285.0,310.0" fill="#12100a" stroke="#6a5010" stroke-width="1.5"/><line x1="304.0" y1="304.0" x2="316.0" y2="316.0" stroke="#c8a030" stroke-width="1.2"/><line x1="316.0" y1="304.0" x2="304.0" y2="316.0" stroke="#c8a030" stroke-width="1.2"/><text x="310.0" y="345.0" text-anchor="middle" font-size="10.9" fill="#c8a030" font-family="JetBrains Mono,monospace" font-weight="600">Наявність</text><text x="310.0" y="355.0" text-anchor="middle" font-size="10.9" fill="#c8a030" font-family="JetBrains Mono,monospace" font-weight="600">вільного</text><text x="310.0" y="365.0" text-anchor="middle" font-size="10.9" fill="#c8a030" font-family="JetBrains Mono,monospace" font-weight="600">оператора?</text>
    <rect x="420.0" y="190.0" width="100.0" height="80.0" rx="4" fill="#0a0e18" stroke="#252e45" stroke-width="1.3"/><text x="470.0" y="217.0" text-anchor="middle" font-size="12.3" fill="#dde6f5" font-family="Mulish,sans-serif" font-weight="700">Переадресація</text><text x="470.0" y="228.0" text-anchor="middle" font-size="12.3" fill="#dde6f5" font-family="Mulish,sans-serif" font-weight="700">на AI із</text><text x="470.0" y="239.0" text-anchor="middle" font-size="12.3" fill="#dde6f5" font-family="Mulish,sans-serif" font-weight="700">проханням</text><text x="470.0" y="250.0" text-anchor="middle" font-size="12.3" fill="#dde6f5" font-family="Mulish,sans-serif" font-weight="700">озвучити запит</text>
    <rect x="920.0" y="270.0" width="100.0" height="80.0" rx="4" fill="#0a0e18" stroke="#252e45" stroke-width="1.3"/><text x="970.0" y="308.0" text-anchor="middle" font-size="12.3" fill="#dde6f5" font-family="Mulish,sans-serif" font-weight="700">Переадресація</text><text x="970.0" y="319.0" text-anchor="middle" font-size="12.3" fill="#dde6f5" font-family="Mulish,sans-serif" font-weight="700">на оператора</text>
    <rect x="160.0" y="430.0" width="100.0" height="80.0" rx="4" fill="#060f1e" stroke="#1a3060" stroke-width="1.3"/><text x="210.0" y="468.0" text-anchor="middle" font-size="12.3" fill="#7aaeff" font-family="Mulish,sans-serif" font-weight="700">Початок запису</text><text x="210.0" y="479.0" text-anchor="middle" font-size="12.3" fill="#7aaeff" font-family="Mulish,sans-serif" font-weight="700">розмови</text>
    <rect x="2020.0" y="430.0" width="100.0" height="80.0" rx="4" fill="#060f1e" stroke="#1a3060" stroke-width="1.3"/><text x="2070.0" y="468.0" text-anchor="middle" font-size="12.3" fill="#7aaeff" font-family="Mulish,sans-serif" font-weight="700">Завершення</text><text x="2070.0" y="479.0" text-anchor="middle" font-size="12.3" fill="#7aaeff" font-family="Mulish,sans-serif" font-weight="700">запису розмови</text>
    <rect x="500.0" y="690.0" width="100.0" height="80.0" rx="4" fill="#041408" stroke="#0c3820" stroke-width="1.3"/><text x="550.0" y="717.0" text-anchor="middle" font-size="12.3" fill="#50e8a0" font-family="Mulish,sans-serif" font-weight="700">Аналіз запитань</text><text x="550.0" y="728.0" text-anchor="middle" font-size="12.3" fill="#50e8a0" font-family="Mulish,sans-serif" font-weight="700">\ історії</text><text x="550.0" y="739.0" text-anchor="middle" font-size="12.3" fill="#50e8a0" font-family="Mulish,sans-serif" font-weight="700">клієнта. Пошук</text><text x="550.0" y="750.0" text-anchor="middle" font-size="12.3" fill="#50e8a0" font-family="Mulish,sans-serif" font-weight="700">RAG \ ЕН</text>
    <polygon points="710.0,705.0 735.0,730.0 710.0,755.0 685.0,730.0" fill="#12100a" stroke="#6a5010" stroke-width="1.5"/><line x1="704.0" y1="724.0" x2="716.0" y2="736.0" stroke="#c8a030" stroke-width="1.2"/><line x1="716.0" y1="724.0" x2="704.0" y2="736.0" stroke="#c8a030" stroke-width="1.2"/><text x="710.0" y="765.0" text-anchor="middle" font-size="10.9" fill="#c8a030" font-family="JetBrains Mono,monospace" font-weight="600">AI може надати</text><text x="710.0" y="775.0" text-anchor="middle" font-size="10.9" fill="#c8a030" font-family="JetBrains Mono,monospace" font-weight="600">відповідь?</text>
    <rect x="920.0" y="780.0" width="100.0" height="80.0" rx="4" fill="#0a0e18" stroke="#252e45" stroke-width="1.3"/><text x="970.0" y="818.0" text-anchor="middle" font-size="12.3" fill="#dde6f5" font-family="Mulish,sans-serif" font-weight="700">Надає відповідь</text><text x="970.0" y="829.0" text-anchor="middle" font-size="12.3" fill="#dde6f5" font-family="Mulish,sans-serif" font-weight="700">клієнту</text>
    <polygon points="970.0,705.0 995.0,730.0 970.0,755.0 945.0,730.0" fill="#12100a" stroke="#6a5010" stroke-width="1.5"/><line x1="964.0" y1="724.0" x2="976.0" y2="736.0" stroke="#c8a030" stroke-width="1.2"/><line x1="976.0" y1="724.0" x2="964.0" y2="736.0" stroke="#c8a030" stroke-width="1.2"/><text x="970.0" y="765.0" text-anchor="middle" font-size="10.9" fill="#c8a030" font-family="JetBrains Mono,monospace" font-weight="600">Клієнт</text><text x="970.0" y="775.0" text-anchor="middle" font-size="10.9" fill="#c8a030" font-family="JetBrains Mono,monospace" font-weight="600">задоволений</text><text x="970.0" y="785.0" text-anchor="middle" font-size="10.9" fill="#c8a030" font-family="JetBrains Mono,monospace" font-weight="600">відповіддю?</text>
    <rect x="1120.0" y="690.0" width="100.0" height="80.0" rx="4" fill="#0a0e18" stroke="#252e45" stroke-width="1.3"/><text x="1170.0" y="717.0" text-anchor="middle" font-size="12.3" fill="#dde6f5" font-family="Mulish,sans-serif" font-weight="700">Очікування</text><text x="1170.0" y="728.0" text-anchor="middle" font-size="12.3" fill="#dde6f5" font-family="Mulish,sans-serif" font-weight="700">інших питань чи</text><text x="1170.0" y="739.0" text-anchor="middle" font-size="12.3" fill="#dde6f5" font-family="Mulish,sans-serif" font-weight="700">завершення</text><text x="1170.0" y="750.0" text-anchor="middle" font-size="12.3" fill="#dde6f5" font-family="Mulish,sans-serif" font-weight="700">дзвінка</text>
    <rect x="920.0" y="590.0" width="100.0" height="80.0" rx="4" fill="#041408" stroke="#0c3820" stroke-width="1.3"/><text x="970.0" y="622.5" text-anchor="middle" font-size="12.3" fill="#50e8a0" font-family="Mulish,sans-serif" font-weight="700">Передає</text><text x="970.0" y="633.5" text-anchor="middle" font-size="12.3" fill="#50e8a0" font-family="Mulish,sans-serif" font-weight="700">контекст</text><text x="970.0" y="644.5" text-anchor="middle" font-size="12.3" fill="#50e8a0" font-family="Mulish,sans-serif" font-weight="700">зібраних даних</text>
    <rect x="1450.0" y="690.0" width="100.0" height="80.0" rx="4" fill="#041408" stroke="#0c3820" stroke-width="1.3"/><text x="1500.0" y="717.0" text-anchor="middle" font-size="12.3" fill="#50e8a0" font-family="Mulish,sans-serif" font-weight="700">Аналіз</text><text x="1500.0" y="728.0" text-anchor="middle" font-size="12.3" fill="#50e8a0" font-family="Mulish,sans-serif" font-weight="700">запитань, пошук</text><text x="1500.0" y="739.0" text-anchor="middle" font-size="12.3" fill="#50e8a0" font-family="Mulish,sans-serif" font-weight="700">у базі знань,</text><text x="1500.0" y="750.0" text-anchor="middle" font-size="12.3" fill="#50e8a0" font-family="Mulish,sans-serif" font-weight="700">накладної</text>
    <rect x="1600.0" y="690.0" width="100.0" height="80.0" rx="4" fill="#041408" stroke="#0c3820" stroke-width="1.3"/><text x="1650.0" y="711.5" text-anchor="middle" font-size="12.3" fill="#50e8a0" font-family="Mulish,sans-serif" font-weight="700">Висвітлення</text><text x="1650.0" y="722.5" text-anchor="middle" font-size="12.3" fill="#50e8a0" font-family="Mulish,sans-serif" font-weight="700">підказок,</text><text x="1650.0" y="733.5" text-anchor="middle" font-size="12.3" fill="#50e8a0" font-family="Mulish,sans-serif" font-weight="700">історії</text><text x="1650.0" y="744.5" text-anchor="middle" font-size="12.3" fill="#50e8a0" font-family="Mulish,sans-serif" font-weight="700">клієнта,</text><text x="1650.0" y="755.5" text-anchor="middle" font-size="12.3" fill="#50e8a0" font-family="Mulish,sans-serif" font-weight="700">найкращих дій</text>
    <rect x="2020.0" y="690.0" width="100.0" height="80.0" rx="4" fill="#060f1e" stroke="#1a3060" stroke-width="1.3"/><text x="2070.0" y="728.0" text-anchor="middle" font-size="12.3" fill="#7aaeff" font-family="Mulish,sans-serif" font-weight="700">Транскрибація.</text><text x="2070.0" y="739.0" text-anchor="middle" font-size="12.3" fill="#7aaeff" font-family="Mulish,sans-serif" font-weight="700">Витяг сутностей</text>
    <rect x="2180.0" y="690.0" width="100.0" height="80.0" rx="4" fill="#060f1e" stroke="#1a3060" stroke-width="1.3"/><text x="2230.0" y="717.0" text-anchor="middle" font-size="12.3" fill="#7aaeff" font-family="Mulish,sans-serif" font-weight="700">Генерація</text><text x="2230.0" y="728.0" text-anchor="middle" font-size="12.3" fill="#7aaeff" font-family="Mulish,sans-serif" font-weight="700">резюме, запиту</text><text x="2230.0" y="739.0" text-anchor="middle" font-size="12.3" fill="#7aaeff" font-family="Mulish,sans-serif" font-weight="700">на інші відділи</text><text x="2230.0" y="750.0" text-anchor="middle" font-size="12.3" fill="#7aaeff" font-family="Mulish,sans-serif" font-weight="700">(опціонально)</text>
    <rect x="2340.0" y="690.0" width="100.0" height="80.0" rx="4" fill="#060f1e" stroke="#1a3060" stroke-width="1.3"/><text x="2390.0" y="722.5" text-anchor="middle" font-size="12.3" fill="#7aaeff" font-family="Mulish,sans-serif" font-weight="700">Заповнення</text><text x="2390.0" y="733.5" text-anchor="middle" font-size="12.3" fill="#7aaeff" font-family="Mulish,sans-serif" font-weight="700">тематик, тегів,</text><text x="2390.0" y="744.5" text-anchor="middle" font-size="12.3" fill="#7aaeff" font-family="Mulish,sans-serif" font-weight="700">тону дзвінка</text>
    <rect x="2570.0" y="685.0" width="100.0" height="80.0" rx="4" fill="#060f1e" stroke="#1a3060" stroke-width="1.3"/><text x="2620.0" y="712.0" text-anchor="middle" font-size="12.3" fill="#7aaeff" font-family="Mulish,sans-serif" font-weight="700">Перевірка</text><text x="2620.0" y="723.0" text-anchor="middle" font-size="12.3" fill="#7aaeff" font-family="Mulish,sans-serif" font-weight="700">проходження</text><text x="2620.0" y="734.0" text-anchor="middle" font-size="12.3" fill="#7aaeff" font-family="Mulish,sans-serif" font-weight="700">оператора по</text><text x="2620.0" y="745.0" text-anchor="middle" font-size="12.3" fill="#7aaeff" font-family="Mulish,sans-serif" font-weight="700">чеклисту</text>
    <rect x="2740.0" y="685.0" width="100.0" height="80.0" rx="4" fill="#060f1e" stroke="#1a3060" stroke-width="1.3"/><text x="2790.0" y="723.0" text-anchor="middle" font-size="12.3" fill="#7aaeff" font-family="Mulish,sans-serif" font-weight="700">Тегування та</text><text x="2790.0" y="734.0" text-anchor="middle" font-size="12.3" fill="#7aaeff" font-family="Mulish,sans-serif" font-weight="700">маркування</text>
    <rect x="2900.0" y="685.0" width="100.0" height="80.0" rx="4" fill="#060f1e" stroke="#1a3060" stroke-width="1.3"/><text x="2950.0" y="717.5" text-anchor="middle" font-size="12.3" fill="#7aaeff" font-family="Mulish,sans-serif" font-weight="700">Інтеграція</text><text x="2950.0" y="728.5" text-anchor="middle" font-size="12.3" fill="#7aaeff" font-family="Mulish,sans-serif" font-weight="700">даних у</text><text x="2950.0" y="739.5" text-anchor="middle" font-size="12.3" fill="#7aaeff" font-family="Mulish,sans-serif" font-weight="700">аналітику BI</text>
    <circle cx="3070.0" cy="725.0" r="18.0" fill="#0b0e14" stroke="#3a4a65" stroke-width="3"/><circle cx="3070.0" cy="725.0" r="14.0" fill="#3a4a65"/>
    <rect x="1300.0" y="970.0" width="100.0" height="80.0" rx="4" fill="#1a0800" stroke="#8a3000" stroke-width="1.3"/><text x="1350.0" y="1002.5" text-anchor="middle" font-size="12.3" fill="#ff9878" font-family="Mulish,sans-serif" font-weight="700">Приймає</text><text x="1350.0" y="1013.5" text-anchor="middle" font-size="12.3" fill="#ff9878" font-family="Mulish,sans-serif" font-weight="700">дзвінок,</text><text x="1350.0" y="1024.5" text-anchor="middle" font-size="12.3" fill="#ff9878" font-family="Mulish,sans-serif" font-weight="700">починає розмову</text><rect x="1304.0" y="974.0" width="34" height="8" rx="2" fill="#501800"/><text x="1321.0" y="981.0" text-anchor="middle" font-size="8.0" fill="#ff6030" font-family="JetBrains Mono,monospace" font-weight="700">MANUAL</text>
    <rect x="1610.0" y="970.0" width="100.0" height="80.0" rx="4" fill="#1a0800" stroke="#8a3000" stroke-width="1.3"/><text x="1660.0" y="997.0" text-anchor="middle" font-size="12.3" fill="#ff9878" font-family="Mulish,sans-serif" font-weight="700">Консультує,</text><text x="1660.0" y="1008.0" text-anchor="middle" font-size="12.3" fill="#ff9878" font-family="Mulish,sans-serif" font-weight="700">читаючи</text><text x="1660.0" y="1019.0" text-anchor="middle" font-size="12.3" fill="#ff9878" font-family="Mulish,sans-serif" font-weight="700">підказки, та</text><text x="1660.0" y="1030.0" text-anchor="middle" font-size="12.3" fill="#ff9878" font-family="Mulish,sans-serif" font-weight="700">шукає рішення</text><rect x="1614.0" y="974.0" width="34" height="8" rx="2" fill="#501800"/><text x="1631.0" y="981.0" text-anchor="middle" font-size="8.0" fill="#ff6030" font-family="JetBrains Mono,monospace" font-weight="700">MANUAL</text>
    <polygon points="1800.0,985.0 1825.0,1010.0 1800.0,1035.0 1775.0,1010.0" fill="#12100a" stroke="#6a5010" stroke-width="1.5"/><line x1="1794.0" y1="1004.0" x2="1806.0" y2="1016.0" stroke="#c8a030" stroke-width="1.2"/><line x1="1806.0" y1="1004.0" x2="1794.0" y2="1016.0" stroke="#c8a030" stroke-width="1.2"/><text x="1800.0" y="948.0" text-anchor="middle" font-size="10.9" fill="#c8a030" font-family="JetBrains Mono,monospace" font-weight="600">Клієнт</text><text x="1800.0" y="960.0" text-anchor="middle" font-size="10.9" fill="#c8a030" font-family="JetBrains Mono,monospace" font-weight="600">задоволений</text><text x="1800.0" y="972.0" text-anchor="middle" font-size="10.9" fill="#c8a030" font-family="JetBrains Mono,monospace" font-weight="600">відповіддю?</text>
    <rect x="1900.0" y="970.0" width="100.0" height="80.0" rx="4" fill="#1a0800" stroke="#8a3000" stroke-width="1.3"/><text x="1950.0" y="997.0" text-anchor="middle" font-size="12.3" fill="#ff9878" font-family="Mulish,sans-serif" font-weight="700">Очікування</text><text x="1950.0" y="1008.0" text-anchor="middle" font-size="12.3" fill="#ff9878" font-family="Mulish,sans-serif" font-weight="700">інших питань чи</text><text x="1950.0" y="1019.0" text-anchor="middle" font-size="12.3" fill="#ff9878" font-family="Mulish,sans-serif" font-weight="700">завершення</text><text x="1950.0" y="1030.0" text-anchor="middle" font-size="12.3" fill="#ff9878" font-family="Mulish,sans-serif" font-weight="700">дзвінка</text><rect x="1904.0" y="974.0" width="34" height="8" rx="2" fill="#501800"/><text x="1921.0" y="981.0" text-anchor="middle" font-size="8.0" fill="#ff6030" font-family="JetBrains Mono,monospace" font-weight="700">MANUAL</text>
    <rect x="520.0" y="1150.0" width="100.0" height="80.0" rx="4" fill="#060f1e" stroke="#1a3060" stroke-width="1.3"/><text x="570.0" y="1188.0" text-anchor="middle" font-size="12.3" fill="#7aaeff" font-family="Mulish,sans-serif" font-weight="700">Аналіз історії</text><text x="570.0" y="1199.0" text-anchor="middle" font-size="12.3" fill="#7aaeff" font-family="Mulish,sans-serif" font-weight="700">клієнта</text>
    <rect x="920.0" y="1150.0" width="100.0" height="80.0" rx="4" fill="#060f1e" stroke="#1a3060" stroke-width="1.3"/><text x="970.0" y="1182.5" text-anchor="middle" font-size="12.3" fill="#7aaeff" font-family="Mulish,sans-serif" font-weight="700">Створення нової</text><text x="970.0" y="1193.5" text-anchor="middle" font-size="12.3" fill="#7aaeff" font-family="Mulish,sans-serif" font-weight="700">картки</text><text x="970.0" y="1204.5" text-anchor="middle" font-size="12.3" fill="#7aaeff" font-family="Mulish,sans-serif" font-weight="700">звернення</text>
    <rect x="2340.0" y="1150.0" width="100.0" height="80.0" rx="4" fill="#1a0800" stroke="#8a3000" stroke-width="1.3"/><rect x="2344.0" y="1154.0" width="34" height="8" rx="2" fill="#501800"/><text x="2361.0" y="1161.0" text-anchor="middle" font-size="8.0" fill="#ff6030" font-family="JetBrains Mono,monospace" font-weight="700">MANUAL</text><text x="2390.0" y="1188.0" text-anchor="middle" font-size="12.3" fill="#ff9878" font-family="Mulish,sans-serif" font-weight="700">Доповнення</text><text x="2390.0" y="1199.0" text-anchor="middle" font-size="12.3" fill="#ff9878" font-family="Mulish,sans-serif" font-weight="700">картки клієнта</text>
    <rect x="2570.0" y="1150.0" width="100.0" height="80.0" rx="4" fill="#1a0800" stroke="#8a3000" stroke-width="1.3"/><rect x="2574.0" y="1154.0" width="34" height="8" rx="2" fill="#501800"/><text x="2591.0" y="1161.0" text-anchor="middle" font-size="8.0" fill="#ff6030" font-family="JetBrains Mono,monospace" font-weight="700">MANUAL</text><text x="2620.0" y="1193.5" text-anchor="middle" font-size="12.3" fill="#ff9878" font-family="Mulish,sans-serif" font-weight="700">Закриття картки</text>
    </svg></div>

      <div class="sl" style="padding-top:24px">Нові можливості TO-BE</div>
      <div class="pg pg4">
        <div class="pgc g"><div class="pgc-t">Голосовий асистент, що надає прості консультації</div><div class="pgc-d">Зменшення навантежності на операторів, шляхом закриття звернень ШІ, чий голос не відрізнятиметься від людини</div></div>
        <div class="pgc g"><div class="pgc-t">Зменшити частку ескалацій і повторних контактів</div><div class="pgc-d">Через кращу першу відповідь — клієнт отримує вирішення з першого дзвінка.</div></div>
        <div class="pgc g"><div class="pgc-t">Прискорити онбординг нових операторів</div><div class="pgc-d">Через стандартизацію знань — новий оператор з підказками працює як досвідчений.</div></div>
        <div class="pgc g"><div class="pgc-t">Покращити аналіз якості роботи КЦ</div><div class="pgc-d">100% дзвінків замість вибірки — системне розуміння якості, а не точкові перевірки</div></div>
      </div>
    </div>'''


def generate_html(
    categories: Dict[str, Category],
    final_scores: Dict[str, str],
    tco_values: Dict[str, str],
    asis_bpmn_xml: str = '',
    tobe_bpmn_xml: str = '',
) -> str:
    """Generate the complete HTML document."""
    _DISPLAY_ORDER = [
        "Google Cloud CCAI",
        "Ender Turing",
        "Cresta",
        "Microsoft Copilot",
        "NICE",
        "NICE Cognigy",
        "Genesys Cloud CX",
        "Live Person",
        "Decagon",
        "Ringostat",
        "Poly AI",
        "11 Labs",
        "Uni Talk",
        "Get Vocal",
    ]
    sorted_providers = [p for p in _DISPLAY_ORDER if p in PROVIDERS] + [
        p for p in PROVIDERS if p not in _DISPLAY_ORDER
    ]

    # Per-provider dict of category subtotal strings
    category_scores: Dict[str, Dict[str, str]] = {
        provider: {
            cat_id: cat.subtotals.get(provider, "0%")
            for cat_id, cat in categories.items()
        }
        for provider in PROVIDERS
    }

    max_weights = {cat_id: cat.weight_percent for cat_id, cat in categories.items()}

    _all_cards = [
        generate_provider_card(
            provider,
            rank,
            final_scores.get(provider, "0%"),
            tco_values.get(provider, "N/A"),
            category_scores[provider],
            max_weights,
        )
        for rank, provider in enumerate(sorted_providers, 1)
    ]
    _row_sizes = [3, 4, 4, 3]
    _rows = []
    _idx = 0
    for _size in _row_sizes:
        _chunk = _all_cards[_idx:_idx + _size]
        if _chunk:
            _rows.append(f'<div class="fs-row fs-row-{_size}">\n' + "\n".join(_chunk) + '\n</div>')
        _idx += _size
    if _idx < len(_all_cards):
        _rows.append('<div class="fs-row fs-row-4">\n' + "\n".join(_all_cards[_idx:]) + '\n</div>')
    provider_cards = "\n".join(_rows)

    category_order = ["copilot", "acw", "analytics", "precall", "it", "business"]
    category_tabs = "\n".join(
        generate_category_tab(cat_id, categories[cat_id], PROVIDERS)
        for cat_id in category_order
        if cat_id in categories
    )

    winner = sorted_providers[0] if sorted_providers else "N/A"
    winner_score = final_scores.get(winner, "0%")

    # Build BPMN data script separately to avoid f-string escaping issues
    _asis_js = json.dumps(asis_bpmn_xml)
    _tobe_js = json.dumps(tobe_bpmn_xml)
    _bpmn_data_script = (
        '<script>\n'
        'window.__bpmnData = {\n'
        '  asis: ' + _asis_js + ',\n'
        '  tobe: ' + _tobe_js + '\n'
        '};\n'
        '</script>'
    )

    _html = f'''<!DOCTYPE html>
<html lang="uk">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Copilot - Аналіз провайдерів</title>
    <style>

        :root {{
            --bg: #080b12;
            --bg2: #0d1320;
            --text: #dde6f5;
            --muted: #5a6e90;
            --border: rgba(255,255,255,.08);
            --border2: #1e2840;
            --ai: #30d890;
            --ai-bg: rgba(48,216,144,.06);
            --ai-b: rgba(48,216,144,.2);
            --warn: #ff7040;
            --warn-bg: rgba(255,112,64,.06);
            --warn-b: rgba(255,112,64,.2);
        }}

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
            max-width: 1500px;
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
            justify-content: center; /* Centers horizontally */
            align-items: center;     /* Centers vertically */
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

        .bpmn-section {{ padding: 24px 0; }}
        .bpmn-scroll-wrap {{ overflow: auto; max-height: 700px; border: 1px solid #252e45; border-radius: 8px; margin: 0 0 24px; background: #080b12; }}
        .bpmn-viewer-wrap {{ position: relative; height: 600px; border: 1px solid #252e45; border-radius: 8px; margin: 0 0 24px; background: #fff; overflow: hidden; }}
        .bpmn-controls {{ position: absolute; top: 10px; right: 10px; z-index: 10; display: flex; flex-direction: column; gap: 4px; }}
        .bpmn-ctrl-btn {{ width: 32px; height: 32px; background: rgba(10,15,28,.85); border: 1px solid #2a3a5a; border-radius: 6px; color: #a0b4d0; font-size: 16px; line-height: 1; cursor: pointer; display: flex; align-items: center; justify-content: center; backdrop-filter: blur(4px); }}
        .bpmn-ctrl-btn:hover {{ background: rgba(30,50,90,.95); color: #fff; }}
        .bpmn-hero {{ display: flex; justify-content: space-between; align-items: flex-start; padding: 0 0 16px; gap: 16px; }}
        .bpmn-eyebrow {{ font-size: 11px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; margin-bottom: 4px; }}
        .bpmn-title {{ font-size: 20px; font-weight: 700; margin-bottom: 6px; }}
        .bpmn-lead {{ font-size: 12px; color: #5a6e90; line-height: 1.6; }}
        .bpmn-chips {{ display: flex; gap: 6px; flex-wrap: wrap; }}
        .bpmn-chip {{ font-size: 10px; padding: 3px 10px; border-radius: 20px; border: 1px solid; }}
        .bpmn-legend {{ display: flex; gap: 16px; flex-wrap: wrap; align-items: center; padding: 0 0 12px; font-size: 11px; color: #5a6e90; }}
        .bpmn-leg {{ display: flex; align-items: center; gap: 6px; }}
        .bpmn-problems {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-top: 20px; }}
        .bpmn-prob-card {{ background: rgba(255,255,255,.03); border: 1px solid rgba(255,70,40,.15); border-radius: 8px; padding: 14px; }}
        .bpmn-prob-title {{ font-size: 12px; font-weight: 700; color: #ff7040; margin-bottom: 6px; }}
        .bpmn-prob-text {{ font-size: 11px; color: #8090a8; line-height: 1.6; }}
        .bpmn-benefit-card {{ background: rgba(255,255,255,.03); border: 1px solid rgba(48,216,144,.15); border-radius: 8px; padding: 14px; }}
        .bpmn-benefit-title {{ font-size: 12px; font-weight: 700; color: #30d890; margin-bottom: 6px; }}
        .bpmn-benefit-text {{ font-size: 11px; color: #8090a8; line-height: 1.6; }}

        .comparison-table {{
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 16px;
            overflow-x: auto;
            margin-bottom: 32px;
        }}

        .comparison-table > * {{
            min-width: max-content;
        }}

        .table-header {{
            display: grid;
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
            min-width: 34px;
            height: 22px;
            padding: 0 4px;
            border-radius: 4px;
            font-size: 11px;
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
            background: rgba(250, 204, 21, 0.2);
            color: #fbbf24;
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
            grid-template-columns: repeat(7, 1fr);
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
            display: flex;
            flex-direction: column;
            gap: 20px;
            margin-bottom: 32px;
        }}
        .fs-row {{
            display: grid;
            gap: 20px;
        }}
        .fs-row-3 {{ grid-template-columns: repeat(3, 1fr); }}
        .fs-row-4 {{ grid-template-columns: repeat(4, 1fr); }}

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

        @media (max-width: 1024px) {{
            .fs-row-4 {{ grid-template-columns: repeat(2, 1fr); }}
            .fs-row-3 {{ grid-template-columns: repeat(3, 1fr); }}
        }}

        @media (max-width: 700px) {{
            .fs-row-3, .fs-row-4 {{ grid-template-columns: repeat(2, 1fr); }}
        }}

        .mth-card {{ background: #161e2e; border: 1px solid #1e2d42; border-radius: 16px; padding: 32px; margin-top: 32px; }}
        .mth-card-title {{ font-size: 20px; font-weight: 700; color: #38bdf8; margin-bottom: 24px; }}
        .mth-inner-divider {{ height: 1px; background: #1e2d42; margin: 24px 0; }}
        .mth-sub-label {{ font-size: 11px; font-weight: 600; color: #4a6080; letter-spacing: 1.2px; text-transform: uppercase; margin-bottom: 14px; }}
        .msc-row {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }}
        .msc-item {{ background: #1a2438; border: 1px solid #243044; border-radius: 10px; padding: 14px 16px; display: flex; gap: 12px; align-items: flex-start; }}
        .msc-icon {{ width: 32px; height: 32px; border-radius: 7px; display: flex; align-items: center; justify-content: center; font-size: 14px; font-weight: 800; flex-shrink: 0; }}
        .msc-item.must .msc-icon   {{ background: rgba(239,68,68,0.15);  color: #ef4444; }}
        .msc-item.should .msc-icon {{ background: rgba(251,146,60,0.15); color: #fb923c; }}
        .msc-item.could .msc-icon  {{ background: rgba(56,189,248,0.15); color: #38bdf8; }}
        .msc-top {{ display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }}
        .msc-name {{ font-size: 13px; font-weight: 700; }}
        .msc-item.must .msc-name   {{ color: #ef4444; }}
        .msc-item.should .msc-name {{ color: #fb923c; }}
        .msc-item.could .msc-name  {{ color: #38bdf8; }}
        .msc-badge {{ font-size: 9px; font-weight: 600; letter-spacing: 0.8px; text-transform: uppercase; padding: 1px 6px; border-radius: 3px; }}
        .msc-item.must .msc-badge   {{ background: rgba(239,68,68,0.12);  color: #ef4444; }}
        .msc-item.should .msc-badge {{ background: rgba(251,146,60,0.12); color: #fb923c; }}
        .msc-item.could .msc-badge  {{ background: rgba(56,189,248,0.12); color: #38bdf8; }}
        .msc-desc {{ font-size: 12px; color: #6a7f9a; line-height: 1.55; }}
        .wf-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
        .pb-list {{ display: flex; flex-direction: column; gap: 10px; justify-content: center; height: 100%; }}
        .pb-row  {{ display: grid; grid-template-columns: 90px 1fr 52px; align-items: center; gap: 10px; }}
        .pb-name {{ font-size: 12px; color: #6a7f9a; white-space: nowrap; }}
        .pb-track {{ height: 5px; background: #243044; border-radius: 99px; overflow: hidden; }}
        .pb-fill  {{ height: 100%; border-radius: 99px; }}
        .pb-val   {{ font-size: 12px; font-weight: 700; text-align: right; white-space: nowrap; }}
        .c-must   {{ color: #ef4444; }} .c-should {{ color: #fb923c; }}
        .c-could  {{ color: #38bdf8; }} .c-total  {{ color: #7a8fa8; }}
        .fill-must   {{ background: #ef4444; }}
        .fill-should {{ background: #fb923c; }}
        .fill-could  {{ background: #38bdf8; }}
        .fill-total  {{ background: linear-gradient(90deg,#ef4444 0%,#fb923c 50%,#38bdf8 100%); }}
        .formula-box {{ background: #1a2438; border: 1px solid #243044; border-radius: 10px; padding: 16px; display: flex; align-items: center; justify-content: center; height: 100%; }}
        .formula-math {{ display: inline-flex; align-items: center; justify-content: center; gap: 6px; flex-wrap: wrap; }}
        .fm-lhs   {{ font-size: 13px; font-weight: 500; color: #8a9bb5; white-space: nowrap; }}
        .fm-eq    {{ font-size: 16px; color: #3a526e; }}
        .fm-sigma {{ font-size: 26px; color: #8a9bb5; font-weight: 300; line-height: 1; }}
        .fm-paren {{ font-size: 34px; color: #3a526e; font-weight: 200; line-height: 1; }}
        .fm-frac  {{ display: inline-flex; flex-direction: column; align-items: center; margin: 0 2px; }}
        .fm-num   {{ font-size: 11px; color: #6a7f9a; white-space: nowrap; padding-bottom: 3px; }}
        .fm-line  {{ width: 100%; height: 1px; background: #364d66; }}
        .fm-den   {{ font-size: 18px; font-weight: 700; color: #e2e8f0; padding-top: 3px; }}
        .fm-op    {{ font-size: 14px; color: #3a526e; }}
        .fm-param {{ font-size: 13px; font-weight: 500; color: #8a9bb5; white-space: nowrap; }}
        .fm-x100  {{ font-size: 18px; font-weight: 700; color: #e2e8f0; }}
        .scale-row {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; }}
        .sg {{ --sc: #22c55e; }} .sl2 {{ --sc: #84cc16; }} .sy {{ --sc: #eab308; }}
        .so {{ --sc: #f97316; }} .srd {{ --sc: #ef4444; }}
        .scale-item {{ background: #1a2438; border: 1px solid #243044; border-left: 3px solid var(--sc); border-radius: 8px; padding: 12px; display: flex; gap: 10px; align-items: flex-start; }}
        .scale-score {{ font-size: 26px; font-weight: 800; color: var(--sc); line-height: 1; flex-shrink: 0; }}
        .scale-name {{ font-size: 11px; font-weight: 700; color: var(--sc); margin-bottom: 4px; }}
        .scale-track {{ height: 3px; background: #243044; border-radius: 99px; margin-bottom: 6px; overflow: hidden; }}
        .scale-fill  {{ height: 100%; border-radius: 99px; background: var(--sc); }}
        .scale-desc  {{ font-size: 11px; color: #6a7f9a; line-height: 1.45; }}
        @media (max-width: 960px) {{ .msc-row, .wf-row {{ grid-template-columns: 1fr; }} .scale-row {{ grid-template-columns: repeat(2,1fr); }} }}

        @media (max-width: 1200px) {{
            .final-scores {{
                grid-template-columns: repeat(4, 1fr);
            }}
            .summary-grid {{
                grid-template-columns: repeat(4, 1fr);
            }}
        }}

        /* Recommendations Tab Styles */
        .recommendations-section {{
            max-width: 900px;
            margin: 0 auto;
        }}

        .rec-header {{
            margin-bottom: 40px;
        }}

        .rec-eyebrow {{
            font-size: 11px;
            letter-spacing: 0.18em;
            text-transform: uppercase;
            color: #10b981;
            margin-bottom: 16px;
            display: flex;
            align-items: center;
            gap: 10px;
        }}

        .rec-eyebrow::before {{
            content: '';
            display: inline-block;
            width: 24px;
            height: 1px;
            background: #10b981;
            opacity: 0.6;
        }}

        .rec-title {{
            font-size: 32px;
            font-weight: 700;
            line-height: 1.2;
            margin-bottom: 16px;
        }}

        .rec-title .highlight {{
            color: #10b981;
        }}

        .rec-lead {{
            font-size: 15px;
            color: #9ca3af;
            line-height: 1.7;
            max-width: 680px;
        }}

        .rec-divider {{
            display: flex;
            align-items: center;
            gap: 12px;
            margin: 40px 0 24px;
        }}

        .rec-divider-label {{
            font-size: 10px;
            letter-spacing: 0.16em;
            text-transform: uppercase;
            color: #6b7280;
            white-space: nowrap;
        }}

        .rec-divider-line {{
            flex: 1;
            height: 1px;
            background: rgba(255, 255, 255, 0.1);
        }}

        .alert-box {{
            border-radius: 12px;
            padding: 20px 24px;
            margin-bottom: 16px;
            display: flex;
            gap: 16px;
            align-items: flex-start;
        }}

        .alert-red {{
            background: rgba(239, 68, 68, 0.1);
            border: 1px solid rgba(239, 68, 68, 0.25);
        }}

        .alert-icon {{
            font-size: 18px;
            flex-shrink: 0;
        }}

        .alert-title {{
            font-size: 12px;
            font-weight: 600;
            letter-spacing: 0.05em;
            margin-bottom: 8px;
            color: #ef4444;
        }}

        .alert-text {{
            font-size: 14px;
            line-height: 1.65;
            color: #d1a0a0;
        }}

        .strategy-alert-card {{
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 12px;
            padding: 28px;
            margin-bottom: 20px;
            position: relative;
            overflow: hidden;
        }}

        .strategy-alert-card::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 2px;
            background: #e97451;
            opacity: 0.5;
        }}

        .strategy-card {{
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 12px;
            padding: 28px;
            margin-bottom: 20px;
            position: relative;
            overflow: hidden;
        }}

        .strategy-card::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 2px;
            background: #10b981;
            opacity: 0.5;
        }}

        .strategy-label {{
            font-size: 10px;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            color: #10b981;
            margin-bottom: 10px;
        }}

        .strategy-title {{
            font-size: 18px;
            font-weight: 700;
            margin-bottom: 12px;
        }}

        .strategy-text {{
            font-size: 14px;
            color: #9ca3af;
            line-height: 1.7;
        }}

        .components-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 16px;
            margin: 20px 0;
        }}

        .component-card {{
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 12px;
            padding: 20px;
        }}

        .component-num {{
            font-size: 11px;
            font-weight: 700;
            color: #6b7280;
            margin-bottom: 10px;
            letter-spacing: 0.08em;
        }}

        .component-tag {{
            display: inline-block;
            font-size: 9px;
            font-weight: 600;
            padding: 4px 8px;
            border-radius: 4px;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            margin-bottom: 10px;
        }}

        .tag-logic {{
            background: rgba(16, 185, 129, 0.15);
            color: #10b981;
            border: 1px solid rgba(16, 185, 129, 0.25);
        }}

        .tag-voice {{
            background: rgba(96, 165, 250, 0.1);
            color: #60a5fa;
            border: 1px solid rgba(96, 165, 250, 0.25);
        }}

        .tag-api {{
            background: rgba(245, 158, 11, 0.1);
            color: #f59e0b;
            border: 1px solid rgba(245, 158, 11, 0.25);
        }}

        .component-name {{
            font-size: 14px;
            font-weight: 700;
            margin-bottom: 8px;
        }}

        .component-desc {{
            font-size: 12px;
            color: #9ca3af;
            line-height: 1.5;
        }}

        .roadmap {{
            position: relative;
            padding-left: 32px;
        }}

        .roadmap::before {{
            content: '';
            position: absolute;
            left: 11px;
            top: 20px;
            bottom: 20px;
            width: 1px;
            background: rgba(255, 255, 255, 0.1);
        }}

        .roadmap-item {{
            position: relative;
            margin-bottom: 20px;
        }}

        .roadmap-item:last-child {{
            margin-bottom: 0;
        }}

        .roadmap-dot {{
            position: absolute;
            left: -26px;
            top: 20px;
            width: 14px;
            height: 14px;
            border-radius: 50%;
            background: #1a1f3a;
            border: 2px solid #10b981;
            display: flex;
            align-items: center;
            justify-content: center;
        }}

        .roadmap-dot-inner {{
            width: 5px;
            height: 5px;
            border-radius: 50%;
            background: #10b981;
        }}

        .roadmap-card {{
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 12px;
            padding: 20px 24px;
        }}

        .roadmap-step {{
            font-size: 9px;
            font-weight: 600;
            letter-spacing: 0.1em;
            text-transform: uppercase;
            color: #6b7280;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            padding: 4px 10px;
            border-radius: 4px;
            display: inline-block;
            margin-bottom: 12px;
        }}

        .roadmap-title {{
            font-size: 16px;
            font-weight: 700;
            margin-bottom: 16px;
        }}

        .roadmap-row {{
            display: flex;
            align-items: flex-start;
            gap: 12px;
            margin-bottom: 12px;
            padding-bottom: 12px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }}

        .roadmap-row:last-child {{
            margin-bottom: 0;
            padding-bottom: 0;
            border-bottom: none;
        }}

        .roadmap-label {{
            font-size: 10px;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            white-space: nowrap;
            padding-top: 2px;
            min-width: 60px;
        }}

        .label-goal {{
            color: #10b981;
        }}

        .label-action {{
            color: #f59e0b;
        }}

        .label-result {{
            color: #60a5fa;
        }}

        .roadmap-text {{
            font-size: 13px;
            color: #9ca3af;
            line-height: 1.55;
        }}

        .benefits-list {{
            display: flex;
            flex-direction: column;
            gap: 12px;
        }}

        .benefit-item {{
            display: flex;
            align-items: flex-start;
            gap: 14px;
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 10px;
            padding: 16px 20px;
        }}

        .benefit-icon {{
            font-size: 16px;
            flex-shrink: 0;
        }}

        .benefit-text {{
            font-size: 14px;
            color: #9ca3af;
            line-height: 1.55;
        }}

        .benefit-text strong {{
            color: #e0e6ed;
        }}

        @media (max-width: 900px) {{
            .components-grid {{
                grid-template-columns: 1fr;
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
                grid-template-columns: repeat(2, 1fr);
            }}
        }}

        .panel{{display:none;padding:0 0 80px}}
        .panel.on{{display:block}}

        .hero{{padding:24px 32px 20px;border-bottom:1px solid var(--border);
          display:flex;align-items:flex-end;justify-content:space-between;gap:16px}}
        .hero h2{{font-family:'Unbounded',sans-serif;font-size:22px;font-weight:900;
          letter-spacing:-.03em;line-height:1.15}}
        .hero p{{font-size:11px;color:var(--muted);margin-top:4px;line-height:1.6;max-width:600px}}
        .chips{{display:flex;gap:6px;flex-wrap:wrap;align-items:flex-start}}
        .chip{{font-family:'JetBrains Mono',monospace;font-size:8px;font-weight:500;
          padding:3px 8px;border-radius:20px;border:1px solid;letter-spacing:.04em;white-space:nowrap}}

        .sl{{font-family:'JetBrains Mono',monospace;font-size:8px;font-weight:500;
          letter-spacing:.16em;text-transform:uppercase;color:var(--muted);
          padding:20px 32px 8px;display:flex;align-items:center;gap:10px}}
        .sl::before{{content:'//';color:var(--ai);opacity:.6}}
        .sl::after{{content:'';flex:1;height:1px;background:var(--border)}}

        .diag-wrap{{width:100vw;position:relative;left:50%;right:50%;margin-left:-50vw;margin-right:-50vw;
          border-top:1px solid var(--border2);border-bottom:1px solid var(--border2);border-radius:0;
          overflow-x:auto;background:#0b0e14}}
        .diag-wrap:active{{cursor:grabbing}}
        .diag-wrap svg{{display:block}}

        .legend{{display:flex;gap:18px;padding:8px 32px 0;flex-wrap:wrap;align-items:center}}
        .leg{{display:flex;align-items:center;gap:6px;
          font-family:'JetBrains Mono',monospace;font-size:8.5px;color:var(--muted)}}

        .pg{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:0 32px}}
        .pg.pg4{{grid-template-columns:repeat(4,1fr)}}
        .pgc{{border-radius:6px;padding:12px 14px;border:1px solid}}
        .pgc.w{{background:var(--warn-bg);border-color:var(--warn-b)}}
        .pgc.g{{background:var(--ai-bg);border-color:var(--ai-b)}}
        .pgc-t{{font-size:11px;font-weight:700;margin-bottom:4px}}
        .pgc.w .pgc-t{{color:var(--warn)}}
        .pgc.g .pgc-t{{color:var(--ai)}}
        .pgc-d{{font-size:10.5px;line-height:1.65;color:#a0b0c8}}

    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="header-tag">НОВА ПОШТА • R&D • 2025</div>
            <h1>AI Copilot<br>Аналіз провайдерів</h1>
            <p class="subtitle">Порівняльна оцінка 14 провайдерів за методологією MSC. Вага критеріїв відповідає пріоритетам запуску контакт-центру на 1000 операторів.</p>

            <div class="legend">
                <div class="legend-item">
                    <div class="legend-dot enterprise"></div>
                    <span>80-100% — Enterprise-ready</span>
                </div>
                <div class="legend-item">
                    <div class="legend-dot needs-config"></div>
                    <span>60-79% — Закриває частину вимог</span>
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
            <button class="tab" data-tab="asis">AS-IS</button>
            <button class="tab" data-tab="tobe">TO-BE</button>
            <button class="tab active" data-tab="overall">Загальний рейтинг</button>
            <button class="tab" data-tab="copilot">Copilot</button>
            <button class="tab" data-tab="acw">Постобробка</button>
            <button class="tab" data-tab="analytics">Аналітика & QA</button>
            <button class="tab" data-tab="precall">PreCall AI</button>
            <button class="tab" data-tab="it">IT & Security</button>
            <button class="tab" data-tab="business">Бізнес</button>
            <button class="tab" data-tab="recommendations">Висновки</button>
        </div>

        <div class="tab-content active" data-content="overall">
            <div class="summary-section">
                <h3 class="summary-title">Підсумкові оцінки</h3>
                <div class="final-scores">

{provider_cards}

                </div>
            </div>

            <div class="mth-card">
              <div class="mth-card-title">Система оцінювання</div>

              <div class="mth-sub-label">Пріоритизація за MSC</div>
              <div class="msc-row">
                <div class="msc-item must">
                  <div class="msc-icon">M</div>
                  <div class="msc-body">
                    <div class="msc-top"><span class="msc-name">Must Have</span><span class="msc-badge">Критичний</span></div>
                    <p class="msc-desc">Вимоги без яких система не може бути запущена або не відповідає бізнес-меті. Блокер для релізу, найвища вага в оцінці.</p>
                  </div>
                </div>
                <div class="msc-item should">
                  <div class="msc-icon">S</div>
                  <div class="msc-body">
                    <div class="msc-top"><span class="msc-name">Should Have</span><span class="msc-badge">Важливий</span></div>
                    <p class="msc-desc">Вимоги з високою цінністю, не абсолютні блокери. Без них конкурентна перевага та ефективність суттєво нижчі.</p>
                  </div>
                </div>
                <div class="msc-item could">
                  <div class="msc-icon">C</div>
                  <div class="msc-body">
                    <div class="msc-top"><span class="msc-name">Could Have</span><span class="msc-badge">Бажаний</span></div>
                    <p class="msc-desc">Nice-to-have функції, що покращують досвід але не впливають на core-функціональність. Реалізуються за наявності ресурсів.</p>
                  </div>
                </div>
              </div>

              <div class="mth-inner-divider"></div>

              <div class="mth-sub-label">Ваговий аналіз та формула Coverage%</div>
              <div class="wf-row">
                <div class="pb-list">
                  <div class="pb-row">
                    <span class="pb-name">Must Have</span>
                    <div class="pb-track"><div class="pb-fill fill-must" style="width:60%"></div></div>
                    <span class="pb-val c-must">40–60%</span>
                  </div>
                  <div class="pb-row">
                    <span class="pb-name">Should Have</span>
                    <div class="pb-track"><div class="pb-fill fill-should" style="width:39%"></div></div>
                    <span class="pb-val c-should">25–39%</span>
                  </div>
                  <div class="pb-row">
                    <span class="pb-name">Could Have</span>
                    <div class="pb-track"><div class="pb-fill fill-could" style="width:24%"></div></div>
                    <span class="pb-val c-could">5–24%</span>
                  </div>
                  <div style="height:1px;background:#1e2d42;"></div>
                  <div class="pb-row">
                    <span class="pb-name">Разом</span>
                    <div class="pb-track"><div class="pb-fill fill-total" style="width:100%"></div></div>
                    <span class="pb-val c-total">= 100%</span>
                  </div>
                </div>
                <div class="formula-box">
                  <div class="formula-math">
                    <span class="fm-lhs">Підсумковий бал</span>
                    <span class="fm-eq">=</span>
                    <span class="fm-sigma">Σ</span>
                    <span class="fm-paren">(</span>
                    <span class="fm-frac">
                      <span class="fm-num">Оцінка провайдера</span>
                      <span class="fm-line"></span>
                      <span class="fm-den">5</span>
                    </span>
                    <span class="fm-op">×</span>
                    <span class="fm-param">Вага параметра</span>
                    <span class="fm-paren">)</span>
                    <span class="fm-op">×</span>
                    <span class="fm-x100">100</span>
                  </div>
                </div>
              </div>

              <div class="mth-inner-divider"></div>

              <div class="mth-sub-label">Шкала оцінок</div>
              <div class="scale-row">
                <div class="scale-item sg">
                  <div class="scale-score">5</div>
                  <div class="scale-body">
                    <div class="scale-name">Ідеально · 100%</div>
                    <div class="scale-track"><div class="scale-fill" style="width:100%"></div></div>
                    <p class="scale-desc">Готове рішення без кастомізації, одразу в продакшн.</p>
                  </div>
                </div>
                <div class="scale-item sl2">
                  <div class="scale-score">4</div>
                  <div class="scale-body">
                    <div class="scale-name">Добре · 80%</div>
                    <div class="scale-track"><div class="scale-fill" style="width:80%"></div></div>
                    <p class="scale-desc">Відповідає більшості вимог. Мінімальна конфігурація.</p>
                  </div>
                </div>
                <div class="scale-item sy">
                  <div class="scale-score">3</div>
                  <div class="scale-body">
                    <div class="scale-name">Задовільно · 60%</div>
                    <div class="scale-track"><div class="scale-fill" style="width:60%"></div></div>
                    <p class="scale-desc">Часткова відповідність. Потребує доопрацювання.</p>
                  </div>
                </div>
                <div class="scale-item so">
                  <div class="scale-score">2</div>
                  <div class="scale-body">
                    <div class="scale-name">Слабко · 40%</div>
                    <div class="scale-track"><div class="scale-fill" style="width:40%"></div></div>
                    <p class="scale-desc">Покриває менше половини. Потребує значної розробки.</p>
                  </div>
                </div>
                <div class="scale-item srd">
                  <div class="scale-score">1</div>
                  <div class="scale-body">
                    <div class="scale-name">Не відповідає · 20%</div>
                    <div class="scale-track"><div class="scale-fill" style="width:20%"></div></div>
                    <p class="scale-desc">Функція відсутня. Roadmap не передбачає вирішення.</p>
                  </div>
                </div>
              </div>
            </div>
        </div>

{category_tabs}

{generate_recommendations_tab()}

{generate_asis_tab()}

{generate_tobe_tab()}

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

    # Inject bpmn-js CDN assets and BPMN data before </head>
    _cdn = (
        '<link rel="stylesheet" href="https://unpkg.com/bpmn-js@17/dist/assets/diagram-js.css">\n'
        '    <link rel="stylesheet" href="https://unpkg.com/bpmn-js@17/dist/assets/bpmn-font/css/bpmn.css">\n'
        '    <script src="https://unpkg.com/bpmn-js@17/dist/bpmn-navigated-viewer.production.min.js"></script>\n'
        '    ' + _bpmn_data_script
    )
    _html = _html.replace('</head>', _cdn + '\n</head>', 1)

    return _html


def main() -> None:
    """Main function to run the conversion."""
    script_dir = Path(__file__).parent
    csv_path = script_dir / "new_data.csv"
    html_path = script_dir / "index.html"
    backup_path = script_dir / "index_backup.html"

    print(f"Reading CSV from: {csv_path}")

    categories, final_scores, tco_values = parse_csv(str(csv_path), delimiter=',')

    print(f"Parsed {len(categories)} categories:")
    for cat_id, cat in categories.items():
        print(f"  - {cat.name}: {len(cat.criteria)} criteria")

    print("\nFinal scores:")
    for provider, score in sorted(
        final_scores.items(),
        key=lambda x: _parse_score_float(x[1]),
        reverse=True,
    ):
        print(f"  - {provider}: {score}")

    if html_path.exists():
        shutil.copy(html_path, backup_path)
        print(f"\nBackup created: {backup_path}")

    def _read_bpmn(name: str) -> str:
        p = script_dir / name
        if p.exists():
            print(f"Loading BPMN: {p}")
            return p.read_text(encoding='utf-8')
        print(f"BPMN file not found (skipped): {p}")
        return ''

    asis_bpmn = _read_bpmn('asis.bpmn')
    tobe_bpmn = _read_bpmn('tobe.bpmn')
    html_content = generate_html(categories, final_scores, tco_values, asis_bpmn, tobe_bpmn)

    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"\nGenerated HTML: {html_path}")
    print(f"File size: {len(html_content):,} bytes")


if __name__ == "__main__":
    main()
