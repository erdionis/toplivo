import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r'C:\Users\erdi\toplivo')

from monitor import find_matches_with_gb, _enrich_matches_with_gb, format_telegram_message, tb_normalize, gb_normalize
from pathlib import Path

tb = [tb_normalize({
    'id': '1', 'name': 'Газпром', 'address': 'ul Lenina 1',
    'lat': 44.95, 'lon': 38.95,
    'last_transaction': '2026-09-01T23:30:00+03:00',
    'available': True, 'ai95_available': True
})]
gb = [gb_normalize({
    'osm_id': 'test1', 'name': 'Газпром', 'address': 'ul Lenina 1',
    'lat': 44.951, 'lon': 38.951,
    'crowd': 'очередь 20-50', 'crowd_raw': 3,
    'ai95_status': 'available', 'confidence': 88,
    'queue': '20-50', 'last_transaction': '2026-09-01T23:00:00+03:00',
    'fuel_detail': {'queue': 'очередь 20-50'}
})]

matches, tb_only, sber_only, gb_only = find_matches_with_gb(tb, [], gb)
print(f"matches={len(matches)} tb_only={len(tb_only)} gb_only={len(gb_only)}")

if matches:
    m = matches[0]
    print(f"Before enrich: gb_confidence={m.get('gb_confidence')}, gb_queue_info={m.get('gb_queue_info')}, gb_crowd={m.get('gb_crowd')}")
    _enrich_matches_with_gb(matches, gb)
    m = matches[0]
    print(f"After enrich: gb_confidence={m.get('gb_confidence')}, gb_queue_info={m.get('gb_queue_info')}, gb_crowd={m.get('gb_crowd')}")

    msg = format_telegram_message(matches, Path('test.md'))
    for line in msg.split('\n'):
        print(line)
else:
    print("NO MATCHES!")
    print(f"tb_only: {len(tb_only)}")
    print(f"gb_only: {len(gb_only)}")
