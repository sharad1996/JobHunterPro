"""
Compatibility helpers — e.g. urllib3 LibreSSL warning on macOS system Python.

Import this module before `requests` (or import it from main.py first).
"""

import warnings


def suppress_urllib3_openssl_warning() -> None:
    """urllib3 v2 warns when Python's ssl uses LibreSSL; safe to ignore for HTTP clients."""
    warnings.filterwarnings(
        "ignore",
        message=r"urllib3 v2 only supports OpenSSL",
    )
    try:
        from urllib3.exceptions import NotOpenSSLWarning

        warnings.filterwarnings("ignore", category=NotOpenSSLWarning)
    except ImportError:
        pass


suppress_urllib3_openssl_warning()
