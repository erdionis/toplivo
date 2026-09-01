"""Детальная проверка sber API для Газпромнефть Суворова"""
import sys, time, json
sys.path.insert(0, r"C:\Users\erdi\toplivo")
from monitor import *

session_id = f"fuel-test-{int(time.time())}"

results = sber_search_stations("Газпромнефть Суворова Краснодар", session_id)
for sug in results:
    sub = sug.get("subtitle", "")
    if "суворова" in sub.lower():
        sid = sug["id"]
        print(f"Search result: {json.dumps(sug, ensure_ascii=False, indent=2)}")
        
        det_raw = sber_api_get(f"/api/stations/{sid}", session_id)
        print(f"\nDetails raw: {json.dumps(det_raw, ensure_ascii=False, indent=2)}")
        break
