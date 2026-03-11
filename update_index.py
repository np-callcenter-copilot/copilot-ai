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
    - Column 0: MSCW (Must/Should/Could)
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
         if len(row) > 3 and row[0] == "MSCW" and row[2] == "Weight %"),
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

        # Subtotal row (has % in weight column, no MSCW)
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
                            <div style="font-size:9px;letter-spacing:.1em;text-transform:uppercase;color:#6b7280;margin-bottom:10px;">Обмеження</div>
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
    priority_class, priority_letter = get_priority_badge(criterion.priority)
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
                            <span class="priority-badge {priority_class}">{priority_letter}</span>
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

    summary_cards = "\n".join(
        f'                    <div class="summary-card">\n'
        f'                        <h5>{p}</h5>\n'
        f'                        <div class="value">{category.subtotals.get(p, "0%")}</div>\n'
        f'                    </div>'
        for p in providers
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
                        Аналіз 14 рішень за методологією MSCW для AI Copilot контакт-центру на 1 000 операторів.
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

                <div class="components-grid">
                    <div class="component-card">
                        <div class="component-num">01</div>
                        <div class="component-tag tag-logic">Логіка</div>
                        <div class="component-name">Google CCAI / Cresta AI</div>
                        <div class="component-desc">Компонент менеджменту логіки: RAG, NLU, маршрутизація, підказки оператору</div>
                    </div>
                    <div class="component-card">
                        <div class="component-num">02</div>
                        <div class="component-tag tag-voice">Голос / STT</div>
                        <div class="component-name">ElevenLabs Scribe v2</div>
                        <div class="component-desc">Компонент розпізнавання голосу: стрімінгова транскрибація суржику з затримкою &lt;500мс</div>
                    </div>
                    <div class="component-card">
                        <div class="component-num">03</div>
                        <div class="component-tag tag-voice">Аналітика</div>
                        <div class="component-name">Ender Turing</div>
                        <div class="component-desc">Власні аналітичні модулі, глибоке розпізнавання емоцій, чіткі метрики</div>
                    </div>
                    <div class="component-card">
                        <div class="component-num">04</div>
                        <div class="component-tag tag-api">Інтеграція</div>
                        <div class="component-name">Власний інтерфейс + API</div>
                        <div class="component-desc">Компонент інтеграції: вбудовування в наявне робоче місце оператора через API</div>
                    </div>
                </div>

                <div class="rec-divider">
                    <span class="rec-divider-label">Технічна Архітектура TO-BE</span>
                    <div class="rec-divider-line"></div>
                </div>

                <div class="bpmn-scroll-wrap">

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
    return '''        <div class="tab-content" data-content="asis">
            <div class="bpmn-section">
                <div class="bpmn-hero">
                    <div>
                        <div class="bpmn-eyebrow" style="color:#ff7040">AS-IS</div>
                        <h3 class="bpmn-title">Поточний процес контакт-центру</h3>
                        <p class="bpmn-lead">6 учасників: Клієнт · Cisco · EVA (Omilia) · Запис (MP3) · Оператор · Робоче місце</p>
                    </div>
                    <div class="bpmn-chips">
                        <span class="bpmn-chip" style="border-color:#1a3060;color:#4a8cff">Cisco — телефонія</span>
                        <span class="bpmn-chip" style="border-color:#4a3000;color:#f0a030">EVA — Omilia IVR</span>
                        <span class="bpmn-chip" style="border-color:#501800;color:#ff7040">Без AI</span>
                        <span class="bpmn-chip" style="border-color:#501800;color:#ff7040">ACW вручну ~2хв</span>
                    </div>
                </div>

                <div id="bpmn-asis-container" class="bpmn-viewer-wrap">
                    <div class="bpmn-controls">
                        <button class="bpmn-ctrl-btn" onclick="_bpmnZoom('asis',1.3)" title="Zoom in">+</button>
                        <button class="bpmn-ctrl-btn" onclick="_bpmnZoom('asis',-1)" title="Fit to screen">⊡</button>
                        <button class="bpmn-ctrl-btn" onclick="_bpmnZoom('asis',0.77)" title="Zoom out">−</button>
                    </div>
                </div>

                <div class="bpmn-problems">
                    <div class="bpmn-prob-card"><div class="bpmn-prob-title">Контекст губиться при ескалації</div><div class="bpmn-prob-text">EVA ескалює на оператора → Cisco передає в чергу → оператор отримує дзвінок без жодного контексту.</div></div>
                    <div class="bpmn-prob-card"><div class="bpmn-prob-title">Черга без первинної обробки</div><div class="bpmn-prob-text">Якщо всі оператори зайняті — клієнт очікує. Немає механізму, який би обробив запит або відповів на просте питання.</div></div>
                    <div class="bpmn-prob-card"><div class="bpmn-prob-title">Пошук інформації — повністю вручну</div><div class="bpmn-prob-text">Оператор паралельно консультує і шукає: трекінг → AWIS → сайт → політики. Кілька систем, жодних підказок.</div></div>
                    <div class="bpmn-prob-card"><div class="bpmn-prob-title">Опрацювання після дзвінка — 8 кроків, ~2 хв</div><div class="bpmn-prob-text">Резюме → ЕН → «хто звертається» → тематика → підтематика → причина → вид → тон. Все вручну після кожного дзвінка.</div></div>
                    <div class="bpmn-prob-card"><div class="bpmn-prob-title">Якість консультацій не аналізується</div><div class="bpmn-prob-text">MP3 зберігається і лежить. QA — вибіркова, вручну. Більшість дзвінків ніколи не перевіряється.</div></div>
                    <div class="bpmn-prob-card"><div class="bpmn-prob-title">Немає єдиної картини ефективності</div><div class="bpmn-prob-text">Відсутній інструмент з аналітикою по КЦ: топ-причини, динаміка навантаження, якість відповідей, відхилення.</div></div>
                </div>
            </div>
        </div>'''


def generate_tobe_tab() -> str:
    """Generate HTML for the TO-BE BPMN tab."""
    return '''        <div class="tab-content" data-content="tobe">
            <div class="bpmn-section">
                <div class="bpmn-hero">
                    <div>
                        <div class="bpmn-eyebrow" style="color:#30d890">TO-BE</div>
                        <h3 class="bpmn-title">Процес з AI Асистентом</h3>
                        <p class="bpmn-lead">6 учасників: Клієнт · Cisco · Запис (MP3) · AI Асистент (4 транзакції) · Оператор · CRM</p>
                    </div>
                    <div class="bpmn-chips">
                        <span class="bpmn-chip" style="border-color:#0d4028;color:#30d890">Pre-AI: RAG + ЕН</span>
                        <span class="bpmn-chip" style="border-color:#0d4028;color:#30d890">Real-time Copilot</span>
                        <span class="bpmn-chip" style="border-color:#0d4028;color:#30d890">Post-call &le;1хв</span>
                        <span class="bpmn-chip" style="border-color:#0d4028;color:#30d890">Deep Analysis &le;10хв</span>
                    </div>
                </div>

                <div id="bpmn-tobe-container" class="bpmn-viewer-wrap">
                    <div class="bpmn-controls">
                        <button class="bpmn-ctrl-btn" onclick="_bpmnZoom('tobe',1.3)" title="Zoom in">+</button>
                        <button class="bpmn-ctrl-btn" onclick="_bpmnZoom('tobe',-1)" title="Fit to screen">⊡</button>
                        <button class="bpmn-ctrl-btn" onclick="_bpmnZoom('tobe',0.77)" title="Zoom out">−</button>
                    </div>
                </div>


                <div class="bpmn-problems" style="--prob-color: #30d890; --prob-bg: rgba(48,216,144,.07); --prob-border: rgba(48,216,144,.2);">
                    <div class="bpmn-prob-card"><div class="bpmn-prob-title" style="color:#30d890">Скоротити ACW до 13 с</div><div class="bpmn-prob-text">Автозаповнення — оператор витрачає час лише на валідацію та закриття картки.</div></div>
                    <div class="bpmn-prob-card"><div class="bpmn-prob-title" style="color:#30d890">Менше ескалацій і повторних контактів</div><div class="bpmn-prob-text">Уніфікована база знань усіх КЦ — клієнт отримує вирішення з першого дзвінка.</div></div>
                    <div class="bpmn-prob-card"><div class="bpmn-prob-title" style="color:#30d890">Однаковий рівень відповіді</div><div class="bpmn-prob-text">Менше людського фактору — однаковий рівень незалежно від досвіду оператора.</div></div>
                    <div class="bpmn-prob-card"><div class="bpmn-prob-title" style="color:#30d890">Прискорений онбординг</div><div class="bpmn-prob-text">Стандартизація знань — новий оператор з підказками працює як досвідчений.</div></div>
                    <div class="bpmn-prob-card"><div class="bpmn-prob-title" style="color:#30d890">100% аналіз якості дзвінків</div><div class="bpmn-prob-text">Системне розуміння якості замість вибіркових перевірок.</div></div>
                    <div class="bpmn-prob-card"><div class="bpmn-prob-title" style="color:#30d890">Голосовий асистент Pre-Call</div><div class="bpmn-prob-text">Зменшення навантаження через закриття простих звернень ШІ.</div></div>
                </div>
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
    sorted_providers = sorted(
        PROVIDERS,
        key=lambda p: _parse_score_float(final_scores.get(p, "0")),
        reverse=True,
    )

    # Per-provider dict of category subtotal strings
    category_scores: Dict[str, Dict[str, str]] = {
        provider: {
            cat_id: cat.subtotals.get(provider, "0%")
            for cat_id, cat in categories.items()
        }
        for provider in PROVIDERS
    }

    max_weights = {cat_id: cat.weight_percent for cat_id, cat in categories.items()}

    provider_cards = "\n".join(
        generate_provider_card(
            provider,
            rank,
            final_scores.get(provider, "0%"),
            tco_values.get(provider, "N/A"),
            category_scores[provider],
            max_weights,
        )
        for rank, provider in enumerate(sorted_providers, 1)
    )

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
            display: grid;
            grid-template-columns: repeat(5, 1fr);
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

    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="header-tag">НОВА ПОШТА • R&D • 2025</div>
            <h1>AI Copilot<br>Аналіз провайдерів</h1>
            <p class="subtitle">Порівняльна оцінка 14 провайдерів за методологією MSCW. Вага критеріїв відповідає пріоритетам запуску контакт-центру на 1000 операторів.</p>

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
            <button class="tab" data-tab="copilot">Copilot</button>
            <button class="tab" data-tab="acw">Постобробка</button>
            <button class="tab" data-tab="analytics">Аналітика & QA</button>
            <button class="tab" data-tab="precall">PreCall AI</button>
            <button class="tab" data-tab="it">IT & Security</button>
            <button class="tab" data-tab="business">Бізнес</button>
            <button class="tab" data-tab="recommendations">Висновки</button>
            <button class="tab" data-tab="asis">AS-IS</button>
            <button class="tab" data-tab="tobe">TO-BE</button>
        </div>

        <div class="tab-content active" data-content="overall">
            <div class="summary-section">
                <h3 class="summary-title">Підсумкові оцінки</h3>
                <div class="final-scores">

{provider_cards}

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

{category_tabs}

{generate_recommendations_tab()}

{generate_asis_tab()}

{generate_tobe_tab()}

    </div>

    <script>
        const tabs = document.querySelectorAll('.tab');
        const contents = document.querySelectorAll('.tab-content');
        const _bpmnViewers = {{}};

        function _initBpmnViewer(tabId) {{
            if (_bpmnViewers[tabId]) return;
            const xml = (window.__bpmnData || {{}})[tabId];
            if (!xml) return;
            const container = document.getElementById('bpmn-' + tabId + '-container');
            if (!container || typeof BpmnJS === 'undefined') return;
            const viewer = new BpmnJS({{ container }});
            _bpmnViewers[tabId] = viewer;
            viewer.importXML(xml).then(() => {{
                viewer.get('canvas').zoom('fit-viewport');
            }}).catch(err => {{
                container.innerHTML = '<p style="padding:20px;color:#888;font-size:13px">BPMN diagram requires internet connection (CDN)</p>';
            }});
        }}

        function _bpmnZoom(tabId, factor) {{
            const v = _bpmnViewers[tabId];
            if (!v) return;
            const canvas = v.get('canvas');
            if (factor === -1) {{ canvas.zoom('fit-viewport'); return; }}
            canvas.zoom(canvas.zoom() * factor);
        }}

        tabs.forEach(tab => {{
            tab.addEventListener('click', () => {{
                const targetTab = tab.dataset.tab;

                tabs.forEach(t => t.classList.remove('active'));
                contents.forEach(c => c.classList.remove('active'));

                tab.classList.add('active');
                document.querySelector(`[data-content="${{targetTab}}"]`).classList.add('active');

                if (targetTab === 'asis' || targetTab === 'tobe') {{
                    setTimeout(() => _initBpmnViewer(targetTab), 50);
                }}
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
