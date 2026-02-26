# Task 3 — Переход на Event-Driven архитектуру

## Содержимое директории

| Файл | Описание |
|------|----------|
| `problems-and-risks.md` | Анализ проблем и рисков текущей архитектуры |
| `InsureTech_event-driven-architecture.drawio` | Обновлённая контейнерная диаграмма TO-BE (Event-Driven) |

---

## Ключевые решения

### Какие взаимодействия переведены на Event-Streaming

| Было (AS-IS) | Стало (TO-BE) |
|---|---|
| `core-app` → `ins-product-aggregator` REST каждые 15 мин | `core-app` подписан на Kafka-топик `products.updated` |
| `ins-comp-settlement` → `ins-product-aggregator` REST раз в сутки | `ins-comp-settlement` подписан на `products.updated` |
| `ins-comp-settlement` → `core-app` REST батч раз в сутки | `ins-comp-settlement` подписан на Kafka-топик `policies.issued` |

**Синхронный REST сохранён только там, где он уместен:**
- Клиент → API Gateway → `core-app`: пользовательские запросы требуют немедленного ответа

### Transactional Outbox

Применён в `core-app` для публикации событий `PolicyIssued`:

```
core-app транзакция:
  BEGIN
    INSERT INTO policies (...)         -- бизнес-данные
    INSERT INTO outbox_events (...)    -- событие в той же транзакции
  COMMIT

Outbox Relay (Debezium / polling):
  SELECT * FROM outbox_events WHERE published_at IS NULL
  → PUBLISH to Kafka: policies.issued
  → UPDATE outbox_events SET published_at = NOW()
```

**Зачем:** гарантирует, что событие публикуется тогда и только тогда, когда страховка действительно оформлена. Исключает сценарии «событие опубликовано, но транзакция откатилась» и «транзакция прошла, но событие потерялось».

### Как решена проблема роста числа СК (5 → 10)

- `ins-product-aggregator` работает в фоне и подключается к каждой СК независимо
- На каждую СК — свой Circuit Breaker: сбой одной компании не влияет на данные от остальных
- Потребители (`core-app`, `ins-comp-settlement`) не знают о числе СК — они просто читают единый топик `products.updated`
- Добавление новой СК = только изменение конфигурации агрегатора, без деплоя других сервисов

---

## Открыть диаграмму

Файл `InsureTech_event-driven-architecture.drawio` можно открыть на [app.diagrams.net](https://app.diagrams.net) — File → Open from → Device.
