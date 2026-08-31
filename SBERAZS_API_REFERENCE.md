# SberAZS API — Справочник для LLM

## Общая информация

- **Сайт:** https://sberazs.ru
- **Тип:** SPA (React), данные загружаются через REST API
- **Назначение:** Карта заправочных станций сcrowdsource-данными о наличии топлива и транзакциях покупок

---

## API Endpoints

### Базовый URL: `https://sberazs.ru`

### 1. Поиск заправок (POST)

```
POST /api/search/suggest
Content-Type: application/json
X-Sberfuel-Session: <session_id>
```

**Тело запроса:**
```json
{
  "query": "Газпромнефть Краснодар",
  "lat": 45.035,
  "lon": 39.72
}
```

**Ответ:**
```json
{
  "suggestions": [
    {
      "id": "3237490513405107",
      "type": "fuel_station",
      "title": "Газпромнефть, заправочная станция",
      "subtitle": "Краснодарский край, Краснодар, улица Суворова, 2/1",
      "point": {"lat": 45.014343, "lon": 38.977504, "address": "..."},
      "availabilityStatus": "stale",
      "source": "station"
    }
  ]
}
```

**Важно:**
- Параметры `lat`/`lon` — координаты центра поиска (обязательны!)
- `query` — произвольный текст (название бренда, тип топлива, город)
- `type: "fuel_station"` — только АЗС (бывают другие типы)
- Фильтр по адресу: `subtitle` начинается с полного адреса

---

### 2. Детали заправки (GET)

```
GET /api/stations/{station_id}
X-Sberfuel-Session: <session_id>
```

**Ответ (ключевые поля):**
```json
{
  "station": {
    "id": "3237490513405107",
    "name": "Газпромнефть, заправочная станция",
    "address": "Краснодарский край, Краснодар, улица Суворова, 2/1",
    "postcode": "350033",
    "location": {"lat": 45.014343, "lon": 38.977504, "address": "..."},
    "availabilityStatus": "stale",
    "lastPaymentAt": "2026-09-01T00:12:53+03:00",
    "updatedAt": "2026-08-31T21:49:06.690Z",
    "fuels": [
      {"type": "ai92", "availabilityStatus": "unknown", "limitLiters": 40},
      {"type": "ai95", "availabilityStatus": "available", "lastFuelingAt": "2026-08-29T19:23:11.768Z", "limitLiters": 40},
      {"type": "diesel", "availabilityStatus": "unknown", "limitLiters": 40}
    ],
    "externalIds": {"twoGisBranchId": "3237490513405107"},
    "crowdState": {"stationId": "...", "status": "insufficient_data", "confidence": 0}
  }
}
```

**Поля `fuels`:**
- `type`: `ai92`, `ai95`, `ai98`, `ai100`, `diesel`, `propane`, `methane`
- `availabilityStatus`: `available` (есть), `unknown` (нет данных), `stale` (устарело), `unavailable` (нет)
- `limitLiters`: лимит на одно заправление (у брендов Сбер/Татнефть обычно 30-40л)

**Поля для фильтрации:**
- `lastPaymentAt` — время последней покупки (ISO 8601, МСК +03:00)
- `address` — полный адрес, для фильтрации по городу

---

### 3. Заправки по bbox (GET)

```
GET /api/stations?bbox=west,south,east,north
```

**Пример:** `?bbox=39.65,45.00,39.80,45.07`

**Ответ:**
```json
{
  "stationCount": 1,
  "stations": [
    {
      "id": "70000001030868888",
      "name": "ИП Шаов Ю.Е",
      "location": {"lat": 45.049836, "lon": 39.662705, "address": "..."},
      "fuels": []
    }
  ]
}
```

**Ограничение:** Возвращает только станции сети СберАЗС/Сбер燃料. Не включает сторонние бренды (Газпромнефть, Лукойл и т.д.). Использовать для полного поиска НЕЛЬЗЯ.

---

### 4. Заправки по тайлу карты (GET)

```
GET /api/stations/tile?z={zoom}&x={tile_x}&y={tile_y}
```

**Так же возвращает только станции сети Сбер. Ограничен в использовании.**

---

### 5. Обзор станций (GET)

```
GET /api/stations/overview?bbox=...&zoom=12
```

**Агрегирует станции в группы. Подходит для визуализации на карте, но не для получения полного списка.**

---

## Аутентификация

### Заголовок сессии

```
X-Sberfuel-Session: <session_id>
```

- `session_id` — произвольная строка (UUID или timestamp)
- Генерация: `crypto.randomUUID()` на клиенте, хранится в `sessionStorage`
- В скрипте используется: `f"fuel-catalog-{int(time.time())}"`

### Cookie (для маршрутов)

```
fuelMapsRouteSession=<session_id>; Path=/api/stations/{id}/route; Max-Age=60
```

---

## Ключевые находки

### 1. Полный поиск только через `search/suggest`

Эндпоинт `/api/stations` возвращает только станции сети Сбер. Чтобы найти ВСЕ заправки (Газпромнефть, Лукойл, Роснефть, Татнефть и др.), нужно использовать `/api/search/suggest`.

### 2. Поиск ограничивает количество результатов

`search/suggest` возвращает до ~7 результатов за запрос. Чтобы найти больше станций, нужно делать несколько запросов с разными ключевыми словами.

### 3. Фильтр по городу — по строке адреса

API не имеет параметра фильтрации по городу. Фильтрация через проверку `address` или `subtitle` на начало строки:
```python
address.startswith("Краснодарский край, Краснодар,")
```

### 4. Время покупки — `lastPaymentAt`

- Формат: ISO 8601 с таймзоной (`2026-09-01T00:12:53+03:00`)
- Время МСК (+03:00)
- Поле `updatedAt` — время обновления данных на сервере (не время покупки)

### 5. Статус наличия топлива

- `available` — данные подтверждены (есть свежая покупка)
- `unknown` — данных нет или они устарели
- `stale` — данные были, но устарели
- `unavailable` — топливо закончилось

### 6. Crowdsource-модель

Данные о наличии топлива собираются с транзакций покупок пользователей приложения СберАЗС. Если покупок нет — статус `unknown`. Это не прямое подключение к АЗС.

---

## Ограничения

1. **SSL/TLS:** На Windows с некоторыми версиями curl могут быть проблемы с SSL. Использовать Python `urllib` или Node.js `https`.
2. **Rate limiting:** API может вернуть 429 с заголовком `retry-after`. Ставить паузы между запросами (100-200мс).
3. **Кеш:** Данные кешируются на клиенте (Map с TTL 5 минут). При повторных вызовах API может возвращать 304 Not Modified.
4. **Точность координат:** Координаты в `location` могут отличаться от реального адреса (геокодинг неточный у некоторых станций).

---

## Пример использования (Python)

```python
import json, urllib.request

BASE_URL = "https://sberazs.ru"
SESSION = "my-session-123"

def api_search(query, lat, lon):
    data = json.dumps({"query": query, "lat": lat, "lon": lon}).encode()
    req = urllib.request.Request(
        f"{BASE_URL}/api/search/suggest",
        data=data,
        headers={"Content-Type": "application/json", "X-Sberfuel-Session": SESSION},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())

def api_station(station_id):
    req = urllib.request.Request(
        f"{BASE_URL}/api/stations/{station_id}",
        headers={"X-Sberfuel-Session": SESSION}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())

# Поиск
result = api_search("Газпромнефть Краснодар", 45.035, 39.72)
for s in result["suggestions"]:
    details = api_station(s["id"])
    st = details["station"]
    print(f'{st["name"]} | {st["address"]} | lastPayment: {st.get("lastPaymentAt")}')
```

---

## Структура каталога

```
C:\Users\erdi\toplivo\
├── sberazs.py              # Основной скрипт сбора данных
├── SBERAZS_API_REFERENCE.md  # Этот файл
├── SUMMARY.md              # Дополнительные заметки
└── reports/
    ├── sberazs_DD-MM-YYYY HH-MM.md  # Отчёты
    └── ...
```

## Отслеживаемые заправки (вне Краснодара)

Добавлены в `TRACKED_STATION_IDS` в `sberazs.py`:

| ID | Название | Адрес |
|----|----------|-------|
| 70000001031676386 | Газпром, АЗС | ст-ца Северская, А-146 48 км, 2 |
| 70000001030898411 | Южная нефтяная компания, АЗС | ст-ца Северская, А-146 48 км, 1 |
| 70000001076684922 | Южная нефтяная компания | ст-ца Северская, ул. Ленина, 2/1 |
| 70000001031551554 | Роснефть, АЗС | пгт Афипский, Магистральная, 4 |
| 70000001029837404 | Лукойл | пгт Энем, ул. Перова, 42 |

Чтобы добавить новую заправку — найди ID через `search/suggest` и добавь в `TRACKED_STATION_IDS`.

---

## Запуск

```bash
cd C:\Users\erdi
python toplivo\sberazs.py
```

Результат сохраняется в `toplivo/reports/sberazs_<дата>.md`.
