import signal
import sqlite3
import sys
import time
from datetime import datetime, timezone
import os
import re
import ipaddress
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
# Capture the full traceroute hop path every N cycles (~5 min at 30s) for the geo map,
# mirroring the PRUNE_CYCLES cadence pattern. Cheap: 1-in-N cycles, 10-hop cap.
TRACEROUTE_CYCLES = 10
RETENTION_DAYS = 30
# Consecutive cycles where BOTH the ISP gateway and external DNS must fail before
# firing the critical "no internet" alert. Debounces cold-start / transient single
# misses (interface just up, first ICMP dropped) that are not real outages.
CRITICAL_FAIL_STREAK = 3
# When the ISP gateway keeps failing while the internet (DNS) is reachable, the detected
# gateway IP is probably stale/wrong — e.g. detection fell back to FALLBACK_ISP_GATEWAY_IP
# at boot before the network was up, and the one-shot startup detection never re-ran. After
# this many such cycles, re-run detection once and adopt a new, valid IP. Self-heals the
# boot-time misdetection that otherwise pins the gateway line at 500ms until a manual restart.
REDETECT_AFTER_FAILS = 5

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
    # Per-capture traceroute hop path (populated every TRACEROUTE_CYCLES). Rows sharing a
    # timestamp form one capture; the frontend reads the latest capture for the geo map.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS traceroute_hops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            hop_index INTEGER,
            hop_ip TEXT,
            latency_ms REAL
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_hops_timestamp ON traceroute_hops(timestamp)')
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

def is_mappable_hop(ip):
    """True only for a public, geolocatable IPv4 address. Excludes None and every
    private/loopback/link-local/CGNAT range (192.168/16, 10/8, 172.16/12, 100.64/10,
    127/8, 169.254/16) — those can never be placed on the geo map."""
    if not ip or not is_valid_ipv4(ip):
        return False
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    # 100.64.0.0/10 (CGNAT / RFC 6598 shared space) is not flagged is_private on all
    # Python versions but is just as ungeolocatable, so exclude it explicitly.
    if addr in ipaddress.ip_network('100.64.0.0/10'):
        return False
    return not (addr.is_private or addr.is_loopback or addr.is_link_local)

def _traceroute_cmd(max_hops):
    """Per-OS numeric trace command to EXTERNAL_DNS_IP, capped at max_hops."""
    if sys.platform != 'darwin' and os.path.exists('/usr/bin/tracepath'):
        return ['tracepath', '-m', str(max_hops), '-n', EXTERNAL_DNS_IP]
    return ['traceroute', '-m', str(max_hops), '-n', EXTERNAL_DNS_IP]

def parse_traceroute_hops(stdout, platform=None):
    """Pure parser shared by gateway detection and full hop capture. Returns an ordered
    list of {'hop_index', 'ip', 'latency_ms'} for numeric hop lines of either macOS/Linux
    traceroute ('N  IP  X.XXX ms') or Linux tracepath ('N:  IP  X.XXXms'). Starred /
    'no reply' / unreachable hops yield ip=None and latency_ms=-1.0. Multiple probe lines
    for the same hop (tracepath retries, 'N?:' PMTU lines) collapse to one entry, keeping
    the first line that carries a valid IP. `platform` is accepted for API stability; the
    parse is format-agnostic and does not currently branch on it."""
    hops = {}
    order = []
    for line in stdout.splitlines():
        m = re.match(r'^\s*(\d+)[:?\s]', line)
        if not m:
            continue
        hop_index = int(m.group(1))
        ip = next((tok for tok in line.split() if is_valid_ipv4(tok)), None)
        lm = re.search(r'(\d+(?:\.\d+)?)\s*ms', line)
        latency = float(lm.group(1)) if lm else -1.0
        entry = {'hop_index': hop_index, 'ip': ip, 'latency_ms': latency}
        if hop_index not in hops:
            hops[hop_index] = entry
            order.append(hop_index)
        elif hops[hop_index]['ip'] is None and ip is not None:
            # First real IP wins over an earlier starred/PMTU-discovery line for this hop.
            hops[hop_index] = entry
    return [hops[i] for i in order]

def get_isp_gateway():
    """Dynamically trace route to DNS and return the first hop outside the LAN's
    192.168.* space (the physical ISP line). Deliberately NOT is_mappable_hop: the ISP's
    first node is often a 10.x CGNAT address we still want to monitor for latency even
    though it cannot be geolocated on the map."""
    try:
        res = subprocess.run(_traceroute_cmd(5), capture_output=True, text=True)
        for hop in parse_traceroute_hops(res.stdout, sys.platform):
            ip = hop['ip']
            # [DEVELOPER NOTE: Bypassing Double NAT]
            # Home setups often employ a "Double NAT" (e.g., a Google WiFi mesh router
            # plugged into a Converge ISP modem). Both routers assign 192.168.x.x. Skip
            # those to reach the true outside ISP gateway (the neighborhood connection node).
            if ip and not ip.startswith('192.168.'):
                return ip
    except Exception as e:
        print(f"Error auto-detecting ISP gateway: {e}")
    return FALLBACK_ISP_GATEWAY_IP

def capture_route_hops(cursor, conn, now):
    """Run a full numeric trace and persist each geolocatable (mappable) hop of the current
    path under a single shared `now` timestamp. Unmappable hops (LAN/CGNAT) are skipped."""
    try:
        res = subprocess.run(_traceroute_cmd(10), capture_output=True, text=True)
        saved = 0
        for hop in parse_traceroute_hops(res.stdout, sys.platform):
            if not is_mappable_hop(hop['ip']):
                continue
            cursor.execute(
                "INSERT INTO traceroute_hops (timestamp, hop_index, hop_ip, latency_ms) VALUES (?, ?, ?, ?)",
                (now, hop['hop_index'], hop['ip'], hop['latency_ms'])
            )
            saved += 1
        conn.commit()
        print(f"[{now}] Captured {saved} mappable route hop(s).")
    except Exception as e:
        print(f"Error capturing route hops: {e}")

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
    cutoff = f'-{RETENTION_DAYS} days'
    cursor.execute("DELETE FROM network_metrics WHERE timestamp < datetime('now', ?)", (cutoff,))
    cursor.execute("DELETE FROM traceroute_hops WHERE timestamp < datetime('now', ?)", (cutoff,))
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
    gateway_fail_streak = 0
    gateway_redetect_tried = False

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
                        gateway_fail_streak = 0
                        gateway_redetect_tried = False
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
                            # Internet is up but the gateway is unreachable. If this persists, the
                            # detected gateway IP is probably stale (boot-time fallback). Re-detect
                            # once and adopt a new, valid IP so the daemon self-heals without a restart.
                            gateway_fail_streak += 1
                            if gateway_fail_streak >= REDETECT_AFTER_FAILS and not gateway_redetect_tried:
                                gateway_redetect_tried = True
                                new_gateway = get_isp_gateway()
                                if new_gateway != ip and new_gateway != FALLBACK_ISP_GATEWAY_IP:
                                    print(f"[{now}] ISP gateway re-detected: {ip} -> {new_gateway}. Switching target.")
                                    targets['isp_gateway'] = new_gateway
                                else:
                                    print(f"[{now}] ISP gateway re-detection returned {new_gateway}; keeping {ip}.")

            conn.commit()
        except sqlite3.OperationalError as e:
            print(f"[ERROR] DB write failed: {e}")

        # Periodic full-path capture for the geo map (cycle 0 fires immediately so the
        # panel has data on first run rather than waiting ~5 min).
        if cycle % TRACEROUTE_CYCLES == 0:
            capture_route_hops(cursor, conn, now)

        cycle += 1
        if cycle % PRUNE_CYCLES == 0:
            try:
                prune_old_rows(cursor, conn)
            except sqlite3.OperationalError as e:
                print(f"[ERROR] Prune failed: {e}")

        time.sleep(INTERVAL_SECONDS)

if __name__ == "__main__":
    run_prober()
