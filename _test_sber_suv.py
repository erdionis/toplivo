"""Проверка АЗС Газпромнефть Суворова 2/1 в sberazs.ru"""
import sys, time
sys.path.insert(0, r"C:\Users\erdi\toplivo")
from monitor import *

session_id = f"fuel-test-{int(time.time())}"

# Ищем через search
for q in ["Газпромнефть Суворова Краснодар", "Газпромнефть Краснодар"]:
    print(f"Query: {q}")
    results = sber_search_stations(q, session_id)
    for sug in results:
        sub = sug.get("subtitle", "")
        if "суворова" in sub.lower() or "суворов" in sub.lower():
            sid = sug["id"]
            print(f"  FOUND: {sug.get('title')} | {sub}")
            print(f"  id={sid}")
            
            det = sber_get_station_details(sid, session_id)
            if det:
                st = det.get("station", {})
                print(f"  name: {st.get('name')}")
                print(f"  address: {st.get('address')}")
                print(f"  lastPaymentAt: {st.get('lastPaymentAt')}")
                print(f"  fuels:")
                for f in st.get("fuels", []):
                    print(f"    {f.get('type')}: {f.get('availabilityStatus')}")
                
                norm = sber_normalize(sug, det)
                print(f"\n  NORMALIZED:")
                print(f"    has_fuel: {norm['has_fuel']}")
                print(f"    ai95_status: {norm['ai95_status']}")
                print(f"    minutes_ago: {norm['minutes_ago']}")
                print(f"    address: {norm['address']}")
                
                # Проверяем фильтр
                passes = norm["has_fuel"] and norm["minutes_ago"] is not None and norm["minutes_ago"] <= LIMIT_MINUTES
                print(f"    PASSES FILTER: {passes}")
                if not passes:
                    print(f"    REASON: has_fuel={norm['has_fuel']}, minutes_ago={norm['minutes_ago']}, limit={LIMIT_MINUTES}")
            print()
    time.sleep(0.2)
