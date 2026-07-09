import sys
import os
import unittest

sys.path[0:0] = [os.path.dirname(__file__)]
from prober import parse_ping_time, parse_traceroute_hops, is_mappable_hop


class TestParsePingTime(unittest.TestCase):

    def test_valid_linux_output(self):
        stdout = "64 bytes from 1.1.1.1: icmp_seq=1 ttl=58 time=4.23 ms\n"
        result = parse_ping_time(stdout)
        self.assertAlmostEqual(result, 4.23)

    def test_valid_macos_output(self):
        stdout = "64 bytes from 1.1.1.1: icmp_seq=0 ttl=58 time=12.345 ms\n"
        result = parse_ping_time(stdout)
        self.assertAlmostEqual(result, 12.345)

    def test_missing_time_token(self):
        stdout = "PING 1.1.1.1 (1.1.1.1): 56 data bytes\nRequest timeout for icmp_seq 0\n"
        result = parse_ping_time(stdout)
        self.assertIsNone(result)

    def test_empty_output(self):
        result = parse_ping_time("")
        self.assertIsNone(result)

    def test_malformed_numeric(self):
        stdout = "64 bytes from 1.1.1.1: time=abc ms\n"
        result = parse_ping_time(stdout)
        self.assertIsNone(result)

    def test_latency_at_warn_threshold(self):
        stdout = "64 bytes from 1.1.1.1: time=75.000 ms\n"
        result = parse_ping_time(stdout)
        self.assertEqual(result, 75.0)

    def test_no_time_token_on_timeout_line(self):
        stdout = "Request timeout for icmp_seq 0\n"
        result = parse_ping_time(stdout)
        self.assertIsNone(result)


MACOS_TRACEROUTE = """traceroute to 1.1.1.1 (1.1.1.1), 10 hops max, 52 byte packets
 1  192.168.1.1  1.234 ms  1.100 ms  1.050 ms
 2  * * *
 3  10.56.0.1  4.293 ms  4.100 ms  4.050 ms
 4  161.49.4.4  4.696 ms  4.600 ms  4.550 ms
"""

LINUX_TRACEROUTE = """traceroute to 1.1.1.1 (1.1.1.1), 5 hops max, 60 byte packets
 1  192.168.1.1  0.512 ms  0.480 ms  0.470 ms
 2  100.64.0.1  3.100 ms  3.050 ms  3.000 ms
 3  * * *
 4  161.49.7.236  5.010 ms  4.990 ms  4.950 ms
"""

LINUX_TRACEPATH = """ 1?: [LOCALHOST]                      pmtu 1500
 1:  192.168.1.1                       1.372ms
 1:  192.168.1.1                       1.247ms
 2:  192.168.100.1                     1.427ms
 3:  10.56.0.1                         4.293ms
 4:  161.49.4.4                        4.696ms
 5:  no reply
     Too many hops: pmtu 1500
     Resume: pmtu 1500
"""


class TestTracerouteParsing(unittest.TestCase):

    def test_macos_traceroute(self):
        hops = parse_traceroute_hops(MACOS_TRACEROUTE, 'darwin')
        self.assertEqual([h['hop_index'] for h in hops], [1, 2, 3, 4])
        self.assertEqual(hops[0], {'hop_index': 1, 'ip': '192.168.1.1', 'latency_ms': 1.234})
        # Starred hop: no IP, sentinel latency.
        self.assertEqual(hops[1], {'hop_index': 2, 'ip': None, 'latency_ms': -1.0})
        self.assertEqual(hops[2]['ip'], '10.56.0.1')
        self.assertAlmostEqual(hops[2]['latency_ms'], 4.293)
        self.assertEqual(hops[3]['ip'], '161.49.4.4')

    def test_linux_traceroute(self):
        hops = parse_traceroute_hops(LINUX_TRACEROUTE, 'linux')
        self.assertEqual([h['hop_index'] for h in hops], [1, 2, 3, 4])
        self.assertEqual(hops[1]['ip'], '100.64.0.1')
        self.assertEqual(hops[2], {'hop_index': 3, 'ip': None, 'latency_ms': -1.0})
        self.assertEqual(hops[3]['ip'], '161.49.7.236')
        self.assertAlmostEqual(hops[3]['latency_ms'], 5.010)

    def test_linux_tracepath(self):
        hops = parse_traceroute_hops(LINUX_TRACEPATH, 'linux')
        # Retry lines and the '1?:' PMTU line collapse to one entry per hop.
        self.assertEqual([h['hop_index'] for h in hops], [1, 2, 3, 4, 5])
        # First real IP wins over the earlier '1?: [LOCALHOST]' line.
        self.assertEqual(hops[0], {'hop_index': 1, 'ip': '192.168.1.1', 'latency_ms': 1.372})
        self.assertEqual(hops[1]['ip'], '192.168.100.1')
        self.assertEqual(hops[3]['ip'], '161.49.4.4')
        # 'no reply' hop -> no IP, sentinel latency.
        self.assertEqual(hops[4], {'hop_index': 5, 'ip': None, 'latency_ms': -1.0})

    def test_starred_and_noise_never_leak_ip(self):
        noisy = " 2  * * *\n 3:  send failed\n 4:  no reply\n"
        hops = parse_traceroute_hops(noisy, 'linux')
        self.assertTrue(all(h['ip'] is None for h in hops))
        self.assertTrue(all(h['latency_ms'] == -1.0 for h in hops))

    def test_empty_output(self):
        self.assertEqual(parse_traceroute_hops("", 'linux'), [])


class TestMappableHop(unittest.TestCase):

    def test_none_and_noise(self):
        self.assertFalse(is_mappable_hop(None))
        self.assertFalse(is_mappable_hop('send'))
        self.assertFalse(is_mappable_hop(''))

    def test_private_ranges_excluded(self):
        for ip in ('192.168.1.1', '10.56.0.1', '172.16.0.1', '172.31.255.254',
                   '100.64.0.1', '127.0.0.1', '169.254.1.1'):
            self.assertFalse(is_mappable_hop(ip), ip)

    def test_public_ips_mappable(self):
        for ip in ('161.49.4.4', '161.49.7.236', '1.1.1.1', '8.8.8.8', '172.32.0.1'):
            self.assertTrue(is_mappable_hop(ip), ip)


if __name__ == '__main__':
    unittest.main()
