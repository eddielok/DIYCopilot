"""Make Python's HTTPS use the macOS system trust store.

Why this exists:
On corporate networks (and with some antivirus software) HTTPS traffic is
intercepted and re-signed with a company root certificate. macOS tools like
`curl` trust it because it's installed in the system keychain — but Python's
`requests` uses its own bundled cert list (certifi), which doesn't include it.
That causes:

    SSLError(SSLCertVerificationError: self-signed certificate in certificate chain)

`truststore` patches Python's ssl module to use the OS trust store instead, so
Python trusts exactly what the rest of your Mac trusts.

Import this module as the very first thing in any entry point.
"""
from __future__ import annotations

import sys


def apply() -> None:
    try:
        import truststore  # type: ignore

        truststore.inject_into_ssl()
    except ImportError:
        sys.stderr.write(
            "[ssl] 'truststore' not installed — if you hit SSL certificate "
            "errors on a corporate network, run: pip install truststore\n"
        )
    except Exception as exc:  # pragma: no cover - defensive
        sys.stderr.write(f"[ssl] could not apply system trust store: {exc}\n")


# Apply on import.
apply()
