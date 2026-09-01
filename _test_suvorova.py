"""Поиск АЗС Газпромнефть ул Суворова 2/1"""
import sys, json
sys.path.insert(0, r"C:\Users\erdi\toplivo")
from monitor import *

# 1. Ищем в toplivo.tbank.ru
print("=== toplivo.tbank.ru ===")
tb_stations = tb_fetch_stations(KRASNODAR_BOUNDS)
for s in tb_stations:
    addr = s.get("addr", "")
    if "суворова" in addr.lower() or "суворов" in addr.lower():
        print(f"  {s.get('name')} | {addr}")
        print(f"    lat={s.get('lat')}, lon={s.get('lon')}")
        print(f"    status={s.get('status')}, fuel={s.get('statusByFuelType')}")
        print()

# 2. Ищем в sberazs.ru
print("=== sberazs.ru ===")
for q in ["Газпромнефть Суворова Краснодар", "Газпромнефть Краснодар"]:
    results = sber_search(q, KRD_LAT, KRD_LON)
    for sug in results:
        sub = sug.get("subtitle", "")
        if "суворова" in sub.lower() or "суворов" in sub.lower():
            sid = sug["id"]
            print(f"  {sug.get('title')} | {sub}")
            det = sber_get_station_details(sid)
            if det:
                st = det.get("station", {})
                print(f"    fuels: {[f.get('type') + ':' + f.get('availabilityStatus', '?') for f in st.get('fuels', [])]}")
                print(f"    lastPayment: {st.get('lastPaymentAt')}")
            print()
    time.sleep(0.2)

# 3. Проверяем координаты - где должна быть Суворова 2/1
print("=== Координаты ===")
print("  Искомый адрес: Краснодар, улица Суворова, 2/1")
print("  Газпромнефть на Суворова 2/1 в TB:")
for s in tb_stations:
    if "суворов" in s.get("addr", "").lower():
        print(f"    lat={s.get('lat')}, lon={s.get('lon')}")
