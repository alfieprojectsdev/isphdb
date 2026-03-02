import sqlite3
import sys
import time
from datetime import datetime, timezone
import os
import subprocess

# Configuration
LOCAL_ROUTER_IP = "<LAN_IP>" # PHIVOLCS network gateway (hop 1)
ISP_GATEWAY_IP = "10.0.0.1" # ISP gateway (hop 2, first public IP)
EXTERNAL_DNS_IP = "1.1.1.1"     # Cloudflare DNS
DB_PATH = os.path.join(os.path.dirname(__file__), "network_metrics.db")
INTERVAL_SECONDS = 30

def init_db():
    conn = sqlite3.connect(DB_PATH)
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
        os.system(f'osascript -e \'display notification "{msg}" with title "ISP Health Monitor"\'')
    else:
        os.system(f'notify-send "ISP Health Monitor" "{msg}"')

def measure_latency(ip_address):
    try:
        # Use the OS native ping binary to avoid needing root (raw sockets).
        # macOS uses -t for timeout; Linux uses -W.
        timeout_flag = '-t' if sys.platform == 'darwin' else '-W'
        result = subprocess.run(
            ['ping', '-c', '1', timeout_flag, '2', ip_address],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            # Parse latency, e.g. "time=1.062 ms"
            for line in result.stdout.split('\n'):
                if 'time=' in line:
                    return float(line.split('time=')[1].split(' ')[0])
        return -1.0
    except Exception:
        return -1.0

def run_prober():
    conn = init_db()
    cursor = conn.cursor()
    
    print(f"Starting prober. Logging to {DB_PATH}...")
    
    targets = {
        'local': LOCAL_ROUTER_IP,
        'isp_gateway': ISP_GATEWAY_IP,
        'external_dns': EXTERNAL_DNS_IP
    }
    
    isp_history = []
    
    while True:
        now = datetime.now(timezone.utc).isoformat()
        for node_name, ip in targets.items():
            latency = measure_latency(ip)
            
            cursor.execute(
                "INSERT INTO network_metrics (timestamp, target_node, latency_ms) VALUES (?, ?, ?)",
                (now, node_name, latency)
            )
            print(f"[{now}] {node_name} ({ip}): {latency:.2f} ms")
            
            # Anomaly Detection for ISP latency
            if node_name == 'isp_gateway':
                if latency > 0:
                    isp_history.append(latency)
                    if len(isp_history) > 20: # Keep the last 10 minutes (20 * 30s)
                        isp_history.pop(0)
                        
                        # Calculate moving average
                        moving_avg = sum(isp_history) / len(isp_history)
                        
                        # If current latency is double the moving average and > 50ms, trigger alert
                        if latency > (moving_avg * 2) and latency > 50:
                            msg = f"⚠️ ANOMALY DETECTED: ISP latency spiked to {latency:.2f}ms! (Baseline: {moving_avg:.2f}ms)"
                            print(msg)
                            send_alert(msg)
                elif latency == -1.0:
                    msg = "🚨 CRITICAL: ISP Gateway is unreachable!"
                    print(msg)
                    send_alert(msg)

        conn.commit()
        time.sleep(INTERVAL_SECONDS)

if __name__ == "__main__":
    run_prober()
