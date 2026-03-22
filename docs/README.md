# ToBe Архітектура — Технічні Специфікації Компонентів

> **Контекст**: Нова Пошта, контакт-центр, 1,000 операторів, 30,000 дзвінків/день, власна CRM
> **Cisco платформа**: UCCE 12.6(2) + CUCM 12.6 + CVP 12.6 + Cisco Finesse 12.6

## Пріоритет впровадження

```
Фаза 1 — Пілот (P1): Post-Call Processing | ACW | Analytics
Фаза 2 (P2):         Real-time In-Call Copilot
Фаза 3 (P3):         Глибока власна аналітика
Pre-Call AI:         Допоміжний (після підтвердження ROI від P1)
```

## Блоки системи

| # | Файл | Блок | Swimlane | Пріоритет | Складність |
|---|------|------|----------|-----------|------------|
| 1 | [01_telephony_infrastructure.md](01_telephony_infrastructure.md) | Cisco SIPREC + Медіа-форкінг | TELEPHONY | Базовий | Medium-High |
| 2 | [02_pre_call_ai.md](02_pre_call_ai.md) | Pre-Call AI (IVR до оператора) | PRE AI | Допоміжний | High |
| 3 | [03_post_call_processing_acw.md](03_post_call_processing_acw.md) | Post-Call Processing + ACW Auto-fill | DATA PIPELINE → ACW | **P1** ⭐ | High |
| 4 | [04_realtime_copilot.md](04_realtime_copilot.md) | Real-time In-Call AI Copilot | IN-CALL AI | **P2** | High |
| 5 | [05_analytics_qa.md](05_analytics_qa.md) | Post-Call Analytics + QA | POST-CALL AI | **P1+P3** ⭐ | Medium |

## Що об'єднано порівняно з попередньою структурою

| Нові блоки | Що включає |
|---|---|
| Блок 3: Post-Call Processing + ACW | STT Pipeline (batch) + LLM Post-Processing + ACW Auto-fill + Validation |
| Блок 4: Real-time In-Call Copilot | Real-time STT Streaming + Agent Assist Backend + Copilot UI Widget |

---

## Порівняння вартості (30K дзвінків/день, 2–3 хв середній дзвінок)

### Рекомендований стек (оптимум ціна/якість)

| Блок | Рішення | Місячна вартість |
|------|---------|-----------------|
| STT Batch P1 (Блок 3) | OpenAI Whisper API | ~$13,500 |
| LLM Post-processing P1 (Блок 3) | GPT-4o | ~$2,250 |
| QA Analytics P1 (Блок 5) | Custom LLM → Ender Turing | ~$500–60,000 |
| STT Real-time P2 (Блок 4) | Google STT Chirp 3 | ~$36,000 |
| In-call Copilot P2 (Блок 4) | Google CCAI Agent Assist | ~$18,000–21,000 |
| **TOTAL P1** | | **~$16,250–76,250/міс** |
| **TOTAL P1+P2** | | **~$70,250–133,250/міс** |

### One-time Costs (розробка)

| Блок | One-time |
|------|---------|
| SIPREC SRS Bridge (Блок 1) | $30,000–50,000 |
| Post-Call Pipeline + ACW (Блок 3) | $35,000–65,000 |
| Real-time Copilot + UI Widget (Блок 4) | $95,000–140,000 |
| Analytics Dashboard (Блок 5) | $30,000–50,000 |
| **TOTAL** | **$190,000–305,000** |

---

## ROI Аналіз (P1 — Post-processing + ACW)

| Метрика | Значення |
|---------|---------|
| Економія на ACW (75% скорочення) | ~$487,500/міс |
| Вартість впровадження P1 | ~$10K–70K/міс + $65K–115K one-time |
| **Payback period** | **< 1 місяць після launch** |
| **Річна економія (net)** | **~$4.9M–5.3M/рік** |

---

## Архітектурна діаграма

```
                    ┌─────────────────────────────────────────────┐
                    │           NOVA POSHTA CONTACT CENTER         │
                    │                                             │
Клієнт  ──────────►│ Cisco CUBE  ──── SIPREC Fork ─────────────► │
                    │    │                    │                   │
                    │    ▼                    ▼                   │
                    │ Оператор           SIPREC SRS Bridge        │
                    │ (CRM + Copilot)         │                   │
                    │    ▲           ┌────────┴────────┐          │
                    │    │           ▼                 ▼          │
                    │    │     Real-time STT      Batch STT       │
                    │    │     (Google Chirp)     (OpenAI Whisper)│
                    │    │           │                 │          │
                    │    │           ▼                 ▼          │
                    │    │     Agent Assist       LLM Pipeline    │
                    │    │     (Google CCAI)      (Claude Haiku)  │
                    │    │           │                 │          │
                    │    └───────────┘                 ▼          │
                    │    [Підказки]              ACW Auto-fill     │
                    │    [Чеклист]               + Analytics       │
                    │    [Live transcript]        (Ender Turing    │
                    │                             + BigQuery)      │
                    └─────────────────────────────────────────────┘
```

---

## Рекомендований план впровадження

```
Місяць 1–3   │ SIPREC Bridge + STT Batch + LLM ACW (Блок 1, 3)
              │ → 100% дзвінків з auto-fill ACW
              │ → ROI: ~$487K/міс економія

Місяць 4–6   │ Custom QA Scoring + BigQuery Analytics (Блок 5 P1)
              │ → 100% QA coverage без семплування

Місяць 7–9   │ Real-time STT + Agent Assist Copilot (пілот 100 операторів) (Блок 4)
              │ → FCR +5–10%, AHT -10–15%

Місяць 10–12 │ Full rollout Copilot (1,000 операторів) + Ender Turing (Блок 5 P2)
              │ → Pre-Call AI (опціонально, Блок 2)
```
