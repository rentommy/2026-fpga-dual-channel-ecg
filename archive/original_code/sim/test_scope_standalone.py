"""Verify RLD switching stops streaming and checks readback before resuming."""
import importlib.util
from pathlib import Path
import unittest

path=Path(__file__).resolve().parents[1]/'board/run_scope_standalone.py'
spec=importlib.util.spec_from_file_location('standalone_scope',path)
scope=importlib.util.module_from_spec(spec)
spec.loader.exec_module(scope)

class FakeIP:
    def __init__(self):
        self.events=[]
    def read(self,address):
        return 0x45434732
    def write(self,address,value):
        self.events.append(('write',address,value))

class RLDTest(unittest.TestCase):
    def make_io(self,readback):
        ip=FakeIP()
        io=scope.ScopeIO(ip)
        def command(values):
            ip.events.append(('command',values))
            return bytes([0,0,readback]) if values[0]==0x26 else bytes(len(values))
        io.command=command
        return io,ip
    def test_each_channel_stops_and_resumes_in_order(self):
        for ch,value in [(1,0x23),(2,0x2c)]:
            io,ip=self.make_io(value)
            io.select_rld_channel(ch)
            self.assertEqual(ip.events,[('write',0,1),('command',[0x11]),
                ('command',[0x46,0,value]),('command',[0x26,0,0]),
                ('write',0,9),('write',0,3),('command',[0x10]),('write',0,7)])
    def test_bad_readback_never_restarts_acquisition(self):
        io,ip=self.make_io(0)
        with self.assertRaisesRegex(RuntimeError,'readback'):
            io.select_rld_channel(2)
        self.assertNotIn(('write',0,7),ip.events)
    def test_invalid_channel_never_touches_hardware(self):
        io,ip=self.make_io(0)
        with self.assertRaises(ValueError):
            io.select_rld_channel(3)
        self.assertEqual(ip.events,[])

if __name__=='__main__':
    unittest.main()
