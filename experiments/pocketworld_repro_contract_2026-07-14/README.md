# PocketWorld reproducibility contract

This uv project builds and verifies deterministic manifests for local research
asset collections. It reads only the collection root named on the command line;
it does not contact devices, DVC, or research data services.

```text
uv run pocketworld-contract build ROOT --collection ID \
  --license-status LABEL \
  --platform-qualification LABEL \
  --evidence-role LABEL \
  [--lineage-contains-noncommercial] \
  --output FILE
uv run pocketworld-contract verify ROOT MANIFEST
uv run pocketworld-contract gate-verdict CONTRACT
```

Collection manifests use canonical UTF-8 JSON and list every regular file by
safe POSIX-relative path, byte count, SHA-256 digest, deterministic role, and
caller-supplied license status, platform qualification, evidence role, and
noncommercial-lineage flag. Symlinks are rejected.
