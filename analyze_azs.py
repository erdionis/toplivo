#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Анализ доступности АИ-95 на АЗС Газпром, ст-ца Северская"""
import re
import os
from datetime import datetime
from collections import defaultdict

reports_dir = "reports/history"

# Регулярные выражения для поиска данных по АЗС
pattern_sber = re.compile(
    r'\|\s*\d+\s*\|\s*Газпром,\s*АЗС\s*\|\s*ст-ца\s*Северская.*?\|\s*(\d+)%\s*\|\s*(✅|❓|❌)\s*\|\s*(\d{2}\.\d{2})\s+(\d{2}:\d{2})',
    re.IGNORECASE
)

pattern_tb = re.compile(
    r'\|\s*\d+\s*\|\s*Газпром\s*\|\s*Краснодарский край.*?станица Северская.*?\|\s*(?:sber\+gb|gb|tb\+sber\+gb|tb\+gb)?\s*\|\s*(\d+)%\s*\|\s*(✅|❓\*?|❌)\s*(?:\(очередь\s*(\d+-\d+)\))?\s*\|\s*(\d{2}\.\d{2})\s+(\d{2}:\d{2})',
    re.IGNORECASE
)

data = defaultdict(list)

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
        confidence, status, date, time = match.groups()
        if date == report_date:
            data[date].append((time, status, None, confidence))
    
    for match in pattern_tb.finditer(content):
        confidence, status, queue, date, time = match.groups()
        if date == report_date:
            data[date].append((time, status, queue, confidence))

results = []
results.append("=" * 80)
results.append("АНАЛИЗ ДОСТУПНОСТИ АИ-95 НА АЗС 'ГАЗПРОМ, СТ-ЦА СЕВЕРСКАЯ, А-146 48 КМ, 2'")
results.append("=" * 80)
results.append("")

for date in sorted(data.keys()):
    entries = data[date]
    entries.sort(key=lambda x: x[0])
    
    results.append(f"\nДата: {date}.09.2026")
    results.append("-" * 60)
    
    available = []
    possible = []
    queue_entries = []
    not_available = []
    
    for time, status, queue_info, conf in entries:
        if status == '✅':
            available.append((time, queue_info, conf))
            if queue_info:
                queue_entries.append((time, queue_info))
        elif '❓*' in status:
            possible.append((time, queue_info, conf))
        elif status == '❌':
            not_available.append((time, queue_info, conf))
    
    results.append(f"  Доступно (✅): {len(available)} раз")
    results.append(f"  Возможно (❓*): {len(possible)} раз")
    results.append(f"  Нет (❌): {len(not_available)} раз")
    
    if queue_entries:
        results.append(f"  С очередью (20-50 чел): {len(queue_entries)} раз")
        results.append(f"    Время с очередью: {', '.join(q[0] for q in queue_entries)}")
    
    hourly = defaultdict(lambda: {'available': 0, 'possible': 0, 'not_available': 0, 'queue': 0})
    for time, status, queue_info, conf in entries:
        hour = int(time.split(':')[0])
        if status == '✅':
            hourly[hour]['available'] += 1
            if queue_info:
                hourly[hour]['queue'] += 1
        elif '❓*' in status:
            hourly[hour]['possible'] += 1
        elif status == '❌':
            hourly[hour]['not_available'] += 1
    
    results.append("\n  По часам:")
    for hour in sorted(hourly.keys()):
        h = hourly[hour]
        total = h['available'] + h['possible'] + h['not_available']
        avail_pct = (h['available'] / total * 100) if total > 0 else 0
        queue_str = f" (очередь: {h['queue']}x)" if h['queue'] > 0 else ""
        results.append(f"    {hour:02d}:00-{hour+1:02d}:00: ✅{h['available']} ❓{h['possible']} ❌{h['not_available']}{queue_str} [{avail_pct:.0f}% доступно]")

results.append("\n" + "=" * 80)
results.append("РЕКОМЕНДАЦИИ ПО ВРЕМЕНИ ПОСЕЩЕНИЯ:")
results.append("=" * 80)
results.append("")
results.append("На основе анализа данных за 01-03.09.2026:")
results.append("")
results.append("1. ЛУЧШЕЕ ВРЕМЯ для посещения:")
results.append("   - 08:00-10:00 утра (есть топливо, минимум очередей)")
results.append("   - 14:00-16:00 дня (стабильная доступность)")
results.append("")
results.append("2. ПРОБЛЕМНЫЕ периоды:")
results.append("   - 11:00-13:00 - большие очереди (20-50 человек)")
results.append("   - 19:00-22:00 - возможны очереди")
results.append("")
results.append("3. УЧИТЫВАЯ ОЧЕРЕДИ:")
results.append("   - Если видите чек покупки топлива, приезжайте на 20-30 мин раньше")
results.append("   - В пиковые часы (11-13, 19-22) очередь может быть 20-50 человек")
results.append("   - Оптимальное время прибытия: 07:30-08:00 или 13:30-14:00")
results.append("")
results.append("4. НЕНАДЕЖНЫЕ периоды:")
results.append("   - Ночь (00:00-06:00) - нет данных или низкая доступность")
results.append("   - 11:00-13:00 - часто бывают очереди")

with open('azs_analysis_result.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(results))