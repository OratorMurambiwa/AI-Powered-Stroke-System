from dataclasses import dataclass
from pathlib import Path
import os
from .identity import IdentityAdapter
from .source import ClinicalSource
from .store import LinkStore
from .service import ClinicalService
from .inference import InferenceAdapter

@dataclass(frozen=True)
class Config:
    records: Path
    links: Path
    source_id: str
    authority_url: str
    store_version: int = 1
    inference_url: str = ""
    inference_key: str = ""

    @classmethod
    def from_environment(cls):
        if os.environ.get("CLINICAL_DATA_MODE") != "synthetic":
            raise ValueError("Milestone 2B accepts explicitly marked synthetic sources only")
        if os.environ.get("CLINICAL_STORE_VERSION", "1") not in {"1", "2", "3", "4"}:
            raise ValueError("Unsupported clinical store version")
        # No dotenv discovery, default patient DB path or automatic schema creation.
        return cls(Path(os.environ["CLINICAL_RECORDS_DB"]), Path(os.environ["CLINICAL_LINKS_DB"]),
                   os.environ["CLINICAL_SOURCE_ID"], os.environ["IDENTITY_INTROSPECTION_URL"], int(os.environ.get("CLINICAL_STORE_VERSION", "1")),
                   os.environ.get("CLINICAL_INFERENCE_URL", ""), os.environ.get("INFERENCE_SERVICE_KEY", ""))

    def service(self) -> ClinicalService:
        if self.records.resolve() == self.links.resolve():
            raise ValueError("Clinical records and linkage stores must be separate files")
        service = ClinicalService(IdentityAdapter(self.authority_url), LinkStore(self.links, self.source_id, self.store_version), ClinicalSource(self.records, self.source_id))
        if self.inference_url or self.inference_key:
            if self.store_version != 4:
                raise ValueError("Inference requires explicit fresh v4 synthetic store")
            service.inference = InferenceAdapter(self.inference_url, self.inference_key)
        return service
