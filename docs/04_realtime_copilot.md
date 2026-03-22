# Блок 4: Real-time In-Call AI Copilot

> **Пріоритет**: P2 — Real-time підказки оператору
> **Swimlane**: IN-CALL AI
> **Складність**: High
> **Об'єднує**: Real-time STT Streaming, Agent Assist Backend, Copilot UI Widget у CRM

---

## Роль у архітектурі ToBe

Поки оператор розмовляє з клієнтом, AI Copilot в реальному часі:
1. Транскрибує розмову (real-time STT)
2. Аналізує транскрипт і генерує підказки (Agent Assist)
3. Відображає підказки у sidebar власної CRM НП (UI Widget)

Оператор бачить релевантні статті бази знань, FAQ-відповіді і next-best-action — автоматично, без будь-яких дій. Ціль: знизити AHT на 10–15%, підвищити FCR на 5–10%.

**Відмінність від Блоку 3**: Блок 3 — batch обробка після дзвінка. Блок 4 — streaming під час активної розмови, latency < 2 сек.

---

## Масштаб

| Параметр | Значення |
|----------|----------|
| Одночасних сесій (пік) | ~3,750 concurrent calls |
| STT потоків одночасно | ~7,500 (2 на дзвінок: оператор + клієнт) |
| Аудіо/день | ~1,000–1,500 год (75,000 хв) |
| Latency: аудіо → текст | < 1.5 сек |
| Latency: текст → підказка на екрані | < 2 сек |
| Мова | uk-UA |

---

## Архітектура (загальна)

```
Cisco CUBE (SIPREC media fork)
        │ RTP G.711 µ-law 8kHz
        ▼
SIPREC SRS Bridge
  - Декодує G.711 → PCM 16kHz
  - Буферизація 100ms chunks
  - Роздільні канали: operator + customer
        │ gRPC / WebSocket binary
        ▼
Real-time STT (Google STT Chirp)
  - Interim results (часткові, для відображення)
  - Final results (стабільні, для аналізу)
        │ incremental utterance events
        ▼
Agent Assist Backend (Cloud Run)
  - analyzeContent per utterance
  - Повертає suggestions (статті, FAQ, next-action)
        │ WebSocket push
        ▼
Copilot UI Widget (CRM sidebar)
  - Відображає підказки оператору
  - Live transcript
  - Чеклист виконання стандартів
        │ operator interaction logging
        ▼
BigQuery (suggestions_log: shown / accepted / rejected)
```

---

## Рівень 1: Real-time STT

### Варіанти STT для real-time streaming

### Варіант 1 ⭐ Рекомендований: Google STT Chirp (gRPC Streaming)

#### Переваги в контексті НП

**1. Нативна інтеграція з Google CCAI Agent Assist**
Той самий GCP проект → мінімальна latency між STT і Agent Assist. Офіційна підтримка Cisco + Google через CCAI.

**2. Phrase hints для термінів НП**
Можна задати список слів НП (назви відділень, ТТН) зі збільшеним boost — краща точність для специфіки бізнесу.

#### Ризики

| Ризик | Рівень | Деталі |
|---|---|---|
| Вартість real-time | Середній | ~$36,000/міс — найвища серед cloud STT варіантів для uk-UA |
| Google STT quota | Середній | За замовчуванням є ліміти на concurrent streaming сесій → збільшення через Google Cloud support |

**Коли обирати**: верифікований uk-UA real-time STT + нативна інтеграція з Google CCAI Agent Assist. Рекомендований варіант для Блоку 4.

---

### Порівняльна таблиця STT варіантів

| | **Google Chirp ⭐** | **Azure Speech** |
|---|---|---|
| **Вартість/міс** | ~$36,000 | ~$60,000 |
| **Протокол** | gRPC | WebSocket |
| **uk-UA WER** | Немає публічних даних | Немає публічних даних |
| **Інтеграція з Agent Assist** | Нативна (GCP) | Через адаптер |
| **Self-hosted real-time** | ❌ Нереалістично | ❌ Нереалістично |

> ⚠️ Self-hosted real-time STT при 3,750 concurrent потоках потребує 500+ GPU — економічно невиправдано. Cloud STT — єдиний реалістичний варіант.

---

## Рівень 2: Agent Assist (AI Copilot Backend)

### Роль

Agent Assist отримує фінальний utterance від STT і повертає підказки: релевантні статті з бази знань НП, FAQ-відповіді, next-best-action (наприклад, запропонувати компенсацію при скарзі).

### Варіанти Agent Assist

### Варіант 1 ⭐ Рекомендований: Google CCAI Agent Assist + Gemini

#### Переваги в контексті НП

**1. Найбільш зрілий enterprise contact center AI**
Google CCAI — єдина платформа де Cisco UCCE + AI Copilot мають офіційно підтримувану інтеграцію (CCAI Platform for UCCE).

**2. База знань + Generative AI відповіді**
Knowledge Base з 5,000–50,000 статей НП + Gemini для генеративних відповідей прямо у підказці. Не просто "знайди статтю" — а відповідь у контексті поточної розмови.

**3. Smart Reply + Summarization в одному продукті**
Agent Assist дає підказки під час дзвінка + генерує summary після. Один вендор для двох потреб.

#### Ризики

| Ризик | Рівень | Деталі |
|---|---|---|
| Вартість при 30K дзвінків | Середній | ~$18,000–21,000/міс (~$0.006–0.007/utterance × 300K–900K/день) |
| Потрібна розробка Knowledge Base | Середній | 5,000–50,000 статей uk-UA потрібно завантажити, структурувати, підтримувати |
| uk-UA якість підказок | Середній | Залежить від якості Knowledge Base. Потрібен POC |

---

### Яка AI найкраща для яких задач (In-Call Copilot)

| Задача | Найкраща AI | Чому | Де використовується |
|---|---|---|---|
| **Real-time STT + Agent Assist інтеграція** | Google STT Chirp + CCAI | Один GCP проект, офіційна UCCE підтримка, нативна інтеграція | Варіант 1 STT ⭐ |
| **Knowledge Base + Gen AI відповіді** | Google CCAI + Gemini | Єдина платформа де KB + Generative AI + Contact Center інтегровані | Agent Assist ⭐ |
| **Next-best-action підказки** | Google CCAI | Smart Reply + Intent Detection під час розмови | Agent Assist |
| **Checklist monitoring** | Custom (будь-який LLM) | Простий pattern matching per utterance | Вбудовано у pipeline |

---

## Рівень 3: Copilot UI Widget (CRM Sidebar)

### Роль

Точка взаємодії оператора з AI. Frontend-компонент що вбудовується у власну CRM НП і відображає підказки від Agent Assist у реальному часі.

> ⚠️ **Технічна складність мінімальна — UX і adoption критичні.** Якщо оператори ігнорують Copilot або вважають його незручним — весь P2 не принесе ROI.

### Що відображає widget

```
┌─────────────────────────────────┐
│  AI Copilot                     │
├─────────────────────────────────┤
│  Live Transcript                │
│  Клієнт: "...відстежити посилку │
│  59000123456789..."             │
├─────────────────────────────────┤
│  Підказки (автоматично)         │
│                                 │
│  Відстеження посилок            │
│  Введіть ТТН у поле пошуку...   │
│  Confidence: 93%                │
│  [Прийняти] [Відхилити]         │
├─────────────────────────────────┤
│  Чек-лист                       │
│  ✅ Привітання                  │
│  ✅ Ідентифікація               │
│  ⬜ Вирішення питання           │
│  ⬜ Пропозиція послуг           │
└─────────────────────────────────┘
```

### Варіанти інтеграції у власну CRM НП

| Спосіб | Опис | Складність | Рекомендація |
|--------|------|------------|-------------|
| **Web Component** | `<np-copilot-widget>` вбудовується в CRM HTML | Low | ✅ Рекомендований |
| **iframe** | Widget у sandbox iframe, комунікація через postMessage | Low | Для ізоляції CSP |
| **Finesse Gadget** | OpenSocial gadget у Cisco Finesse sidebar | Medium | Якщо Finesse — основний desktop |
| **Browser Extension** | Overlay поверх CRM | Medium | Якщо CRM неможливо модифікувати |

> **Cisco Finesse 12.6 специфіка**: НП має власну CRM — рекомендується **Варіант A**: власна CRM як основний desktop + Finesse лише для call controls (відповісти/перевести/завершити). Widget вбудовується у CRM, не у Finesse.

### Переваги UI Widget

**1. Оператор не перемикає контекст**
Підказки з'являються у sidebar власної CRM — без нових вкладок, без пошуку. Контекст не переривається.

**2. Interaction logging → навчання моделі**
Кожне "прийняти/відхилити" логується у BigQuery. З часом система вчиться які підказки оператори приймають частіше — precision зростає.

**3. Live checklist — real-time feedback оператору**
Оператор бачить які пункти стандарту вже виконані (привітання, ідентифікація) і що ще залишилось. Без QA-менеджера.

### Ризики UI Widget

| Ризик | Рівень | Деталі |
|---|---|---|
| Adoption операторів | **Високий** | Потрібен UX-дослідження з реальними операторами до розробки. Поступовий rollout: 10 → 50 → 200 → 1,000 |
| CRM модифікація | Середній | Залежить від архітектури власної CRM НП — потрібна оцінка CRM-команди |
| WebSocket масштабування | Середній | 3,750 concurrent WebSocket з'єднань — потрібен масштабований gateway |

---

## Складність впровадження

**Рівень: High**

| Компонент | Відповідальний | Складність | Час |
|-----------|--------------|------------|-----|
| SIPREC SRS Bridge (real-time mode) | НП / підрядник | High | 4–8 тижнів |
| Real-time STT інтеграція | НП / підрядник | Medium | 2–3 тижні |
| Google CCAI Agent Assist + Knowledge Base | НП / Google Partner | High | 8–12 тижнів |
| Agent Assist → WebSocket Push Gateway | НП / підрядник | Medium | 3–5 тижнів |
| Copilot UI Widget розробка | НП / підрядник | Medium | 3–5 тижнів |
| CRM інтеграція (widget embed) | НП CRM-команда | Medium | 2–4 тижні |
| Interaction logging pipeline | НП / підрядник | Low | 1–2 тижні |
| **Всього до production** | | | **20–35 тижнів** |

**Ключові ризики:**
- **SIPREC Bridge масштабування**: 7,500+ RTP потоків паралельно — найскладніша інфраструктурна задача
- **Knowledge Base якість**: від кількості і якості статей uk-UA залежить корисність підказок
- **Google STT quota**: потрібно збільшити ліміти concurrent streaming sessions через Google Cloud Support
- **Network latency**: SIPREC Bridge → STT API → Agent Assist → WebSocket → CRM — кожен hop додає затримку

---

## Оцінка вартості при 30K дзвінків/день

| Компонент | Вартість |
|---|---|
| Real-time STT (Google STT Chirp) | ~$36,000/міс |
| Google CCAI Agent Assist | ~$18,000–21,000/міс |
| WebSocket Gateway hosting | ~$1,000–2,000/міс |
| Interaction logging (BigQuery) | ~$200/міс |
| **Разом/міс** | **~$55,200–59,200** |
| **One-time розробка** | **$95,000–140,000** |

---

## Рекомендації для пілоту (MVP scope)

**Тижні 1–4 — STT якість тест:**
1. 100 архівних дзвінків НП → Google STT Chirp real-time
2. Перевірити WER особливо для: номерів ТТН, назв відділень, імен
3. Підтвердити latency < 1.5 сек при поточній мережевій архітектурі НП

**Тижні 5–8 — Live STT без Copilot:**
1. Real-time STT для 10 операторів (без Agent Assist)
2. Відображати live transcript у тестовому UI
3. Критерій: latency < 1.5 сек, WER < 12%, uptime 99.5%+

**Тижні 9–20 — Copilot пілот (100 операторів):**
1. Agent Assist + Knowledge Base (пілотний набір ~500 статей)
2. Widget у CRM sidebar
3. Метрики: AHT, FCR, % прийнятих підказок, NPS операторів

---

## Джерела та документація

- Google CCAI Agent Assist: https://cloud.google.com/agent-assist/docs
- Google CCAI pricing: https://cloud.google.com/agent-assist/pricing
- Google STT v2 Streaming: https://cloud.google.com/speech-to-text/v2/docs/streaming-recognize
- Web Components MDN: https://developer.mozilla.org/en-US/docs/Web/API/Web_components
- Cisco UCCE CCAI Integration: https://developer.cisco.com/docs/contact-center/
