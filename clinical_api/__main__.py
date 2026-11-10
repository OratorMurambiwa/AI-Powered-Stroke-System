from wsgiref.simple_server import make_server, WSGIRequestHandler
from .config import Config
from .app import ClinicalApplication

class PrivateHandler(WSGIRequestHandler):
    def log_message(self, *_args):
        pass  # No request paths, bearer tokens or clinical payloads in access logs.

def main():
    service = Config.from_environment().service()
    with service.store.connection(), service.source.connection():
        pass
    with make_server("127.0.0.1", 8010, ClinicalApplication(service), handler_class=PrivateHandler) as server:
        server.serve_forever()

if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("Clinical boundary startup failed; check explicit synthetic configuration") from None
