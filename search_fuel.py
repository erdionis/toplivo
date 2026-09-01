#!/usr/bin/env python3
"""
Поиск АЗС в Краснодаре с бензином АИ-95 и статусом "Есть топливо".
Данные берутся с gdebenz.ru в реальном времени.
"""

import requests
import csv
import os
import time
from datetime import datetime

# Настройки
KUBDARODAR_CENTER = (45.0355, 38.9753)
BBOX_SIZE = 0.15  # Размер одной области запроса (градусы) — больше = меньше запросов
RT_URL = "https://gdebenz.ru/api/rt"
STATIONS_URL = "https://gdebenz.ru/api/stations"
REPORTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://gdebenz.ru/",
}


def get_rt_token() -> str:
    """Получить runtime-токен с сервера."""
    resp = requests.get(RT_URL, headers=HEADERS, timeout=10)
    resp.raise_for_status()
    return resp.json()["rt"]


def get_stations_in_bbox(lat1: float, lon1: float, lat2: float, lon2: float, rt_token: str) -> list:
    """Получить список АЗС в bounding box с retry."""
    params = {"lat1": lat1, "lon1": lon1, "lat2": lat2, "lon2": lon2}
    headers = {**HEADERS, "X-RT": rt_token}
    
    for attempt in range(3):
        try:
            resp = requests.get(STATIONS_URL, params=params, headers=headers, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
            else:
                print(f"  Ошибка bbox ({lat1:.2f},{lon1:.2f})-({lat2:.2f},{lon2:.2f}): {e}")
                return []


def generate_bboxes(center_lat: float, center_lon: float, size: float) -> list:
    """Сгенерировать bbox-области вокруг центральной точки (3x3 сетка)."""
    bboxes = []
    for i in range(-1, 2):  # -1, 0, 1
        for j in range(-1, 2):
            lat1 = center_lat + i * size - size / 2
            lon1 = center_lon + j * size - size / 2
            lat2 = center_lat + i * size + size / 2
            lon2 = center_lon + j * size + size / 2
            bboxes.append((lat1, lon1, lat2, lon2))
    return bboxes


def is_ai95_available(station: dict) -> bool:
    """Проверить, есть ли АИ-95 и статус 'Есть топливо'."""
    status = station.get("status")
    if status != "yes":
        return False
    
    fuels_now = station.get("fuels_now", "")
    if "95" in fuels_now:
        return True
    
    prices_now = station.get("prices_now", {})
    if "95" in prices_now and prices_now["95"].get("p"):
        return True
    
    return False


def main():
    """Основная функция."""
    print("=" * 60)
    print("Поиск АЗС в Краснодаре с бензином АИ-95")
    print("=" * 60)
    
    # Получаем токен
    print("\n[1/4] Получаю токен...")
    rt_token = get_rt_token()
    print(f"  Токен: {rt_token[:8]}...")
    
    # Генерируем области запроса (3x3 сетка, каждая ~15 км)
    print("\n[2/4] Генерирую области запроса...")
    bboxes = generate_bboxes(*KUBDARODAR_CENTER, BBOX_SIZE)
    print(f"  Всего областей: {len(bboxes)}")
    
    # Запрашиваем станции
    print("\n[3/4] Запрашиваю станции...")
    all_stations = {}  # osm_id -> station (дедупликация)
    
    for i, (lat1, lon1, lat2, lon2) in enumerate(bboxes):
        stations = get_stations_in_bbox(lat1, lon1, lat2, lon2, rt_token)
        new_count = 0
        for s in stations:
            osm_id = s.get("osm_id")
            if osm_id and osm_id not in all_stations:
                all_stations[osm_id] = s
                new_count += 1
        print(f"  Область {i+1}/{len(bboxes)}: {len(stations)} станций ({new_count} новых)")
        time.sleep(1)  # пауза между запросами
    
    print(f"\n  Всего уникальных станций: {len(all_stations)}")
    
    # Фильтруем по АИ-95
    print("\n[4/4] Фильтрую по АИ-95...")
    filtered = [s for s in all_stations.values() if is_ai95_available(s)]
    print(f"  Найдено с АИ-95 (есть топливо): {len(filtered)}")
    
    # Сохраняем в CSV
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    filename = f"krasnodar_ai95_{timestamp}.csv"
    filepath = os.path.join(REPORTS_DIR, filename)
    
    os.makedirs(REPORTS_DIR, exist_ok=True)
    
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow([
            "Название", "Бренд", "Адрес", "Широта", "Долгота",
            "Статус", "Цена АИ-95", "Цена АИ-92", "Цена ДТ", "Марки топлива",
        ])
        
        filtered.sort(key=lambda x: x.get("name", ""))
        
        for s in filtered:
            prices = s.get("prices_now", {})
            writer.writerow([
                s.get("name", ""),
                s.get("brand", ""),
                s.get("addr", ""),
                s.get("lat", ""),
                s.get("lon", ""),
                s.get("status", ""),
                prices.get("95", {}).get("p", ""),
                prices.get("92", {}).get("p", ""),
                prices.get("ДТ", {}).get("p", ""),
                s.get("fuels_now", ""),
            ])
    
    print(f"\n{'=' * 60}")
    print(f"Отчет сохранен: {filepath}")
    print(f"{'=' * 60}")
    
    # Таблица в консоль
    if filtered:
        print(f"\n{'Название':<25} {'Адрес':<30} {'95 цена':<10} {'Статус'}")
        print("-" * 80)
        for s in filtered:
            prices = s.get("prices_now", {})
            price_95 = prices.get("95", {}).get("p", "—")
            print(f"{s.get('name', ''):<25} {s.get('addr', '')[:28]:<30} {price_95:<10} {s.get('status', '')}")
    else:
        print("\nАЗС с АИ-95 (есть топливо) не найдены.")


if __name__ == "__main__":
    main()
