#*This code and documentation were originally written by [Amir Jamali](https://github.com/Amirwpi), updated for Telegram rules compliance, passive scraping, and stability.*
"""
Passive Telegram Scraper
- Read-only: strictly retrieves channel/group message history without writing or modifying anything.
- Compliant with Telegram Anti-Spam: uses humanized random delays and rate-limit backoffs.
- Compatible with Channels and Groups: captures posts even when message.from_id is None.
- Configurable media download: downloads media safely without overloading network or hitting flood limits.
"""

import asyncio
import csv
import datetime
import os
import random
import sys
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError
import nest_asyncio

nest_asyncio.apply()

# ---------------------------------------------------------
# Load Settings from .env or Fallback Variables
# ---------------------------------------------------------
try:
    from dotenv import load_dotenv
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Load .env from script's directory first, then fallback to current working directory
    load_dotenv(os.path.join(script_dir, ".env"))
    load_dotenv()
except ImportError:
    pass

API_ID = os.getenv("TELEGRAM_API_ID", "").strip()
API_HASH = os.getenv("TELEGRAM_API_HASH", "").strip()
SESSION_STRING = os.getenv("TELEGRAM_SESSION_STRING", "").strip()
TARGET_CHAT = os.getenv("TARGET_CHAT", "").strip()

# Passive scraping delay settings (in seconds)
# Jitter prevents regular request patterns that could trigger Telegram's automated spam filters
MIN_DELAY = 2.0
MAX_DELAY = 4.0

# Batch scraping settings
MESSAGES_PER_BATCH = 100     # Telegram's maximum per GetHistory request is 100
MAX_BATCHES = 50             # Number of batches per CSV file (e.g. 50 * 100 = up to 5,000 messages)
DOWNLOAD_MEDIA = os.getenv("DOWNLOAD_MEDIA", "False").lower() in ("true", "1", "yes")

# Date to start scraping backwards from (UTC). Leave None to scrape from the most recent messages.
START_DATE_STR = os.getenv("SCRAPE_START_DATE", "").strip()
if START_DATE_STR:
    try:
        DATETIME_BEFORE = datetime.datetime.fromisoformat(START_DATE_STR).replace(tzinfo=datetime.timezone.utc)
    except Exception:
        DATETIME_BEFORE = None
else:
    DATETIME_BEFORE = None

MEDIA_SAVE_PATH = "downloaded_media"
if DOWNLOAD_MEDIA:
    os.makedirs(MEDIA_SAVE_PATH, exist_ok=True)


def ensure_config():
    """Ensure required credentials and target are provided."""
    global API_ID, API_HASH, SESSION_STRING, TARGET_CHAT

    if not API_ID:
        val = input("Enter your numeric Telegram API ID: ").strip()
        API_ID = val
    if not API_HASH:
        API_HASH = input("Enter your Telegram API Hash: ").strip()
    if not SESSION_STRING:
        SESSION_STRING = input("Enter your Telegram Session String (generated from script 01): ").strip()
    if not TARGET_CHAT:
        TARGET_CHAT = input("Enter target channel or group username/link (e.g. 'example' or 'https://t.me/example'): ").strip()


def extract_media_type(message):
    """Determine the type of media attached to a message without triggering heavy operations."""
    if not message.media:
        return "None"
    media_class = message.media.__class__.__name__
    if "Photo" in media_class:
        return "Photo"
    elif "Document" in media_class:
        # Document can be video, audio, gif, or regular file
        if message.video:
            return "Video"
        elif message.audio:
            return "Audio"
        elif message.gif:
            return "GIF"
        return "Document"
    elif "WebPage" in media_class:
        return "WebPage Preview"
    elif "Poll" in media_class:
        return "Poll"
    elif "Contact" in media_class:
        return "Contact"
    elif "Geo" in media_class:
        return "Location"
    return media_class


def clean_message_record(message, media_path=None):
    """
    Extract a clean, structured dictionary for CSV export.
    Supports both broadcast channels (where from_id is None) and groups.
    """
    sender_id = message.sender_id
    post_author = getattr(message, 'post_author', None) or ""

    return {
        "message_id": message.id,
        "date_utc": message.date.isoformat() if message.date else "",
        "text": message.text or "",
        "sender_id": sender_id if sender_id is not None else "",
        "post_author": post_author,
        "views": getattr(message, 'views', '') or 0,
        "forwards": getattr(message, 'forwards', '') or 0,
        "replies_count": message.replies.replies if message.replies else 0,
        "media_type": extract_media_type(message),
        "media_file_path": media_path or "",
        "is_reply": bool(message.reply_to),
        "reply_to_msg_id": message.reply_to.reply_to_msg_id if message.reply_to else "",
        "edit_date": message.edit_date.isoformat() if message.edit_date else "",
    }


async def save_to_csv(messages, filename):
    """Save records to CSV with UTF-8 BOM encoding for Excel compatibility."""
    if not messages:
        return
    fieldnames = list(messages[0].keys())
    with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(messages)
    print(f"[+] Saved {len(messages)} messages to: {filename}")


async def scrape_channel(client, entity, start_datetime):
    """
    Passively scrape messages backwards from start_datetime in chunks.
    Respects rate limits, applies random delays, and handles flood waits gracefully.
    """
    offset_id = 0
    offset_date = start_datetime
    total_scraped = 0
    all_collected = []

    clean_target_name = getattr(entity, 'username', None) or getattr(entity, 'title', 'telegram_chat')
    clean_target_name = "".join(c for c in clean_target_name if c.isalnum() or c in ('_', '-'))

    print(f"\n[*] Target identified: {getattr(entity, 'title', clean_target_name)}")
    print(f"[*] Media downloading: {'ENABLED' if DOWNLOAD_MEDIA else 'DISABLED (metadata only)'}")
    print(f"[*] Starting passive scrape...\n")

    batch_index = 0

    try:
        while batch_index < MAX_BATCHES:
            batch_index += 1
            print(f"--- Batch {batch_index}/{MAX_BATCHES} (Offset ID: {offset_id}) ---")

            try:
                # Fetch message history chunk using Telethon's high-level get_messages
                messages_chunk = await client.get_messages(
                    entity,
                    limit=MESSAGES_PER_BATCH,
                    offset_id=offset_id,
                    offset_date=offset_date
                )

            except FloodWaitError as e:
                wait_time = e.seconds + 2
                print(f"[!] Rate limit (FloodWait): Telegram requested waiting {wait_time} seconds.")
                if wait_time > 300:
                    print("[!] FloodWait is longer than 5 minutes. Stopping gracefully to protect account.")
                    break
                await asyncio.sleep(wait_time)
                continue
            except Exception as e:
                print(f"[-] Error fetching messages: {e}")
                break

            if not messages_chunk:
                print("[*] Reached the beginning of the channel history (no more messages).")
                break

            # Process the retrieved messages
            for msg in messages_chunk:
                media_path = None
                if DOWNLOAD_MEDIA and msg.media:
                    try:
                        # Download media gently
                        media_path = await client.download_media(msg, file=MEDIA_SAVE_PATH)
                        print(f"    [Media] Downloaded: {media_path}")
                    except FloodWaitError as e:
                        print(f"    [!] FloodWait during media download: sleeping {e.seconds + 2}s")
                        await asyncio.sleep(e.seconds + 2)
                    except Exception as e:
                        print(f"    [-] Could not download media for msg {msg.id}: {e}")

                record = clean_message_record(msg, media_path)
                all_collected.append(record)

            total_scraped += len(messages_chunk)
            oldest_msg = messages_chunk[-1]
            offset_id = oldest_msg.id
            offset_date = None  # After the first batch, offset_id provides strict pagination

            print(f"    Collected {len(messages_chunk)} messages in this batch. Total: {total_scraped}")
            print(f"    Oldest message in batch: ID {oldest_msg.id} dated {oldest_msg.date}")

            # Passive delay: randomized wait between batches to avoid bot-like flood patterns
            sleep_delay = random.uniform(MIN_DELAY, MAX_DELAY)
            print(f"    Passive sleep: waiting {sleep_delay:.2f}s before next request...")
            await asyncio.sleep(sleep_delay)

    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\n[*] Scraping interrupted by user. Saving collected messages...")
    finally:
        # Save to CSV
        if all_collected:
            first_date_str = all_collected[0]['date_utc'][:10]
            last_date_str = all_collected[-1]['date_utc'][:10]
            csv_filename = f"{clean_target_name}__{last_date_str}_to_{first_date_str}.csv"
            await save_to_csv(all_collected, csv_filename)
        else:
            print("[-] No messages were collected.")


async def main():
    print("=" * 60)
    print(" Passive Telegram Scraper")
    print("=" * 60)

    ensure_config()

    # Create Telethon client with automatic flood wait handling
    client = TelegramClient(StringSession(SESSION_STRING), int(API_ID), API_HASH)
    client.flood_sleep_threshold = 120  # Automatically sleep for rate limits up to 2 minutes

    async with client:
        if not await client.is_user_authorized():
            print("[-] Error: The session string is invalid or expired. Please re-run script 01.")
            return

        print("[+] Authorized with Telegram successfully.")

        try:
            # Resolve entity once
            entity = await client.get_entity(TARGET_CHAT)
        except Exception as e:
            print(f"[-] Could not resolve target '{TARGET_CHAT}': {e}")
            print("    Please check that the username/link is correct and that your account has joined if it is private.")
            return

        await scrape_channel(client, entity, DATETIME_BEFORE)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[*] Scraper stopped by user (Ctrl+C). Any data already saved is preserved.")
