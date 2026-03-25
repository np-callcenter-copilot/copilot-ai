# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a single-page HTML dashboard for comparing AI Copilot providers for a contact center (Нова Пошта context). The dashboard is generated from a CSV data file via a Python script.

## Key Command

To regenerate `index.html` from updated CSV data:

```bash
python3 update_index.py
```

This automatically backs up the current `index.html` to `index_backup.html` before overwriting.

## Architecture

The project has two artifacts:

- **`new_data.csv`** — Source of truth. Contains provider scores structured with MSCW priorities, weights, criterion names, descriptions, and numeric scores (1–5) per provider.
- **`update_index.py`** — Converts the CSV into a fully self-contained `index.html`. The script contains both the data parsing logic and the entire HTML/CSS/JS template as Python f-strings. No external build tools, no dependencies beyond the Python standard library.
- **`index.html`** — Generated output. Do not edit directly; changes will be overwritten on the next script run.

## CSV Structure

The CSV header row is identified by `MSCW` in column 0 and `Weight %` in column 2. Rows are interpreted as:
- **Category headers**: `MSCW` column matches a key in `CATEGORY_MAP`
- **Criterion rows**: `MSCW` is `Must`, `Should`, or `Could`; scores are in columns 4–15
- **Subtotal rows**: no `MSCW`, weight column contains `%`
- **Final score row**: weight is `100%`, description contains `Загальна оцінка`
- **TCO row**: score cells match pattern `\d+ - \d+000`

Provider column order in the CSV must match the `PROVIDERS` list in the script (columns 4–15).

## Providers and Categories

**12 providers** (in column order): Google Cloud CCAI, Ender Turing, NICE, Microsoft Copilot, Genesys Cloud CX, NICE Cognigy, Live Person, Ringo stat, Deca gon, Eleven Labs, Poly AI, Get Vocal.

**6 categories** with their weights: Copilot (15%), Постобробка/ACW (25%), Аналітика & QA (15%), PreCall AI (5%), IT & Security (30%), Бізнес (10%).

## Пріоритет впровадження (docs/)

Завжди використовувати описові назви блоків, **не номери і не "P1/P2/P3"**:

| Назва | Опис | Ітерація |
|---|---|---|
| **Копіювання аудіо** | Технічна основа — без неї нічого не працює | Разом з Ітерацією 1 |
| **Постобробка і ACW** | Автоматичне заповнення картки після дзвінка | **Ітерація 1 ⭐ Найвищий пріоритет** |
| **Аналітика і QA** | 100% контроль якості дзвінків, тренди, coaching | **Ітерація 1 ⭐ Найвищий пріоритет** |
| **Підказки оператору** | AI-підказки під час активного дзвінка | Ітерація 2 |
| **Голосовий асистент** | AI розмовляє з клієнтом до з'єднання з оператором | Ітерація 3 |

**Ітерація 1** (Постобробка + Аналітика) — найвищий пріоритет: найшвидший ROI, окупність < 1 місяця, найнижча складність впровадження.
**Ітерація 2** (Підказки оператору) — після підтвердження ROI від Ітерації 1.
**Ітерація 3** (Голосовий асистент) — найдорожчий і найскладніший компонент, лише після підтвердження ROI від Ітерацій 1 і 2.

У всіх документах `docs/` використовувати ці назви замість "Блок X" або "P1/P2/P3".

## STT Provider Constraints (docs/)

**Deepgram** — виключений з усієї документації. Deepgram для uk-UA підтримує **лише транскрипцію** (STT). Sentiment analysis, entity extraction, topic modeling, summarization — доступні тільки для англійської мови. Не включати Deepgram у жодні варіанти чи рекомендації в `docs/`.

**ElevenLabs** — використовується **виключно в Блоці 2 (Pre-Call AI)** як голосовий асистент (ElevenLabs Conversational AI). ElevenLabs **не слухає розмову оператора з клієнтом** — це продукт що розмовляє з клієнтом до з'єднання з оператором. Не включати ElevenLabs як STT-провайдер для Блоків 3, 4, 5.

**Верифіковані STT-провайдери для uk-UA (для транскрипції розмов оператор-клієнт):**
- **Google STT Chirp 3** — верифікована підтримка uk-UA, real-time streaming та batch режими. **Рекомендований для Постобробки і ACW (Варіант 1 ⭐)** — єдиний хмарний варіант що надійно відповідає вимозі ACW < 15 сек. Також рекомендований для Підказок оператору (real-time).
- **OpenAI Whisper API** — верифікована підтримка uk-UA (Whisper large-v3), **тільки batch режим після завершення дзвінка**. $0.006/хв — найдешевший хмарний STT. **Не відповідає вимозі ACW < 15 сек** (batch дає 15–35 сек затримки). Розглядати тільки якщо вимогу переглянуто до < 40 сек.
- **Azure Speech** — верифікована підтримка uk-UA. Альтернатива Google для real-time.
- **Azure Speech** — верифікована підтримка uk-UA. Альтернатива Google для real-time.
- **OpenAI Whisper Large v3 self-hosted** — підтримує uk-UA, але публічних WER-даних немає. Доступний як self-hosted (faster-whisper) для Блоку 3 Варіант 3.

## Термінологія (docs/)

**РМ КЦ** (Робоче Місце Контакт-Центру) — правильна назва системи оператора НП. Використовувати замість "CRM", "власна CRM НП", "CRM НП" у всіх документах `docs/`. При першому згадуванні в документі: "РМ КЦ (CRM)", далі — просто "РМ КЦ".

## AI Provider Model (docs/)

**Vendor-managed продукти** (Google CCAI, Google STT, Gemini через Vertex AI) — мають готову інфраструктуру, managed сервіси (Cloud Run, Pub/Sub, GCS triggers), офіційну підтримку і партнерські програми. One-time розробка нижча, операційна підтримка простіша.

**Raw API провайдери** (OpenAI Whisper, GPT-4o, Claude) — надають лише HTTP endpoint'и без готової contact center інтеграції. Вся pipeline розробка (SRS Bridge, оркестрація, error handling, retry логіка, моніторинг, CRM connector) — повністю на команді розробки НП. Це збільшує one-time вартість і терміни впровадження, а також вимагає підтримки команди після launch. **Це мінус для замовника**, але якщо cloud-економіка краща — варіант залишається в розгляді.

При порівнянні варіантів завжди вказувати:
- Чи є провайдер vendor-managed продуктом або raw API
- Який обсяг розробки падає на команду НП
- One-time вартість розробки поряд з місячною cloud-вартістю

## Modifying the Dashboard

- **To change HTML/CSS/JS**: edit the f-string templates inside `generate_html()`, `generate_provider_card()`, `generate_criteria_row()`, etc. in `update_index.py`, then re-run the script.
- **To add/remove providers**: update both `PROVIDERS` and `PROVIDER_DISPLAY_NAMES` in `update_index.py` and the corresponding CSV columns.
- **To add/rename categories**: update `CATEGORY_MAP` in `update_index.py`.
- **Score coloring**: `get_score_class()` maps score ≥5→`s5`, ≥4→`s4`, ≥3→`s3`, ≥2→`s2`, else→`s1`.
