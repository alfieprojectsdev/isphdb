export function evaluateStatus(dataArr) {
  if (!dataArr || dataArr.length === 0) return { status: 'unknown', msg: 'No Data' };

  const recentData = dataArr
    .slice(-20)
    .map(pt => (Array.isArray(pt) ? pt[1] : pt))
    .filter(val => val !== null);

  if (recentData.length === 0) return { status: 'offline', msg: 'Disconnected' };

  const latest = recentData[recentData.length - 1];

  // 500 is the failure sentinel (prober -1 mapped to 500 for the chart). A fresh
  // failure as the latest sample means the target is currently unreachable.
  if (latest >= 500) return { status: 'offline', msg: 'Disconnected' };

  // Average only successful samples so intermittent ping-blocking (bursts of the
  // 500 sentinel) does not inflate the baseline and flip a healthy target to 'bad'.
  const successful = recentData.filter(val => val < 500);
  const avg = successful.reduce((a, b) => a + b, 0) / successful.length;

  if (latest > 150 || avg > 100) return { status: 'bad', msg: 'High Latency' };
  if (latest > 75 || avg > 60) return { status: 'warn', msg: 'Degraded' };
  return { status: 'good', msg: 'Healthy' };
}

export function applyPingBlockedOverride(localStatus, ispStatus, dnsStatus) {
  const local = { ...localStatus };
  const isp = { ...ispStatus };
  if (dnsStatus.status === 'good' || dnsStatus.status === 'warn') {
    if (local.status === 'offline') {
      local.status = 'good';
      local.msg = 'Healthy (Ping Blocked)';
    }
    if (isp.status === 'offline') {
      isp.status = 'good';
      isp.msg = 'Healthy (Ping Blocked)';
    }
  }
  return { local, isp };
}
