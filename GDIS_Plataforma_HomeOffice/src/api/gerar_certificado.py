import os
import datetime
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

def gerar_autoassinado(cert_file, key_file, common_name="GDIS_Plataforma"):
    """Gera um certificado autoassinado e uma chave privada."""
    # Gera a chave privada
    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    # Assunto e Emissor (mesmo para autoassinado)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "BR"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Minas Gerais"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, "Cemig"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "GDIS Platform"),
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),
    ])

    # Cria o certificado
    cert = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        issuer
    ).public_key(
        key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.datetime.now(datetime.timezone.utc)
    ).not_valid_after(
        # Certificado válido por 10 anos
        datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=3650)
    ).add_extension(
        x509.SubjectAlternativeName([x509.DNSName("localhost"), x509.IPAddress(datetime.netaddr.IPAddress("127.0.0.1"))] if False else [x509.DNSName(common_name)]),
        critical=False,
    ).sign(key, hashes.SHA256())

    # Salva a chave privada
    with open(key_file, "wb") as f:
        f.write(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ))

    # Salva o certificado
    with open(cert_file, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

if __name__ == "__main__":
    # Define caminhos padrão
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    data_dir = os.path.join(base_dir, "data")
    os.makedirs(data_dir, exist_ok=True)
    
    cert_path = os.path.join(data_dir, "server.crt")
    key_path = os.path.join(data_dir, "server.key")
    
    if not os.path.exists(cert_path) or not os.path.exists(key_path):
        print(f"Gerando novo certificado autoassinado em: {data_dir}")
        gerar_autoassinado(cert_path, key_path)
    else:
        print("Certificado já existe. Pulando geração.")
