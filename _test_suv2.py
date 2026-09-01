"""Детальная проверка двух Газпромнефть на Суворова"""
import sys
sys.path.insert(0, r"C:\Users\erdi\toplivo")
from monitor import *

tb_stations = tb_fetch_stations(KRASNODAR_BOUNDS)
for s in tb_stations:
    addr = s.get("addr", "")
    if "суворова" in addr.lower():
        norm = tb_normalize(s)
        print(f"ID: {s['id']}")
        print(f"  addr: {addr}")
        print(f"  status: {s.get('status')}")
        print(f"  statusByFuelType: {s.get('statusByFuelType')}")
        print(f"  lastTransactionAt: {s.get('lastTransactionAt')}")
        print(f"  has_fuel: {norm['has_fuel']}")
        print(f"  ai95_status: {norm['ai95_status']}")
        print(f"  minutes_ago: {norm['minutes_ago']}")
        print()
