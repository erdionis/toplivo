"""
Получение списка заправок в Краснодаре с покупкой за последние 30 минут.
Сохраняет результат в markdown файл.

Запуск: python fuel_stations.py
"""

import json
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

BASE_URL = "https://sberazs.ru"
KRD_LAT = 45.035
KRD_LON = 39.72
GASOLINE_TYPES = {"ai92", "ai95", "ai98", "ai100"}
LIMIT_MINUTES = 30

# Заправки Краснодара — поиск по городу
KRD_SEARCH_QUERIES = [
    "АЗС Краснодар", "заправка Краснодар", "Газпромнефть Краснодар",
    "Лукойл Краснодар", "Роснефть Краснодар", "Татнефть Краснодар",
    "Атан Краснодар", "Уфимнефть Краснодар", "Русойл Краснодар",
    "Дельта Краснодар", "Сивнефть Краснодар", "Петрол Краснодар",
    "Башнефть Краснодар", "СберАЗС Краснодар", "Магнит Краснодар",
    "Краснодар АИ-92", "Краснодар АИ-95", "Краснодар АИ-98",
]

# Конкретные заправки вне Краснодара — ищем по ID
TRACKED_STATION_IDS = [
    "70000001031676386",  # Газпром, АЗС — ст-ца Северская, А-146 48 км, 2
    "70000001030898411",  # Южная нефтяная компания, АЗС — ст-ца Северская, А-146 48 км, 1
    "70000001076684922",  # Южная нефтяная компания — ст-ца Северская, ул. Ленина, 2/1
    "70000001031551554",  # Роснефть, АЗС — пгт Афипский, Магистральная, 4
    "70000001029837404",  # Лукойл — пгт Энем, ул. Перова, 42
]

# Адреса Краснодара (город, не край)
KRD_CITY_PREFIX = "Краснодарский край, Краснодар,"


def api_post(path: str, body: dict, session_id: str) -> dict:
    """POST-запрос к API."""
    url = BASE_URL + path
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-Sberfuel-Session": session_id,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def api_get(path: str, session_id: str) -> dict:
    """GET-запрос к API."""
    url = BASE_URL + path
    req = urllib.request.Request(
        url,
        headers={"X-Sberfuel-Session": session_id},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def search_stations(query: str, session_id: str) -> list:
    """Поиск заправок по запросу (только город Краснодар)."""
    result = api_post(
        "/api/search/suggest",
        {"query": query, "lat": KRD_LAT, "lon": KRD_LON},
        session_id,
    )
    return [
        s for s in result.get("suggestions", [])
        if s.get("type") == "fuel_station"
        and s.get("subtitle", "").startswith(KRD_CITY_PREFIX)
    ]


def get_station_details(station_id: str, session_id: str) -> dict | None:
    """Получение деталей заправки по ID."""
    try:
        result = api_get(f"/api/stations/{station_id}", session_id)
        return result.get("station")
    except urllib.error.HTTPError:
        return None


def collect_krasnodar_stations(session_id: str) -> dict[str, dict]:
    """Сбор всех уникальных заправок в Краснодаре через поиск."""
    stations = {}
    for q in KRD_SEARCH_QUERIES:
        try:
            for s in search_stations(q, session_id):
                sid = s["id"]
                if sid not in stations:
                    stations[sid] = s
        except Exception:
            pass
        time.sleep(0.15)
    return stations


def collect_tracked_stations(session_id: str) -> dict[str, dict]:
    """Получение конкретных отслеживаемых заправок по ID."""
    stations = {}
    for sid in TRACKED_STATION_IDS:
        try:
            details = get_station_details(sid, session_id)
            if details:
                stations[sid] = {
                    "id": sid,
                    "title": details["name"],
                    "subtitle": details["address"],
                }
        except Exception:
            pass
        time.sleep(0.1)
    return stations


def filter_by_time_and_fuel(
    stations: dict[str, dict], now: datetime, session_id: str
) -> list[dict]:
    """Фильтрация: есть бензин + покупка за последние N минут."""
    cutoff = now - timedelta(minutes=LIMIT_MINUTES)
    tracked_ids = set(TRACKED_STATION_IDS)
    results = []

    for sid, basic_info in stations.items():
        details = get_station_details(sid, session_id)
        if not details or not details.get("fuels") or not details.get("lastPaymentAt"):
            continue

        # проверка адреса: город Краснодар ИЛИ отслеживаемая заправка
        addr = details.get("address", "")
        is_krd_city = addr.startswith(KRD_CITY_PREFIX)
        is_tracked = sid in tracked_ids
        if not is_krd_city and not is_tracked:
            continue

        # проверка бензина
        gasoline = [
            f for f in details["fuels"] if f["type"] in GASOLINE_TYPES
        ]
        if not gasoline:
            continue

        # проверка времени
        last_payment = datetime.fromisoformat(details["lastPaymentAt"])
        if last_payment.tzinfo is None:
            last_payment = last_payment.replace(tzinfo=timezone(timedelta(hours=3)))
        if last_payment < cutoff:
            continue

        minutes_ago = int((now - last_payment).total_seconds() / 60)
        results.append({
            "id": details["id"],
            "name": details["name"],
            "address": details["address"],
            "gasoline": gasoline,
            "last_payment": details["lastPaymentAt"],
            "minutes_ago": minutes_ago,
        })
        time.sleep(0.08)

    results.sort(key=lambda x: x["minutes_ago"])
    return results


def format_fuel(fuel_list: list[dict]) -> str:
    """Форматирование списка топлива."""
    parts = []
    for f in fuel_list:
        status_icon = "✅" if f["availabilityStatus"] == "available" else ""
        limit = f" ({f['limitLiters']}л)" if f.get("limitLiters") else ""
        parts.append(f"{f['type'].upper()}{status_icon}{limit}")
    return ", ".join(parts)


def save_markdown(results: list[dict], now: datetime, filepath: str) -> None:
    """Сохранение результатов в markdown файл."""
    msk = timezone(timedelta(hours=3))
    now_msk = now.astimezone(msk) if now.tzinfo else now.replace(tzinfo=timezone.utc).astimezone(msk)

    lines = [
        f"# Заправки: г. Краснодар + отслеживаемые ({len(results)} шт.)",
        "",
        f"**Дата формирования:** {now_msk.strftime('%d.%m.%Y %H:%M:%S')} МСК",
        f"**Окно:** покупка за последние {LIMIT_MINUTES} минут",
        f"**Отслеживаемые заправки:** Северская (3), Афипский (1), Энем (1)",
        "",
        "---",
        "",
    ]

    if not results:
        lines.append("_Заправок с покупкой за последние 30 минут не найдено._")
    else:
        lines.append("| # | Название | Адрес | Бензин | Минут назад |")
        lines.append("|---|----------|-------|--------|-------------|")
        for i, r in enumerate(results, 1):
            fuel_str = format_fuel(r["gasoline"])
            link = f"[ссылка](https://sberazs.ru/?station={r['id']})"
            lines.append(
                f"| {i} | **{r['name']}** | {r['address']} | {fuel_str} | {r['minutes_ago']} |"
            )

        lines.extend([
            "",
            "---",
            "",
            "## Детали",
            "",
        ])
        for i, r in enumerate(results, 1):
            fuel_str = format_fuel(r["gasoline"])
            lines.extend([
                f"### {i}. {r['name']}",
                f"- **Адрес:** {r['address']}",
                f"- **Бензин:** {fuel_str}",
                f"- **Последняя покупка:** {r['last_payment']} ({r['minutes_ago']} мин назад)",
                f"- **Ссылка:** https://sberazs.ru/?station={r['id']}",
                "",
            ])

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    session_id = f"fuel-catalog-{int(time.time())}"
    now = datetime.now(timezone.utc)

    print("Сбор заправок в Краснодаре...")
    krd_stations = collect_krasnodar_stations(session_id)
    print(f"Найдено уникальных заправок (Краснодар): {len(krd_stations)}")

    print("Получение отслеживаемых заправок...")
    tracked_stations = collect_tracked_stations(session_id)
    print(f"Отслеживаемых заправок: {len(tracked_stations)}")

    all_stations = {**krd_stations, **tracked_stations}

    print("Фильтрация по времени покупки и наличию бензина...")
    results = filter_by_time_and_fuel(all_stations, now, session_id)
    print(f"Заправок с покупкой за {LIMIT_MINUTES} мин: {len(results)}")

    ts = now.strftime("%d-%m-%Y %H-%M")
    filename = f"sberazs_{ts}.md"
    filepath = f"toplivo/reports/{filename}"

    save_markdown(results, now, filepath)
    print(f"Результат сохранён: {filepath}")


if __name__ == "__main__":
    main()
