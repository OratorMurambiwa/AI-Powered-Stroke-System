import json
import re
from .errors import ClinicalError
from .service import ClinicalService

class ClinicalApplication:
    def __init__(self, service: ClinicalService):
        self.service = service

    def __call__(self, environ, start_response):
        status = 200
        try:
            if environ.get("REQUEST_METHOD") != "GET":
                raise ClinicalError(405, "read_only_api")
            if environ.get("QUERY_STRING"):
                raise ClinicalError(400, "query_not_supported")
            path = environ.get("PATH_INFO", "")
            bearer = environ.get("HTTP_AUTHORIZATION")
            if path == "/health":
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
