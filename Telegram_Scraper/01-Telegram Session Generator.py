#*This code and documentation were written by [Amir Jamali](https://github.com/Amirwpi), updated for safety and reliability.*

import asyncio
import os
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import StringSession

# Load from .env if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Retrieve from environment or allow manual entry
API_ID_ENV = os.getenv("TELEGRAM_API_ID", "").strip()
API_HASH_ENV = os.getenv("TELEGRAM_API_HASH", "").strip()
PHONE_ENV = os.getenv("TELEGRAM_PHONE_NUMBER", "").strip()

def prompt_credentials():
    global API_ID_ENV, API_HASH_ENV, PHONE_ENV

    if not API_ID_ENV or not API_ID_ENV.isdigit():
        while True:
            val = input("Enter your numeric Telegram API ID (from https://my.telegram.org): ").strip()
            if val.isdigit():
                API_ID_ENV = val
                break
            print("API ID must be an integer (e.g., 12345678). Please try again.")

    if not API_HASH_ENV:
        API_HASH_ENV = input("Enter your Telegram API Hash: ").strip()

    if not PHONE_ENV:
        PHONE_ENV = input("Enter your phone number with country code (e.g. +1234567890): ").strip()

    return int(API_ID_ENV), API_HASH_ENV, PHONE_ENV

async def main():
    print("=" * 60)
    print(" Telegram Session Generator")
    print("=" * 60)

    api_id, api_hash, phone_number = prompt_credentials()

    session = StringSession()
    client = TelegramClient(session, api_id, api_hash)

    try:
        await client.start(phone=phone_number)
        print("\n[+] Successfully connected to Telegram!")

        if not await client.is_user_authorized():
            print("[-] Authorization failed. Please verify credentials.")
            return

        print("[+] Authorization successful.")

    except SessionPasswordNeededError:
        password = input("\nTwo-step verification enabled. Please enter your 2FA password: ")
        await client.sign_in(password=password)
        print("[+] Successfully authorized with 2FA.")

    session_string = client.session.save()
    print("\n" + "=" * 60)
    print("YOUR SESSION STRING (Keep this secret!):")
    print(session_string)
    print("=" * 60 + "\n")

    # Save to .env file in the same folder
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    env_vars = {}
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env_vars[k.strip()] = v.strip()

    env_vars["TELEGRAM_API_ID"] = str(api_id)
    env_vars["TELEGRAM_API_HASH"] = api_hash
    env_vars["TELEGRAM_PHONE_NUMBER"] = phone_number
    env_vars["TELEGRAM_SESSION_STRING"] = session_string

    with open(env_path, "w", encoding="utf-8") as f:
        for k, v in env_vars.items():
            f.write(f"{k}={v}\n")

    print(f"[+] Credentials and session string automatically saved to:\n    {env_path}")
    print("[+] You are now ready to run '02-Telegram Scraper.py'!\n")

    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
