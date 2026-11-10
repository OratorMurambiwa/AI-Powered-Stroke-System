import json
import re
from .errors import ClinicalError
from .service import ClinicalService
from .assessment import AssessmentService
from .workflow import ReviewWorkflow
from .validation import strict_json

class ClinicalApplication:
    def __init__(self, service: ClinicalService):
        self.service = service
        self.assessments = AssessmentService(service) if service.store.version >= 2 else None
        self.workflow = ReviewWorkflow(service) if service.store.version == 3 else None

    def __call__(self, environ, start_response):
        status = 200
        try:
            if environ.get("QUERY_STRING"):
                raise ClinicalError(400, "query_not_supported")
            path = environ.get("PATH_INFO", "")
            bearer = environ.get("HTTP_AUTHORIZATION")
            method = environ.get("REQUEST_METHOD")
            workflow_match = re.fullmatch(r"/api/v1/clinical/encounters/([^/]+)/assessment", path) if self.workflow else None
            scan_match = re.fullmatch(r"/api/v1/clinical/encounters/([^/]+)/scans/([^/]+)", path) if self.workflow else None
            if method == "GET" and scan_match:
                raw = self.workflow.scan(bearer, scan_match[1], scan_match[2])
                start_response('200 OK', [('Content-Type','image/png'),('Content-Length',str(len(raw))),
                    ('Content-Disposition',f'attachment; filename="{scan_match[2]}.png"'),
                    ('Cache-Control','no-store'),('X-Content-Type-Options','nosniff'),
                    ('Content-Security-Policy',"default-src 'none'; sandbox")])
                return [raw]
            if method == "GET" and workflow_match:
                result = self.workflow.read(bearer, workflow_match[1])
            elif method == "POST" and workflow_match:
                command = self._body(environ, 1400000)
                result = self.workflow.mutate(bearer, workflow_match[1], command)
            elif method == "POST" and self.assessments and path in {"/api/v1/clinical/assessment-requests", "/api/v1/clinical/emergency-assessments"}:
                command = self._body(environ, 8192)
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

    @staticmethod
    def _body(environ, maximum):
        length = environ.get('CONTENT_LENGTH', '')
        if environ.get('HTTP_TRANSFER_ENCODING'):
            raise ClinicalError(400, 'invalid_request_body')
        if not length.isdigit() or not 1 <= int(length) <= maximum:
            raise ClinicalError(413 if length.isdigit() and int(length) > maximum else 400, 'invalid_request_body')
        if environ.get('CONTENT_TYPE', '').split(';')[0].strip().lower() != 'application/json':
            raise ClinicalError(415, 'unsupported_media_type')
        try:
            raw = environ['wsgi.input'].read(int(length))
            if len(raw) != int(length):
                raise ValueError
            return strict_json(raw)
        except (ValueError, UnicodeError, RecursionError):
            raise ClinicalError(400, 'invalid_request_body') from None
