# Phase 10 — MSMA Bridge Architecture

**Status:** Design proposal | **For:** Walid Al-Bassel review
**Date:** 2026-05-14 | **Author:** Claude Sonnet 4.6 (autonomous design)

> **NO CODE WRITTEN.** This is a design-only document. Walid reviews, modifies, approves before any implementation.

---

## 1. Overview

Phase 10 connects Jarvis to the MSMA bot (running at `C:\Users\walid\Documents\MSMA`) via a local FastAPI server. Walid can then use voice commands to query customer info, check pending RFQs, draft quotes, and more — without touching keyboard.

**Architecture:**
```
Jarvis Voice → BrainRouter → execute msma_query action
                                   ↓ HTTP
             MSMA Bot (FastAPI localhost:9000)
                                   ↓
                        MSMA Database / Google Sheets / Email
```

---

## 2. What MSMA Bot Already Has

*(Walid: verify this list against actual MSMA code before proceeding)*

From previous sprints, MSMA bot likely has:
- Customer database (Zamilfood, SMI, Olayan Descon, BHIG, Taj Construction, Fardeen)
- RFQ/quote tracking
- Email draft generation
- Payment status tracking
- Google Sheets integration

---

## 3. FastAPI Server Design

### 3.1 Location
```
C:\Users\walid\Documents\MSMA\jarvis_api\
  server.py       — FastAPI app
  auth.py         — HMAC token validation
  routes/
    customers.py
    quotes.py
    rfq.py
    emails.py
    reports.py
  audit.py        — log every Jarvis→MSMA call
```

### 3.2 Authentication

HMAC-SHA256 shared secret between Jarvis and MSMA:

```python
# Both sides share: JARVIS_MSMA_SECRET = "..." in config/.env

# Request header:
X-Jarvis-Token: HMAC-SHA256(timestamp + path + body, secret)
X-Jarvis-Timestamp: 1716700000  # reject if > 30s old (replay protection)
```

### 3.3 Endpoints (15 proposed)

| Method | Path | Action | Voice trigger example |
|--------|------|--------|----------------------|
| GET | `/health` | Ping/status | "is MSMA online" |
| GET | `/customers` | List all customers | "list my customers" |
| GET | `/customers/{name}` | Customer brief | "show brief for Zamilfood" |
| GET | `/customers/{name}/pending` | Pending items for customer | "what's pending for SMI" |
| GET | `/rfq/today` | Today's RFQs | "ايه الـ-RFQs النهارده" |
| GET | `/rfq/pending` | All unresponded RFQs | "RFQs محتاجة رد" |
| GET | `/rfq/{id}` | RFQ detail | "show RFQ 147" |
| GET | `/quotes/recent` | Last 10 quotes | "show recent quotes" |
| GET | `/quotes/pending_payment` | Unpaid quotes | "ايه المبالغ المستحقة" |
| GET | `/quotes/{id}` | Quote detail | "show quote 123" |
| POST | `/quotes/draft` | Draft a quote | "ابعت quote لـ Zamilfood رقم 123" |
| GET | `/emails/pending_reply` | Emails needing reply | "ايه الإيميلات اللي محتاجة رد" |
| POST | `/emails/draft` | Draft reply | "ارد على إيميل Fardeen" |
| GET | `/reports/daily` | Daily summary | "summary النهارده" |
| GET | `/reports/monthly` | Monthly KPIs | "كيف الشهر" |

### 3.4 Safety Whitelist (Hard Rules)

**ALLOWED:** GET (read-only), POST to `/quotes/draft`, POST to `/emails/draft`

**NEVER ALLOWED via Jarvis:**
- DELETE on any endpoint
- Any destructive database operation
- Sending emails directly (draft only — Walid reviews in Outlook before sending)
- Any financial transaction
- Modifying customer records

---

## 4. New Jarvis Action: `msma_query`

### 4.1 In `actions/safe_actions.py`

```python
def msma_query(self, transcript=None) -> dict:
    """Route query to MSMA API and speak result."""
    url, params = self._parse_msma_intent(transcript)
    resp = requests.get(f'http://localhost:9000{url}',
                        headers=self._msma_auth_headers(url),
                        timeout=5)
    data = resp.json()
    summary = data.get('spoken_summary', str(data)[:100])
    self.speak(summary)
    return {'action': 'msma_query', 'endpoint': url, 'success': True, 'data': data}
```

### 4.2 In `brain_router.py` SYSTEM_PROMPT

Add to ACTIONS section:
```
- msma_query: query MSMA bot for customer/quote/RFQ/email data
  params: natural language query → router maps to endpoint
  examples: "show Zamilfood pending", "list unresponded RFQs", "draft quote 123"
```

### 4.3 Endpoint Intent Mapping

In `safe_actions.py`, add `_parse_msma_intent(transcript)` that maps phrases to endpoints:

```python
MSMA_INTENT_MAP = [
    (r'(brief|info|show).*(zamilfood|smi|olayan|bhig|taj|fardeen)', '/customers/{name}'),
    (r'pending.*(rfq|requests)', '/rfq/pending'),
    (r'(today|اليوم).*(rfq)', '/rfq/today'),
    (r'(pending|outstanding).*(payment|invoice|مبلغ)', '/quotes/pending_payment'),
    (r'pending.*(reply|رد|email)', '/emails/pending_reply'),
    (r'daily.*(summary|report)', '/reports/daily'),
]
```

---

## 5. Audit Log

Every Jarvis→MSMA API call logged to `logs/msma_audit.jsonl`:

```json
{
  "timestamp": "2026-05-14T08:00:00",
  "transcript": "show Zamilfood pending",
  "endpoint": "/customers/zamilfood/pending",
  "method": "GET",
  "status_code": 200,
  "response_summary": "3 pending RFQs, 1 pending payment",
  "duration_ms": 45
}
```

---

## 6. Error Handling

| Error | Jarvis response |
|-------|----------------|
| MSMA API offline | "MSMA is offline يابابا. Check if the bot is running." |
| Endpoint not found | "I don't know how to query that yet يابابا." |
| Auth failure | "Authentication failed — check JARVIS_MSMA_SECRET in .env" |
| Timeout (>5s) | "MSMA is slow, try again يابابا." |
| Bad data format | "Got a response but couldn't parse it يابابا." |

---

## 7. Implementation Plan

**Total estimated effort:** 16h

| Sub-task | Effort | Owner | Description |
|----------|--------|-------|-------------|
| 1. MSMA audit | 2h | Walid + Claude | Read MSMA code, list available data |
| 2. MSMA FastAPI server skeleton | 2h | Claude | server.py + auth.py + health endpoint |
| 3. MSMA customer routes | 2h | Claude | GET /customers, /customers/{name} |
| 4. MSMA RFQ + quote routes | 2h | Claude | GET /rfq/*, /quotes/* |
| 5. MSMA email draft route | 2h | Claude | POST /emails/draft |
| 6. Jarvis msma_query action | 2h | Claude | safe_actions.py + intent map |
| 7. brain_router prompt update | 1h | Claude | Add msma_query to ACTIONS |
| 8. Integration tests | 3h | Claude | Mock MSMA API, test Jarvis→MSMA flow |

**Prerequisite for Sub-task 1:** Walid reads MSMA code and confirms what data is accessible.

---

## 8. Risks + Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| MSMA data format unknown | HIGH | HIGH | Sub-task 1: audit first |
| Voice misinterprets customer name | MEDIUM | LOW | Always confirm before draft actions |
| MSMA API port 9000 conflicts | LOW | MEDIUM | Make port configurable |
| Auth secret exposed in logs | LOW | HIGH | Never log secret, only HMAC hash |
| Jarvis speaks sensitive data aloud | MEDIUM | MEDIUM | Truncate to summary, not full data |

---

## 9. Walid's Review Checklist

Before approving implementation:

- [ ] Confirm MSMA bot has data accessible by code (not just UI)
- [ ] Confirm customer names match expected spelling (Zamilfood / Zamilfood Food?)
- [ ] Approve endpoint list — add/remove as needed
- [ ] Approve `msma_query` confirmation flow (should drafts need "yes"?)
- [ ] Confirm port 9000 is free on laptop
- [ ] Agree on JARVIS_MSMA_SECRET rotation policy
- [ ] Review audit log format — is transcript logging acceptable?
- [ ] Sign off: "only drafts, never send" as hard rule

---

## 10. Voice Command Examples

```
"ايه الـ-RFQs اللي محتاجة رد"
→ msma_query → GET /rfq/pending
→ "3 RFQs pending reply: SMI #147 (2 days old), Zamilfood #89, Taj #211"

"show Zamilfood brief"
→ msma_query → GET /customers/zamilfood
→ "Zamilfood: cash customer, 5 open quotes, last contact 3 days ago, 2 pending RFQs"

"draft quote 123 for Zamilfood"
→ msma_query → POST /quotes/draft {quote_id: 123, customer: 'zamilfood'}
→ "Draft created يابابا. Check Outlook to review before sending."

"كيف الشهر"
→ msma_query → GET /reports/monthly
→ "May so far: 12 quotes sent, 4 approved, SAR 145,000 total value, 3 pending payment"
```
