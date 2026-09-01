# GdeBenz.ru — Справочник по API и работе с сайтом

**Дата создания:** 01.09.2026
**Назначение:** Справочник для LLM-сессий по парсингу данных с gdebenz.ru

---

## 1. Общая информация

- **Сайт:** https://gdebenz.ru (запасной: gdebenz.org)
- **API домен:** https://gdebenz.ru/api/ (не api.gdebenz.ru — там 404)
- **Тип:** SPA (React/Vue), данные загружаются через REST API
- **Данные:** Краудсорсинг — водители сами отмечают наличие топлива, очереди, лимиты

---

## 2. Аутентификация

### Runtime-токен (обязателен для GET-запросов)

```python
# Получение токена
resp = requests.get("https://gdebenz.ru/api/rt", headers=HEADERS)
rt_token = resp.json()["rt"]  # например "e7bb04940efdd2fa4641a8da"

# Использование в запросах
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://gdebenz.ru/",
    "X-RT": rt_token
}
```

### Version-токен (для POST-запросов)

```python
resp = requests.get("https://gdebenz.ru/api/vt", headers=HEADERS)
vt_token = resp.json()["vt"]  # передаётся как поле "vt" в JSON body
```

**Важно:**
- Токены живут ~30 минут (ttl: 1800)
- Обновлять перед каждым пакетом запросов
- Заголовок `X-RT` обязателен для всех GET-запросов к API

---

## 3. Основные эндпоинты

### АЗС

| Эндпоинт | Метод | Описание |
|----------|-------|----------|
| `/api/stations?lat1=&lon1=&lat2=&lon2=` | GET | АЗС в bounding box |
| `/api/nearby?lat=&lon=&radius_km=20&full=1` | GET | Ближайшие АЗС (требует X-RT) |
| `/api/comments/{osm_id}` | GET | Детали станции (уверенность, время, статус) |
| `/api/comments/{osm_id}/recent?limit=12` | GET | Последние отметки водителей |

### Поиск

| Эндпоинт | Метод | Описание |
|----------|-------|----------|
| `/api/search?q=...` | GET | Поиск АЗС по названию |
| `/api/cities?q=...` | GET | Поиск города (возвращает lat, lon, zoom) |
| `/api/geosuggest?q=...` | GET | Гео-подсказки |
| `/api/reverse-city?lat=&lon=` | GET | Обратное геокодирование города |

### Пользователь

| Эндпоинт | Метод | Описание |
|----------|-------|----------|
| `/api/me/state` | GET | Состояние пользователя |
| `/api/mystate?cid=` | GET | Состояние с ID канала |

---

## 4. Формат ответов

### /api/stations (bbox)

```json
[
  {
    "osm_id": "usr_ftjulj3dDJw",
    "name": "Газпром",
    "brand": "Газпром",
    "lat": 44.84368,
    "lon": 38.65290,
    "addr": "",
    "status": "yes",          // yes|no|queue|low|null
    "fuels_now": "92,95,ДТ",  // перечисление доступного топлива
    "dt_only": 0,
    "conflict": null,
    "prices_now": {
      "92": {"p": 65.55, "n": 0, "t": "2026-09-01 06:28:32"},
      "95": {"p": 72.1, "n": 0, "t": "2026-09-01 06:28:32"},
      "ДТ": {"p": 76.7, "n": 0, "t": "2026-09-01 06:28:32"}
    },
    "meta": {"f": ["95", "ДТ"]}  //.array of fuel types available
  }
]
```

### /api/comments/{osm_id}

```json
{
  "status": "yes",              // текущий статус
  "confirmations": 2,           // кол-во подтверждений
  "confirmationsFresh": 4,      // свежие подтверждения
  "realCount": 5,               // реальное кол-во отметок
  "updated": "2026-09-01 07:05:44",  // UTC время обновления!
  "confidenceBase": 0.8549,     // уверенность (0-1)
  "fuelsNow": "92,95,ДТ",      // доступное топливо
  "limited": true,              // есть лимиты
  "limits": {
    "q": "yes",                 // очередь
    "qn": "20-50",             // размер очереди
    "lim": null,               // лимит литров
    "cash": false              // только наличные
  },
  "addr": "",
  "brand": "Газпром",
  "name": "Газпром",
  "lat": 44.84368,
  "lon": 38.65290
}
```

**Важно:** Поле `updated` — это **UTC время**. Для MSK нужно прибавить +3 часа!

### /api/comments/{osm_id}/recent

```json
[
  {
    "status": "yes",
    "detail": "92, 95",
    "created_at": "2026-09-01 06:01:15",  // UTC
    "edited": false,
    "on_site": true,
    "svc": true
  }
]
```

### /api/cities?q=...

```json
{
  "results": [
    {
      "name": "Северская",
      "sub": "Россия",
      "lat": 44.85393,
      "lon": 38.67924,
      "zoom": 12
    }
  ]
}
```

---

## 5. Статусы АЗС

| Статус | Значение | Описание |
|--------|----------|----------|
| `yes` | Есть топливо | Подтверждено водителями |
| `no` | Нет топлива | Водители не смогли заправиться |
| `queue` | Очередь | Топливо есть, но очередь |
| `low` | Мало | Остаётся немного |
| `null` | Нет данных | Отметок нет |

---

## 6. Bounding box для городов

### Краснодар
```
Центр: 45.0355, 38.9753
BBOX_SIZE = 0.15 (примерно 15 км)
Сетка: 3x3 = 9 областей
```

### Северская
```
Центр: 44.8539, 38.6792
BBOX: lat1=44.80, lon1=38.60, lat2=44.90, lon2=38.75
```

### Афипский
```
Центр: 44.87, 38.78
BBOX: lat1=44.85, lon1=38.75, lat2=44.90, lon2=38.82
```

### Энем
```
Центр: 44.92, 38.88
BBOX: lat1=44.88, lon1=38.80, lat2=44.96, lon2=38.92
```

---

## 7. Алгоритм поиска АЗС

```
1. Получить RT-токен: GET /api/rt
2. Сгенерировать bbox вокруг центра города (3x3 сетка, шаг 0.15°)
3. Для каждого bbox: GET /api/stations?lat1=&lon1=&lat2=&lon2=
4. Дедупликация по osm_id
5. Фильтрация по наличию нужного топлива (fuels_now или meta.f)
6. Для каждой станции: GET /api/comments/{osm_id}
7. Фильтрация по времени updated (UTC → MSK: +3 часа)
8. Сохранение в markdown
```

---

## 8. Известные станции (отслеживаемые)

| Название | Адрес | osm_id | Координаты |
|----------|-------|--------|------------|
| Газпром | ст. Северская, А-146, 48-й км, 2 | usr_ftjulj3dDJw | 44.84368, 38.65290 |
| Южная нефтяная компания | ст. Северская, ул. Ленина, 2 | 2892720110 | 44.83291, 38.66340 |
| ЮНК | ст. Северская, ул. Западная, 3 | usr_nnYnvLUqBHA | 44.84434, 38.65641 |
| Роснефть | Афипский, Магистральная ул., 4 | w229004932 | 44.89293, 38.85808 |
| Лукойл | Энем, ул. Перова, 42 | usr_KgInCQzo1og | 44.90898, 38.88211 |

---

## 9. Лимиты запросов

- API может возвращать **502 Bad Gateway** при частых запросах
- Рекомендуется: **пауза 1 сек** между bbox-запросами, **0.3-0.5 сек** между detail-запросами
- При 502: retry с экспоненциальной задержкой (2 сек, 4 сек, 6 сек)
- Максимум 3 попытки

---

## 10. Особенности

### Время
- Все временные метки в API — **UTC**
- Для отображения в MSK: ` UTC_time + timedelta(hours=3) `
- Сравнение с локальным временем: `datetime.now()` (MSK) vs `updated` (UTC)

### osm_id
- Формат: `usr_XXXX` (пользовательские) или числовой `1234567890`
- Уникальный идентификатор станции

### Цены
- Цены хранятся в `prices_now` с полем `t` (время обновления, UTC)
- Формат: `{"95": {"p": 72.1, "n": 0, "t": "2026-09-01 06:28:32"}}`
- `p` — цена, `n` — кол-во голосов, `t` — время

### Лимиты
- `limits.q` — очередь (yes/no)
- `limits.qn` — размер очереди ("20-50", "50-100")
- `limits.lim` — лимит литров
- `limits.cash` — только наличные

---

## 11. Пример скрипта (минимальный)

```python
import requests
import time
from datetime import datetime, timedelta

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://gdebenz.ru/",
}

def get_rt():
    return requests.get("https://gdebenz.ru/api/rt", headers=HEADERS).json()["rt"]

def get_stations(lat1, lon1, lat2, lon2, rt):
    h = {**HEADERS, "X-RT": rt}
    return requests.get("https://gdebenz.ru/api/stations",
                        params={"lat1": lat1, "lon1": lon1, "lat2": lat2, "lon2": lon2},
                        headers=h).json()

def get_details(osm_id, rt):
    h = {**HEADERS, "X-RT": rt}
    return requests.get(f"https://gdebenz.ru/api/comments/{osm_id}", headers=h).json()

# Использование
rt = get_rt()
stations = get_stations(44.80, 38.60, 44.90, 38.75, rt)
for s in stations[:5]:
    det = get_details(s["osm_id"], rt)
    updated = datetime.strptime(det["updated"], "%Y-%m-%d %H:%M:%S") + timedelta(hours=3)
    print(f"{det['name']} | {det['addr']} | {det['confidenceBase']:.0%} | {updated}")
```

---

## 12. Файлы проекта

| Файл | Назначение |
|------|------------|
| `C:\Users\erdi\toplivo\search_fuel.py` | Основной скрипт мониторинга |
| `C:\Users\erdi\toplivo\reports\*.md` | Отчёты в формате markdown |

---

## 13. Частые ошибки

1. **404 на api.gdebenz.ru** — использовать `gdebenz.ru/api/`, а не `api.gdebenz.ru/api/`
2. **502 Bad Gateway** — слишком частые запросы, добавить паузы
3. **Пустой updated** — станция без отметок, пропускать
4. **Время не совпадает** — API возвращает UTC, не MSK
5. **Нет X-RT** — все GET-запросы требуют заголовок `X-RT`
