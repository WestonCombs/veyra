"""Public certificate validation and readable metadata for the desktop UI."""
from pathlib import Path
from datetime import datetime,timezone
from cryptography import x509
from cryptography.hazmat.primitives import hashes
import ssl

def certificate_info(path):
 raw=Path(path).read_bytes()
 cert=x509.load_pem_x509_certificate(raw) if b'-----BEGIN CERTIFICATE-----' in raw else x509.load_der_x509_certificate(raw)
 now=datetime.now(timezone.utc)
 if not cert.not_valid_before_utc<=now<=cert.not_valid_after_utc:raise ValueError('Certificate is expired or not yet valid.')
 if not cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:raise ValueError('Choose the host public CA certificate, not its server certificate.')
 # The sender uses a CA file, so require the same format it can load.
 ssl.create_default_context(cafile=str(path))
 return dict(subject=cert.subject.rfc4514_string(),issuer=cert.issuer.rfc4514_string(),expires=cert.not_valid_after_utc.strftime('%Y-%m-%d'),fingerprint=cert.fingerprint(hashes.SHA256()).hex(':').upper())
