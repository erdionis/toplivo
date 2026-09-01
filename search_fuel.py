#!/usr/bin/env python3
"""
Мониторинг АЗС Краснодара + 5 конкретных заправок.
Формат: Название | Адрес | Уверенность | АИ-95 | Последняя отметка
Данные: gdebenz.ru
"""

import requests
import os
import time
from datetime import datetime, timedelta

# === НАСТРОЙКИ ===

# Центр Краснодара для поиска по bbox
KUBDARODAR_CENTER = (45.0355, 38.9753)
BBOX_SIZE = 0.15

# 5 конкретных заправок (osm_id) — ищем всегда, независимо от bbox
TRACKED_STATIONS = [
    "usr_ftjulj3dDJw",   # Газпром, ст. Северская, А-146, 48-й км, 2
    "2892720110",         # Южная нефтяная компания, ст. Северская
    "usr_nnYnvLUqBHA",   # ЮНК, ст. Северская, А-146, 48-й км, 1
    "w229004932",         # Роснефть, Афипский, Магистральная ул., 4
    "usr_KgInCQzo1og",   # Лукойл, Энем, ул. Перова, 42
]

RT_URL = "https://gdebenz.ru/api/rt"
STATIONS_URL = "https://gdebenz.ru/api/stations"
COMMENTS_URL = "https://gdebenz.ru/api/comments"
REPORTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://gdebenz.ru/",
}


def get_rt_token() -> str:
    resp = requests.get(RT_URL, headers=HEADERS, timeout=10)
    resp.raise_for_status()
    return resp.json()["rt"]


def get_stations_in_bbox(lat1, lon1, lat2, lon2, rt_token):
    params = {"lat1": lat1, "lon1": lon1, "lat2": lat2, "lon2": lon2}
    headers = {**HEADERS, "X-RT": rt_token}
    for attempt in range(3):
        try:
            resp = requests.get(STATIONS_URL, params=params, headers=headers, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
    return []


def get_station_by_id(osm_id, rt_token):
    """Получить станцию по osm_id через bbox-запрос."""
    headers = {**HEADERS, "X-RT": rt_token}
    try:
        # Ищем станцию через search
        resp = requests.get(f"{COMMENTS_URL}/{osm_id}", headers=headers, timeout=8)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


def get_station_details(osm_id, rt_token):
    """Получить детали станции: уверенность, время обновления."""
    headers = {**HEADERS, "X-RT": rt_token}
    try:
        resp = requests.get(f"{COMMENTS_URL}/{osm_id}", headers=headers, timeout=8)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


def generate_bboxes(center_lat, center_lon, size):
    bboxes = []
    for i in range(-1, 2):
        for j in range(-1, 2):
            lat1 = center_lat + i * size - size / 2
            lon1 = center_lon + j * size - size / 2
            lat2 = center_lat + i * size + size / 2
            lon2 = center_lon + j * size + size / 2
            bboxes.append((lat1, lon1, lat2, lon2))
    return bboxes


def parse_updated(updated_str):
    """Парсить строку времени обновления (UTC) и конвертировать в MSK."""
    if not updated_str:
        return None
    try:
        dt_utc = datetime.strptime(updated_str, "%Y-%m-%d %H:%M:%S")
        return dt_utc + timedelta(hours=3)
    except Exception:
        return None


def format_datetime(dt):
    if not dt:
        return "—"
    return dt.strftime("%d.%m.%Y %H:%M")


def status_icon(status, fuels_now, has_95):
    if status == "no":
        return "❌"
    if status == "queue":
        return "🟡"
    if status == "low":
        return "⚠️"
    if status == "yes" and has_95:
        return "✅"
    if status == "yes" and not has_95:
        return "❓"
    return "—"


def build_station_record(osm_id, raw, details, source):
    """Собрать единый словарь станции из сырых данных + details."""
    name = details.get("name", "") if details else ""
    addr = details.get("addr", "") if details else ""
    brand = details.get("brand", "") if details else ""
    status = details.get("status") if details else None
    fuels_now = details.get("fuelsNow", "") if details else ""
    confidence = ""
    updated_dt = None
    if details:
        cb = details.get("confidenceBase")
        if cb is not None:
            confidence = f"{int(cb * 100)}%"
        updated_dt = parse_updated(details.get("updated", ""))
    limits = details.get("limits", {}) if details else {}
    lat = details.get("lat", 0) if details else 0
    lon = details.get("lon", 0) if details else 0

    return {
        "osm_id": osm_id,
        "name": name,
        "addr": addr,
        "brand": brand,
        "lat": lat,
        "lon": lon,
        "status": status,
        "fuels_now": fuels_now,
        "confidence": confidence,
        "updated": updated_dt,
        "limits": limits,
        "source": source,
    }


def main():
    print("=" * 60)
    print("АЗС Краснодара + отслеживаемые заправки (АИ-95)")
    print("=" * 60)

    # Токен
    print("\n[1/5] Токен...")
    rt_token = get_rt_token()
    print(f"  OK: {rt_token[:8]}...")

    # --- Часть 1: Краснодар по bbox ---
    print("\n[2/5] Краснодар (bbox)...")
    bboxes = generate_bboxes(*KUBDARODAR_CENTER, BBOX_SIZE)
    all_stations = {}
    for i, (lat1, lon1, lat2, lon2) in enumerate(bboxes):
        stations = get_stations_in_bbox(lat1, lon1, lat2, lon2, rt_token)
        new = 0
        for s in stations:
            osm_id = s.get("osm_id")
            if osm_id and osm_id not in all_stations:
                all_stations[osm_id] = s
                new += 1
        print(f"  {i+1}/{len(bboxes)}: {len(stations)} ({new} новых)")
        time.sleep(1)
    print(f"  Всего Краснодар: {len(all_stations)}")

    # --- Часть 2: 5 конкретных заправок ---
    print("\n[3/5] Отслеживаемые заправки...")
    tracked_raw = {}
    for osm_id in TRACKED_STATIONS:
        if osm_id not in all_stations:
            # Получаем данные из comments
            det = get_station_details(osm_id, rt_token)
            if det:
                tracked_raw[osm_id] = {
                    "osm_id": osm_id,
                    "name": det.get("name", ""),
                    "addr": det.get("addr", ""),
                    "brand": det.get("brand", ""),
                }
                print(f"  + {det.get('name', osm_id)}")
            else:
                print(f"  ! Не найдена: {osm_id}")
            time.sleep(0.5)
        else:
            print(f"  = {all_stations[osm_id].get('name', osm_id)} (уже в Краснодаре)")

    # --- Часть 3: Детали ---
    print("\n[4/5] Детали (уверенность, время)...")
    now = datetime.now()
    cutoff = now - timedelta(minutes=30)
    results = []

    # Краснодар
    for osm_id, s in all_stations.items():
        det = get_station_details(osm_id, rt_token)
        time.sleep(0.3)
        rec = build_station_record(osm_id, s, det, "Краснодар")
        if rec["updated"] and rec["updated"] >= cutoff:
            results.append(rec)

    print(f"  Краснодар (последние 30 мин): {sum(1 for r in results if r['source']=='Краснодар')}")

    # Отслеживаемые
    tracked_count = 0
    for osm_id in TRACKED_STATIONS:
        det = get_station_details(osm_id, rt_token)
        time.sleep(0.3)
        raw = tracked_raw.get(osm_id) or all_stations.get(osm_id, {})
        rec = build_station_record(osm_id, raw, det, "Отслеживаемая")
        # Отслеживаемые показываем всегда (даже без отметок)
        results.append(rec)
        if rec["updated"] and rec["updated"] >= cutoff:
            tracked_count += 1
    print(f"  Отслеживаемые (всего): {len(TRACKED_STATIONS)}, с отметкой за 30 мин: {tracked_count}")

    # --- Часть 4: Сохранение ---
    print("\n[5/5] Сохранение...")
    timestamp = now.strftime("%Y-%m-%d_%H-%M")
    filename = f"krasnodar_ai95_{timestamp}.md"
    filepath = os.path.join(REPORTS_DIR, filename)
    os.makedirs(REPORTS_DIR, exist_ok=True)

    # Сортировка: отслеживаемые первыми, потом по времени
    results.sort(key=lambda x: (
        0 if x["source"] == "Отслеживаемая" else 1,
        -(x["updated"].timestamp() if x["updated"] else 0),
    ))

    now_str = now.strftime("%d.%m.%Y %H:%M")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"# АЗС Краснодара с бензином АИ-95\n\n")
        f.write(f"**Дата:** {now_str} МСК\n")
        f.write(f"**Источник:** gdebenz.ru (отметки водителей)\n")
        f.write(f"**Фильтр:** отметка не позднее 30 минут\n")
        f.write(f"**Найдено:** {len(results)} заправок\n\n")

        # Сначала отслеживаемые
        tracked_results = [r for r in results if r["source"] == "Отслеживаемая"]
        krasnodar_results = [r for r in results if r["source"] == "Краснодар"]

        if tracked_results:
            f.write("## Отслеживаемые заправки\n\n")
            f.write("| # | Название | Адрес | Уверенность | АИ-95 | Последняя отметка |\n")
            f.write("|---|---------|-------|-------------|-------|------------------|\n")
            for i, s in enumerate(tracked_results, 1):
                name = s["name"]
                addr = s["addr"] or "—"
                confidence = s["confidence"] or "—"
                updated = format_datetime(s["updated"])
                icon = status_icon(s["status"], s["fuels_now"], "95" in s["fuels_now"])
                queue = ""
                if s["limits"] and s["limits"].get("q") == "yes" and s["limits"].get("qn"):
                    queue = f" (очередь {s['limits']['qn']})"
                f.write(f"| {i} | {name} | {addr} | {confidence} | {icon}{queue} | {updated} |\n")
            f.write("\n")

        if krasnodar_results:
            f.write("## Краснодар (поиск по городу)\n\n")
            f.write("| # | Название | Адрес | Уверенность | АИ-95 | Последняя отметка |\n")
            f.write("|---|---------|-------|-------------|-------|------------------|\n")
            for i, s in enumerate(krasnodar_results, 1):
                name = s["name"]
                addr = s["addr"] or "—"
                confidence = s["confidence"] or "—"
                updated = format_datetime(s["updated"])
                icon = status_icon(s["status"], s["fuels_now"], "95" in s["fuels_now"])
                queue = ""
                if s["limits"] and s["limits"].get("q") == "yes" and s["limits"].get("qn"):
                    queue = f" (очередь {s['limits']['qn']})"
                f.write(f"| {i} | {name} | {addr} | {confidence} | {icon}{queue} | {updated} |\n")

        f.write(f"\n---\n\n")
        f.write(f"**Легенда:** ✅ есть | 🟡 очередь | ⚠️ мало | ❌ нет | ❓ нет данных по 95\n")

    print(f"\n{'=' * 60}")
    print(f"Сохранено: {filepath}")
    print(f"{'=' * 60}")

    # Консоль
    print(f"\n=== Отслеживаемые ===")
    print(f"{'#':<3} {'Название':<25} {'Адрес':<30} {'Увер.':<7} {'95':<6} {'Отметка'}")
    print("-" * 100)
    for i, s in enumerate(tracked_results, 1):
        name = s["name"][:23]
        addr = (s["addr"] or "—")[:28]
        confidence = s["confidence"] or "—"
        updated = format_datetime(s["updated"])
        status = s["status"] or ""
        fuels = s["fuels_now"] or ""
        has_95 = "95" in fuels
        if status == "no": st = "NET"
        elif status == "queue": st = "OCHERED"
        elif status == "low": st = "MALO"
        elif status == "yes" and has_95: st = "EST"
        elif status == "yes": st = "?"
        else: st = "—"
        print(f"{i:<3} {name:<25} {addr:<30} {confidence:<7} {st:<6} {updated}")

    print(f"\n=== Краснодар (последние 30 мин) ===")
    print(f"{'#':<3} {'Название':<25} {'Адрес':<30} {'Увер.':<7} {'95':<6} {'Отметка'}")
    print("-" * 100)
    for i, s in enumerate(krasnodar_results, 1):
        name = s["name"][:23]
        addr = (s["addr"] or "—")[:28]
        confidence = s["confidence"] or "—"
        updated = format_datetime(s["updated"])
        status = s["status"] or ""
        fuels = s["fuels_now"] or ""
        has_95 = "95" in fuels
        if status == "no": st = "NET"
        elif status == "queue": st = "OCHERED"
        elif status == "low": st = "MALO"
        elif status == "yes" and has_95: st = "EST"
        elif status == "yes": st = "?"
        else: st = "—"
        print(f"{i:<3} {name:<25} {addr:<30} {confidence:<7} {st:<6} {updated}")


if __name__ == "__main__":
    main()
