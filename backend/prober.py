import signal
import sqlite3
import sys
import time
from datetime import datetime, timezone
import os
import subprocess
import socket

# Fallback Configuration (Used if auto-detection fails)
FALLBACK_LOCAL_ROUTER_IP = "192.168.1.1" # Default LAN
FALLBACK_ISP_GATEWAY_IP = "10.0.0.1"     # Standard default
EXTERNAL_DNS_IP = "1.1.1.1"              # Cloudflare DNS
DB_PATH = os.path.join(os.path.dirname(__file__), "network_metrics.db")
INTERVAL_SECONDS = 30
ANOMALY_WINDOW = 20
PRUNE_CYCLES = 120
RETENTION_DAYS = 30
# Consecutive cycles where BOTH the ISP gateway and external DNS must fail before
# firing the critical "no internet" alert. Debounces cold-start / transient single
# misses (interface just up, first ICMP dropped) that are not real outages.
CRITICAL_FAIL_STREAK = 3

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA busy_timeout=5000')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS network_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            target_node TEXT,
            latency_ms REAL
        )
    ''')
    # Index for faster time-series querying
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON network_metrics(timestamp)')
    conn.commit()
    return conn

def send_alert(msg):
    if sys.platform == 'darwin':
        safe = msg.replace('"', '\\"')
        script = f'display notification "{safe}" with title "ISP Health Monitor"'
        subprocess.run(['osascript', '-e', script], check=False)
    else:
        subprocess.run(['notify-send', 'ISP Health Monitor', msg], check=False)

def tcp_ping(ip_address, port=53, timeout=2.0):
    """Fallback latency measurement using TCP socket connection duration if ICMP is blocked."""
    try:
        start_time = time.perf_counter()
        with socket.create_connection((ip_address, port), timeout=timeout):
            pass
        end_time = time.perf_counter()
        return (end_time - start_time) * 1000.0
    except OSError:
        # If DNS port 53 fails, try HTTP port 80 just in case it's a web-only router config
        if port == 53:
            return tcp_ping(ip_address, port=80, timeout=timeout)
        return -1.0

def parse_ping_time(stdout):
    """Return the round-trip time in ms parsed from ping stdout, or None if absent."""
    for line in stdout.split('\n'):
        if 'time=' in line:
            try:
                return float(line.split('time=')[1].split(' ')[0])
            except (IndexError, ValueError):
                return None
    return None

def measure_latency(ip_address):
    try:
        timeout_flag = '-t' if sys.platform == 'darwin' else '-W'
        result = subprocess.run(
            ['ping', '-c', '1', timeout_flag, '2', ip_address],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            parsed = parse_ping_time(result.stdout)
            if parsed is not None:
                return parsed
    except Exception:
        pass
    return tcp_ping(ip_address)

def get_default_gateway():
    """Dynamically determine the LAN gateway IP address."""
    try:
        if sys.platform == 'darwin':
            # macOS: netstat -rn
            res = subprocess.run(['netstat', '-rn'], capture_output=True, text=True)
            for line in res.stdout.splitlines():
                if line.startswith('default'):
                    # e.g. "default   192.168.1.1   UGScg   ... "
                    parts = line.split()
                    if len(parts) > 1:
                        return parts[1]
        else:
            # Linux: ip route
            res = subprocess.run(['ip', 'route'], capture_output=True, text=True)
            for line in res.stdout.splitlines():
                if line.startswith('default via'):
                    # e.g. "default via 192.168.1.1 dev eth0 ..."
                    parts = line.split()
                    if len(parts) > 2:
                        return parts[2]
    except Exception as e:
        print(f"Error auto-detecting default gateway: {e}")
    return FALLBACK_LOCAL_ROUTER_IP

def is_valid_ipv4(token):
    """True only for a dotted-quad IPv4 literal. Rejects tracepath noise like
    'send' (from 'send failed'), 'no' (from 'no reply'), 'Too', hostnames, etc."""
    try:
        socket.inet_aton(token)
        return token.count('.') == 3
    except (OSError, TypeError):
        return False

def get_isp_gateway():
    """Dynamically trace route to DNS and extract the first hop outside the local network."""
    try:
        if sys.platform == 'darwin':
            # traceroute to 1.1.1.1, max 5 hops, numeric IPs only
            res = subprocess.run(['traceroute', '-m', '5', '-n', EXTERNAL_DNS_IP], capture_output=True, text=True)
            for line in res.stdout.splitlines():
                stripped_line = line.strip()
                if len(stripped_line) > 0 and stripped_line[0].isdigit(): # Hit a hop line
                    parts = stripped_line.split()
                    if len(parts) > 1 and is_valid_ipv4(parts[1]):
                        ip = parts[1]

                        # [DEVELOPER NOTE: Bypassing Double NAT]
                        # Home setups often employ a "Double NAT" (e.g., a Google WiFi mesh router plugged into a Converge ISP modem).
                        # Both routers usually assign local 192.168.x.x addresses.
                        # To find the true outside ISP gateway (the neighborhood connection node), we ignore any hops
                        # that fall within the private 192.168.* IP space. The highest routing logic applies here.
                        if not ip.startswith('192.168.'):
                            return ip
        else:
            # Linux: use tracepath or traceroute
            cmd = ['tracepath', '-m', '5', '-n', EXTERNAL_DNS_IP] if os.path.exists('/usr/bin/tracepath') else ['traceroute', '-m', '5', '-n', EXTERNAL_DNS_IP]
            res = subprocess.run(cmd, capture_output=True, text=True)
            for line in res.stdout.splitlines():
                parts = line.split()
                if len(parts) > 1:
                    ip = None
                    if line.strip().startswith(tuple(str(i)+':' for i in range(1, 6))) and is_valid_ipv4(parts[1]): # tracepath format
                        ip = parts[1]
                    elif line.strip().startswith(tuple(str(i)+' ' for i in range(1, 6))) and is_valid_ipv4(parts[1]): # traceroute format
                        ip = parts[1]

                    if ip and not ip.startswith('192.168.'):
                        return ip
    except Exception as e:
        print(f"Error auto-detecting ISP gateway: {e}")
    return FALLBACK_ISP_GATEWAY_IP

def check_isp_anomaly(latency, isp_history):
    """Append latency sample, trim history, and return an alert message if a spike is detected."""
    if latency > 0:
        isp_history.append(latency)
        if len(isp_history) > ANOMALY_WINDOW:
            isp_history.pop(0)

        if len(isp_history) >= ANOMALY_WINDOW:
            moving_avg = sum(isp_history) / len(isp_history)
            # 2x of the post-append moving average (current sample included). Effective pre-spike ratio ~2.11x, so the AC's 3x spike scenario triggers. Do not raise to 3x here — that would test against the diluted average and cut sensitivity.
            if latency > (moving_avg * 2) and latency > 50:
                return f"⚠️ ANOMALY DETECTED: ISP latency spiked to {latency:.2f}ms! (Baseline: {moving_avg:.2f}ms)"
    return None

def prune_old_rows(cursor, conn):
    """Delete rows older than RETENTION_DAYS to bound DB size."""
    cursor.execute(
        "DELETE FROM network_metrics WHERE timestamp < datetime('now', ?)",
        (f'-{RETENTION_DAYS} days',)
    )
    conn.commit()

def run_prober():
    conn = init_db()
    cursor = conn.cursor()

    _conn_ref = [conn]

    def _shutdown(signum, frame):
        try:
            _conn_ref[0].commit()
            _conn_ref[0].close()
        except Exception:
            pass
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # Auto-detect gateways inside the startup sequence
    local_gateway = get_default_gateway()
    isp_gateway = get_isp_gateway()

    print(f"Starting prober. Logging to {DB_PATH}...")
    print(f"Auto-Detected Local Router: {local_gateway}")
    print(f"Auto-Detected ISP Gateway: {isp_gateway}")

    targets = {
        'local': local_gateway,
        'isp_gateway': isp_gateway,
        'external_dns': EXTERNAL_DNS_IP
    }

    isp_history = []
    cycle = 0
    dns_down_streak = 0
    critical_alerted = False

    while True:
        # SQLite-canonical UTC format ('YYYY-MM-DD HH:MM:SS') so datetime() comparisons
        # (retention prune, frontend 3-hour window) work. isoformat()'s 'T'/'+00:00'
        # sorts lexicographically wrong against datetime('now') and silently breaks them.
        now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        try:
            for node_name, ip in targets.items():
                latency = measure_latency(ip)

                cursor.execute(
                    "INSERT INTO network_metrics (timestamp, target_node, latency_ms) VALUES (?, ?, ?)",
                    (now, node_name, latency)
                )
                print(f"[{now}] {node_name} ({ip}): {latency:.2f} ms")

                if node_name == 'isp_gateway':
                    msg = check_isp_anomaly(latency, isp_history)
                    if msg:
                        print(msg)
                        send_alert(msg)

                    if latency != -1.0:
                        # ISP gateway reachable -> internet is up; clear any pending outage state.
                        dns_down_streak = 0
                        critical_alerted = False
                    else:
                        # ISP gateway ping failed. To avoid false positives on networks that block
                        # pings to the gateway, only treat this as an outage if external DNS is ALSO
                        # unreachable, and only after CRITICAL_FAIL_STREAK consecutive such cycles so a
                        # cold-start / transient single miss never fires the scary alert.
                        dns_latency = measure_latency(EXTERNAL_DNS_IP)
                        if dns_latency == -1.0:
                            dns_down_streak += 1
                            if dns_down_streak >= CRITICAL_FAIL_STREAK and not critical_alerted:
                                msg = "🚨 CRITICAL: ISP Gateway and Internet are unreachable!"
                                print(msg)
                                send_alert(msg)
                                critical_alerted = True
                            else:
                                print(f"[{now}] ISP+DNS unreachable ({dns_down_streak}/{CRITICAL_FAIL_STREAK}); deferring critical alert.")
                        else:
                            dns_down_streak = 0
                            critical_alerted = False
                            print(f"[{now}] ISP Gateway ping blocked, but Internet (DNS) is reachable. Suppressing false alert.")

            conn.commit()
        except sqlite3.OperationalError as e:
            print(f"[ERROR] DB write failed: {e}")

        cycle += 1
        if cycle % PRUNE_CYCLES == 0:
            try:
                prune_old_rows(cursor, conn)
            except sqlite3.OperationalError as e:
                print(f"[ERROR] Prune failed: {e}")

        time.sleep(INTERVAL_SECONDS)

if __name__ == "__main__":
    run_prober()
