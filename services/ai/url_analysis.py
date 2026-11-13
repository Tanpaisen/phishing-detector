"""Offline URL inspection; shared later by training and inference.

No DNS lookup, target fetch, redirect expansion or risk prediction occurs here.
"""
import hashlib
import ipaddress
import platform
import re
import unicodedata
from importlib.metadata import version
from importlib.resources import files
from urllib.parse import urlsplit

import idna
import tldextract

PREPROCESSING_VERSION = "url-inspection-v1"
PSL_SHA256 = hashlib.sha256(
    files("tldextract").joinpath(".tld_set_snapshot").read_bytes()
).hexdigest()
EXTRACTOR = tldextract.TLDExtract(
    cache_dir=None,
    suffix_list_urls=(),
    fallback_to_snapshot=True,
    include_psl_private_domains=True,
)


class URLInputError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def inspect_url(raw: str) -> dict:
    if not isinstance(raw, str) or not 1 <= len(raw) <= 4096:
        raise URLInputError("INVALID_URL_LENGTH", "URL phải dài từ 1 đến 4.096 ký tự.")
    # Check BEFORE urlsplit: it silently removes some control characters.
    if any(unicodedata.category(c) in {"Cc", "Cs"} for c in raw):
        raise URLInputError("INVALID_URL", "URL chứa ký tự điều khiển không hợp lệ.")
    value = raw.strip(" ")
    if not value or any(c.isspace() for c in value) or "\\" in value:
        raise URLInputError("INVALID_URL", "URL chứa khoảng trắng hoặc dấu gạch chéo ngược.")
    if re.search(r"%(?![0-9A-Fa-f]{2})", value):
        raise URLInputError("INVALID_URL", "URL chứa percent-encoding không hợp lệ.")
    match = re.fullmatch(r"(https?)://([^/?#]*)(.*)", value, re.IGNORECASE)
    if not match:
        raise URLInputError("UNSUPPORTED_SCHEME", "Cần URL đầy đủ bắt đầu bằng http:// hoặc https://.")
    scheme, authority, tail = match.groups()
    if "@" in authority:
        raise URLInputError("USERINFO_NOT_ALLOWED", "Không hỗ trợ URL chứa thông tin đăng nhập.")
    # Explicit authority grammar avoids lenient handling of IPv6 suffixes/ports.
    host_match = re.fullmatch(r"(\[[0-9A-Fa-f:.]+\]|[^:\[\]]+)(?::([0-9]+))?", authority)
    if not host_match:
        raise URLInputError("INVALID_HOST", "Hostname hoặc cổng không hợp lệ.")
    original_host, port_text = host_match.groups()
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise URLInputError("INVALID_URL", "URL hoặc cổng không hợp lệ.") from None
    if port is not None and not 1 <= port <= 65535:
        raise URLInputError("INVALID_PORT", "Cổng phải nằm trong khoảng 1–65535.")
    if "%" in original_host:
        raise URLInputError("INVALID_HOST", "Không hỗ trợ hostname mã hóa hoặc IPv6 zone ID.")
    bracketed = original_host.startswith("[")
    host = original_host[1:-1] if bracketed else original_host
    try:
        ascii_host = host.lower() if bracketed else idna.encode(
            host, uts46=True, std3_rules=True, transitional=False
        ).decode("ascii").removesuffix(".").lower()
    except (idna.IDNAError, UnicodeError):
        raise URLInputError("INVALID_HOST", "Tên miền Unicode/IDNA không hợp lệ.") from None

    try:
        ip = ipaddress.ip_address(ascii_host)
    except ValueError:
        ip = None
    if bracketed and (ip is None or ip.version != 6):
        raise URLInputError("INVALID_HOST", "Địa chỉ IPv6 không hợp lệ.")

    registered_domain = None
    subdomain = ""
    suffix = ""
    is_private_suffix = False
    if ip is not None:
        if not ip.is_global or ip.is_multicast or ip.is_reserved:
            raise URLInputError("UNSUPPORTED_HOST", "Không hỗ trợ IP nội bộ hoặc địa chỉ đặc biệt.")
        ascii_host = ip.compressed
        unicode_host = ascii_host
    else:
        # Reject browser-style legacy IPv4 forms such as 127.1 / 0x7f000001.
        last_label = ascii_host.rsplit(".", 1)[-1]
        if re.fullmatch(r"(?:[0-9]+|0x[0-9a-f]+)", last_label):
            raise URLInputError("UNSUPPORTED_HOST", "Không hỗ trợ địa chỉ IP viết tắt hoặc không chuẩn.")
        domain = EXTRACTOR(ascii_host)
        if not domain.suffix or not domain.domain:
            raise URLInputError("UNSUPPORTED_HOST", "Hostname chưa có miền đăng ký trong PSL cục bộ.")
        registered_domain = domain.top_domain_under_public_suffix
        subdomain = domain.subdomain
        suffix = domain.suffix
        is_private_suffix = domain.is_private
        unicode_host = idna.decode(ascii_host)

    normalized_authority = f"[{ascii_host}]" if bracketed else ascii_host
    if port_text is not None:
        normalized_authority += f":{port}"
    # Keep path/query/fragment byte-for-byte as text, including empty ? and #.
    normalized_url = f"{scheme.lower()}://{normalized_authority}{tail}"
    return {
        "schema_version": "1.0",
        "stage": "URL_INSPECTION",
        "model_loaded": False,
        "preprocessing_version": PREPROCESSING_VERSION,
        "resources": {
            "psl_sha256": PSL_SHA256,
            "tldextract_version": version("tldextract"),
            "idna_version": version("idna"),
            "python_version": platform.python_version(),
            "unicode_version": unicodedata.unidata_version,
            "private_suffixes_included": True,
        },
        "url": {
            "normalized_url": normalized_url,
            "scheme": scheme.lower(),
            "hostname_input": host,
            "hostname_ascii": ascii_host,
            "hostname_unicode": unicode_host,
            "registered_domain": registered_domain,
            "public_suffix": suffix,
            "subdomain": subdomain,
            "port": port,
            "is_ip": ip is not None,
            "is_private_suffix": is_private_suffix,
        },
        "features": {
            "url_length": len(value),
            "hostname_length": len(ascii_host),
            "subdomain_count": len(subdomain.split(".")) if subdomain else 0,
            "digit_count": sum(c in "0123456789" for c in value),
            "has_unicode_input": any(ord(c) > 127 for c in value),
            "has_unicode_hostname": any(ord(c) > 127 for c in host),
            "has_format_characters_in_hostname": any(unicodedata.category(c) == "Cf" for c in host),
            "has_punycode_hostname": any(label.startswith("xn--") for label in ascii_host.split(".")),
            "has_query": "?" in tail.split("#", 1)[0],
            "has_fragment": "#" in tail,
        },
        "limitations": [
            "Chỉ kiểm tra cấu trúc URL; chưa đánh giá nguy cơ phishing.",
            "Không truy cập website, phân giải DNS hoặc theo dõi chuyển hướng.",
            "IDNA không đồng nghĩa với phát hiện ký tự giả mạo thương hiệu.",
        ],
    }
