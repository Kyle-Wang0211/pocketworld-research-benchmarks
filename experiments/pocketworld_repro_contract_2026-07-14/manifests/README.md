# Pre-copy source manifests

These canonical UTF-8 JSON files are the authoritative per-file identity for the
static cap50 trees before any payload is copied or DVC-added.

| Manifest | Source-relative root | Files | Bytes | Canonical JSON SHA-256 |
|---|---|---:|---:|---|
| `cap50-raw-selected-115-source-v1.json` | `cap50_frames/photos_highres/` | 230 (115 JPEG + 115 JSON) | 205162291 | `4288a756f80a49a12f8da520b564a3a4a856ac4949540b2ab50bebb671f6a0ad` |
| `cap50-work-png-115-source-v1.json` | `cap50_full_build/images_full/` | 115 PNG | 96336651 | `ca9ed3bafdc2a479769b553268a2eb8e8ee322d238b88997ffc428899d4d5ad4` |

The JSON SHA-256 is computed over the exact newline-terminated canonical bytes
committed here. Each asset record is sorted by POSIX-relative path and contains
its bytes, complete SHA-256, deterministic role, and the four independent
license/platform/evidence/lineage axes.

Collection-level producer, consumer, inclusion reason, and source-root mapping
are inherited from
`openspec/changes/freeze-pocketworld-research-contract/evidence/pre-copy-evidence-inventory.json`.
The older aggregate tree digests remain audit observations, but their original
normalization algorithm was not recorded; they are not the authoritative input
identity. These per-file manifests were independently reconciled against a
separate 345-row streaming-hash TSV before commit.

Generation and verification used the Task 1 verifier through commit
`135ed7bf1ba3b97433bfd7029ba1b96e6dc1e1f3`. No capture or experiment payload
was copied while producing these metadata files.
