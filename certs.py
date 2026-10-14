"""Self-signed HTTPS certificate for the phone capture page.

Phone browsers only allow the camera and motion sensors on HTTPS. The certificate
is made on this PC and never leaves it. The phone shows a warning once; tap
"continue" (Advanced > Proceed) to accept it.
"""
import datetime
import ipaddress
import os


def ensure_cert(ip, folder=os.path.join("data", "certs")):
    crt, key, marker = (os.path.join(folder, n) for n in ("server.crt", "server.key", "ip.txt"))
    if all(os.path.exists(p) for p in (crt, key, marker)) and open(marker).read().strip() == ip:
        return crt, key

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    os.makedirs(folder, exist_ok=True)
    k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "img23d local capture")])
    names = [x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
    try:
        names.append(x509.IPAddress(ipaddress.ip_address(ip)))
    except ValueError:
        names.append(x509.DNSName(ip))
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(k.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=800))
        .add_extension(x509.SubjectAlternativeName(names), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(k, hashes.SHA256())
    )
    with open(key, "wb") as f:
        f.write(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                                serialization.NoEncryption()))
    with open(crt, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    with open(marker, "w") as f:
        f.write(ip)
    return crt, key
