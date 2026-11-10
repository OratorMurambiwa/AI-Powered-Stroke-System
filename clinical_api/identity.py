import base64
from http.client import HTTPException
import re
import ssl
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler, HTTPSHandler
from .errors import ClinicalError
from .validation import ISSUER, ROLES, strict_json, subject_id, uuid_id, integer

@dataclass(frozen=True)
class Principal:
    issuer: str
    subject: str
    role: str
    session_id: str
    expires_at: int
    role_version: int

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

class IdentityAdapter:
    """Online authority validation; no signing key, cached success or legacy login."""
    def __init__(self, url: str, timeout: float = 2.0):
        parts = urlsplit(url)
        if (parts.scheme not in {"http", "https"} or parts.hostname not in {"127.0.0.1", "localhost", "::1"}
                or parts.username or parts.password or parts.query or parts.fragment
                or parts.path != "/api/v1/identity/clinical-introspect" or not 0.05 <= timeout <= 5):
            raise ValueError("Explicit local authority URL and bounded timeout required")
        self.url = url
        self.timeout = timeout
        self.opener = build_opener(ProxyHandler({}), NoRedirect(), HTTPSHandler(context=ssl.create_default_context()))

    def introspect(self, authorization: str | None) -> Principal:
        if not isinstance(authorization, str) or not authorization.startswith("Bearer ") or len(authorization) > 4096:
            raise ClinicalError(401, "authentication_required")
        token = authorization[7:]
        # This unverified parsing binds the authority response to the request.
        # It NEVER authenticates: a successful live POST is mandatory below.
        try:
            parts = token.split(".")
            if len(parts) != 3 or any(not re.fullmatch(r"[A-Za-z0-9_-]+", part) for part in parts):
                raise ValueError
            payload = strict_json(base64.b64decode(parts[1] + "=" * (-len(parts[1]) % 4), altchars=b"-_", validate=True))
            if not isinstance(payload, dict):
                raise ValueError
        except (ValueError, UnicodeError, RecursionError, ClinicalError):
            raise ClinicalError(401, "invalid_token") from None
        request = Request(self.url, data=b"{}", method="POST", headers={
            "Authorization": authorization, "Content-Type": "application/json", "Accept": "application/json",
        })
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                if response.status != 200 or response.headers.get_content_type() != "application/json":
                    raise ValueError
                if len(response.headers.get_all("Content-Length", [])) != 1 or response.headers.get("Transfer-Encoding"):
                    raise ValueError
                length = response.headers.get("Content-Length", "")
                if not length.isdigit() or not 1 <= int(length) <= 4096:
                    raise ValueError
                raw = response.read(int(length) + 1)
                if len(raw) != int(length):
                    raise ValueError
                data = strict_json(raw)
        except HTTPError as error:
            error.close()
            if error.code in {401, 403}:
                raise ClinicalError(401, "invalid_session") from None
            raise ClinicalError(503, "identity_unavailable") from None
        except (OSError, URLError, HTTPException, ValueError, UnicodeError, RecursionError):
            raise ClinicalError(503, "identity_unavailable") from None
        try:
            expected = {"active", "schemaVersion", "issuer", "subject", "role", "sessionId", "expiresAt", "roleVersion"}
            if not isinstance(data, dict) or set(data) != expected or data["active"] is not True:
                raise ValueError
            if type(data["schemaVersion"]) is not int or data["schemaVersion"] != 1 or data["issuer"] != ISSUER or data["role"] not in ROLES:
                raise ValueError
            subject = subject_id(data["subject"])
            sid = uuid_id(data["sessionId"])
            expiry = integer(data["expiresAt"])
            epoch = integer(data["roleVersion"])
            if not time.time() < expiry <= time.time() + 905:
                raise ValueError
            if (payload.get("sub") != subject or payload.get("sid") != sid or type(payload.get("exp")) is not int
                    or payload["exp"] != expiry or payload.get("iss") != ISSUER
                    or payload.get("aud") != "urn:stroke-platform:booking:v1" or payload.get("ver") != 1):
                raise ValueError
            return Principal(ISSUER, subject, data["role"], sid, expiry, epoch)
        except (ValueError, TypeError, ClinicalError):
            raise ClinicalError(503, "invalid_identity_response") from None
