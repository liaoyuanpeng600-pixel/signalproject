# SCHEMA_EVOLUTION — Schema Versioning Policy

> **Document role:** Wire-level rules for evolving the schemas defined in [04_data_schema.md](04_data_schema.md). Authoritative for whether a given change is MAJOR, MINOR, or PATCH.
>
> Read alongside: [SPEC_VERSION.md](SPEC_VERSION.md), [INVARIANTS.md](INVARIANTS.md), [GOVERNANCE.md](GOVERNANCE.md), [04_data_schema.md](04_data_schema.md).

---

## 1. Why Schema Evolution Needs Its Own Rules

Schemas are wire-level contracts. A producer (e.g., the detector agent) writes data; a consumer (e.g., the scorer, the report generator, the API) reads it. A schema change that breaks the consumer is a **production incident**.

This document defines the precise rules. Any change to a schema field requires classification under these rules **before** writing the change.

---

## 2. Semver Rules for Schemas

Schemas follow strict semver. The bump type is determined **per change**, summed across all changes in the release.

### 2.1 Decision Table

| Change | Bump | Reasoning |
|---|---|---|
| Add optional field | MINOR | Old producers don't write; new consumers ignore it |
| Add required field with default | MINOR | Old consumers must accept; new producers must write (default) |
| Add enum value | MINOR | Old consumers treat unknown as error → MAJOR if no fallback |
| Add enum value with safe default | MINOR | Old consumers default to safe value |
| **Remove optional field** | MAJOR | Old producers may write; new consumers can't read it |
| **Remove required field** | MAJOR | Old consumers expect it; data is unreadable |
| **Change field type** | MAJOR | Incompatible representations |
| **Rename field** | MAJOR (treat as remove + add) |  |
| **Tighten validation** | MAJOR | E.g., `string` → `enum[A,B,C]` rejects previously-valid data |
| **Add enum constraint to existing field** | MAJOR | Same as tighten |
| **Make field required (was optional)** | MAJOR | Old producers won't write; new consumers require it |
| **Make field optional (was required)** | MINOR | Old producers still write; new consumers must handle absence |
| Change field description text only | PATCH | No semantic change |
| Fix typo in enum value spelling | MAJOR | Breaks any code matching the string |
| Add a new field with deprecation flag | MINOR | Allow consumers to migrate |
| Move field (top-level → nested) | MAJOR | Path changes |
| Split a schema into two | MAJOR | Type identity changes |
| Merge two schemas | MAJOR | Type identity changes |

### 2.2 Reading the Table

The bump is determined by the **consumer's view**, not the producer's. Ask:

> "If a consumer built against the old schema encounters data produced under the new schema, will it fail?"

If yes → MAJOR. If the consumer might miss new data but won't crash → MINOR. If nothing changes for the consumer → PATCH.

---

## 3. Schema Identity

A schema's identity is the combination of:

- Its **name** (e.g., `Signal`, `Evidence`, `Provenance`)
- Its **version** (`MAJOR.MINOR.PATCH`)
- Its **owner document** (always [04_data_schema.md](04_data_schema.md) for core schemas)

Renaming a schema is a MAJOR break. Re-homing a schema to a different owner document is also MAJOR (consumers reference the URL).

---

## 4. Backward Compatibility Rules

### 4.1 Adding a Field Safely

When adding a field, ensure:

1. The field is **optional** (`?Type`).
2. Default value (if required at the application level) is documented.
3. The new field has no semantic interaction with existing fields.
4. The new field does not introduce a new invariant (that would be MAJOR anyway).

Example of a safe MINOR addition:

```yaml
# Old (1.0):
Signal := {
  id, entity_ref, type, claim, evidence, ...
}

# New (1.1):
Signal := {
  id, entity_ref, type, claim, evidence, ...,
  metadata?: Metadata  # NEW, optional
}
```

### 4.2 Removing a Field Safely

Removing a field is **never safe** for an existing consumer. It is always MAJOR. Even if the field is "unused," consumers may have code paths that reference it.

The migration window ([SPEC_VERSION §5](SPEC_VERSION.md)) exists exactly so that consumers have time to remove their references.

### 4.3 Changing a Field's Meaning

Renaming or repurposing a field is **always MAJOR**. There is no compatibility story. Treat it as remove + add, with a deprecation alias for the old name during the window.

---

## 5. The Deprecation Lifecycle

A field or value can be **deprecated** before being removed.

```
Active ─────────────────────────────────────────────►
   │
   │ mark deprecated
   ▼
Deprecated (still in schema, emits warning if read/written)
   │
   │ removal target SPEC_VERSION reached
   ▼
Removed (schema MAJOR bump; migration required)
```

### 5.1 Marking Deprecated

To deprecate a field:

1. Add a `> DEPRECATED: use X instead. Removed in SPEC_VERSION Y.0` note in [04_data_schema.md](04_data_schema.md).
2. Add an entry to the migration log ([09 §11](09_development_roadmap.md)).
3. Emit a runtime warning if the field is read or written.
4. Update consumers to use the replacement.
5. Wait at least one MINOR release cycle.
6. Remove in a subsequent MAJOR bump.

### 5.2 Removal Window

| Change | Minimum wait before removal |
|---|---|
| Optional field | 1 MINOR release (≥ 30 days) |
| Required field | 1 MAJOR release cycle (≥ 180 days) |
| Enum value | 1 MINOR release + announcement |

---

## 6. Migration Patterns

When a schema MAJOR bumps, the migration is implemented as a **shim**. There are three patterns.

### 6.1 Add-Only Pattern (Field Addition)

Easiest. New field is optional, so old data is valid as-is. Old consumers ignore the field. No shim needed.

### 6.2 Translation Pattern (Field Rename)

When a field is renamed `old_name` → `new_name`:

```python
# migrations/v1_to_v2/shim.py
def upgrade_v1_to_v2(record: dict) -> dict:
    if "old_name" in record:
        record["new_name"] = record.pop("old_name")
    return record

def downgrade_v2_to_v1(record: dict) -> dict:
    if "new_name" in record:
        record["old_name"] = record.pop("new_name")
    return record
```

The shim is invoked:
- On read, when reading old data into new schema.
- On write, never (we always write new schema).

### 6.3 Structural Pattern (Nested, Split, Merge)

When the schema's structure changes, the shim is more complex. A small example:

```python
# Before: nested
record = {"address": {"city": "SF", "zip": "94105"}}

# After: flat
record = {"city": "SF", "zip": "94105"}

# Upgrade shim
def upgrade(record):
    addr = record.pop("address", {})
    record.update(addr)
    return record
```

Structural changes are inherently MAJOR and require careful shim tests.

---

## 7. Compatibility Testing

Every schema change MUST include compatibility tests in `migrations/<v>/test_shim.py`:

1. **Round-trip**: `downgrade(upgrade(x)) == x` for all x in old format.
2. **Forward-only**: New data validates as old format after `downgrade()`.
3. **Old-only**: Old data validates as new format after `upgrade()`.
4. **Lossless**: No data is silently dropped.

If a round-trip is lossy, the migration is **incomplete** and the change must be redesigned.

---

## 8. Schema Registry Pattern

Schemas are stored in a registry (per [08 §3](08_architecture.md)):

```
schemas/
├── signal/
│   ├── v1.0.0.yaml
│   ├── v1.1.0.yaml
│   └── v2.0.0.yaml
├── evidence/
│   └── ...
```

Each version file is immutable once published. Reads specify a version; writes always use the current version. During the migration window, both versions are readable.

---

## 9. Required Invariants on Schema Changes

Some invariants ([INVARIANTS.md](INVARIANTS.md)) apply specifically to schema evolution:

| Invariant | Rule |
|---|---|
| INV-2 | Signal ID never changes regardless of schema version |
| INV-7 | Schema authority cannot be duplicated |
| INV-9 | cycle_id format is ULID regardless of schema version |
| INV-10 | Times are ISO8601 UTC regardless of schema version |
| (NEW) INV-13 | Schema fields cannot be repurposed without going through MAJOR + migration |

---

## 10. Bumping a Schema Version

To bump a schema:

1. Identify the change type per §2.
2. For MAJOR: write an RFC (per [GOVERNANCE.md](GOVERNANCE.md)).
3. For MINOR: an ADR is sufficient.
4. For PATCH: no formal proposal needed; just a commit.
5. Update the schema definition in [04_data_schema.md](04_data_schema.md).
6. Update [04 §13 schema versioning table](04_data_schema.md).
7. If MAJOR: write migration code in `migrations/`.
8. Update [GLOSSARY.md](GLOSSARY.md) if field names change.
9. Add ADR or RFC reference to the schema header.

---

## 11. Versioning of This Document

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-07-16 | Initial schema evolution policy |

Changes to the bump-type table (§2) require an RFC. Adding new patterns (§6) is MAJOR. Clarifications are PATCH.