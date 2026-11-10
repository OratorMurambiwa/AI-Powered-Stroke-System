import json
import re
from .errors import ClinicalError
from .service import ClinicalService
from .assessment import AssessmentService
from .validation import strict_json

class ClinicalApplication:
    def __init__(self, service: ClinicalService):
        self.service = service
        self.assessments = AssessmentService(service) if service.store.version == 2 else None

    def __call__(self, environ, start_response):
        status = 200
        try:
            if environ.get("QUERY_STRING"):
                raise ClinicalError(400, "query_not_supported")
            path = environ.get("PATH_INFO", "")
            bearer = environ.get("HTTP_AUTHORIZATION")
            method = environ.get("REQUEST_METHOD")
            if method == "POST" and self.assessments and path in {"/api/v1/clinical/assessment-requests", "/api/v1/clinical/emergency-assessments"}:
                length = environ.get("CONTENT_LENGTH", "")
                if not length.isdigit() or not 1 <= int(length) <= 8192 or not environ.get('CONTENT_TYPE', '').startswith('application/json'):
                    raise ClinicalError(400, "invalid_request_body")
                try:
                    raw = environ['wsgi.input'].read(int(length))
                    if len(raw) != int(length):
                        raise ValueError
                    command = strict_json(raw)
                except (ValueError, UnicodeError, RecursionError):
                    raise ClinicalError(400, "invalid_request_body") from None
                result = self.assessments.scheduled(bearer, command) if path.endswith('/assessment-requests') else self.assessments.emergency(bearer, command)
            elif method != "GET":
                raise ClinicalError(405, "method_not_allowed")
            elif path == "/health":
                with self.service.store.connection(), self.service.source.connection():
                    result = {"schemaVersion": 1, "status": "ready"}
            elif match := re.fullmatch(r"/api/v1/clinical/patients/([^/]+)(/encounters)?", path):
                result = self.service.patient(bearer, match[1], encounters=bool(match[2]))
            elif match := re.fullmatch(r"/api/v1/clinical/encounters/([^/]+)", path):
                result = self.service.encounter(bearer, match[1])
            else:
                raise ClinicalError(404, "route_not_found")
        except ClinicalError as error:
            status = error.status
            result = {"schemaVersion": 1, "error": error.code}
        except Exception:
            status = 500
            result = {"schemaVersion": 1, "error": "internal_error"}
        raw = json.dumps(result, allow_nan=False).encode("utf-8")
        from http import HTTPStatus
        start_response(f"{status} {HTTPStatus(status).phrase}", [
            ("Content-Type", "application/json"), ("Content-Length", str(len(raw))),
            ("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff"),
        ])
        return [raw]
