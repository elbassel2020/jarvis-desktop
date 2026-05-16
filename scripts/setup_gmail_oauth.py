"""One-time Gmail + Calendar + Drive OAuth setup. Run interactively."""
from jarvis.integrations.gmail.auth import setup_interactive

if __name__ == "__main__":
    success = setup_interactive(account="walid")
    print("Setup OK — all Google scopes granted." if success else "Setup FAILED — see docs/SPRINT_B_SETUP.md")
