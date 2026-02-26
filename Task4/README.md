# Task 4 — Проектирование продажи ОСАГО онлайн

## Содержимое директории

| Файл | Описание |
|------|----------|
| `InsureTech_osago-architecture.drawio` | Обновлённая контейнерная диаграмма TO-BE с ОСАГО |

---

## Принятые архитектурные решения

### 1. Нужно ли osago-aggregator своё хранилище данных?

**Да, Redis обязателен.**

osago-aggregator хранит in-flight состояние каждой активной заявки:

```
{
  application_id:  "uuid",
  ic_app_ids:      { "СК1": "ext-id-1", "СК2": "ext-id-2", ... },
  status_per_ic:   { "СК1": "pending", "СК2": "received", ... },
  created_at:      timestamp
}
TTL: 75 секунд
```

**Почему Redis, а не БД:**
- Данные временные (живут максимум 75 с), нет смысла в долгосрочном хранении
- TTL из коробки — автоматическая очистка заброшенных заявок
- Высокая скорость чтения/записи для частых poll-операций
- Stateless scale-out сервиса: несколько инстансов osago-aggregator читают общий Redis

### 2. Какой API osago-aggregator предоставляет core-app?

Единственный синхронный эндпоинт — **быстрый приём заявки**:

```
POST /osago/applications
Body: { user_id, vehicle_info, owner_info, driver_info, ... }

Response 202 Accepted:
{ application_id: "uuid" }
```

Агрегатор отвечает немедленно (после сохранения в Redis и запуска фоновой логики). Результаты доставляются **асинхронно через Kafka**.

**Почему не polling-эндпоинт:**
core-app не опрашивает агрегатор — результаты приходят push-моделью через `osago.quotes`.

### 3. Средство интеграции между core-app и osago-aggregator

Используется **гибридная интеграция**:

| Направление | Протокол | Обоснование |
|-------------|----------|-------------|
| core-app → osago-aggregator | **REST** (POST /osago/applications) | Нужен быстрый синхронный ответ с `application_id`, чтобы core-app мог настроить SSE-подписку для клиента |
| osago-aggregator → core-app | **Kafka** (топик `osago.quotes`) | Результаты от СК приходят асинхронно в течение до 60 с; Kafka позволяет доставить каждое предложение сразу по получении, независимо от других СК |

**Сохраняем подход Task 3:** результаты от СК передаются через Kafka-топик, как и `products.updated`. Это консистентный паттерн: все асинхронные данные от СК идут через брокер.

```
Топик: osago.quotes
Событие: OsagoQuoteReceived {
  application_id, company_id, premium,
  conditions, received_at, status (received|timeout)
}
Retention: 1 час
Partitions: по application_id (гарантирует порядок per-заявка)
```

### 4. API для веб-приложения в core-app (ОСАГО)

| Операция | Метод | Описание |
|----------|-------|----------|
| Создать заявку | `POST /api/osago/applications` | Синхронный, возвращает `application_id` |
| Получить предложения | `GET /api/osago/applications/{id}/quotes` | **SSE** — стрим предложений по мере поступления |

**Схема взаимодействия клиента:**
```
1. Клиент: POST /api/osago/applications → { application_id }
2. Клиент: GET /api/osago/applications/{id}/quotes (SSE-соединение)
3. core-app стримит события по мере получения ответов из Kafka:
   event: quote
   data: { company_id: "СК1", premium: 12500, ... }

   event: quote
   data: { company_id: "СК3", premium: 11200, ... }

   ...
4. После 60 с — событие `done` (или по получении ответов от всех СК)
```

### 5. Средство интеграции между веб-приложением и core-app

**Server-Sent Events (SSE)** — в дополнение к существующему REST.

На схеме добавлена новая стрелка (тёмно-бирюзовая, пунктирная двунаправленная) для SSE.

**Почему SSE, а не WebSocket:**
- Однонаправленный поток (сервер → клиент) — именно то, что нужно
- Проще WebSocket: нет необходимости в двустороннем протоколе
- Нативная поддержка браузерами (`EventSource` API)
- Работает через HTTP/1.1 и HTTP/2 без специальной конфигурации балансировщика
- SSE автоматически переподключается при обрыве; клиент передаёт `Last-Event-ID`

**Почему не WebSocket, не long-polling:**
- Long-polling создаёт нагрузку повторными запросами (2 500 пользователей × частый polling = дорого)
- WebSocket избыточен: данные идут только от сервера к клиенту

### 6. Паттерны отказоустойчивости

#### Rate Limiting — API Gateway
**Применено:** на уровне Nginx Ingress / API Gateway.

Пик: 2 500 одновременных пользователей. Rate Limiting защищает backend от перегрузки:
- Ограничение per-IP и per-user на создание заявок
- Защита SSE-подключений (лимит открытых соединений per-user)

**Зависит ли от нескольких инстансов:** Redis-based rate limiting (nginx-limit-req + Redis) работает корректно при нескольких репликах API Gateway.

#### Circuit Breaker — оба агрегатора → СК (per СК)
**Применено:** в `osago-aggregator` и `ins-product-aggregator`, отдельный CB на каждую СК.

- Если СК 3 недоступна — CB размыкается только для неё, остальные 9 продолжают работать
- Клиент видит предложения от доступных СК без задержки
- После timeout CB переходит в half-open и проверяет восстановление

**Зависит ли от нескольких инстансов:** при нескольких инстансах агрегатора CB должен быть shared (через Redis) или каждый инстанс имеет свой CB (допустимо, каждый сам убедится в недоступности).

#### Timeout — osago-aggregator → СК (60 сек)
**Применено:** hard timeout в 60 с — бизнес-требование.

- Для каждой СК запускается таймер при отправке заявки
- По истечении 60 с публикуется `OsagoQuoteReceived { status: timeout }` в Kafka
- Клиент видит: «СК X не ответила в срок»

#### Retry — osago-aggregator (polling GET /quote)
**Применено:** в цикле polling внутри osago-aggregator.

- GET /applications/{id}/quote опрашивается с интервалом (например, каждые 2–5 с)
- Retry только на transient-ошибки (5xx, network error), не на 404 (заявка не найдена)
- Ограничен общим timeout 60 с — retry не выходит за пределы окна

#### Timeout — core-app → osago-aggregator (REST)
**Применено:** короткий timeout (~5 с) на POST /osago/applications.

- Агрегатор должен ответить быстро (только сохранить в Redis и запустить фон)
- Если агрегатор не отвечает за 5 с → core-app возвращает клиенту ошибку немедленно

### 7. Влияние нескольких инстансов

#### core-app (несколько K8s pods)
**Проблема:** SSE-соединение клиента привязано к конкретному pod-у. Kafka-сообщение из `osago.quotes` может быть прочитано любым pod-ом в consumer group.

**Решение: Redis Pub/Sub**
```
Pod A (с SSE-соединением клиента):
  при старте SSE → SUBSCRIBE osago-quotes:{application_id}

Pod B (прочитал Kafka):
  при получении OsagoQuoteReceived → PUBLISH osago-quotes:{app_id} {quote_data}

Pod A получает через Redis Pub/Sub → отправляет клиенту по SSE
```

Sticky sessions **не нужны** — решение work-корректно при любом распределении сообщений.

#### osago-aggregator (несколько K8s pods)
Все in-flight состояния хранятся в Redis → инстансы stateless → можно добавлять/убирать pod-ы без потери заявок.

---

## Открыть диаграмму

Файл `InsureTech_osago-architecture.drawio` можно открыть на [app.diagrams.net](https://app.diagrams.net) — File → Open from → Device.
