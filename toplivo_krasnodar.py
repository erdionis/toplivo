"""
Приложение для получения списка заправок в Краснодаре и окрестностях
с наличием АИ-95 и покупкой за последние 30 минут.
Данные берутся с API toplivo.tbank.ru.
"""

import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path

# API endpoint
API_URL = "https://toplivo.tbank.ru/api/v1/stations"

# Время жизни транзакции (в минутах)
TRANSACTION_MAX_AGE_MINUTES = 30

# Регионы для отслеживания
# Каждый регион: name, bounds (bounding box), address_filters (список подстрок для фильтрации)
REGIONS = [
    {
        "name": "Краснодар",
        "bounds": {
            "minLat": 44.94,
            "maxLat": 45.13,
            "minLon": 38.82,
            "maxLon": 39.15,
        },
        "address_filters": None,  # Все заправки в регионе
    },
    {
        "name": "Станица Северская (А-146)",
        "bounds": {
            "minLat": 44.83,
            "maxLat": 44.88,
            "minLon": 38.65,
            "maxLon": 38.72,
        },
        "address_filters": ["Северская", "А-146"],
    },
    {
        "name": "Пос. Афипский",
        "bounds": {
            "minLat": 44.88,
            "maxLat": 44.94,
            "minLon": 38.80,
            "maxLon": 38.87,
        },
        "address_filters": ["Афипск"],
    },
    {
        "name": "Пос. Энем (Адыгея)",
        "bounds": {
            "minLat": 44.89,
            "maxLat": 44.97,
            "minLon": 38.85,
            "maxLon": 38.96,
        },
        "address_filters": ["Энем"],
    },
]


def fetch_stations(bounds: dict) -> list[dict]:
    """Получение списка АЗС из API по bounding box."""
    response = requests.get(API_URL, params=bounds, timeout=15)
    response.raise_for_status()
    data = response.json()
    if data.get("status") != "ok":
        raise ValueError(f"API вернул статус: {data.get('status')}")
    return data.get("payload", [])


def matches_address_filters(station: dict, filters: list[str] | None) -> bool:
    """Проверка, соответствует ли АЗС фильтрам адреса."""
    if not filters:
        return True
    addr = station.get("addr", "").lower()
    return any(f.lower() in addr for f in filters)


def filter_by_transaction_time(
    stations: list[dict], now: datetime, max_age_minutes: int
) -> list[dict]:
    """Фильтрация АЗС, где покупка была за последние N минут."""
    cutoff = now - timedelta(minutes=max_age_minutes)
    result = []
    for station in stations:
        last_tx = station.get("lastTransactionAt")
        if not last_tx:
            continue
        tx_time = datetime.fromisoformat(last_tx.replace("Z", "+00:00"))
        if tx_time >= cutoff:
            result.append(station)
    return result


def filter_by_fuel_ai95(stations: list[dict]) -> list[dict]:
    """Фильтрация АЗС, где АИ-95 доступен или возможно доступен."""
    return [
        s
        for s in stations
        if s.get("statusByFuelType", {}).get("95") in ("available", "maybe_available")
    ]


def fuel_icon(status: str) -> str:
    """Возвращает иконку для статуса топлива."""
    mapping = {
        "available": "✅",
        "not_available": "❌",
        "maybe_available": "❓",
        "no_data": "—",
    }
    return mapping.get(status, "?")


def ai95_status_label(station: dict) -> str:
    """Возвращает метку статуса АИ-95 для отчёта."""
    status = station.get("statusByFuelType", {}).get("95", "no_data")
    if status == "available":
        return "✅"
    elif status == "maybe_available":
        return "❓*"
    return "❌"


def generate_markdown(
    stations: list[dict], now: datetime, total_fetched: int
) -> str:
    """Генерация markdown-отчёта."""
    msk = timezone(timedelta(hours=3))
    now_msk = now.astimezone(msk)
    lines = [
        f"# Заправки Краснодара и окрестностей — АИ-95 (покупка за 30 мин)",
        "",
        f"**Дата формирования:** {now_msk.strftime('%d.%m.%Y %H:%M:%S')} МСК",
        f"**Регионы:** {', '.join(r['name'] for r in REGIONS)}",
        f"**Всего АЗС получено:** {total_fetched}",
        f"**С АИ-95 и покупкой за 30 мин:** {len(stations)}",
        "",
        "## Таблица заправок",
        "",
        "| # | Название | Бренд | Адрес | Уверенность | Покупка (МСК) | 92 | 95 | 100 | ДТ |",
        "|---|---------|-------|-------|-------------|---------------|----|----|-----|----|",
    ]

    for i, s in enumerate(stations, 1):
        name = s.get("name", "—")
        brand = s.get("brand") or "—"
        addr = s.get("addr", "—")
        # Убираем "Россия, " из адреса для краткости
        addr_short = addr.replace("Россия, ", "")
        confidence = s.get("confidence", 0) * 100
        last_tx = s.get("lastTransactionAt", "")
        if last_tx:
            tx_time = datetime.fromisoformat(last_tx.replace("Z", "+00:00"))
            tx_msk = tx_time.astimezone(msk)
            tx_str = tx_msk.strftime("%H:%M")
        else:
            tx_str = "—"

        fuel = s.get("statusByFuelType", {})
        f92 = fuel_icon(fuel.get("92", "no_data"))
        f95 = ai95_status_label(s)
        f100 = fuel_icon(fuel.get("100", "no_data"))
        fd = fuel_icon(fuel.get("diesel", "no_data"))

        lines.append(
            f"| {i} | {name} | {brand} | {addr_short} | {confidence:.1f}% | {tx_str} | {f92} | {f95} | {f100} | {fd} |"
        )

    lines.extend(
        [
            "",
            "---",
            "",
            "**Легенда:** ✅ есть | ❓* возможно есть (неподтверждённо) | ❌ нет | — нет данных",
        ]
    )

    return "\n".join(lines)


def main():
    now = datetime.now(timezone.utc)
    print(f"Текущее время (UTC): {now.strftime('%Y-%m-%d %H:%M:%S')}")

    all_stations = {}  # id -> station (дедупликация)
    total_fetched = 0

    for region in REGIONS:
        print(f"\n--- {region['name']} ---")
        try:
            stations = fetch_stations(region["bounds"])
            total_fetched += len(stations)
            print(f"  Получено АЗС: {len(stations)}")

            # Фильтр по адресу (если указаны фильтры)
            if region["address_filters"]:
                stations = [
                    s for s in stations
                    if matches_address_filters(s, region["address_filters"])
                ]
                print(f"  После фильтра по адресу: {len(stations)}")

            for s in stations:
                all_stations[s["id"]] = s

        except Exception as e:
            print(f"  Ошибка: {e}")

    print(f"\n--- Итого уникальных АЗС: {len(all_stations)} ---")

    stations_list = list(all_stations.values())

    print(f"Фильтрация по времени транзакции (за {TRANSACTION_MAX_AGE_MINUTES} мин)...")
    stations_list = filter_by_transaction_time(stations_list, now, TRANSACTION_MAX_AGE_MINUTES)
    print(f"  Осталось АЗС: {len(stations_list)}")

    print("Фильтрация по наличию АИ-95...")
    stations_list = filter_by_fuel_ai95(stations_list)
    print(f"  Осталось АЗС: {len(stations_list)}")

    # Сортировка по времени транзакции (новые сверху)
    stations_list.sort(key=lambda s: s.get("lastTransactionAt", ""), reverse=True)

    print("Генерация markdown-отчёта...")
    md_content = generate_markdown(stations_list, now, total_fetched)

    # Сохранение в файл
    output_dir = Path(__file__).parent / "reports"
    output_dir.mkdir(exist_ok=True)

    filename = f"toplivo_{now.strftime('%Y%m%d_%H%M%S')}.md"
    filepath = output_dir / filename
    filepath.write_text(md_content, encoding="utf-8")
    print(f"Отчёт сохранён: {filepath}")

    # Вывод в консоль (с обработкой ошибки кодировки Windows)
    try:
        print("\n" + md_content)
    except UnicodeEncodeError:
        print(f"\nОтчёт сохранён в {filepath}")
        print("Откройте файл для просмотра отчёта.")


if __name__ == "__main__":
    main()
