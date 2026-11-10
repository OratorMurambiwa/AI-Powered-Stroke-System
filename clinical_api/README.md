# Synthetic clinical service

This isolated Python 3.12 standard-library package owns explicit UUID linkage, live booking-authority checks, audited clinical reads and opt-in v2 assessment intake. It does not import legacy Streamlit/SQLAlchemy/ML code and never defaults to the existing patient database.

Run all relevant tests from the repository root:

```sh
bash scripts/test-clinical-bridge.sh
```

Read [clinical linkage v1](../docs/clinical-linkage-v1.md) for source contracts, operator approvals, stable IDs, role-generation behavior, API paths and explicit synthetic configuration. [Verification](../docs/hospital-milestone-2b-verification.md) records actual results and remaining limits. The original Streamlit sessions are separate; no clinical inference or hosted AI call is introduced.

Milestone 3 adds explicit `CLINICAL_STORE_VERSION=2` fresh-store assessment intake, patient-scoped emergency grants and committed read audits. Original source records remain read-only. See [appointment/encounter v1](../docs/appointment-encounters-v1.md) and [Milestone 3 results](../docs/hospital-milestone-3-verification.md); no existing store is upgraded on startup.
