"""Prepared fake-HTTP tests; no network, payload execution or resource enrollment.

Run only with the canonical PC verification turn. Extracts the existing sender
function from the reviewed candidate AST; does not import its side-QA globals.
"""
import ast
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
import urllib.error
import urllib.request
import uuid
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
CONFIG = json.loads((HERE / 'CONFIG-r3.json').read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name)
        source = HERE / 'console-choice.candidate.py'
        self.assertEqual(sha(source), CONFIG['helper_sha256']['port/hebrew-rtl/console-choice.py'])
        tree = ast.parse(source.read_text(encoding='utf-8'))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'send_websrv_payload')
        self.assertEqual(ast.literal_eval(node.args.kw_defaults[0]),
                         ('launch-side.elf', 'seed-side-data.elf', 'close-failed-side.elf'))
        namespace = {'urllib': urllib, 'uuid': uuid,
                     'm': SimpleNamespace(sha=sha, api=SimpleNamespace(HOST='192.168.1.135'),
                                          proof=lambda p: {'path': str(p), 'sha256': sha(p)})}
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), 'exec'), namespace)
        self.sender = SimpleNamespace(send_websrv_payload=namespace['send_websrv_payload'])
        driver = HERE / 'driver-r3.py'
        self.assertEqual(sha(driver), CONFIG['driver_sha256'])
        spec = importlib.util.spec_from_file_location('fs_transport_review', driver)
        self.driver = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.driver)
        self.observations = []
        self.api = SimpleNamespace(install_guard=lambda: SimpleNamespace(
            observe_connection=lambda *a: self.observations.append(a)))

    def artifact(self, name='launch.elf'):
        source = self.out / name
        source.write_bytes(b'FAKE-NONEXECUTABLE-ELF-FIXTURE\x00\xff')
        return {'path': str(source), 'remote_path': '/data/homebrew/PPSA91780/launch.elf', 'sha256': sha(source)}

    def response(self, status=200):
        response = io.BytesIO(b'fake launcher response')
        response.status = status
        return response

    def test_default_allowlist_unchanged(self):
        for name in ('launch-side.elf', 'seed-side-data.elf', 'close-failed-side.elf'):
            artifact = self.artifact(name)
            with patch('urllib.request.urlopen', return_value=self.response()) as call:
                result = self.sender.send_websrv_payload(Path(artifact['path']), self.out, artifact['sha256'])
            self.assertEqual(result['http_status'], 200)
            self.assertEqual(call.call_count, 1)
        artifact = self.artifact()
        with patch('urllib.request.urlopen') as call, self.assertRaisesRegex(RuntimeError, 'Unsupported'):
            self.sender.send_websrv_payload(Path(artifact['path']), self.out, artifact['sha256'])
        call.assert_not_called()

    def test_fs_allowlist_form_payload_and_single_post(self):
        artifact = self.artifact()
        with patch('urllib.request.urlopen', return_value=self.response()) as call:
            result = self.driver.launch_declared(self.api, self.sender, artifact, self.out)
        self.assertEqual(call.call_count, 1)
        request = call.call_args.args[0]
        self.assertEqual(request.full_url, 'http://192.168.1.135:8080/elfldr?pipe=1&args=launch.elf')
        self.assertEqual(request.method, 'POST')
        self.assertEqual(call.call_args.kwargs, {'timeout': 45})
        boundary = request.headers['Content-type'].split('boundary=')[1]
        expected = (('--' + boundary + '\r\nContent-Disposition: form-data; name="elf"; filename="launch.elf"\r\n'
                     'Content-Type: application/octet-stream\r\n\r\n').encode()
                    + Path(artifact['path']).read_bytes() + ('\r\n--' + boundary + '--\r\n').encode())
        self.assertEqual(request.data, expected)
        self.assertEqual(result['payload_sha256'], artifact['sha256'])
        self.assertEqual(self.observations, [])

    def test_changed_source_rejected_before_http(self):
        artifact = self.artifact()
        Path(artifact['path']).write_bytes(b'CHANGED')
        with patch('urllib.request.urlopen') as call, self.assertRaisesRegex(ValueError, 'local launcher changed'):
            self.driver.launch_declared(self.api, self.sender, artifact, self.out)
        call.assert_not_called()

    def test_callback_source_pin_checked_before_import(self):
        fake_root = self.out / 'repo'
        relative = 'port/hebrew-rtl/console-choice.py'
        path = fake_root / relative
        path.parent.mkdir(parents=True)
        path.write_text('raise RuntimeError("must never be imported")', encoding='utf-8')
        config = {'repo': str(fake_root), 'helper_sha256': {relative: '0' * 64}}
        with patch.object(self.driver, 'load') as call, self.assertRaisesRegex(ValueError, 'before import'):
            self.driver.load_sender(config)
        call.assert_not_called()

    def test_helper_source_sha_rejected_before_http(self):
        artifact = self.artifact()
        with patch('urllib.request.urlopen') as call, self.assertRaisesRegex(RuntimeError, 'ELF changed'):
            self.sender.send_websrv_payload(Path(artifact['path']), self.out, '0' * 64, allowed_names=('launch.elf',))
        call.assert_not_called()

    def test_fs_rejects_foreign_path_and_name_before_http(self):
        for artifact in (self.artifact('other.elf'), {**self.artifact(), 'remote_path': '/data/homebrew/PPSA91762/launch.elf'}):
            with patch('urllib.request.urlopen') as call, self.assertRaises(ValueError):
                self.driver.launch_declared(self.api, self.sender, artifact, self.out)
            call.assert_not_called()

    def test_non200_response_not_confirmed_or_retried(self):
        with patch('urllib.request.urlopen', return_value=self.response(202)) as call, self.assertRaisesRegex(RuntimeError, 'did not confirm'):
            self.driver.launch_declared(self.api, self.sender, self.artifact(), self.out)
        self.assertEqual(call.call_count, 1)
        self.assertEqual(self.observations, [])

    def test_http_application_error_does_not_pause_or_retry(self):
        failure = urllib.error.HTTPError('http://fake.invalid', 400, 'application rejection', {}, None)
        with patch('urllib.request.urlopen', side_effect=failure) as call, self.assertRaises(urllib.error.HTTPError):
            self.driver.launch_declared(self.api, self.sender, self.artifact(), self.out)
        self.assertEqual(call.call_count, 1)
        self.assertEqual(self.observations, [])

    def test_transport_error_observed_offline_without_retry(self):
        failure = urllib.error.URLError(OSError('synthetic transport failure'))
        with patch('urllib.request.urlopen', side_effect=failure) as call, self.assertRaises(urllib.error.URLError):
            self.driver.launch_declared(self.api, self.sender, self.artifact(), self.out)
        self.assertEqual(call.call_count, 1)
        self.assertEqual(self.observations, [('offline', 'HTTP: ' + str(failure))])

    def test_local_log_error_is_not_observed_as_network_outage(self):
        artifact = self.artifact()
        with patch('urllib.request.urlopen', return_value=self.response()) as call:
            with patch.object(Path, 'write_bytes', side_effect=OSError('synthetic local disk full')):
                with self.assertRaises(OSError):
                    self.driver.launch_declared(self.api, self.sender, artifact, self.out)
        self.assertEqual(call.call_count, 1)
        self.assertEqual(self.observations, [])


if __name__ == '__main__':
    unittest.main()
