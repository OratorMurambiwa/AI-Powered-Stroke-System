"""Explicit local approval CLI. Never mounted as a clinical HTTP endpoint."""
import getpass
import json
import sys
from .config import Config
from .errors import ClinicalError
from .linkage import LinkOperator
from .validation import strict_json, text

def main() -> None:
    service = Config.from_environment().service()
    operator = text(input("Authorized operator/change reference: "), 120)
    reason = text(input("Independent identity/record verification approval reference: "), 500)
    if len(sys.argv) != 2:
        raise ValueError
    action = sys.argv[1]
    manager = LinkOperator(service.store, service.source, service.identity)
    if action == "init":
        with service.source.connection():
            pass
        service.store.initialize()
        with service.store.connection(write=True) as db:
            service.store.audit(db, "STORE_INITIALIZED", service.source.source_id, operator, reason)
        result = {"schemaVersion": 1, "sourceId": service.source.source_id}
    else:
        raw = input("Versioned JSON command (IDs only, no secrets): ").encode("utf-8")
        if len(raw) > 4096:
            raise ValueError
        command = strict_json(raw)
        if action in {"link", "assign", "grant_intake"}:
            if not sys.stdin.isatty():
                raise ClinicalError(400, "private_terminal_required")
            token = getpass.getpass("Target person's live authority bearer token (hidden): ")
            result = getattr(manager, action)(command, "Bearer " + token, operator, reason)
        elif action in {"register_person", "register_encounter"}:
            result = getattr(manager, action)(command, operator, reason)
        elif action == "revoke_intake":
            manager.revoke_intake(command, operator, reason)
            result = {"schemaVersion": 1, "status": "revoked"}
        elif action in {"revoke_link", "revoke_assignment"}:
            manager.revoke(command, operator, reason, assignment=action == "revoke_assignment")
            result = {"schemaVersion": 1, "status": "revoked"}
        else:
            raise ValueError
    print(json.dumps(result))  # IDs only; never print target tokens or patient data.

if __name__ == "__main__":
    try:
        main()
    except ClinicalError as error:
        raise SystemExit(f"Operator action denied: {error.code}") from None
    except Exception:
        raise SystemExit("Operator action failed; no credentials logged") from None
