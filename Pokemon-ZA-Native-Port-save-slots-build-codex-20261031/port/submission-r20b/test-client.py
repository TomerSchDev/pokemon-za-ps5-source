"""Offline tests for the actual observer client command and receipt paths."""
import io
import json
from pathlib import Path
import tempfile
import unittest
import client

SID = '000004c4dad1b643'

class FakeFTP:
    def __init__(self, ack): self.ack = ack
    def retrbinary(self, cmd, callback, blocksize):
        assert cmd.endswith('/ack_1.json'), cmd
        callback(json.dumps(self.ack).encode())

class ClientTests(unittest.TestCase):
    def test_commands(self):
        for name in client.PROFILES:
            self.assertEqual(client.text_command(SID, 1, 'submission', name),
                             f'{SID} 1 submission {name}\n'.encode())
        self.assertEqual(client.text_command(SID, 1, 'measure', 20),
                         f'{SID} 1 measure 20\n'.encode())
        self.assertEqual(client.text_command(SID, 1, 'input', 'A', 1),
                         f'{SID} 1 input A 1\n'.encode())
        for bad in ('batch', 'batch3', 'each extra', 'BATCH4', ''):
            with self.assertRaises(AssertionError): client.text_command(SID, 1, 'submission', bad)
        with self.assertRaises(AssertionError): client.text_command(SID, 1, 'submission', 'each', 1)

    def test_actual_collect_validates_applied_receipt(self):
        ack = dict(session=SID, seq=1, op='submission', result='applied', file='',
                   requested_profile='batch4', profile='batch4', max_lists=4, frame=123, cost_ns=100)
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            self.assertEqual(client.collect(FakeFTP(ack), SID, 1, out)['ack'], ack)
            self.assertTrue((out/'command_1.json').exists())
            for changes in ({'max_lists':2}, {'profile':'each'}, {'frame':0},
                            {'result':'queued'}, {'requested_profile':'batch'}):
                with self.assertRaises(ValueError):
                    client.collect(FakeFTP({**ack, **changes}), SID, 1, out)
            for result in ('rejected_boundary','rejected_override','drain_failed'):
                rejected = {**ack, 'result':result, 'profile':'', 'max_lists':0}
                self.assertEqual(client.collect(FakeFTP(rejected), SID, 1, out)['ack']['result'], result)
                with self.assertRaises(ValueError):
                    client.collect(FakeFTP({**rejected, 'profile':'batch4', 'max_lists':4}), SID, 1, out)

if __name__ == '__main__': unittest.main()
