"""Interactive Zoho IMAP credential setup."""
import getpass
from jarvis.security.credential_broker import broker

if __name__ == "__main__":
    print("Zoho IMAP Setup — server: imap.zoho.com:993")
    print("Use an App Password if 2FA is enabled on your account.\n")
    user = input("Email (e.g., lighting@amscontrol.com): ").strip()
    pw = getpass.getpass("App password: ")
    broker.store("zoho_imap_user", "lighting", user)
    broker.store("zoho_imap_password", "lighting", pw)
    print("Stored: cred://zoho_imap_user/lighting + cred://zoho_imap_password/lighting")
