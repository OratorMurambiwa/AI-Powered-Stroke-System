import time
from http.client import HTTPException
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request
from urllib.error import HTTPError, URLError
from .identity import IdentityAdapter, Principal
from .validation import ISSUER, uuid_id, subject_id, integer, strict_json
from .errors import ClinicalError

class BookingAdapter:
    def __init__(self, identity: IdentityAdapter):
        self.identity = identity

    def proof(self, bearer: str, principal: Principal, appointment_id: str, request_id: str, command_hash: str, encounter_id: str) -> dict:
        parts = urlsplit(self.identity.url)
        path = f"/api/v1/appointments/{uuid_id(appointment_id)}/assessment-proof"
        url = urlunsplit((parts.scheme, parts.netloc, path, '', ''))
        import json
        request = Request(url, data=json.dumps({"schemaVersion": 1, "requestId": uuid_id(request_id)}).encode(), method='POST',
                          headers={"Authorization": bearer, "Content-Type": "application/json"})
        try:
            with self.identity.opener.open(request, timeout=self.identity.timeout) as response:
                length = response.headers.get('Content-Length', '')
                if response.status != 200 or response.headers.get_content_type() != 'application/json' or not length.isdigit() or not 1 <= int(length) <= 4096:
                    raise ValueError
                raw = response.read(int(length) + 1)
                if len(raw) != int(length):
                    raise ValueError
                data = strict_json(raw)
        except HTTPError as error:
            error.close()
            if error.code in {401, 403}:
                raise ClinicalError(401, 'invalid_session') from None
            if error.code in {404, 409}:
                raise ClinicalError(409, 'appointment_proof_unavailable') from None
            raise ClinicalError(503, 'booking_unavailable') from None
        except (OSError, URLError, HTTPException, ValueError, UnicodeError, RecursionError):
            raise ClinicalError(503, 'booking_unavailable') from None
        try:
            expected = {'schemaVersion','issuer','appointmentId','requestId','encounterId','commandHash','patientSubject','patientRoleVersion','doctorSubject','doctorRoleVersion','actorSubject','actorRoleVersion','sessionId','status','expiresAt'}
            if not isinstance(data, dict) or set(data) != expected or type(data['schemaVersion']) is not int or data['schemaVersion'] != 1 or data['issuer'] != ISSUER or data['status'] != 'RESERVED':
                raise ValueError
            for key, value in [('appointmentId', appointment_id), ('requestId', request_id), ('encounterId', encounter_id), ('commandHash', command_hash), ('actorSubject', principal.subject), ('sessionId', principal.session_id), ('actorRoleVersion', principal.role_version)]:
                if data[key] != value:
                    raise ValueError
            subject_id(data['patientSubject']); subject_id(data['doctorSubject'])
            for key in ('patientRoleVersion', 'doctorRoleVersion', 'actorRoleVersion', 'expiresAt'):
                integer(data[key])
            if data['doctorSubject'] != principal.subject or data['doctorRoleVersion'] != principal.role_version or not time.time() < data['expiresAt'] <= time.time() + 65:
                raise ValueError
            return data
        except (ClinicalError, ValueError, TypeError):
            raise ClinicalError(503, 'invalid_appointment_proof') from None
