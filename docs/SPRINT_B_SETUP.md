# Jarvis v0.14.0 Sprint B — Manual Setup Guide

Sprint B adds Gmail, Zoho IMAP, Google Calendar, Google Drive, and Telegram.
Each requires a one-time credential setup. All secrets stored in Windows Credential Manager via the Credential Broker.

---

## 1. Google Cloud Project (Gmail + Calendar + Drive)

One OAuth flow covers all three Google services.

### Cloud Console setup (~15 min)

1. Go to https://console.cloud.google.com
2. Create project: **"jarvis-walid-personal"**
3. Enable these APIs (search each):
   - Gmail API
   - Google Calendar API
   - Google Drive API
4. APIs & Services → OAuth consent screen:
   - User Type: **External**
   - App name: Jarvis
   - Support email: lighting@amscontrol.com
   - Add yourself as a test user
5. Credentials → Create Credentials → **OAuth client ID**:
   - Application type: **Desktop app**
   - Name: Jarvis Desktop
6. Download the JSON → save as:
   `C:\Users\walid\Documents\Jarvis\config\google_client_secret.json`

### Run the OAuth flow (once)

```powershell
cd C:\Users\walid\Documents\Jarvis
.\venv\Scripts\Activate.ps1
python scripts/setup_gmail_oauth.py
```

Browser opens → sign in with your Google account → grant all permissions → done.
Refresh token is stored in Windows Credential Manager as `cred://gmail_refresh/walid`.

---

## 2. Zoho IMAP (lighting@amscontrol.com)

### If 2FA is enabled

1. Login to https://mail.zoho.com
2. Settings → Mail Accounts → **Application-Specific Passwords**
3. Generate one, name it "Jarvis"

### Store credentials

```powershell
python scripts/setup_zoho_credentials.py
```

Enter: email = `lighting@amscontrol.com`, password = app password.

---

## 3. Telegram Bot (@MSMA_Walid_bot)

1. Open Telegram → **@BotFather** → `/mybots` → `@MSMA_Walid_bot` → API Token

```powershell
python scripts/setup_telegram_bot.py
```

Paste the token. Bot will **only** respond to your chat_id (1032010360).

---

## 4. Verify all integrations

```powershell
cd C:\Users\walid\Documents\Jarvis
.\venv\Scripts\Activate.ps1

python -c "from jarvis.integrations.gmail import email_list_unread; print('Gmail unread:', len(email_list_unread(5)))"
python -c "from jarvis.integrations.zoho_mail import list_unread; print('Zoho unread:', len(list_unread(5)))"
python -c "from jarvis.integrations.gcal import list_today; print('Today events:', len(list_today()))"
python -c "from jarvis.integrations.gdrive import search; print('Drive search:', len(search('Zamilfood', 3)))"
```

All should return numbers (0 or more) without errors.

---

## v0.14.0-beta.3 — Intelligence Layer (May 17, 2026)

### 1. Council Mode
Parallel LLM ensemble (Sonnet + Haiku + Gemini Flash-Lite → synthesis pass).
```python
from jarvis.intelligence import council_decide
result = await council_decide(
    "How should I reply to an angry customer?",
    context="Customer received wrong price quote 3 times."
)
print(result.decision)      # synthesized recommendation
print(result.confidence)    # 0.0–1.0
print(result.cost_usd_cents)
```

### 2. Specialist Agents
Four agents auto-routed by keyword (Arabic + English).
```python
from jarvis.agents import route_to_agent, detect_agent

# Auto-route
result = await route_to_agent("Tell me about Zamilfood's order history")
# → CustomerAgent enriched with deepdive summary

# Force an agent
result = await route_to_agent(
    "Draft a follow-up email",
    agent_name="email",
    context="Customer hasn't replied in 10 days."
)
```
Agents: `sales`, `research`, `email`, `customer`.

### 3. Daily Morning Brief
Council-synthesized morning summary, cached in `daily_briefs` table.
```python
from jarvis.tasks.daily_brief import generate_brief, get_brief
await generate_brief()               # or schedule via task queue
print(get_brief())                   # returns cached content
# Enqueue via scheduler:
from jarvis.tasks.queue import enqueue
enqueue("daily_brief", {})
```

### 4. Action Orchestrator
LLM decomposes complex requests into ordered, executable steps.
```python
from jarvis.intelligence import plan_actions, execute_plan

plan = await plan_actions(
    "Find Zamilfood's last quote and draft a follow-up email",
    context="We haven't heard from them in 3 weeks."
)
# plan.steps → [customer_lookup, email_draft]
# plan.risk_level → "MEDIUM"

results = await execute_plan(
    plan,
    action_handlers={"customer_lookup": ..., "email_draft": ...},
    confirm_callback=async_confirm_fn,   # called for email_send_draft etc.
)
```

### 5. Health Dashboard
```python
from jarvis.dashboard import get_health_status, get_audit_report

status = get_health_status()
# status["integrations"] → {gmail: "configured", zoho: "missing", ...}
# status["task_queue"]   → {pending: 2, completed: 148, ...}
# status["memory"]       → {semantic: 315, daily_briefs: 7, ...}

report = get_audit_report(days=7)
# report["by_actor"]  → {agent:sales: 12, council: 5, ...}
# report["by_outcome"] → {ok: 90, error:ValueError: 2, ...}
```

---

## v0.14.0-beta.4 — Sprint E: Bridge Client + Voice Wiring (May 17, 2026)

### MSMA Bridge Client
Talks to MSMA Bot bridge server with HMAC-SHA256 per-request auth.
```python
from jarvis.bridges import MsmaBridgeClient, BridgeNotConfiguredError

client = MsmaBridgeClient()  # reads cred://msma_bridge/hmac_key

# Create a quote
quote = await client.create_quote(
    customer="Zamilfood",
    items=[{"sku": "CB-16A", "qty": 10, "unit_price": 45.0}],
)

# Full workflow
invoice = await client.send_invoice(quote["quote_id"], "ceo@zamilfood.com")
payment = await client.log_payment(invoice["invoice_id"], 4500.0, "bank_transfer", "TXN-001")

# Other endpoints
balance = await client.customer_balance("Zamilfood")
quotes  = await client.list_open_quotes(customer="Zamilfood")
health  = await client.health()
```

### Mock Server (local testing)
```bash
# Standalone
python scripts/mock_msma_bridge.py --port 9000

# In tests
from scripts.mock_msma_bridge import start_mock_server, stop_mock_server
server = start_mock_server(port=9001, hmac_key="test-key")
# ... run tests ...
stop_mock_server(server)
```

### 5 New Voice Commands
| Voice command | Intent | Action |
|---|---|---|
| "council: should I offer a discount?" | `council` | 3-LLM ensemble decision |
| "brief" / "daily brief" | `brief` | Speak cached or generate morning brief |
| "ask: what are ZATCA requirements?" | `ask` | Route to specialist agent |
| "health" / "system health" | `health` | Report integration status |
| "plan: find quote and draft follow-up" | `plan` | Decompose task into steps |
