#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Анализ чеков покупки АИ-95 на АЗС Газпром, ст-ца Северская
Только из toplivo.tbank.ru и sberazs.ru (без gdebenz.ru)"""
import re
import os
from collections import defaultdict

reports_dir = "reports/history"

# Ищем строки с "Газпром" и "Северская" и чеком покупки (✅)
# Формат: | # | Название | Адрес | ... | ✅ | DD.MM HH:MM |
# Нам нужны только чеки покупки (✅) - это подтвержденные покупки топлива

pattern = re.compile(
    r'\|\s*\d+\s*\|\s*Газпром[^|]*Северская[^|]*\|\s*(?:[^|]*\|\s*)*(✅)\s*\|\s*(\d{2}\.\d{2})\s+(\d{2}:\d{2})',
    re.IGNORECASE
)

# Альтернативный паттерн для sberazs формата
pattern_sber = re.compile(
    r'\|\s*\d+\s*\|\s*Газпром,\s*АЗС\s*\|\s*ст-ца\s*Северская[^|]*\|\s*(\d+)%\s*\|\s*(✅)\s*\|\s*(\d{2}\.\d{2})\s+(\d{2}:\d{2})',
    re.IGNORECASE
)

# Паттерн для tb формата с пересечением или только tb
pattern_tb = re.compile(
    r'\|\s*\d+\s*\|\s*Газпром\s*\|\s*Краснодарский край[^|]*станица Северская[^|]*\|\s*(?:sber\+gb|sber|tb\+sber\+gb|tb\+sber)?\s*\|\s*(\d+)%\s*\|\s*(✅)\s*(?:\(очередь\s*(\d+-\d+)\))?\s*\|\s*(\d{2}\.\d{2})\s+(\d{2}:\d{2})',
    re.IGNORECASE
)

data = []

for filename in sorted(os.listdir(reports_dir)):
    if not filename.endswith('.md'):
        continue
    
    filepath = os.path.join(reports_dir, filename)
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Проверяем, что отчет из tb+sber (без gdebenz)
    if 'gdebenz' in content.lower() or 'gb=' in content.lower():
        # Если отчет содержит gdebenz, пропускаем его или фильтруем
        # Но нужно проверить заголовок - иногда gdebenz добавляется позже
        pass
    
    date_match = re.search(r'monitor_(\d{8})_', filename)
    if not date_match:
        continue
    file_date = date_match.group(1)
    report_date = f"{file_date[6:8]}.{file_date[4:6]}"
    report_time = f"{file_date[8:10]}:{file_date[10:12]}"
    
    # Ищем наши АЗС
    for match in pattern_sber.finditer(content):
        conf, status, date, time = match.groups()
        if date == report_date and status == '✅':
            data.append({
                'date': date,
                'time': time,
                'source': 'sber',
                'queue': None,
                'file': filename,
                'report_time': report_time
            })
    
    for match in pattern_tb.finditer(content):
        conf, status, queue, date, time = match.groups()
        if date == report_date and status == '✅':
            data.append({
                'date': date,
                'time': time,
                'source': 'tb',
                'queue': queue,
                'file': filename,
                'report_time': report_time
            })

# Удаляем дубликаты (одна покупка может быть в двух источниках)
seen = set()
unique_data = []
for item in data:
    key = (item['date'], item['time'])
    if key not in seen:
        seen.add(key)
        unique_data.append(item)

# Сортируем по дате и времени
unique_data.sort(key=lambda x: (x['date'], x['time']))

# Вывод
results = []
results.append("=" * 80)
results.append("ЧЕКИ ПОКУПКИ АИ-95 НА АЗС 'ГАЗПРОМ, СТ-ЦА СЕВЕРСКАЯ, А-146 48 КМ, 2'")
results.append("Источники: toplivo.tbank.ru + sberazs.ru (без gdebenz.ru)")
results.append("=" * 80)
results.append("")

# Группировка по дням
by_date = defaultdict(list)
for item in unique_data:
    by_date[item['date']].append(item)

for date in sorted(by_date.keys()):
    entries = by_date[date]
    results.append(f"Дата: {date}.09.2026")
    results.append("-" * 60)
    results.append(f"  Всего чеков покупки: {len(entries)}")
    results.append("")
    
    for e in entries:
        queue_str = f" (очередь {e['queue']})" if e['queue'] else ""
        results.append(f"  {e['time']} МСК - ✅ покупка{queue_str} [{e['source']}]")
    
    # Группировка по часам
    hourly = defaultdict(int)
    for e in entries:
        hour = int(e['time'].split(':')[0])
        hourly[hour] += 1
    
    results.append("")
    results.append("  По часам:")
    for hour in sorted(hourly.keys()):
        results.append(f"    {hour:02d}:00-{hour+1:02d}:00 - {hourly[hour]} чеков")
    results.append("")

# Итого
results.append("=" * 80)
results.append("ИТОГОВАЯ СВОДКА")
results.append("=" * 80)
results.append(f"Всего чеков покупки: {len(unique_data)}")
results.append("")

# По дням
results.append("По дням:")
for date in sorted(by_date.keys()):
    results.append(f"  {date}.09: {len(by_date[date])} чеков")

# По часам (суммарно)
all_hourly = defaultdict(int)
for item in unique_data:
    hour = int(item['time'].split(':')[0])
    all_hourly[hour] += 1

results.append("")
results.append("По часам (суммарно за все дни):")
for hour in sorted(all_hourly.keys()):
    bar = '█' * all_hourly[hour]
    results.append(f"  {hour:02d}:00 - {all_hourly[hour]:2d} {bar}")

results.append("")
results.append("=" * 80)
results.append("ВЫВОДЫ")
results.append("=" * 80)

# Анализ
morning = sum(v for k, v in all_hourly.items() if 6 <= k < 12)
afternoon = sum(v for k, v in all_hourly.items() if 12 <= k < 18)
evening = sum(v for k, v in all_hourly.items() if 18 <= k < 24)

results.append(f"Утро (06:00-12:00): {morning} чеков")
results.append(f"День (12:00-18:00): {afternoon} чеков")
results.append(f"Вечер (18:00-24:00): {evening} чеков")
results.append("")

# Самые частые часы
if all_hourly:
    max_hour = max(all_hourly.items(), key=lambda x: x[1])
    results.append(f"Самый активный час: {max_hour[0]:02d}:00 ({max_hour[1]} чеков)")

with open('azs_cheques_analysis.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(results))

print("Готово! Результаты в azs_cheques_analysis.txt")