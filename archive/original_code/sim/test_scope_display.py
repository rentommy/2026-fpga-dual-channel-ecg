"""Host-side display protocol checks; no PYNQ import or hardware required."""
import importlib.util
from pathlib import Path
import unittest
import numpy as np

path = Path(__file__).resolve().parents[1] / 'board/run_scope.py'
spec = importlib.util.spec_from_file_location('scope_display', path)
scope = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scope)


class FakeIP:
    def __init__(self):
        self.regs = {0x3c: 0x45434732, 0x10: 0, 0x1c: 0}
        self.mmio = type('Memory', (), {'array': np.zeros(0x6800 // 4, dtype=np.uint32)})()
        self.writes = []

    def read(self, address):
        return self.regs[address]

    def write(self, address, value):
        self.writes.append((address, value))


class DisplayTest(unittest.TestCase):
    def test_commit_and_continuous_extrema(self):
        ip = FakeIP()
        history = np.zeros((2000, 2, 2), dtype=np.int32)
        edges = np.linspace(0, 2000, 641, dtype=int)
        for column in range(640):
            history[edges[column]:edges[column + 1]] = 15000 if column % 2 else -15000
        self.assertTrue(scope.ScopeIO(ip).draw(history))
        self.assertEqual(ip.writes, [(0x1c, 1)])
        packed = ip.mmio.array[0x4000 // 4:0x6800 // 4].reshape(2, 2, 640)
        lo, hi = packed & 1023, packed >> 10
        self.assertTrue(np.all(lo[:, :, 1:] <= hi[:, :, :-1]))
        self.assertTrue(np.all(lo[:, :, :-1] <= hi[:, :, 1:]))
        ip.regs[0x1c] = 3  # Bank 1 acknowledged, no pending request.
        self.assertTrue(scope.ScopeIO(ip).draw(history))
        self.assertEqual(ip.writes[-1], (0x1c, 0))

    def test_pending_and_hold_never_overwrite(self):
        for ui, state in [(0, 6), (4, 0)]:
            ip = FakeIP()
            ip.regs.update({0x10: ui, 0x1c: state})
            ip.mmio.array.fill(0x12345)
            before = ip.mmio.array.copy()
            self.assertFalse(scope.ScopeIO(ip).draw(np.ones((2000, 2, 2), dtype=np.int32)))
            np.testing.assert_array_equal(before, ip.mmio.array)
            self.assertEqual(ip.writes, [])

    def test_old_bitstream_is_rejected(self):
        ip = FakeIP()
        ip.regs[0x3c] = 0x45434731
        with self.assertRaisesRegex(RuntimeError, 'double-buffer'):
            scope.ScopeIO(ip)


if __name__ == '__main__':
    unittest.main()
