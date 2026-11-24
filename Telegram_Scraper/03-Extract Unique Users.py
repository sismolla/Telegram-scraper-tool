"""
Extract Unique User IDs from Scraped Telegram Messages
Finds the latest scraped CSV file in the directory, extracts all unique sender user IDs,
and saves them sorted by activity (message count) into CSV and TXT files.
"""

import os
import glob
import csv
from collections import defaultdict

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Find all scraped message CSV files
    csv_files = [
        f for f in glob.glob(os.path.join(script_dir, "*.csv"))
        if not f.endswith("unique_user_ids.csv") and "__" in os.path.basename(f)
    ]
    
    if not csv_files:
        print("[-] No scraped CSV files found in directory.")
        return

    # Pick the most recently modified CSV
    latest_csv = max(csv_files, key=os.path.getmtime)
    print(f"[*] Processing latest file: {os.path.basename(latest_csv)}")

    users = defaultdict(lambda: {'count': 0, 'first_seen': None, 'last_seen': None})

    with open(latest_csv, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            s_id = row.get('sender_id', '').strip()
            date = row.get('date_utc', '').strip()
            if not s_id:
                continue
            users[s_id]['count'] += 1
            if users[s_id]['last_seen'] is None:
                users[s_id]['last_seen'] = date
            users[s_id]['first_seen'] = date

    sorted_users = sorted(users.items(), key=lambda x: x[1]['count'], reverse=True)

    output_csv = os.path.join(script_dir, "unique_user_ids.csv")
    output_txt = os.path.join(script_dir, "unique_user_ids.txt")

    # Save detailed CSV
    with open(output_csv, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['user_id', 'messages_count', 'first_seen_date', 'last_seen_date'])
        for u_id, info in sorted_users:
            writer.writerow([u_id, info['count'], info['first_seen'], info['last_seen']])

    # Save clean TXT (one ID per line)
    with open(output_txt, 'w', encoding='utf-8') as f:
        for u_id, _ in sorted_users:
            f.write(f"{u_id}\n")

    print(f"[+] Successfully extracted {len(sorted_users)} unique user IDs.")
    print(f"[+] Detailed CSV saved to: {output_csv}")
    print(f"[+] Plain text IDs saved to: {output_txt}")

if __name__ == '__main__':
    main()
