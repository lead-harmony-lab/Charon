### CreateDocModal.tsx Architecture

**Scope & Purpose**
Acts as the central entry point for authoring new documentation entities, ensuring all generated ADRs and Specs conform to strict metadata schemas and naming conventions prior to persistence.

**Technical Implementation**
* **Polymorphic Form Engine**: Supports both ADR and Spec entity creation via the `docType` prop. Dynamically adapts form fields between architectural metadata (`status`, `summary`, `date`) and technical spec versioning (`version`).
* **Strict Validation Rules**: Enforces structural constraints using regex patterns (`ID_REGEX` and `SEMVER_REGEX`). Validates `ADR-` or `SPEC-` prefixes, minimum content lengths, and semantic versioning before network requests.
* **REST Lifecycle**: Submits structured payloads to `/v1/docs/adrs` or `/v1/docs/specs` via `authFetch`, handling network loading states and error toast signaling. 