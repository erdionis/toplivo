# Топливо Т-Банк — API и методы работы

## Обзор

Сервис **toplivo.tbank.ru** — одностраничное приложение (SPA) от Т-Банка для проверки наличия топлива на АЗС России. Основная функция — показать, где сейчас есть топливо, на основе транзакций покупок (кэшбэк Drive+).

---

## API эндпоинты

### Основной API для АЗС

```
GET https://toplivo.tbank.ru/api/v1/stations
```

**Query-параметры (обязательные — прямоугольник на карте):**

| Параметр | Тип | Описание |
|----------|-----|----------|
| `minLat` | float | Минимальная широта |
| `maxLat` | float | Максимальная широта |
| `minLon` | float | Минимальная долгота |
| `maxLon` | float | Максимальная долгота |

**Пример запроса (Краснодар):**
```
https://toplivo.tbank.ru/api/v1/stations?minLat=44.94&maxLat=45.13&minLon=38.82&maxLon=39.15
```

**Ответ (JSON):**
```json
{
  "status": "ok",
  "payload": [
    {
      "id": "01KX3GXSZXBT5F78Q5Z4ZMGF8M",
      "name": "Газпромнефть",
      "brand": "Газпромнефть",
      "addr": "Россия, Краснодар, Уральская улица, 96/3",
      "lat": 45.031597,
      "lon": 39.041514,
      "partnerAzsIds": ["77970", "5342", ...],
      "status": "available",
      "statusByFuelType": {
        "92": "available",
        "95": "available",
        "100": "not_available",
        "diesel": "available"
      },
      "priceByFuelType": {},
      "confidence": 0.96424487,
      "yandexOrgId": "51358165364",
      "lastTransactionAt": "2026-08-31T21:42:04.075Z",
      "recentEvents": [
        {
          "type": "transaction",
          "lastUpdatedAt": "2026-08-31T21:42:04.075Z",
          "text": "Купили топливо"
        }
      ]
    }
  ]
}
```

### Структура объекта АЗС

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | string | Уникальный ID станции |
| `name` | string | Название АЗС |
| `brand` | string\|null | Бренд (Газпромнефть, ЛУКОЙЛ, RusOil и т.д.) |
| `addr` | string | Полный адрес |
| `lat`, `lon` | float | Координаты |
| `partnerAzsIds` | string[] | Внутренние ID партнёров Т-Банка |
| `status` | string | Общий статус топлива |
| `statusByFuelType` | object | Статус по типам топлива |
| `confidence` | float | Уверенность в данных (0.0–1.0) |
| `yandexOrgId` | string | ID организации в Яндекс |
| `lastTransactionAt` | string\|null | Время последней покупки (ISO 8601, UTC) |
| `recentEvents` | array[] | Последние события на АЗС |

### Статусы топлива

| Значение | Описание |
|----------|----------|
| `available` | Топливо есть |
| `maybe_available` | Возможно есть |
| `maybe_not_available` | Возможно нет |
| `not_available` | Топлива нет |
| `no_data` | Нет данных |

### Типы топлива (ключи `statusByFuelType`)

| Ключ | Топливо |
|------|---------|
| `92` | АИ-92 |
| `95` | АИ-95 |
| `100` | АИ-100 |
| `diesel` | Дизельное топливо |

---

## Как определить координаты города/адреса

Для геокодинга используется OpenStreetMap Nominatim API:

```
GET https://nominatim.openstreetmap.org/search?q={адрес}&format=json&limit=1
```

**Пример:**
```
https://nominatim.openstreetmap.org/search?q=Краснодар+Уральская+улица+96/3&format=json&limit=1
```

**Ответ:**
```json
[{
  "lat": "45.0315804",
  "lon": "39.0415057",
  "display_name": "96/3, Uralskaya Street, ..."
}]
```

### Примерные bounding box городов

| Регион | minLat | maxLat | minLon | maxLon |
|--------|--------|--------|--------|--------|
| Краснодар | 44.94 | 45.13 | 38.82 | 39.15 |
| Станица Северская (А-146) | 44.83 | 44.88 | 38.65 | 38.72 |
| Пос. Афипский | 44.88 | 44.94 | 38.80 | 38.87 |
| Пос. Энем (Адыгея) | 44.89 | 44.97 | 38.85 | 38.96 |
| Москва | 55.49 | 55.92 | 37.35 | 37.95 |
| Санкт-Петербург | 59.82 | 60.05 | 30.15 | 30.55 |

### Отслеживаемые АЗС в окрестностях

| Бренд | Адрес | Регион |
|-------|-------|--------|
| Газпром | ст. Северская, А-146, 48-й км, 2 | Северская |
| Южная нефтяная компания | ст. Северская | Северская |
| Южная нефтяная компания | ст. Северская, А-146, 48-й км, 1 | Северская |
| Роснефть | пос. Афипский, Магистральная ул., 4 | Афипский |
| Лукойл | пос. Энем, ул. Перова, 42 | Энем (Адыгея) |

---

## Фильтрация данных

### По времени транзакции (последние N минут)

Поле `lastTransactionAt` содержит время последней покупки в **UTC** (ISO 8601).

```python
from datetime import datetime, timedelta, timezone

now = datetime.now(timezone.utc)
cutoff = now - timedelta(minutes=30)

tx_time = datetime.fromisoformat(station["lastTransactionAt"].replace("Z", "+00:00"))
if tx_time >= cutoff:
    # Покупка была за последние 30 минут
```

### По наличию определённого топлива

```python
if station["statusByFuelType"].get("95") == "available":
    # АИ-95 есть
```

---

## Другие API (вторичные)

| Эндпоинт | Метод | Описание |
|----------|-------|----------|
| `/api/v1/users/info` | GET | Информация о текущем пользователе |
| `/api/v1/auth/login` | POST | Авторизация |
| `/api/v1/auth/logout` | POST | Выход |
| `/api/v1/tasks` | GET | Список задач пользователя |
| `/api/v1/tasks/{id}/complete` | POST | Отметка задачи выполненной |
| `/api/v1/drawes` | GET | Список розыгрышей |
| `/api/v1/projects` | GET | Список проектов |

### Feature Toggles

```
POST https://cfg.tbank.ru/api-gateway/v2/getToggles
```

### SSO (идентификация)

```
POST https://id.tbank.ru/auth/ping
POST https://id.tbank.ru/auth/logout
```

---

## Архитектура приложения

- **Тип:** SPA (React), серверный рендеринг с гидратацией
- **JS Bundle:** `https://ps.t-static.ru/projects/game-center/prod/toplivo.tbank.ru/static/js/index.*.js`
- **API Base URL:** относительный `/api` (то же домен)
- **Трекинг:** `https://acdn.t-static.ru/twa/v5/bundles/generic/client.js`
- **Ошибки:** Sentry (`https://error-hub.tinkoff.ru`)
- **SSO:** `https://id.tbank.ru`

---

## Домены проекта

| Домен | Назначение |
|-------|-----------|
| `toplivo.tbank.ru` | Основной домен |
| `toplivo.t-bank-app.ru` | WebView в мобильном приложении |
| `toplivo.tbank-online.com` | Альтернативный домен |

---

## Зависимости Python-скрипта

```
requests>=2.28.0
```

Стандартная библиотека: `datetime`, `pathlib`, `json`.

---

## Второй источник: sberazs.ru

### API sberazs.ru

**Base URL:** `https://sberazs.ru`

**Headers:**
```
Content-Type: application/json
X-Sberfuel-Session: {session_id}  # произвольная строка
```

### Поиск заправок

```
POST /api/search/suggest
```

**Body:**
```json
{
  "query": "АЗС Краснодар",
  "lat": 45.035,
  "lon": 39.72
}
```

**Ответ:**
```json
{
  "suggestions": [
    {
      "id": "...",
      "type": "fuel_station",
      "title": "Газпромнефть",
      "subtitle": "Краснодарский край, Краснодар, ..."
    }
  ]
}
```

### Детали заправки

```
GET /api/stations/{station_id}
```

**Headers:** `X-Sberfuel-Session: {session_id}`

**Ответ (ключевые поля):**
```json
{
  "station": {
    "id": "...",
    "name": "Газпромнефть",
    "address": "Краснодарский край, Краснодар, ...",
    "lastPaymentAt": "2026-08-31T21:42:04+03:00",
    "fuels": [
      {
        "type": "ai92",
        "availabilityStatus": "available",
        "limitLiters": 20
      },
      {
        "type": "ai95",
        "availabilityStatus": "available"
      }
    ]
  }
}
```

### Ключевые различия между API

| Параметр | toplivo.tbank.ru | sberazs.ru |
|----------|------------------|------------|
| Метод | GET с query params | POST с JSON body |
| Авторизация | Не требуется | `X-Sberfuel-Session` (произвольная) |
| Поиск | Bounding box (minLat/maxLat/minLon/maxLon) | Текстовый запрос + координаты |
| Время покупки | `lastTransactionAt` (UTC) | `lastPaymentAt` (локальное время) |
| Типы топлива | `92`, `95`, `100`, `diesel` | `ai92`, `ai95`, `ai98`, `ai100` |
| Статусы | `available`, `not_available`, `maybe_available`, `no_data` | `available` и другие |
| Лимиты | Нет | `limitLiters` (если есть) |

---

## Текущая структура проекта

```
C:\Users\erdi\toplivo\
├── .git/
├── toplivo_krasnodar.py      # Скрипт для toplivo.tbank.ru (API)
├── sberazs.py                # Скрипт для sberazs.ru (API)
├── SUMMARY.md                # Этот файл
└── reports/                  # Директория с отчётами
    ├── toplivo_20260831_215647.md
    ├── toplivo_20260831_215700.md
    ├── sberazs_31-08-2026 22-04.md
    └── sberazs_31-08-2026 22-05.md
```

---

## Идеи для доработки

1. **Мониторинг в реальном времени** — запуск по cron/scheduler каждые N минут
2. **Уведомления** — Telegram bot / push при появлении топлива
3. **История цен** — парсинг и хранение цен на топливо
4. **Карта** — визуализация АЗС на карте (Leaflet/Mapbox)
5. **Фильтры** — по типу топлива, бренду, району, цене
6. ~~Мультигород~~ — уже реализовано (Краснодар + Северская + Афипский + Энем)
7. **API сервер** — FastAPI/Flask для получения данных по HTTP
8. **БД** — хранение истории для аналитики (SQLite/PostgreSQL)
9. **Объединение данных** — сводка из двух источников (toplivo.tbank.ru + sberazs.ru)
