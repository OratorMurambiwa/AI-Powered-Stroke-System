PRAGMA foreign_keys=ON;
CREATE TABLE metadata (version INTEGER NOT NULL CHECK(version=3), source_id TEXT NOT NULL);
CREATE TABLE people (
 id TEXT PRIMARY KEY, source_id TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('patient','doctor','technician')),
 native_id INTEGER NOT NULL CHECK(native_id>0), created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX patient_record ON people(source_id,native_id) WHERE kind='patient';
CREATE UNIQUE INDEX staff_record ON people(source_id,native_id) WHERE kind IN ('doctor','technician');
CREATE TABLE encounters (
 id TEXT PRIMARY KEY, patient_id TEXT NOT NULL REFERENCES people(id), source_id TEXT NOT NULL,
 native_id INTEGER CHECK(native_id>0), created_at TEXT NOT NULL, UNIQUE(source_id,native_id)
);
CREATE TABLE identity_links (
 id TEXT PRIMARY KEY, schema_version INTEGER NOT NULL CHECK(schema_version=1), issuer TEXT NOT NULL,
 subject TEXT NOT NULL, person_id TEXT NOT NULL REFERENCES people(id), role TEXT NOT NULL CHECK(role IN ('patient','doctor','technician')),
 role_version INTEGER NOT NULL CHECK(role_version>=0), created_at TEXT NOT NULL, revoked_at TEXT
);
CREATE UNIQUE INDEX active_subject ON identity_links(issuer,subject) WHERE revoked_at IS NULL;
CREATE UNIQUE INDEX active_person ON identity_links(person_id) WHERE revoked_at IS NULL;
CREATE TABLE assignments (
 id TEXT PRIMARY KEY, link_id TEXT NOT NULL REFERENCES identity_links(id), encounter_id TEXT NOT NULL REFERENCES encounters(id),
 created_at TEXT NOT NULL, revoked_at TEXT
);
CREATE UNIQUE INDEX active_assignment ON assignments(link_id,encounter_id) WHERE revoked_at IS NULL;
CREATE TABLE audit (
 id TEXT PRIMARY KEY, at TEXT NOT NULL, operator TEXT NOT NULL, reason TEXT NOT NULL,
 action TEXT NOT NULL, object_id TEXT NOT NULL
);

CREATE TABLE intake_grants (
 id TEXT PRIMARY KEY, link_id TEXT NOT NULL REFERENCES identity_links(id), patient_id TEXT NOT NULL REFERENCES people(id),
 expires_at INTEGER NOT NULL, created_at TEXT NOT NULL, revoked_at TEXT
);
CREATE UNIQUE INDEX active_intake_grant ON intake_grants(link_id,patient_id) WHERE revoked_at IS NULL;
CREATE TABLE assessment_records (
 id TEXT PRIMARY KEY REFERENCES encounters(id), mode TEXT NOT NULL CHECK(mode IN ('SCHEDULED','EMERGENCY')),
 appointment_id TEXT UNIQUE, actor_link_id TEXT NOT NULL REFERENCES identity_links(id),
 clinician_link_id TEXT NOT NULL REFERENCES identity_links(id), reason_code TEXT,
 status TEXT NOT NULL CHECK(status='ASSESSMENT_PENDING'), created_at TEXT NOT NULL
);
CREATE TABLE assessment_receipts (
 request_id TEXT PRIMARY KEY, request_hash TEXT NOT NULL, actor_subject TEXT NOT NULL,
 encounter_id TEXT NOT NULL, appointment_id TEXT, state TEXT NOT NULL CHECK(state IN ('CREATED','REJECTED')),
 receipt TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX created_appointment_receipt ON assessment_receipts(appointment_id) WHERE state='CREATED';

-- Scan bytes live in this private store, never in a public directory or client path.
CREATE TABLE assessment_workflows (
 encounter_id TEXT PRIMARY KEY REFERENCES assessment_records(id), version INTEGER NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('DRAFT','SUBMITTED','APPROVED','REJECTED')),
 document TEXT NOT NULL, approved_summary TEXT, reviewed_by TEXT, reviewed_at TEXT
);
CREATE TABLE assessment_changes (
 request_id TEXT PRIMARY KEY, encounter_id TEXT NOT NULL REFERENCES assessment_records(id),
 actor_subject TEXT NOT NULL, request_hash TEXT NOT NULL, version INTEGER NOT NULL,
 action TEXT NOT NULL, at TEXT NOT NULL, provenance TEXT NOT NULL, snapshot TEXT NOT NULL, receipt TEXT NOT NULL,
 UNIQUE(encounter_id,version)
);
CREATE TABLE assessment_scans (
 id TEXT PRIMARY KEY, encounter_id TEXT NOT NULL REFERENCES assessment_records(id),
 sha256 TEXT NOT NULL, mime_type TEXT NOT NULL CHECK(mime_type='image/png'),
 size INTEGER NOT NULL CHECK(size BETWEEN 1 AND 1048576), content BLOB NOT NULL,
 created_version INTEGER NOT NULL, created_at TEXT NOT NULL, created_by TEXT NOT NULL
);
