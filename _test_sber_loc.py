import json, urllib.request, ssl, time

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

# GET session
req = urllib.request.Request('https://sberazs.ru/api/session', method='POST',
    headers={'Content-Type':'application/json', 'User-Agent':'Mozilla/5.0', 'Accept':'application/json'})
with urllib.request.urlopen(req, context=ctx) as r:
    sid = json.loads(r.read())['sessionId']
print(f"Session: {sid[:12]}...")

# Get details for Газпром Северская
sber_id = "70000001031676386"
req3 = urllib.request.Request(
    f'https://sberazs.ru/api/stations/{sber_id}',
    headers={'X-Sberfuel-Session': sid, 'User-Agent':'Mozilla/5.0', 'Accept':'application/json'}
)
with urllib.request.urlopen(req3, context=ctx) as r:
    data = json.loads(r.read())
    details = data.get('station', {})
    loc = details.get('location', {})
    print(f"location = {json.dumps(loc)}")
    print(f"lastPaymentAt = {details.get('lastPaymentAt')}")
    print(f"fuels = {json.dumps(details.get('fuels', []), ensure_ascii=False)}")
    print(f"crowdState = {json.dumps(details.get('crowdState', {}))}")
