# Synthetic clinical identity boundary

This isolated Python 3.12 standard-library package adds explicit UUID linkage, live booking-authority introspection and read-only ownership/assignment checks. It does not import legacy Streamlit/SQLAlchemy/ML code and never defaults to the existing patient database.

Run all relevant tests from the repository root:

```sh
bash scripts/test-clinical-bridge.sh
```

Read [clinical linkage v1](../docs/clinical-linkage-v1.md) for source contracts, operator approvals, stable IDs, role-generation behavior, API paths and explicit synthetic configuration. [Verification](../docs/hospital-milestone-2b-verification.md) records actual results and remaining limits. The original Streamlit sessions are separate; no clinical inference or hosted AI call is introduced.
