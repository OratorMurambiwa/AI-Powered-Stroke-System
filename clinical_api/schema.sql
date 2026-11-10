PRAGMA foreign_keys=ON;
CREATE TABLE metadata (version INTEGER NOT NULL CHECK(version=1), source_id TEXT NOT NULL);
CREATE TABLE people (
 id TEXT PRIMARY KEY, source_id TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('patient','doctor','technician')),
 native_id INTEGER NOT NULL CHECK(native_id>0), created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX patient_record ON people(source_id,native_id) WHERE kind='patient';
CREATE UNIQUE INDEX staff_record ON people(source_id,native_id) WHERE kind IN ('doctor','technician');
CREATE TABLE encounters (
 id TEXT PRIMARY KEY, patient_id TEXT NOT NULL REFERENCES people(id), source_id TEXT NOT NULL,
 native_id INTEGER NOT NULL CHECK(native_id>0), created_at TEXT NOT NULL, UNIQUE(source_id,native_id)
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
