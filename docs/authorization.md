# Authorization

## Organization boundary
Tenant-scoped business records carry a mandatory organization_id foreign key. API authorization derives organization context from the authenticated server-side session rather than request payloads.

## Roles
Current roles are:
- owner: organization-wide administrative authority.
- admin: administration plus finance/tax/audit permissions.
- tax: tax operations and audit read access.
- finance: finance operations, approval, posting and audit read access.
- auditor: audit read access.
- viewer: authenticated read-only baseline.

Permissions are evaluated server-side. Frontend visibility is not a security boundary.

## Object-level authorization
Invoice retrieval and finance mutations require the target record to belong to the authenticated organization. Cross-tenant object IDs therefore do not become accessible merely because the numeric ID is known.

## Property-level authorization
The API uses explicit Pydantic request models rather than arbitrary ORM deserialization. Sensitive workflow properties such as organization, role, approval state and posting timestamps are not accepted from normal client payloads.

## Remaining work
Later slices will add administrative membership management, explicit permission administration where needed, export authorization, evidence authorization, and a dedicated cross-tenant integration test suite.
