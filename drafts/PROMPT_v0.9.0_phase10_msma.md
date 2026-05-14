# Sprint Prompt: JARVIS v0.9.0 — MSMA Bridge Implementation

> Paste this AFTER Walid approves PHASE_10_MSMA_BRIDGE.md and audits MSMA code.
> Requires: MSMA FastAPI server already running at localhost:9000.

---

JARVIS v0.9.0 — MSMA Voice Bridge (Implementation)

PREREQUISITE: Read drafts/PHASE_10_MSMA_BRIDGE.md. Walid has audited MSMA code and confirmed available endpoints. FastAPI server is running.

SCOPE:
- Add `msma_query` action to Jarvis safe_actions.py
- Add `msma_bridge.py` client module
- Update brain_router.py ACTIONS prompt
- Tests for Jarvis→MSMA flow (MSMA API mocked)

CONSTRAINTS:
- New file: `core/msma_bridge.py` — MSMAClient class
- Modify: `actions/safe_actions.py` — add `msma_query()` method
- Modify: `core/brain_router.py` — add msma_query to SYSTEM_PROMPT ACTIONS
- DO NOT modify MSMA bot code here — that was separate sprint
- All MSMA calls are read-only from Jarvis side (drafts only for writes)
- HMAC auth from `JARVIS_MSMA_SECRET` env var
- Timeout: 5s hard limit on all MSMA API calls

IMPLEMENTATION STEPS:

1. Create core/msma_bridge.py:
```python
class MSMAClient:
    BASE_URL = 'http://localhost:9000'
    TIMEOUT = 5

    def __init__(self):
        self._secret = os.environ.get('JARVIS_MSMA_SECRET', '')

    def _auth_headers(self, path: str) -> dict:
        ts = str(int(time.time()))
        payload = ts + path
        sig = hmac.new(self._secret.encode(), payload.encode(), 'sha256').hexdigest()
        return {'X-Jarvis-Token': sig, 'X-Jarvis-Timestamp': ts}

    def get(self, path: str) -> dict:
        resp = requests.get(
            self.BASE_URL + path,
            headers=self._auth_headers(path),
            timeout=self.TIMEOUT
        )
        resp.raise_for_status()
        return resp.json()

    def post(self, path: str, data: dict) -> dict:
        resp = requests.post(
            self.BASE_URL + path,
            json=data,
            headers=self._auth_headers(path),
            timeout=self.TIMEOUT
        )
        resp.raise_for_status()
        return resp.json()

    def health(self) -> bool: ...
    def customers(self) -> list: ...
    def customer_brief(self, name: str) -> dict: ...
    def rfq_pending(self) -> list: ...
    def rfq_today(self) -> list: ...
    def quotes_pending_payment(self) -> list: ...
    def daily_report(self) -> dict: ...
    def monthly_report(self) -> dict: ...
```

2. Intent regex map in core/msma_bridge.py:
```python
MSMA_ROUTES = [
    (r'health|online|running|شغال', '/health', 'GET'),
    (r'customers|عملاء', '/customers', 'GET'),
    (r'(zamilfood|smi|olayan|bhig|taj|fardeen).*(brief|info|show)', '/customers/{name}', 'GET'),
    (r'(pending|today).*(rfq|requests)', '/rfq/pending', 'GET'),
    (r'(today|اليوم).*(rfq|طلب)', '/rfq/today', 'GET'),
    (r'(pending|outstanding).*(payment|invoice|مبلغ)', '/quotes/pending_payment', 'GET'),
    (r'pending.*(reply|رد|email|إيميل)', '/emails/pending_reply', 'GET'),
    (r'(daily|اليوم).*(summary|report|تقرير)', '/reports/daily', 'GET'),
    (r'(monthly|الشهر).*(summary|report|كيف)', '/reports/monthly', 'GET'),
]

def route_transcript(transcript: str) -> tuple[str, str] | None:
    """Returns (path, method) or None."""
```

3. Add to actions/safe_actions.py:
```python
def msma_query(self, transcript=None) -> dict:
    if not transcript:
        return {'action': 'msma_query', 'error': 'no transcript', 'success': False}
    from core.msma_bridge import MSMAClient, route_transcript
    client = MSMAClient()
    route = route_transcript(transcript)
    if not route:
        self.speak("لم أفهم ماذا تريد من MSMA يابابا")
        return {'action': 'msma_query', 'error': 'no route', 'success': False}
    path, method = route
    try:
        data = client.get(path) if method == 'GET' else {}
        summary = data.get('spoken_summary') or data.get('summary') or str(data)[:100]
        self.speak(summary)
        # Audit log
        self._log_msma_call(transcript, path, 200, summary)
        return {'action': 'msma_query', 'endpoint': path, 'success': True}
    except requests.Timeout:
        self.speak("MSMA بطيء يابابا، حاول تاني")
        return {'action': 'msma_query', 'error': 'timeout', 'success': False}
    except Exception as e:
        self.speak("MSMA مش شغال يابابا")
        return {'action': 'msma_query', 'error': str(e), 'success': False}

def _log_msma_call(self, transcript, endpoint, status, summary):
    from pathlib import Path
    import json
    entry = {
        'timestamp': datetime.now().isoformat(),
        'transcript': transcript,
        'endpoint': endpoint,
        'status': status,
        'summary': summary[:100],
    }
    with open('logs/msma_audit.jsonl', 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')
```

4. Add to ACTION_MAP:
```python
'msma_query': 'msma_query',
```

5. Add to brain_router.py SYSTEM_PROMPT under ACTIONS:
```
- msma_query: query MSMA business bot for customer/quote/RFQ/email data
  Use for: customer status, pending RFQs, outstanding payments, daily report
  Examples: "show Zamilfood pending", "ايه RFQs اليوم", "monthly report"
```

TESTS: tests/test_msma_bridge.py
- Mock requests.get/post
- Test route_transcript() for 8 patterns
- Test auth header generation
- Test timeout → correct spoken response
- Test unknown intent → correct response

COMMIT: feat: v0.9.0 — MSMA voice bridge (customer/RFQ/quote/report queries)

ENV var to add to config/.env:
```
JARVIS_MSMA_SECRET=<shared-secret-with-msma-server>
```
