#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Анализ пиков покупок АИ-95 на АЗС Газпром, ст-ца Северская
Рекомендации: приезжать за 20-30 мин до пика покупок"""
import re
import os
from collections import defaultdict
from datetime import datetime, timedelta

reports_dir = "reports/history"

pattern_sber = re.compile(
    r'\|\s*\d+\s*\|\s*Газпром,\s*АЗС\s*\|\s*ст-ца\s*Северская[^|]*\|\s*(\d+)%\s*\|\s*(✅)\s*\|\s*(\d{2}\.\d{2})\s+(\d{2}:\d{2})',
    re.IGNORECASE
)

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
    
    date_match = re.search(r'monitor_(\d{8})_', filename)
    if not date_match:
        continue
    file_date = date_match.group(1)
    report_date = f"{file_date[6:8]}.{file_date[4:6]}"
    
    for match in pattern_sber.finditer(content):
        conf, status, date, time = match.groups()
        if date == report_date and status == '✅':
            data.append({'date': date, 'time': time, 'source': 'sber', 'queue': None})
    
    for match in pattern_tb.finditer(content):
        conf, status, queue, date, time = match.groups()
        if date == report_date and status == '✅':
            data.append({'date': date, 'time': time, 'source': 'tb', 'queue': queue})

# Удаляем дубликаты
seen = set()
unique_data = []
for item in data:
    key = (item['date'], item['time'])
    if key not in seen:
        seen.add(key)
        unique_data.append(item)

unique_data.sort(key=lambda x: (x['date'], x['time']))

def find_clusters(entries, gap_minutes=60):
    """Находит кластеры (пики) покупок. gap_minutes - максимальный разрыв между покупками в кластере"""
    if not entries:
        return []
    
    clusters = []
    current_cluster = [entries[0]]
    
    for i in range(1, len(entries)):
        prev_time = datetime.strptime(f"{entries[i-1]['date']} {entries[i-1]['time']}", "%d.%m %H:%M")
        curr_time = datetime.strptime(f"{entries[i]['date']} {entries[i]['time']}", "%d.%m %H:%M")
        
        diff_minutes = (curr_time - prev_time).total_seconds() / 60
        
        if diff_minutes <= gap_minutes:
            current_cluster.append(entries[i])
        else:
            if len(current_cluster) >= 2:  # Кластер = 2+ покупки подряд
                clusters.append(current_cluster)
            current_cluster = [entries[i]]
    
    if len(current_cluster) >= 2:
        clusters.append(current_cluster)
    
    return clusters

results = []
results.append("=" * 80)
results.append("АНАЛИЗ ПИКОВ ПОКУПОК АИ-95")
results.append("АЗС 'ГАЗПРОМ, СТ-ЦА СЕВЕРСКАЯ, А-146 48 КМ, 2'")
results.append("Источники: toplivo.tbank.ru + sberazs.ru")
results.append("=" * 80)
results.append("")
results.append("ЛОГИКА:")
results.append("  Чек покупки (✅) = топливо ЕСТЬ на АЗС")
results.append("  Пик покупок = топливо привезли и активно раскупают")
results.append("  Затишье между пиками = топливо закончилось")
results.append("  => Приезжайте ЗА 20-30 мин до пика покупок!")
results.append("")

# Группировка по дням
by_date = defaultdict(list)
for item in unique_data:
    by_date[item['date']].append(item)

for date in sorted(by_date.keys()):
    entries = by_date[date]
    clusters = find_clusters(entries)
    
    results.append(f"День: {date}.09.2026")
    results.append("-" * 60)
    results.append(f"  Всего покупок: {len(entries)}")
    results.append(f"  Кластеров (пиков): {len(clusters)}")
    results.append("")
    
    # Все покупки
    results.append("  Все покупки:")
    for e in entries:
        results.append(f"    {e['time']}")
    results.append("")
    
    # Кластеры
    if clusters:
        results.append("  КЛАСТЕРЫ (ПИКИ ПОКУПОК):")
        for i, cluster in enumerate(clusters, 1):
            start_time = cluster[0]['time']
            end_time = cluster[-1]['time']
            count = len(cluster)
            
            # Рекомендуемое время прибытия (за 20-30 мин до начала)
            start_dt = datetime.strptime(f"{date} {start_time}", "%d.%m %H:%M")
            recommend_dt = start_dt - timedelta(minutes=25)
            recommend_time = recommend_dt.strftime("%H:%M")
            
            results.append(f"    Пик #{i}: {start_time} - {end_time} ({count} покупок)")
            results.append(f"    => Рекомендация: приезжать в {recommend_time} (за 25 мин до начала)")
        results.append("")

# Итоги
results.append("=" * 80)
results.append("ИТОГОВЫЕ РЕКОМЕНДАЦИИ")
results.append("=" * 80)
results.append("")

# Собираем все кластеры за все дни
all_clusters = []
for date in sorted(by_date.keys()):
    clusters = find_clusters(by_date[date])
    for cluster in clusters:
        all_clusters.append(cluster)

results.append(f"Всего кластеров (пиков) за 3 дня: {len(all_clusters)}")
results.append("")

# Группируем кластеры по времени суток
time_groups = {
    'утро (08:00-12:00)': [],
    'день (12:00-17:00)': [],
    'вечер (17:00-22:00)': []
}

for cluster in all_clusters:
    start_hour = int(cluster[0]['time'].split(':')[0])
    if 8 <= start_hour < 12:
        time_groups['утро (08:00-12:00)'].append(cluster)
    elif 12 <= start_hour < 17:
        time_groups['день (12:00-17:00)'].append(cluster)
    elif 17 <= start_hour < 22:
        time_groups['вечер (17:00-22:00)'].append(cluster)

results.append("Пики покупок по времени суток:")
for group_name, clusters in time_groups.items():
    if clusters:
        results.append(f"  {group_name}: {len(clusters)} пиков")
        for cluster in clusters:
            start = cluster[0]['time']
            end = cluster[-1]['time']
            results.append(f"    - {start}-{end} ({len(cluster)} покупок)")

results.append("")
results.append("=" * 80)
results.append("КОГДА ПРИЕЗЖАТЬ (рекомендации)")
results.append("=" * 80)
results.append("")
results.append("На основе анализа пиков покупок:")
results.append("")

# Находим самые частые времена начала пиков
peak_starts = defaultdict(int)
for cluster in all_clusters:
    start_hour = cluster[0]['time'].split(':')[0]
    peak_starts[start_hour] += 1

results.append("Самые частые начала пиков покупок:")
for hour, count in sorted(peak_starts.items(), key=lambda x: -x[1])[:5]:
    rec_hour = int(hour) - 1 if int(hour) > 0 else 0
    results.append(f"  {hour}:00 - {count} раз (приезжайте в ~{rec_hour}:30-{hour}:00)")

results.append("")
results.append("ОБЩИЕ РЕКОМЕНДАЦИИ:")
results.append("  1. Следите за чеками покупки в мониторинге")
results.append("  2. Как только видите чек - приезжайте через 20-30 минут")
results.append("  3. Не ждите идеального времени - чек = топливо есть!")
results.append("  4. В пиковые часы (11-13, 19-22) очередь 20-50 человек")

with open('azs_peaks_analysis.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(results))

print("Готово! Результаты в azs_peaks_analysis.txt")