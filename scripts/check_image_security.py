#!/usr/bin/env python3
"""Fail the image gate on old Python, incident anchors, or unused installers."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import ssl
import sys


REVOKED = {
    '86a1ecba089c4a8d3bbe2734c612ba341d813e043cf9e8a862cd5c57a36bbe6b',
    'd7a7a0fb5d7e2731d771e9484ebcdef71d5f0c3e0a2948782bc83ee0ea699ef4',
}


def check_bundle(content, revoked=REVOKED):
    certificates = re.findall(r'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----', content, re.S)
    if not certificates:
        raise ValueError('Certificate bundle is empty or unreadable')
    # PEM-to-DER decoding alone accepts some malformed base64. Require OpenSSL
    # to parse the actual X.509 bundle before treating the inventory as valid.
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_verify_locations(cadata=content)
    fingerprints = {hashlib.sha256(ssl.PEM_cert_to_DER_cert(cert)).hexdigest() for cert in certificates}
    if fingerprints & revoked:
        raise ValueError('Revoked incident anchor remains in the trust bundle')
    return len(fingerprints)


def main():
    if sys.version_info < (3, 14, 9):
        raise ValueError('Python 3.14.9 or newer is required')
    for package in ('pip', 'ensurepip', 'setuptools', 'msgpack'):
        if importlib.util.find_spec(package) is not None:
            raise ValueError('Unused runtime package is present: ' + package)
    if (shutil.which('cupsd') or shutil.which('foomatic-rip')
            or Path('/usr/sbin/cupsd').exists()
            or Path('/usr/lib/cups/backend/ipp').exists()
            or Path('/usr/lib/cups/filter/foomatic-rip').exists()):
        raise ValueError('Unexpected print-server or filter component in the exporter image')
    paths = {Path('/etc/ssl/certs/ca-certificates.crt')}
    default = ssl.get_default_verify_paths().cafile
    if default:
        paths.add(Path(default).resolve())
    bundles = {str(path): check_bundle(path.read_text()) for path in paths}
    context = ssl.create_default_context()
    effective = {hashlib.sha256(cert).hexdigest() for cert in context.get_ca_certs(binary_form=True)}
    if not effective or effective & REVOKED:
        raise ValueError('Effective OpenSSL trust is empty or contains a revoked anchor')
    print(json.dumps({'python': sys.version.split()[0], 'bundles': bundles,
                      'effective_roots': len(effective), 'revoked_anchors': [], 'installers': 'absent'}))


if __name__ == '__main__':
    main()
