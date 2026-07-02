import sys
import os
import unittest

sys.path[0:0] = [os.path.dirname(__file__)]
from prober import parse_ping_time


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


if __name__ == '__main__':
    unittest.main()
