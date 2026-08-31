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

# ============================================================
# Общие настройки
# ============================================================

LIMIT_MINUTES = 30
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
    if last_tx:
        tx_time = datetime.fromisoformat(last_tx.replace("Z", "+00:00"))
        minutes_ago = int((datetime.now(timezone.utc) - tx_time).total_seconds() / 60)

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
        "last_transaction": last_tx,
        "fuel_detail": fuel,
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
        return {
            "source": "sber",
            "id": station.get("id", ""),
            "name": station.get("title", "—"),
            "brand": "—",
            "address": station.get("subtitle", "—"),
            "confidence": 0,
            "ai95_status": "no_data",
            "has_fuel": False,
            "minutes_ago": None,
            "last_transaction": None,
            "fuel_detail": {},
        }

    fuels = details.get("fuels", [])
    gasoline = [f for f in fuels if f.get("type") in ("ai92", "ai95", "ai98", "ai100")]
    has_fuel = len(gasoline) > 0

    # Статус АИ-95
    ai95_fuel = next((f for f in fuels if f.get("type") == "ai95"), None)
    ai95 = ai95_fuel.get("availabilityStatus", "no_data") if ai95_fuel else "no_data"

    last_payment = details.get("lastPaymentAt")
    minutes_ago = None
    if last_payment:
        try:
            payment_time = datetime.fromisoformat(last_payment)
            if payment_time.tzinfo is None:
                payment_time = payment_time.replace(tzinfo=MSK)
            minutes_ago = int((datetime.now(timezone.utc) - payment_time).total_seconds() / 60)
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
        "last_transaction": last_payment,
        "fuel_detail": {f["type"]: f.get("availabilityStatus", "no_data") for f in fuels},
    }


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
    Использует нечёткое сопоставление по адресу.
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

    # Ищем пересечения
    for key, tb_s in tb_by_key.items():
        if key in sber_by_key:
            sber_s = sber_by_key[key]
            # Объединяем данные: берём лучшие значения
            match = {
                "name": tb_s["name"],
                "brand": tb_s["brand"],
                "address": tb_s["address"],
                "confidence": max(tb_s["confidence"], sber_s["confidence"]),
                "ai95_status": _merge_ai95(tb_s["ai95_status"], sber_s["ai95_status"]),
                "has_fuel": tb_s["has_fuel"] or sber_s["has_fuel"],
                "minutes_ago": _min_minutes(tb_s["minutes_ago"], sber_s["minutes_ago"]),
                "source_tb": tb_s,
                "source_sber": sber_s,
            }
            matches.append(match)
        else:
            tb_only.append(tb_s)

    for key, sber_s in sber_by_key.items():
        if key not in tb_by_key:
            sber_only.append(sber_s)

    return matches, tb_only, sber_only


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


def format_minutes(minutes: int | None) -> str:
    """Форматирование минут назад."""
    if minutes is None:
        return "—"
    return str(minutes)


def generate_unified_report(
    matches: list[dict],
    tb_only: list[dict],
    sber_only: list[dict],
    now: datetime,
) -> str:
    """Генерация объединённого markdown-отчёта."""
    now_msk = now.astimezone(MSK)
    total = len(matches) + len(tb_only) + len(sber_only)

    lines = [
        f"# Объединённый отчёт: заправки Краснодара и окрестностей",
        "",
        f"**Дата:** {now_msk.strftime('%d.%m.%Y %H:%M:%S')} МСК",
        f"**Источники:** toplivo.tbank.ru + sberazs.ru",
        f"**Окно:** покупка за {LIMIT_MINUTES} минут",
        f"**Найдено:** {total} заправок (пересечение: {len(matches)}, Т-Банк: {len(tb_only)}, Сбер: {len(sber_only)})",
        "",
    ]

    # --- Таблица 1: Пересечение ---
    lines.append("## Пересечение (оба источника подтверждают)")
    lines.append("")
    if matches:
        lines.append("| # | Название | Бренд | Адрес | Уверенность | АИ-95 | Покупка (МСК) мин. назад |")
        lines.append("|---|---------|-------|-------|-------------|-------|--------------------------|")
        for i, s in enumerate(matches, 1):
            addr_short = s["address"].replace("Россия, ", "")
            lines.append(
                f"| {i} | {s['name']} | {s['brand']} | {addr_short} | {s['confidence']:.0f}% | {ai95_icon(s['ai95_status'])} | {format_minutes(s['minutes_ago'])} |"
            )
    else:
        lines.append("_Нет заправок, найденных в обоих источниках._")
    lines.append("")

    # --- Таблица 2: Только Т-Банк ---
    lines.append("## Только toplivo.tbank.ru")
    lines.append("")
    if tb_only:
        lines.append("| # | Название | Бренд | Адрес | Уверенность | АИ-95 | Покупка (МСК) мин. назад |")
        lines.append("|---|---------|-------|-------|-------------|-------|--------------------------|")
        for i, s in enumerate(tb_only, 1):
            addr_short = s["address"].replace("Россия, ", "")
            lines.append(
                f"| {i} | {s['name']} | {s['brand']} | {addr_short} | {s['confidence']:.0f}% | {ai95_icon(s['ai95_status'])} | {format_minutes(s['minutes_ago'])} |"
            )
    else:
        lines.append("_Нет заправок только из этого источника._")
    lines.append("")

    # --- Таблица 3: Только Сбер ---
    lines.append("## Только sberazs.ru")
    lines.append("")
    if sber_only:
        lines.append("| # | Название | Адрес | Уверенность | АИ-95 | Покупка (МСК) мин. назад |")
        lines.append("|---|---------|-------|-------------|-------|--------------------------|")
        for i, s in enumerate(sber_only, 1):
            addr_short = s["address"].replace("Краснодарский край, ", "")
            lines.append(
                f"| {i} | {s['name']} | {addr_short} | {s['confidence']:.0f}% | {ai95_icon(s['ai95_status'])} | {format_minutes(s['minutes_ago'])} |"
            )
    else:
        lines.append("_Нет заправок только из этого источника._")
    lines.append("")

    lines.extend([
        "---",
        "",
        "**Легенда:** ✅ есть | ❓* возможно есть | ❌ нет | — нет данных",
    ])

    return "\n".join(lines)


# ============================================================
# Главная функция
# ============================================================


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

    # Фильтрация: покупка за 30 мин + есть бензин
    sber_filtered = [
        s for s in sber_all.values()
        if s["has_fuel"]
        and s["minutes_ago"] is not None
        and s["minutes_ago"] <= LIMIT_MINUTES
    ]
    print(f"  Итого Сбер (с фильтром): {len(sber_filtered)}")

    # --- 3. Сопоставление и генерация отчёта ---
    print("\n--- Сопоставление ---")
    matches, tb_only, sber_only = find_matches(tb_filtered, sber_filtered)
    print(f"  Пересечение: {len(matches)}")
    print(f"  Только Т-Банк: {len(tb_only)}")
    print(f"  Только Сбер: {len(sber_only)}")

    report = generate_unified_report(matches, tb_only, sber_only, now)

    # Сохранение
    output_dir = Path(__file__).parent / "reports"
    output_dir.mkdir(exist_ok=True)

    filename = f"monitor_{now.strftime('%Y%m%d_%H%M%S')}.md"
    filepath = output_dir / filename
    filepath.write_text(report, encoding="utf-8")
    print(f"\nОтчёт сохранён: {filepath}")

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

        # Добавляем файл
        subprocess.run(
            ["git", "add", str(filepath.name)],
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
