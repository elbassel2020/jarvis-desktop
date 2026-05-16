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
