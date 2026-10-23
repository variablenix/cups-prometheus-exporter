import hashlib
import importlib.util
from pathlib import Path
import ssl
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    'image_security', Path(__file__).resolve().parents[1] / 'scripts/check_image_security.py')
security = importlib.util.module_from_spec(spec)
spec.loader.exec_module(security)


class CertificateGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        cls.certificates = []
        for number in range(2):
            path = Path(cls.directory.name) / str(number)
            subprocess.run(['openssl', 'req', '-x509', '-newkey', 'ec', '-pkeyopt',
                            'ec_paramgen_curve:prime256v1', '-nodes', '-days', '1',
                            '-subj', '/CN=Synthetic Test CA', '-keyout', str(path) + '.key',
                            '-out', str(path) + '.pem'], check=True, capture_output=True)
            cls.certificates.append(Path(str(path) + '.pem').read_text())

    def test_exact_der_fingerprint_rejects_anchor_and_preserves_other_data(self):
        removed, retained = self.certificates
        revoked = {hashlib.sha256(ssl.PEM_cert_to_DER_cert(removed)).hexdigest()}
        self.assertEqual(security.check_bundle(retained, revoked), 1)
        with self.assertRaisesRegex(ValueError, 'Revoked'):
            security.check_bundle(removed + retained, revoked)

    def test_empty_bundle_cannot_pass_security_gate(self):
        with self.assertRaisesRegex(ValueError, 'empty'):
            security.check_bundle('# no trusted certificates here')

    def test_malformed_pem_cannot_pass_security_gate(self):
        with self.assertRaises(Exception):
            security.check_bundle('-----BEGIN CERTIFICATE-----\n%%%\n-----END CERTIFICATE-----')
