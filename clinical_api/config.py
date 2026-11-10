from dataclasses import dataclass
from pathlib import Path
import os
from .identity import IdentityAdapter
from .source import ClinicalSource
from .store import LinkStore
from .service import ClinicalService

@dataclass(frozen=True)
class Config:
    records: Path
    links: Path
    source_id: str
    authority_url: str
    store_version: int = 1

    @classmethod
    def from_environment(cls):
        if os.environ.get("CLINICAL_DATA_MODE") != "synthetic":
            raise ValueError("Milestone 2B accepts explicitly marked synthetic sources only")
        if os.environ.get("CLINICAL_STORE_VERSION", "1") not in {"1", "2", "3"}:
            raise ValueError("Unsupported clinical store version")
        # No dotenv discovery, default patient DB path or automatic schema creation.
        return cls(Path(os.environ["CLINICAL_RECORDS_DB"]), Path(os.environ["CLINICAL_LINKS_DB"]),
                   os.environ["CLINICAL_SOURCE_ID"], os.environ["IDENTITY_INTROSPECTION_URL"], int(os.environ.get("CLINICAL_STORE_VERSION", "1")))

    def service(self) -> ClinicalService:
        if self.records.resolve() == self.links.resolve():
            raise ValueError("Clinical records and linkage stores must be separate files")
        return ClinicalService(IdentityAdapter(self.authority_url), LinkStore(self.links, self.source_id, self.store_version), ClinicalSource(self.records, self.source_id))
