"""
One-shot migration: read existing config/.env, move secrets to keyring,
print a removal manifest.
"""
import os
import re
from pathlib import Path
from dotenv import dotenv_values
from jarvis.security.credential_broker import broker

ENV_PATH = Path("config/.env")
MAPPING = {
    "ANTHROPIC_API_KEY":  ("anthropic", "default"),
    "GEMINI_API_KEY":     ("gemini", "default"),
    "GROQ_API_KEY":       ("groq", "default"),
    "ELEVENLABS_API_KEY": ("elevenlabs", "default"),
    "OPENAI_API_KEY":     ("openai", "default"),
    "ZOHO_IMAP_USER":     ("zoho_imap_user", "lighting"),
    "ZOHO_IMAP_PASSWORD": ("zoho_imap_password", "lighting"),
    "TELEGRAM_BOT_TOKEN": ("telegram", "msma_walid_bot"),
}

if not ENV_PATH.exists():
    print(f"No {ENV_PATH} found; nothing to migrate")
    raise SystemExit(0)

env = dotenv_values(str(ENV_PATH))
migrated = []
for env_key, (service, account) in MAPPING.items():
    val = env.get(env_key)
    if val and val.strip():
        broker.store(service, account, val.strip())
        migrated.append((env_key, service, account, len(val)))
        print(f"  Migrated: {env_key} -> cred://{service}/{account} ({len(val)} bytes)")
    else:
        print(f"  Skipped (empty): {env_key}")

# Write removal manifest
out = Path("config/.env.removed.md")
out.write_text(
    "# Migrated to Windows Credential Manager\n\n"
    "These environment variables have been moved to the keyring namespace `jarvis/`.\n"
    "You can safely remove them from `config/.env`.\n\n"
    + "\n".join(f"- `{k}` -> `cred://{s}/{a}` ({n} bytes)" for k, s, a, n in migrated),
    encoding="utf-8"
)
print(f"\nMigration complete. {len(migrated)} secrets stored. See {out}")
print("Existing .env unchanged; review .env.removed.md then manually clear those lines.")
