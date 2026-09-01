"""
Объединённый мониторинг заправок Краснодара и окрестностей.
Опрашивает 2 сайта: toplivo.tbank.ru и sberazs.ru.
Формирует единый отчёт с пересечением и отдельными таблицами.

Запуск:
  python monitor.py              — одноразовый запуск
  python monitor.py --loop       — цикл каждые 30 минут
  python monitor.py --loop 5     — цикл каждые 5 минут
  pythonw monitor.py --loop      — в фоне без окна
"""

import sys
import json
import time
import subprocess
import urllib.request
import urllib.error
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Загрузка .env
def load_env():
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                import os
                os.environ[key.strip()] = value.strip()

load_env()

TELEGRAM_BOT_TOKEN = __import__("os").environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = __import__("os").environ.get("TELEGRAM_CHAT_ID", "")


# ============================================================
# Telegram
# ============================================================


def yandex_maps_url(address: str) -> str:
    """Генерация ссылки на Яндекс.Карты."""
    import urllib.parse
    query = urllib.parse.quote(address)
    return f"https://yandex.ru/maps/?text={query}"


def format_telegram_message(matches: list, filepath: Path) -> str:
    """Форматирование сообщения для Telegram."""
    lines = ["⛽ <b>Пересечение</b> (2+ источника):", ""]

    if matches:
        for i, s in enumerate(matches, 1):
            addr = s.get("address", "—")
            name = s.get("name", "—")
            url = yandex_maps_url(addr)
            last_tx = s.get("last_transaction")
            tx_str = format_datetime(last_tx) if last_tx else "—"

            # Уверенность из gdebenz (если есть)
            gb_conf = ""
            if s.get("gb_confidence") and s["gb_confidence"] > 0:
                gb_conf = f" | 📊 {s['gb_confidence']:.0f}%"

            # Очередь от gdebenz
            gb_queue = ""
            if s.get("gb_queue_info"):
                gb_queue = f" | 🚗 {s['gb_queue_info']}"
            elif s.get("gb_crowd"):
                gb_queue = f" | 🚗 {s['gb_crowd']}"

            lines.append(f"{i}. <b>{name}</b> — {addr}")
            lines.append(f"   📍 <a href=\"{url}\">Маршрут</a> | 🕐 {tx_str}{gb_conf}{gb_queue}")
            lines.append("")  # пустая строка между пунктами
    else:
        lines.append("_Нет пересечений._")

    lines.append("")
    report_url = f"https://github.com/erdionis/toplivo/blob/main/reports/{filepath.name}"
    lines.append(f"📄 <a href=\"{report_url}\">Детали отчёта</a>")

    return "\n".join(lines)


def send_telegram(message: str) -> bool:
    """Отправка сообщения в Telegram (с разбивкой на части при необходимости)."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram: токен или chat_id не заданы, пропускаю")
        return False

    MAX_LEN = 4000  # Лимит Telegram (4096, но с запасом)
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    # Разбиваем на части по лимиту
    messages = []
    if len(message) <= MAX_LEN:
        messages = [message]
    else:
        # Разбиваем по станциям (каждая начинается с数字+точка)
        import re
        parts = re.split(r'(?=\n\d+\. )', message)
        current = ""
        for part in parts:
            if len(current) + len(part) > MAX_LEN and current:
                messages.append(current)
                current = part
            else:
                current += part
        if current:
            messages.append(current)
        print(f"Telegram: сообщение разбито на {len(messages)} частей")

    sent = False
    for msg in messages:
        data = json.dumps({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }).encode("utf-8")

        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                if result.get("ok"):
                    print(f"Telegram: часть {len(messages)} сообщений отправлена")
                    sent = True
                else:
                    print(f"Telegram ошибка: {result.get('description', 'unknown')}")
                    return False
        except Exception as e:
            print(f"Telegram ошибка: {e}")
            return False

    return sent

# ============================================================
# Общие настройки
# ============================================================

LIMIT_MINUTES = 45  # TB и Sber: покупка за 45 минут
GB_LIMIT_MINUTES = 240  # gdebenz: отметка за 4 часа (пользователи)
MSK = timezone(timedelta(hours=3))

# 5 отслеживаемых заправок вне Краснодара
TRACKED_STATIONS = [
    {
        "name": "Газпром",
        "address_pattern": "Северская, А-146, 48-й километр, 2",
        "tb_bounds": {"minLat": 44.83, "maxLat": 44.88, "minLon": 38.65, "maxLon": 38.72},
        "tb_addr_filter": ["Северская", "А-146", "48-й километр, 2"],
        "sber_id": "70000001031676386",
    },
    {
        "name": "Южная нефтяная компания",
        "address_pattern": "Северская, А-146, 48-й километр, 1",
        "tb_bounds": {"minLat": 44.83, "maxLat": 44.88, "minLon": 38.65, "maxLon": 38.72},
        "tb_addr_filter": ["Северская", "А-146", "48-й километр, 1"],
        "sber_id": "70000001030898411",
    },
    {
        "name": "Южная нефтяная компания (Северская)",
        "address_pattern": "Северская",
        "tb_bounds": {"minLat": 44.83, "maxLat": 44.88, "minLon": 38.65, "maxLon": 38.72},
        "tb_addr_filter": ["Северская"],
        "sber_id": "70000001076684922",
    },
    {
        "name": "Роснефть",
        "address_pattern": "Афипский, Магистральная, 4",
        "tb_bounds": {"minLat": 44.88, "maxLat": 44.94, "minLon": 38.80, "maxLon": 38.87},
        "tb_addr_filter": ["Афипск", "Магистральная"],
        "sber_id": "70000001031551554",
    },
    {
        "name": "Лукойл",
        "address_pattern": "Энем, ул. Перова, 42",
        "tb_bounds": {"minLat": 44.89, "maxLat": 44.97, "minLon": 38.85, "maxLon": 38.96},
        "tb_addr_filter": ["Энем", "Перова, 42"],
        "sber_id": "70000001029837404",
    },
]

# Регион Краснодара
KRASNODAR_BOUNDS = {
    "minLat": 44.94, "maxLat": 45.13,
    "minLon": 38.82, "maxLon": 39.15,
}

# Поисковые запросы для sberazs.ru
SBER_SEARCH_QUERIES = [
    "АЗС Краснодар", "заправка Краснодар", "Газпромнефть Краснодар",
    "Лукойл Краснодар", "Роснефть Краснодар", "Татнефть Краснодар",
    "Атан Краснодар", "Уфимнефть Краснодар", "Русойл Краснодар",
    "Дельта Краснодар", "Сивнефть Краснодар", "Петрол Краснодар",
    "Башнефть Краснодар", "СберАЗС Краснодар", "Магнит Краснодар",
    "Краснодар АИ-92", "Краснодар АИ-95", "Краснодар АИ-98",
]

SBER_BASE_URL = "https://sberazs.ru"
SBER_CITY_PREFIX = "Краснодарский край, Краснодар,"

# ============================================================
# gdebenz.ru API
# ============================================================

GB_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://gdebenz.ru/",
}

GB_RT_URL = "https://gdebenz.ru/api/rt"
GB_STATIONS_URL = "https://gdebenz.ru/api/stations"
GB_COMMENTS_URL = "https://gdebenz.ru/api/comments"

# Центр Краснодара для bbox-поиска
GB_KRASNODAR_CENTER = (45.0355, 38.9753)
GB_BBOX_SIZE = 0.15

# 5 отслеживаемых заправок (osm_id)
GB_TRACKED_IDS = [
    "usr_ftjulj3dDJw",   # Газпром, ст. Северская
    "2892720110",         # Южная нефтяная компания, ст. Северская
    "usr_nnYnvLUqBHA",   # ЮНК, ст. Северская
    "w229004932",         # Роснефть, Афипский
    "usr_KgInCQzo1og",   # Лукойл, Энем
]

# ============================================================
# toplivo.tbank.ru API
# ============================================================

TB_API_URL = "https://toplivo.tbank.ru/api/v1/stations"


def tb_fetch_stations(bounds: dict) -> list[dict]:
    """Получение АЗС от Т-Банка по bounding box."""
    response = requests.get(TB_API_URL, params=bounds, timeout=15)
    response.raise_for_status()
    data = response.json()
    if data.get("status") != "ok":
        raise ValueError(f"TB API: {data.get('status')}")
    return data.get("payload", [])


def tb_matches_filters(station: dict, filters: list[str] | None) -> bool:
    """Проверка соответствия АЗС фильтрам адреса."""
    if not filters:
        return True
    addr = station.get("addr", "").lower()
    return any(f.lower() in addr for f in filters)


def tb_normalize(station: dict) -> dict:
    """Нормализация данных АЗС от Т-Банка в единый формат."""
    fuel = station.get("statusByFuelType", {})
    # Бензин: есть АИ-92 или АИ-95 или АИ-100
    has_fuel = any(fuel.get(t) in ("available", "maybe_available") for t in ("92", "95", "100"))
    # Статус АИ-95
    ai95 = fuel.get("95", "no_data")

    last_tx = station.get("lastTransactionAt")
    minutes_ago = None
    last_tx_msk = None
    if last_tx:
        tx_time = datetime.fromisoformat(last_tx.replace("Z", "+00:00"))
        minutes_ago = int((datetime.now(timezone.utc) - tx_time).total_seconds() / 60)
        last_tx_msk = tx_time.astimezone(MSK)

    confidence = station.get("confidence", 0) * 100

    return {
        "source": "tb",
        "id": station.get("id", ""),
        "name": station.get("name", "—"),
        "brand": station.get("brand") or "—",
        "address": station.get("addr", "—"),
        "confidence": confidence,
        "ai95_status": ai95,
        "has_fuel": has_fuel,
        "minutes_ago": minutes_ago,
        "last_transaction": last_tx_msk,
        "fuel_detail": fuel,
        "lat": station.get("lat"),
        "lon": station.get("lon"),
    }


# ============================================================
# sberazs.ru API
# ============================================================


def sber_api_post(path: str, body: dict, session_id: str) -> dict:
    """POST-запрос к API СберАЗС."""
    url = SBER_BASE_URL + path
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json", "X-Sberfuel-Session": session_id},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def sber_api_get(path: str, session_id: str) -> dict:
    """GET-запрос к API СберАЗС."""
    url = SBER_BASE_URL + path
    req = urllib.request.Request(
        url, headers={"X-Sberfuel-Session": session_id}, method="GET",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def sber_search_stations(query: str, session_id: str) -> list:
    """Поиск АЗС через search/suggest."""
    result = sber_api_post(
        "/api/search/suggest",
        {"query": query, "lat": 45.035, "lon": 39.72},
        session_id,
    )
    return [
        s for s in result.get("suggestions", [])
        if s.get("type") == "fuel_station"
        and s.get("subtitle", "").startswith(SBER_CITY_PREFIX)
    ]


def sber_get_station_details(station_id: str, session_id: str) -> dict | None:
    """Получение деталей АЗС по ID."""
    try:
        result = sber_api_get(f"/api/stations/{station_id}", session_id)
        return result.get("station")
    except (urllib.error.HTTPError, Exception):
        return None


def sber_collect_krasnodar(session_id: str) -> dict[str, dict]:
    """Сбор всех уникальных АЗС в Краснодаре."""
    stations = {}
    for q in SBER_SEARCH_QUERIES:
        try:
            for s in sber_search_stations(q, session_id):
                sid = s["id"]
                if sid not in stations:
                    stations[sid] = s
        except Exception:
            pass
        time.sleep(0.15)
    return stations


def sber_normalize(station: dict, details: dict | None) -> dict:
    """Нормализация данных АЗС от СберАЗС в единый формат."""
    if not details:
        # Используем данные поиска (availabilityStatus, point)
        avail = station.get("availabilityStatus", "unknown")
        has_fuel = avail in ("available", "stale")
        point = station.get("point", {})
        return {
            "source": "sber",
            "id": station.get("id", ""),
            "name": station.get("title", "—"),
            "brand": "—",
            "address": station.get("subtitle", "—"),
            "confidence": 0,
            "ai95_status": "unknown" if avail in ("available", "stale") else "no_data",
            "has_fuel": has_fuel,
            "minutes_ago": None,
            "last_transaction": None,
            "fuel_detail": {},
            "lat": point.get("lat"),
            "lon": point.get("lon"),
        }

    fuels = details.get("fuels", [])
    gasoline = [f for f in fuels if f.get("type") in ("ai92", "ai95", "ai98", "ai100")]
    has_fuel = len(gasoline) > 0

    # Статус АИ-95
    ai95_fuel = next((f for f in fuels if f.get("type") == "ai95"), None)
    ai95 = ai95_fuel.get("availabilityStatus", "no_data") if ai95_fuel else "no_data"

    last_payment = details.get("lastPaymentAt")
    minutes_ago = None
    last_tx_msk = None
    if last_payment:
        try:
            payment_time = datetime.fromisoformat(last_payment)
            if payment_time.tzinfo is None:
                payment_time = payment_time.replace(tzinfo=MSK)
            minutes_ago = int((datetime.now(timezone.utc) - payment_time).total_seconds() / 60)
            last_tx_msk = payment_time.astimezone(MSK)
        except (ValueError, TypeError):
            pass

    crowd = details.get("crowdState", {})
    confidence = crowd.get("confidence", 0) * 100

    return {
        "source": "sber",
        "id": details.get("id", station.get("id", "")),
        "name": details.get("name", station.get("title", "—")),
        "brand": "—",
        "address": details.get("address", station.get("subtitle", "—")),
        "confidence": confidence,
        "ai95_status": ai95,
        "has_fuel": has_fuel,
        "minutes_ago": minutes_ago,
        "last_transaction": last_tx_msk,
        "fuel_detail": {f["type"]: f.get("availabilityStatus", "no_data") for f in fuels},
        "lat": details.get("location", {}).get("lat") or station.get("point", {}).get("lat"),
        "lon": details.get("location", {}).get("lon") or station.get("point", {}).get("lon"),
    }


# ============================================================
# gdebenz.ru API
# ============================================================


def gb_get_rt_token() -> str:
    """Получить runtime-токен с gdebenz.ru."""
    resp = requests.get(GB_RT_URL, headers=GB_HEADERS, timeout=10)
    resp.raise_for_status()
    return resp.json()["rt"]


def gb_get_stations_bbox(lat1, lon1, lat2, lon2, rt_token) -> list:
    """Получить АЗС в bounding box."""
    params = {"lat1": lat1, "lon1": lon1, "lat2": lat2, "lon2": lon2}
    headers = {**GB_HEADERS, "X-RT": rt_token}
    for attempt in range(3):
        try:
            resp = requests.get(GB_STATIONS_URL, params=params, headers=headers, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
    return []


def gb_get_station_details(osm_id: str, rt_token: str) -> dict | None:
    """Получить детали станции (уверенность, время обновления)."""
    headers = {**GB_HEADERS, "X-RT": rt_token}
    try:
        resp = requests.get(f"{GB_COMMENTS_URL}/{osm_id}", headers=headers, timeout=8)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


def gb_generate_bboxes(center_lat, center_lon, size) -> list:
    """Сетка 3x3 bbox вокруг точки."""
    bboxes = []
    for i in range(-1, 2):
        for j in range(-1, 2):
            lat1 = center_lat + i * size - size / 2
            lon1 = center_lon + j * size - size / 2
            lat2 = center_lat + i * size + size / 2
            lon2 = center_lon + j * size + size / 2
            bboxes.append((lat1, lon1, lat2, lon2))
    return bboxes


def gb_parse_updated(updated_str: str):
    """Парсинг UTC времени обновления → MSK datetime."""
    if not updated_str:
        return None
    try:
        dt_utc = datetime.strptime(updated_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        return dt_utc.astimezone(MSK)
    except Exception:
        return None


def gb_normalize(details: dict, source: str) -> dict:
    """Нормализация данных АЗС от gdebenz.ru в единый формат."""
    if not details:
        return None

    status = details.get("status")
    fuels_now = details.get("fuelsNow", "")
    has_95 = "95" in fuels_now

    # Маппинг статуса gdebenz → наш формат
    if status == "yes" and has_95:
        ai95 = "available"
    elif status == "yes":
        ai95 = "maybe_available"
    elif status == "no":
        ai95 = "not_available"
    else:
        ai95 = "no_data"

    confidence = 0
    cb = details.get("confidenceBase")
    if cb is not None:
        confidence = cb * 100

    updated_msk = gb_parse_updated(details.get("updated", ""))
    minutes_ago = None
    if updated_msk:
        delta = datetime.now(MSK) - updated_msk
        minutes_ago = int(delta.total_seconds() / 60)

    # Очередь
    limits = details.get("limits") or {}
    queue = ""
    if limits.get("q") == "yes" and limits.get("qn"):
        queue = f" (очередь {limits['qn']})"

    return {
        "source": f"gb_{source}",
        "id": details.get("name", ""),
        "name": details.get("name", "—"),
        "brand": details.get("brand", "—"),
        "address": details.get("addr", "—") or "—",
        "confidence": confidence,
        "ai95_status": ai95,
        "has_fuel": has_95 or ("92" in fuels_now),
        "minutes_ago": minutes_ago,
        "last_transaction": updated_msk,
        "fuel_detail": {"fuels_now": fuels_now, "queue": queue},
        "lat": details.get("lat"),
        "lon": details.get("lon"),
    }


def gb_enrich_addresses(stations: list[dict]) -> list[dict]:
    """Обогащение адресов gdebenz станций данными из toplivo.tbank.ru и sberazs.ru."""
    # Определяем станции без адреса
    missing_addr = [s for s in stations if s.get("address") == "—"]
    if not missing_addr:
        return stations

    print(f"  Обогащение адресов для {len(missing_addr)} станций...")

    # Кэш для результатов поиска
    address_cache = {}

    for s in missing_addr:
        lat = s.get("lat")
        lon = s.get("lon")
        if not lat or not lon:
            continue

        cache_key = f"{lat:.4f},{lon:.4f}"
        if cache_key in address_cache:
            s["address"] = address_cache[cache_key]
            continue

        # 1. Ищем в toplivo.tbank.ru (bbox 0.01° ≈ 1 км)
        found_addr = None
        try:
            delta = 0.01
            tb_url = (
                f"https://toplivo.tbank.ru/api/v1/stations"
                f"?minLat={lat - delta}&maxLat={lat + delta}"
                f"&minLon={lon - delta}&maxLon={lon + delta}"
            )
            resp = requests.get(tb_url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                tb_stations = data.get("payload", [])
                if tb_stations:
                    # Ищем ближайшую по координатам
                    min_dist = float("inf")
                    nearest = None
                    for tb in tb_stations:
                        tb_lat = tb.get("lat", 0)
                        tb_lon = tb.get("lon", 0)
                        dist = ((lat - tb_lat) ** 2 + (lon - tb_lon) ** 2) ** 0.5
                        if dist < min_dist:
                            min_dist = dist
                            nearest = tb
                    if nearest and min_dist < 0.005:  # < 500м
                        found_addr = nearest.get("addr", "")
                        if found_addr:
                            # Убираем "Россия, " в начале
                            if found_addr.startswith("Россия, "):
                                found_addr = found_addr[8:]
        except Exception:
            pass

        # 2. Если не нашли — ищем в sberazs.ru
        if not found_addr:
            try:
                sber_url = "https://sberazs.ru/api/search/suggest"
                payload = {"query": f"АЗС {s.get('brand', '')}", "lat": lat, "lon": lon}
                headers_sber = {
                    "Content-Type": "application/json",
                    "X-Sberfuel-Session": f"fuel-catalog-{int(time.time())}",
                }
                resp = requests.post(sber_url, json=payload, headers=headers_sber, timeout=10)
                if resp.status_code == 200:
                    suggestions = resp.json().get("suggestions", [])
                    if suggestions:
                        # Ищем ближайшую по координатам
                        min_dist = float("inf")
                        nearest = None
                        for sug in suggestions:
                            point = sug.get("point", {})
                            sug_lat = point.get("lat", 0)
                            sug_lon = point.get("lon", 0)
                            dist = ((lat - sug_lat) ** 2 + (lon - sug_lon) ** 2) ** 0.5
                            if dist < min_dist:
                                min_dist = dist
                                nearest = sug
                        if nearest and min_dist < 0.005:
                            found_addr = nearest.get("subtitle", "")
                            if found_addr:
                                # Убираем "Краснодарский край, " в начале
                                if found_addr.startswith("Краснодарский край, "):
                                    found_addr = found_addr[20:]
            except Exception:
                pass

        if found_addr:
            s["address"] = found_addr
            address_cache[cache_key] = found_addr
            print(f"    {s['name']}: {found_addr}")

        time.sleep(0.2)

    return stations


def gb_collect_krasnodar(rt_token: str) -> list[dict]:
    """Сбор АЗС Краснодара через gdebenz.ru (bbox-поиск)."""
    bboxes = gb_generate_bboxes(*GB_KRASNODAR_CENTER, GB_BBOX_SIZE)
    all_stations = {}
    for lat1, lon1, lat2, lon2 in bboxes:
        stations = gb_get_stations_bbox(lat1, lon1, lat2, lon2, rt_token)
        for s in stations:
            osm_id = s.get("osm_id")
            if osm_id and osm_id not in all_stations:
                all_stations[osm_id] = s
        time.sleep(1)

    results = []
    for osm_id, s in all_stations.items():
        det = gb_get_station_details(osm_id, rt_token)
        if det:
            norm = gb_normalize(det, "krasnodar")
            if norm:
                results.append(norm)
        time.sleep(0.3)
    return results


def gb_collect_tracked(rt_token: str) -> list[dict]:
    """Получение данных по 5 отслеживаемым заправкам."""
    results = []
    for osm_id in GB_TRACKED_IDS:
        det = gb_get_station_details(osm_id, rt_token)
        if det:
            norm = gb_normalize(det, "tracked")
            if norm:
                results.append(norm)
        time.sleep(0.3)
    return results


# ============================================================
# Сопоставление АЗС между источниками
# ============================================================


def normalize_address(addr: str) -> str:
    """Нормализация адреса для сравнения."""
    import re
    addr = addr.lower()
    # Убираем префиксы
    for prefix in ("россия, ", "краснодарский край, ", "республика адыгея (адыгея), "):
        addr = addr.replace(prefix, "")
    # Убираем "улица", "улица имени" и т.д.
    addr = re.sub(r'\bулица\s+(имени\s+)?', '', addr)
    addr = re.sub(r'\bул\.\s*', '', addr)
    # Убираем "микрорайон"
    addr = re.sub(r'\bмикрорайон\s+', '', addr)
    # Убираем "посёлок городского типа", "поселок городского типа"
    addr = re.sub(r'\bпос[ёе]лок\s+городского\s+типа\s+', '', addr)
    # Нормализуем номера: убираем буквы (1А -> 1, 96/3 -> 96/3)
    addr = re.sub(r'(\d+)/(\d+)', r'\1-\2', addr)  # 96/3 -> 96-3
    # Убираем лишние символы
    addr = addr.replace(',', ' ').replace('.', ' ')
    addr = ' '.join(addr.split())
    return addr


def extract_address_key(addr: str) -> str:
    """Извлекает ключевой элемент адреса для нечёткого сравнения."""
    import re
    norm = normalize_address(addr)
    # Убираем "краснодар" и подобные из ключа
    for city in ("краснодара", "краснодар", "краснодарский"):
        norm = norm.replace(city, "")
    norm = ' '.join(norm.split())
    # Ищем числовой номер в конце
    match = re.search(r'(\d+[\-/]?\d*)\s*$', norm)
    if match:
        number = match.group(1)
        # Берём слово перед номером (название улицы)
        before = norm[:match.start()].strip()
        words = before.split()
        if words:
            return f"{words[-1]}_{number}"
    # Если нет номера, берём последние 2 слова
    words = norm.split()
    if len(words) >= 2:
        return f"{words[-2]}_{words[-1]}"
    return norm


def find_matches(tb_stations: list[dict], sber_stations: list[dict]) -> tuple[list, list, list]:
    """
    Поиск пересечений между двумя источниками.
    Использует нечёткое сопоставление по адресу и координатам.
    Возвращает: (matches, tb_only, sber_only)
    """
    # Создаём карты по ключу адреса
    tb_by_key = {}
    for s in tb_stations:
        key = extract_address_key(s["address"])
        tb_by_key[key] = s

    sber_by_key = {}
    for s in sber_stations:
        key = extract_address_key(s["address"])
        sber_by_key[key] = s

    matches = []
    tb_only = []
    sber_only = []
    tb_matched = set()
    sber_matched = set()

    # 1. Сначала ищем по адресу (точное совпадение ключа)
    for key, tb_s in tb_by_key.items():
        if key in sber_by_key:
            sber_s = sber_by_key[key]
            match = _merge_two_stations(tb_s, sber_s, "tb", "sber")
            matches.append(match)
            tb_matched.add(id(tb_s))
            sber_matched.add(id(sber_s))

    # 2. Затем ищем по координатам (для несопоставленных)
    COORD_THRESHOLD = 0.003  # ~300м
    for tb_s in tb_stations:
        if id(tb_s) in tb_matched:
            continue
        tb_lat = tb_s.get("lat", 0)
        tb_lon = tb_s.get("lon", 0)
        if not tb_lat or not tb_lon:
            continue
        
        best_dist = COORD_THRESHOLD
        best_sber = None
        for sber_s in sber_stations:
            if id(sber_s) in sber_matched:
                continue
            sber_lat = sber_s.get("lat", 0)
            sber_lon = sber_s.get("lon", 0)
            if not sber_lat or not sber_lon:
                continue
            dist = ((tb_lat - sber_lat) ** 2 + (tb_lon - sber_lon) ** 2) ** 0.5
            if dist < best_dist:
                best_dist = dist
                best_sber = sber_s
        
        if best_sber:
            match = _merge_two_stations(tb_s, best_sber, "tb", "sber")
            match["coord_distance"] = best_dist
            matches.append(match)
            tb_matched.add(id(tb_s))
            sber_matched.add(id(best_sber))

    # 3. Оставшиеся — только из одного источника
    for tb_s in tb_stations:
        if id(tb_s) not in tb_matched:
            tb_only.append(tb_s)
    for sber_s in sber_stations:
        if id(sber_s) not in sber_matched:
            sber_only.append(sber_s)

    return matches, tb_only, sber_only


def _enrich_matches_with_gb(matches: list[dict], gb_stations: list[dict]) -> None:
    """Обогащение пересечений данными gdebenz (очередь, статус)."""
    COORD_THRESHOLD = 0.003

    for match in matches:
        lat = match.get("lat", 0)
        lon = match.get("lon", 0)
        addr_key = extract_address_key(match.get("address", ""))

        best_gb = None
        best_dist = COORD_THRESHOLD

        for gb_s in gb_stations:
            gb_lat = gb_s.get("lat", 0)
            gb_lon = gb_s.get("lon", 0)

            # По координатам
            if lat and lon and gb_lat and gb_lon:
                dist = ((lat - gb_lat) ** 2 + (lon - gb_lon) ** 2) ** 0.5
                if dist < best_dist:
                    best_dist = dist
                    best_gb = gb_s
                continue

            # По адресу
            gb_key = extract_address_key(gb_s.get("address", ""))
            if addr_key and gb_key and addr_key == gb_key:
                best_gb = gb_s
                break

        if best_gb:
            match["gb_crowd"] = best_gb.get("crowd")
            match["gb_crowd_raw"] = best_gb.get("crowd_raw")
            match["gb_queue"] = best_gb.get("queue")
            match["gb_source"] = "gdebenz"
            # Доп. данные от gdebenz
            match["gb_confidence"] = best_gb.get("confidence", 0)
            match["gb_ai95_status"] = best_gb.get("ai95_status", "no_data")
            match["gb_last_transaction"] = best_gb.get("last_transaction")
            fuel_detail = best_gb.get("fuel_detail", {})
            match["gb_queue_info"] = fuel_detail.get("queue", "")


def _addresses_match(addr1: str, addr2: str) -> bool:
    """Проверка совпадения адресов."""
    key1 = extract_address_key(addr1)
    key2 = extract_address_key(addr2)
    return key1 and key2 and key1 == key2


def find_matches_with_gb(
    tb_stations: list[dict],
    sber_stations: list[dict],
    gb_stations: list[dict],
) -> tuple[list, list, list, list]:
    """
    Поиск пересечений между ТБ, Сбер и gdebenz.
    Пересечение = минимум 2 из 3 источников подтвердили наличие АИ-95.
    Исходные списки НЕ редактируются — все станции остаются в своих таблицах.
    Возвращает: (all_match, tb_all, sber_all, gb_all)
    """
    COORD_THRESHOLD = 0.003  # ~300м

    # Объединяем все станции с пометкой источника
    all_stations = []
    for s in tb_stations:
        s["_src"] = "tb"
        all_stations.append(s)
    for s in sber_stations:
        s["_src"] = "sber"
        all_stations.append(s)
    for s in gb_stations:
        s["_src"] = "gb"
        all_stations.append(s)

    # Кластеризация по координатам и адресам
    clusters = []  # [[station, ...], ...]
    used = set()

    for i, s1 in enumerate(all_stations):
        if i in used:
            continue
        cluster = [s1]
        used.add(i)
        lat1 = s1.get("lat", 0)
        lon1 = s1.get("lon", 0)

        for j, s2 in enumerate(all_stations):
            if j in used:
                continue
            # Проверяем координаты
            lat2 = s2.get("lat", 0)
            lon2 = s2.get("lon", 0)
            if lat1 and lon1 and lat2 and lon2:
                dist = ((lat1 - lat2) ** 2 + (lon1 - lon2) ** 2) ** 0.5
                if dist < COORD_THRESHOLD:
                    cluster.append(s2)
                    used.add(j)
                    continue
            # Проверяем адрес
            key1 = extract_address_key(s1.get("address", ""))
            key2 = extract_address_key(s2.get("address", ""))
            if key1 and key2 and key1 == key2:
                cluster.append(s2)
                used.add(j)

        clusters.append(cluster)

    # Определяем пересечения
    result_matches = []

    for cluster in clusters:
        srcs = set(s["_src"] for s in cluster)

        if len(srcs) >= 2:
            # Проверяем условия пересечения: минимум 2 источника с 95-м
            sources_with_fuel = 0
            for s in cluster:
                ai95 = s.get("ai95_status", "no_data")
                if ai95 in ("available", "maybe_available") or s.get("has_fuel", False):
                    sources_with_fuel += 1

            if sources_with_fuel >= 2:
                merged = _merge_cluster(cluster)
                result_matches.append(merged)

    # Исходные списки остаются БЕЗ ИЗМЕНЕНИЙ
    return result_matches, tb_stations, sber_stations, gb_stations


def _merge_two_stations(s1: dict, s2: dict, src1: str, src2: str) -> dict:
    """Объединение данных двух станций."""
    # Выбираем имя: приоритет TB > Sber > GB
    name = s1.get("name", "—")
    if src2 == "tb" or (src1 != "tb" and s2.get("name", "—") != "—"):
        name = s2.get("name", name)
    if src1 == "tb":
        name = s1.get("name", name)

    # Адрес: приоритет TB > Sber > GB
    address = s1.get("address", "—")
    if src2 == "tb" or (src1 != "tb" and s2.get("address", "—") not in ("—", "")):
        address = s2.get("address", address)
    if src1 == "tb":
        address = s1.get("address", address)

    return {
        "name": _unify_brand_name(name, s1, s2),
        "brand": s1.get("brand", s2.get("brand", "—")),
        "address": address,
        "confidence": max(s1.get("confidence", 0), s2.get("confidence", 0)),
        "ai95_status": _merge_ai95(s1.get("ai95_status", "no_data"), s2.get("ai95_status", "no_data")),
        "has_fuel": s1.get("has_fuel", False) or s2.get("has_fuel", False),
        "minutes_ago": _min_minutes(s1.get("minutes_ago"), s2.get("minutes_ago")),
        "last_transaction": _min_datetime(s1.get("last_transaction"), s2.get("last_transaction")),
        "sources": [s1.get("_src", src1), s2.get("_src", src2)],
        "lat": s1.get("lat") or s2.get("lat"),
        "lon": s1.get("lon") or s2.get("lon"),
    }


def _merge_cluster(cluster: list[dict]) -> dict:
    """Объединение кластера станций из разных источников."""
    # Сортируем: TB первый, потом Sber, потом GB
    src_order = {"tb": 0, "sber": 1, "gb": 2}
    cluster.sort(key=lambda s: src_order.get(s.get("_src", ""), 3))

    result = cluster[0].copy()
    result["sources"] = [s.get("_src", "?") for s in cluster]

    # Уверенность: TB/Sber в приоритете, gdebenz только если нет других
    tb_sber = [s for s in cluster if s.get("_src") in ("tb", "sber")]
    if tb_sber:
        result["confidence"] = max(s.get("confidence", 0) for s in tb_sber)
    else:
        result["confidence"] = max(s.get("confidence", 0) for s in cluster)

    for s in cluster[1:]:
        result["name"] = _unify_brand_name(result.get("name", ""), result, s)
        result["address"] = s.get("address", result.get("address", "—")) if s.get("address", "—") not in ("—", "") else result.get("address", "—")
        result["ai95_status"] = _merge_ai95(result.get("ai95_status", "no_data"), s.get("ai95_status", "no_data"))
        result["has_fuel"] = result.get("has_fuel", False) or s.get("has_fuel", False)
        result["minutes_ago"] = _min_minutes(result.get("minutes_ago"), s.get("minutes_ago"))
        result["last_transaction"] = _min_datetime(result.get("last_transaction"), s.get("last_transaction"))
        if not result.get("lat") and s.get("lat"):
            result["lat"] = s.get("lat")
        if not result.get("lon") and s.get("lon"):
            result["lon"] = s.get("lon")

    return result


def _unify_brand_name(name: str, s1: dict, s2: dict) -> str:
    """Унификация названия бренда между источниками."""
    # Нормализуем к нижнему регистру для сравнения
    n1 = s1.get("name", "").lower().strip()
    n2 = s2.get("name", "").lower().strip()
    
    # Известные маппинги брендов
    brand_aliases = {
        "газпром": ["газпром", "газпромнефть", "АЗС Газпром", "Газпром АЗС"],
        "лукойл": ["лукойл"],
        "роснефть": ["роснефть"],
        "сити ойл": ["сити ойл", "сити-ойл"],
        "атан": ["атан", "atan"],
        "rusoil": ["rusoil", "русоил"],
        "petrol office": ["petrol office"],
        "ирбис": ["ирбис", "irbis"],
        "газон+": ["газон+", "газон плюс"],
        "pnf": ["pnf", "пнб"],
        "экооил": ["экооил", "эко oils"],
        "gas oil": ["gas oil", "gas-oil", "gas_oil"],
        "ANK": ["АНК", "ank"],
    }
    
    # Ищем общий бренд
    for brand, aliases in brand_aliases.items():
        for alias in aliases:
            if alias.lower() in n1 or alias.lower() in n2:
                # Возвращаем каноническое название
                return brand.title() if brand not in ("gas oil", "pnf") else brand.upper()
    
    # Если не нашли маппинг — берём имя из TB (самое полное)
    if s1.get("_src") == "tb" and s1.get("name", "—") != "—":
        return s1["name"]
    if s2.get("_src") == "tb" and s2.get("name", "—") != "—":
        return s2["name"]
    
    # Иначе — самое длинное название
    candidates = [s.get("name", "") for s in [s1, s2] if s.get("name", "—") != "—"]
    return max(candidates, key=len) if candidates else "—"


def _merge_ai95(tb_status: str, sber_status: str) -> str:
    """Объединение статуса АИ-95 из двух источников."""
    available = {"available", "maybe_available"}
    if tb_status in available or sber_status in available:
        if tb_status == "available" or sber_status == "available":
            return "available"
        return "maybe_available"
    return "not_available"


def _min_minutes(a: int | None, b: int | None) -> int | None:
    """Минимальное значение из двух (ближайшая покупка)."""
    if a is None:
        return b
    if b is None:
        return a
    return min(a, b)


def _min_datetime(a: datetime | None, b: datetime | None) -> datetime | None:
    """Минимальная дата из двух (ближайшая покупка)."""
    if a is None:
        return b
    if b is None:
        return a
    return min(a, b)


# ============================================================
# Генерация отчёта
# ============================================================


def ai95_icon(status: str) -> str:
    """Иконка для статуса АИ-95."""
    mapping = {
        "available": "✅",
        "maybe_available": "❓*",
        "not_available": "❌",
        "unknown": "❓",
        "stale": "❓",
        "unavailable": "❌",
        "no_data": "—",
    }
    return mapping.get(status, "?")


def format_datetime(dt: datetime | None) -> str:
    """Форматирование даты-времени МСК."""
    if dt is None:
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=MSK)
    return dt.astimezone(MSK).strftime("%d.%m %H:%M")


def yandex_maps_link(lat, lon) -> str:
    """Генерация ссылки на Яндекс Карты/Навигатор для построения маршрута."""
    if not lat or not lon:
        return "—"
    return f"[Маршрут](https://yandex.ru/maps/?rtext=~{lat},{lon})"


def generate_unified_report(
    matches: list[dict],
    tb_only: list[dict],
    sber_only: list[dict],
    now: datetime,
    gb_stations: list[dict] = None,
    gb_tracked: list[dict] = None,
) -> str:
    """Генерация объединённого markdown-отчёта."""
    now_msk = now.astimezone(MSK)
    total = len(matches) + len(tb_only) + len(sber_only) + len(gb_stations or [])

    lines = [
        f"# Объединённый отчёт: заправки Краснодара и окрестностей",
        "",
        f"**Дата:** {now_msk.strftime('%d.%m.%Y %H:%M:%S')} МСК",
        f"**Источники:** toplivo.tbank.ru + sberazs.ru + gdebenz.ru",
        f"**Окно:** покупка за {LIMIT_MINUTES} мин (TB/Sber), отметка за {GB_LIMIT_MINUTES // 60} ч (gdebenz)",
        f"**Найдено:** {total} заправок",
        f"  - Пересечение (2+ источника): {len(matches)}",
        f"  - Только Т-Банк: {len(tb_only)}",
        f"  - Только Сбер: {len(sber_only)}",
        f"  - Только gdebenz: {len(gb_stations or [])}",
        "",
    ]

    # --- Таблица 1: Пересечение ---
    lines.append("## Пересечение (2+ источника)")
    lines.append("")
    if matches:
        lines.append("| # | Название | Адрес | Источники | Уверенность | АИ-95 | Покупка (МСК) | gdebenz | Маршрут |")
        lines.append("|---|---------|-------|-----------|-------|-------|-------|---------|---------|")
        for i, s in enumerate(matches, 1):
            addr_short = s["address"].replace("Россия, ", "")
            sources = "+".join(s.get("sources", []))
            link = yandex_maps_link(s.get("lat"), s.get("lon"))
            # Инфо от gdebenz: очередь + Уверенность gdebenz
            gb_info = ""
            if s.get("gb_queue_info"):
                gb_info = s["gb_queue_info"]
            elif s.get("gb_crowd"):
                gb_info = s["gb_crowd"]
            # Уверенность gdebenz отдельно
            gb_conf = ""
            if s.get("gb_confidence") and s["gb_confidence"] > 0:
                gb_conf = f"{s['gb_confidence']:.0f}%"
            gb_display = ""
            if gb_info and gb_conf:
                gb_display = f"{gb_info} ({gb_conf})"
            elif gb_info:
                gb_display = gb_info
            elif gb_conf:
                gb_display = gb_conf
            lines.append(
                f"| {i} | {s['name']} | {addr_short} | {sources} | {s['confidence']:.0f}% | {ai95_icon(s['ai95_status'])} | {format_datetime(s['last_transaction'])} | {gb_display} | {link} |"
            )
    else:
        lines.append("_Нет заправок, найденных в нескольких источниках._")
    lines.append("")

    # --- Таблица 2: Только Т-Банк ---
    lines.append("## Только toplivo.tbank.ru")
    lines.append("")
    if tb_only:
        lines.append("| # | Название | Адрес | Уверенность | АИ-95 | Покупка (МСК) | Маршрут |")
        lines.append("|---|---------|-------|-------|-------|-------|---------|")
        for i, s in enumerate(tb_only, 1):
            addr_short = s["address"].replace("Россия, ", "")
            link = yandex_maps_link(s.get("lat"), s.get("lon"))
            lines.append(
                f"| {i} | {s['name']} | {addr_short} | {s['confidence']:.0f}% | {ai95_icon(s['ai95_status'])} | {format_datetime(s['last_transaction'])} | {link} |"
            )
    else:
        lines.append("_Нет заправок только из этого источника._")
    lines.append("")

    # --- Таблица 3: Только Сбер ---
    lines.append("## Только sberazs.ru")
    lines.append("")
    if sber_only:
        lines.append("| # | Название | Адрес | Уверенность | АИ-95 | Покупка (МСК) | Маршрут |")
        lines.append("|---|---------|-------|-------|-------|-------|---------|")
        for i, s in enumerate(sber_only, 1):
            addr_short = s["address"].replace("Краснодарский край, ", "")
            link = yandex_maps_link(s.get("lat"), s.get("lon"))
            lines.append(
                f"| {i} | {s['name']} | {addr_short} | {s['confidence']:.0f}% | {ai95_icon(s['ai95_status'])} | {format_datetime(s['last_transaction'])} | {link} |"
            )
    else:
        lines.append("_Нет заправок только из этого источника._")
    lines.append("")

    # --- Таблица 4: gdebenz.ru только gdebenz ---
    if gb_stations:
        lines.append("## Только gdebenz.ru")
        lines.append("")
        lines.append("| # | Название | Адрес | Уверенность | АИ-95 | Последняя отметка | Маршрут |")
        lines.append("|---|---------|-------|-------------|-------|------------------|---------|")
        for i, s in enumerate(gb_stations, 1):
            queue = s.get("fuel_detail", {}).get("queue", "")
            link = yandex_maps_link(s.get("lat"), s.get("lon"))
            lines.append(
                f"| {i} | {s['name']} | {s['address']} | {s['confidence']:.0f}% | {ai95_icon(s['ai95_status'])}{queue} | {format_datetime(s['last_transaction'])} | {link} |"
            )
        lines.append("")

    lines.extend([
        "---",
        "",
        "**Легенда:** ✅ есть | ❓* возможно есть | ❌ нет | — нет данных",
        "**Источники:** tb=Т-Банк, sber=Сбер, gb=gdebenz",
    ])

    return "\n".join(lines)


# ============================================================
# Главная функция
# ============================================================


def move_old_reports_to_history(output_dir: Path):
    """Перемещение старых отчётов в подкаталог history."""
    history_dir = output_dir / "history"
    history_dir.mkdir(exist_ok=True)

    # Находим все .md файлы в reports (не в history)
    reports = sorted(
        [f for f in output_dir.glob("monitor_*.md")],
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )

    # Оставляем только最新的, остальные перемещаем
    if len(reports) > 1:
        for old_file in reports[1:]:
            dest = history_dir / old_file.name
            try:
                old_file.rename(dest)
            except Exception:
                pass


def run_once():
    """Один цикл сбора данных."""
    now = datetime.now(timezone.utc)
    now_msk = now.astimezone(MSK)
    print(f"=== Мониторинг заправок ===")
    print(f"Время: {now_msk.strftime('%d.%m.%Y %H:%M:%S')} МСК")
    print()

    session_id = f"fuel-monitor-{int(time.time())}"

    # --- 1. Получение данных от Т-Банка ---
    print("--- toplivo.tbank.ru ---")
    tb_all = {}
    try:
        stations = tb_fetch_stations(KRASNODAR_BOUNDS)
        for s in stations:
            tb_all[s["id"]] = tb_normalize(s)
        print(f"  Краснодар: {len(stations)} АЗС")
    except Exception as e:
        print(f"  Ошибка Краснодар: {e}")

    for tracked in TRACKED_STATIONS:
        try:
            stations = tb_fetch_stations(tracked["tb_bounds"])
            for s in stations:
                if tb_matches_filters(s, tracked["tb_addr_filter"]):
                    tb_all[s["id"]] = tb_normalize(s)
                    print(f"  {tracked['name']}: найдена")
                    break
        except Exception as e:
            print(f"  Ошибка {tracked['name']}: {e}")

    # Фильтрация: покупка за 30 мин + есть бензин
    tb_filtered = [
        s for s in tb_all.values()
        if s["has_fuel"]
        and s["minutes_ago"] is not None
        and s["minutes_ago"] <= LIMIT_MINUTES
    ]
    print(f"  Итого Т-Банк (с фильтром): {len(tb_filtered)}")

    # --- 2. Получение данных от СберАЗС ---
    print("\n--- sberazs.ru ---")
    sber_all = {}

    # Краснодар
    try:
        krd_stations = sber_collect_krasnodar(session_id)
        print(f"  Краснодар поиск: {len(krd_stations)} АЗС")
        for sid, basic in krd_stations.items():
            details = sber_get_station_details(sid, session_id)
            if details:
                sber_all[sid] = sber_normalize(basic, details)
            else:
                # Добавляем даже без деталей — по данным поиска
                sber_all[sid] = sber_normalize(basic, None)
            time.sleep(0.08)
    except Exception as e:
        print(f"  Ошибка Краснодар: {e}")

    # Отслеживаемые заправки
    for tracked in TRACKED_STATIONS:
        try:
            details = sber_get_station_details(tracked["sber_id"], session_id)
            if details:
                sber_all[tracked["sber_id"]] = sber_normalize(
                    {"id": tracked["sber_id"], "title": details["name"], "subtitle": details["address"]},
                    details,
                )
                print(f"  {tracked['name']}: найдена")
        except Exception as e:
            print(f"  Ошибка {tracked['name']}: {e}")

    # Фильтрация: покупка за 45 мин + есть бензин (или есть данные из поиска)
    sber_filtered = [
        s for s in sber_all.values()
        if s["has_fuel"]
        and (
            (s["minutes_ago"] is not None and s["minutes_ago"] <= LIMIT_MINUTES)
            or s.get("ai95_status") == "unknown"  # есть данные из поиска, details не загрузились
        )
    ]
    print(f"  Итого Сбер (с фильтром): {len(sber_filtered)}")

    # --- 3. Получение данных от gdebenz.ru ---
    print("\n--- gdebenz.ru ---")
    gb_stations = []
    gb_tracked = []
    try:
        gb_rt = gb_get_rt_token()
        print(f"  RT-токен: {gb_rt[:8]}...")

        # Краснодар
        gb_stations = gb_collect_krasnodar(gb_rt)
        gb_filtered = [
            s for s in gb_stations
            if s["has_fuel"]
            and s["minutes_ago"] is not None
            and s["minutes_ago"] <= GB_LIMIT_MINUTES
        ]
        print(f"  Краснодар: {len(gb_stations)} АЗС, с фильтром: {len(gb_filtered)}")

        # Отслеживаемые — показываем всегда (даже без recent marks)
        gb_tracked = gb_collect_tracked(gb_rt)
        gb_tracked_filtered = gb_tracked
        print(f"  Отслеживаемые: {len(gb_tracked)}")

        # Обогащение адресами из toplivo.tbank.ru / sberazs.ru
        gb_enrich_addresses(gb_filtered)
        gb_enrich_addresses(gb_tracked_filtered)

    except Exception as e:
        print(f"  Ошибка gdebenz: {e}")

    # --- 4. Сопоставление и генерация отчёта ---
    print("\n--- Сопоставление ---")
    # Пересечение: любые 2+ из 3 источников
    all_gb = list(gb_filtered) + list(gb_tracked_filtered)
    matches, tb_only, sber_only, gb_only = find_matches_with_gb(tb_filtered, sber_filtered, all_gb)
    
    # Обогащение пересечений данными gdebenz (очередь, статус, Уверенность)
    _enrich_matches_with_gb(matches, all_gb)
    
    print(f"  Пересечение (2+ источника): {len(matches)}")
    print(f"  Только Т-Банк: {len(tb_only)}")
    print(f"  Только Сбер: {len(sber_only)}")
    print(f"  Только gdebenz: {len(gb_only)}")

    report = generate_unified_report(matches, tb_only, sber_only, now, gb_only, [])

    # Сохранение
    output_dir = Path(__file__).resolve().parent / "reports"
    output_dir.mkdir(exist_ok=True)

    # Перемещаем старые отчёты в history
    move_old_reports_to_history(output_dir)

    filename = f"monitor_{datetime.now(MSK).strftime('%Y%m%d_%H%M%S')}.md"
    filepath = output_dir / filename
    filepath.write_text(report, encoding="utf-8")
    print(f"\nОтчёт сохранён: {filepath}")

    # Отправка в Telegram
    tg_msg = format_telegram_message(matches, filepath)
    send_telegram(tg_msg)

    # Git commit and push
    git_commit_and_push(filepath)

    return filepath


def git_commit_and_push(filepath: Path):
    """Коммит и пуш отчёта в git."""
    try:
        repo_dir = Path(__file__).parent

        # Проверяем что это git репозиторий
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=repo_dir, capture_output=True, text=True
        )
        if result.returncode != 0:
            print("Git: не git репозиторий, пропускаю")
            return

        # Добавляем все изменения (новый отчёт + перемещённые старые)
        subprocess.run(
            ["git", "add", "-A"],
            cwd=repo_dir, capture_output=True, text=True
        )

        # Коммитим
        now_msk = datetime.now(MSK)
        commit_msg = f"report: {filepath.stem} ({now_msk.strftime('%H:%M')})"
        result = subprocess.run(
            ["git", "commit", "-m", commit_msg],
            cwd=repo_dir, capture_output=True, text=True
        )
        if "nothing to commit" in result.stdout or "nothing to commit" in result.stderr:
            print("Git: нет изменений для коммита")
        else:
            print(f"Git: коммит — {commit_msg}")

        # Пушим
        result = subprocess.run(
            ["git", "push"],
            cwd=repo_dir, capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            print("Git: push выполнен")
        else:
            print(f"Git push: {result.stderr.strip()[:100]}")

    except subprocess.TimeoutExpired:
        print("Git push: таймаут")
    except Exception as e:
        print(f"Git: ошибка — {e}")


def main():
    """Точка входа: одноразовый запуск или цикл."""
    interval = None

    # Парсинг аргументов
    args = sys.argv[1:]
    if "--loop" in args:
        idx = args.index("--loop")
        if idx + 1 < len(args):
            try:
                interval = int(args[idx + 1])
            except ValueError:
                interval = 30
        else:
            interval = 30

    if interval is None:
        # Одноразовый запуск
        run_once()
    else:
        # Цикл
        print(f"Режим цикла: каждые {interval} минут. Для остановки: Ctrl+C")
        while True:
            try:
                run_once()
                print(f"\nСледующий запуск через {interval} минут...")
                time.sleep(interval * 60)
            except KeyboardInterrupt:
                print("\nОстановлено пользователем")
                break
            except Exception as e:
                print(f"\nОшибка: {e}")
                print(f"Повтор через {interval} минут...")
                time.sleep(interval * 60)


if __name__ == "__main__":
    main()
