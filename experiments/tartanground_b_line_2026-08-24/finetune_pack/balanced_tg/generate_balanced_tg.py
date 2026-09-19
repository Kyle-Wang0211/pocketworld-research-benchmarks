#!/usr/bin/env python3
"""Generate deterministic meta-balanced DiffMVS datasets without touching sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence
from urllib.parse import quote


@dataclass(frozen=True)
class Meta:
    domain: str
    scan: str
    ref: int
    sources: tuple[int, ...]
    source_line: str

    @property
    def identity(self) -> tuple[str, str, int]:
        return self.domain, self.scan, self.ref


@dataclass(frozen=True)
class Plan:
    epochs: tuple[dict[str, tuple[Meta, ...]], ...]
    calibration: dict[str, tuple[Meta, ...]]


@dataclass(frozen=True)
class Config:
    mvg_root: Path
    mvg_list: Path
    mvg_val: Path
    tg_root: Path
    tg_list: Path
    out_root: Path
    seed: int = 20_260_825
    trainviews: int = 9
    epochs: int = 10
    per_domain: int = 1_774
    calib_per_domain: int = 400
    expected_mvg_scans: int = 494
    expected_tg_scans: int = 23
    expected_val_metas: int = 914


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _digest_named_files(root: Path, paths: Sequence[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: str(item.relative_to(root))):
        relative = str(path.relative_to(root))
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(bytes.fromhex(_sha256_file(path)))
    return digest.hexdigest()


def _read_required_line(stream, description: str) -> str:
    line = stream.readline()
    if line == "":
        raise ValueError(f"truncated pair.txt while reading {description}")
    return line.rstrip("\r\n")


def parse_scan_metas(root: Path, scan: str, domain: str, nviews: int) -> list[Meta]:
    """Mirror datasets/blend.py::build_list eligibility and source parsing."""
    pair_path = root / scan / "cams" / "pair.txt"
    with pair_path.open(encoding="utf-8") as stream:
        count = int(_read_required_line(stream, "viewpoint count"))
        metas: list[Meta] = []
        for index in range(count):
            ref = int(_read_required_line(stream, f"reference {index}"))
            source_line = _read_required_line(stream, f"sources for reference {ref}")
            tokens = source_line.split()
            sources = tuple(int(value) for value in tokens[1::2])
            if len(sources) < nviews - 1:
                continue
            metas.append(Meta(domain, scan, ref, sources, source_line))
    return metas


def _read_list(path: Path) -> list[str]:
    scans = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not scans:
        raise ValueError(f"empty scan list: {path}")
    if len(scans) != len(set(scans)):
        raise ValueError(f"duplicate scan in list: {path}")
    return scans


def _collect_metas(root: Path, scans: Iterable[str], domain: str, nviews: int) -> list[Meta]:
    metas: list[Meta] = []
    for scan in scans:
        metas.extend(parse_scan_metas(root, scan, domain, nviews))
    identities = [meta.identity for meta in metas]
    if len(identities) != len(set(identities)):
        raise ValueError(f"duplicate eligible meta identity in {domain} source")
    return metas


def plan_datasets(
    mvg_metas: Sequence[Meta],
    tg_metas: Sequence[Meta],
    *,
    seed: int,
    epochs: int,
    per_domain: int,
    calib_per_domain: int,
) -> Plan:
    if epochs <= 0 or per_domain <= 0:
        raise ValueError("epochs and per-domain must be positive")
    if not 0 < calib_per_domain <= per_domain:
        raise ValueError("calib-per-domain must be in [1, per-domain]")
    wanted_mvg = epochs * per_domain
    if len(mvg_metas) < wanted_mvg:
        raise ValueError(f"MVG has {len(mvg_metas)} eligible metas; need at least {wanted_mvg}")
    if len(tg_metas) != per_domain:
        raise ValueError(f"TG must have exactly {per_domain} eligible metas; found {len(tg_metas)}")

    shuffled_mvg = list(mvg_metas)
    random.Random(seed).shuffle(shuffled_mvg)
    selected_mvg = shuffled_mvg[:wanted_mvg]

    shuffled_tg = list(tg_metas)
    random.Random(seed ^ 0x5447_4D45_5441).shuffle(shuffled_tg)
    epochs_out: list[dict[str, tuple[Meta, ...]]] = []
    for index in range(epochs):
        start = index * per_domain
        epochs_out.append(
            {
                "mvg": tuple(selected_mvg[start : start + per_domain]),
                "tg": tuple(shuffled_tg),
            }
        )

    calibration_rng = random.Random(seed ^ 0x4341_4C49_4252)
    calibration = {
        "mvg": tuple(calibration_rng.sample(list(epochs_out[0]["mvg"]), calib_per_domain)),
        "tg": tuple(calibration_rng.sample(list(epochs_out[0]["tg"]), calib_per_domain)),
    }
    return Plan(tuple(epochs_out), calibration)


def _virtual_scan(domain: str, source_scan: str) -> str:
    return f"{domain}__{quote(source_scan, safe='._-')}"


def _symlink(source: Path, destination: Path, *, directory: bool = False) -> None:
    source_exists = source.is_dir() if directory else source.is_file()
    if not source_exists:
        kind = "directory" if directory else "file"
        raise FileNotFoundError(f"missing source {kind}: {source}")
    destination.symlink_to(source.resolve(), target_is_directory=directory)


def _group_for_loader(metas: Sequence[Meta]) -> OrderedDict[tuple[str, str], list[Meta]]:
    groups: OrderedDict[tuple[str, str], list[Meta]] = OrderedDict()
    for meta in metas:
        groups.setdefault((meta.domain, meta.scan), []).append(meta)
    return groups


def _manifest_item(meta: Meta, virtual_scan: str) -> dict[str, object]:
    return {
        "domain": meta.domain,
        "source_scan": meta.scan,
        "virtual_scan": virtual_scan,
        "ref": meta.ref,
        "sources": list(meta.sources),
    }


def _selection_digest(items: Sequence[dict[str, object]]) -> str:
    canonical = json.dumps(items, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def _build_dataset(
    directory: Path,
    selected: dict[str, Sequence[Meta]],
    *,
    source_roots: dict[str, Path],
    val_scans: Sequence[str],
    mvg_root: Path,
    seed: int,
    trainviews: int,
    label: str,
    val_metas: Sequence[Meta],
    source_identity: dict[str, str],
) -> None:
    root = directory / "root"
    root.mkdir(parents=True)
    combined = [*selected["mvg"], *selected["tg"]]
    groups = _group_for_loader(combined)
    train_scans: list[str] = []
    loader_items: list[dict[str, object]] = []

    for (domain, source_scan), metas in groups.items():
        virtual_scan = _virtual_scan(domain, source_scan)
        train_scans.append(virtual_scan)
        source_scan_root = source_roots[domain] / source_scan
        virtual_root = root / virtual_scan
        virtual_root.mkdir()
        _symlink(source_scan_root / "blended_images", virtual_root / "blended_images", directory=True)
        _symlink(source_scan_root / "rendered_depth_maps", virtual_root / "rendered_depth_maps", directory=True)
        cams = virtual_root / "cams"
        cams.mkdir()
        with (cams / "pair.txt").open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(f"{len(metas)}\n")
            for meta in metas:
                stream.write(f"{meta.ref}\n{meta.source_line}\n")
                loader_items.append(_manifest_item(meta, virtual_scan))
        camera_ids = sorted({camera for meta in metas for camera in (meta.ref, *meta.sources)})
        for camera_id in camera_ids:
            filename = f"{camera_id:08d}_cam.txt"
            _symlink(source_scan_root / "cams" / filename, cams / filename)

    (directory / "train.txt").write_text(
        "".join(f"{scan}\n" for scan in train_scans), encoding="utf-8", newline="\n"
    )

    virtual_val_scans: list[str] = []
    for source_scan in val_scans:
        virtual_scan = _virtual_scan("val", source_scan)
        virtual_val_scans.append(virtual_scan)
        _symlink(mvg_root / source_scan, root / virtual_scan, directory=True)
    (directory / "val.txt").write_text(
        "".join(f"{scan}\n" for scan in virtual_val_scans), encoding="utf-8", newline="\n"
    )

    counts = {
        "mvg": len(selected["mvg"]),
        "tg": len(selected["tg"]),
        "total": len(combined),
    }
    artifact_paths = [directory / "train.txt", directory / "val.txt"]
    artifact_paths.extend(sorted(root.glob("*/cams/pair.txt")))
    artifact_sha256 = {
        str(path.relative_to(directory)): _sha256_file(path)
        for path in artifact_paths
    }
    val_loader_metas = [
        _manifest_item(meta, _virtual_scan("val", meta.scan))
        for meta in val_metas
    ]
    manifest = {
        "schema_version": 1,
        "dataset": label,
        "seed": seed,
        "trainviews": trainviews,
        "counts": counts,
        "loader_metas": loader_items,
        "selection_sha256": _selection_digest(loader_items),
        "val_loader_metas": val_loader_metas,
        "val_selection_sha256": _selection_digest(val_loader_metas),
        "artifact_sha256": artifact_sha256,
        "source_identity": source_identity,
        "generator_sha256": _sha256_file(Path(__file__)),
        "val_scans": [
            {"source_scan": scan, "virtual_scan": virtual}
            for scan, virtual in zip(val_scans, virtual_val_scans)
        ],
    }
    (directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )


def _assert_output_is_separate(config: Config) -> None:
    output = config.out_root.resolve()
    for source in (config.mvg_root.resolve(), config.tg_root.resolve()):
        if output == source or source in output.parents or output in source.parents:
            raise ValueError(f"output root and source root must be separate: {output}, {source}")
    if config.out_root.exists() and any(config.out_root.iterdir()):
        raise FileExistsError(f"output root is not empty: {config.out_root}")


def generate(config: Config) -> None:
    _assert_output_is_separate(config)
    mvg_scans = _read_list(config.mvg_list)
    tg_scans = _read_list(config.tg_list)
    val_scans = _read_list(config.mvg_val)
    if config.mvg_root.resolve() == config.tg_root.resolve():
        raise ValueError("MVG and TG roots must be independent")
    if len({config.mvg_list.resolve(), config.mvg_val.resolve(), config.tg_list.resolve()}) != 3:
        raise ValueError("MVG train, MVG val, and TG lists must be independent")
    if len(mvg_scans) != config.expected_mvg_scans:
        raise ValueError(
            f"MVG train list must contain {config.expected_mvg_scans} scans; found {len(mvg_scans)}"
        )
    if len(tg_scans) != config.expected_tg_scans:
        raise ValueError(f"TG list must contain {config.expected_tg_scans} scans; found {len(tg_scans)}")
    if len(val_scans) != 7:
        raise ValueError(f"MVG validation list must contain the official 7 scans; found {len(val_scans)}")
    overlap = sorted(set(mvg_scans) & set(val_scans))
    if overlap:
        raise ValueError(f"MVG train/val scan overlap: {overlap}")

    mvg_metas = _collect_metas(config.mvg_root, mvg_scans, "mvg", config.trainviews)
    tg_metas = _collect_metas(config.tg_root, tg_scans, "tg", config.trainviews)
    val_metas = _collect_metas(config.mvg_root, val_scans, "val", config.trainviews)
    if len(val_metas) != config.expected_val_metas:
        raise ValueError(
            f"MVG validation must contain {config.expected_val_metas} eligible metas; found {len(val_metas)}"
        )
    source_identity = {
        "mvg_train_list_sha256": _sha256_file(config.mvg_list),
        "mvg_val_list_sha256": _sha256_file(config.mvg_val),
        "tg_list_sha256": _sha256_file(config.tg_list),
        "mvg_pair_files_sha256": _digest_named_files(
            config.mvg_root,
            [config.mvg_root / scan / "cams" / "pair.txt" for scan in [*mvg_scans, *val_scans]],
        ),
        "tg_pair_files_sha256": _digest_named_files(
            config.tg_root,
            [config.tg_root / scan / "cams" / "pair.txt" for scan in tg_scans],
        ),
    }
    plan = plan_datasets(
        mvg_metas,
        tg_metas,
        seed=config.seed,
        epochs=config.epochs,
        per_domain=config.per_domain,
        calib_per_domain=config.calib_per_domain,
    )
    config.out_root.mkdir(parents=True, exist_ok=True)
    source_roots = {"mvg": config.mvg_root, "tg": config.tg_root}
    for index, epoch in enumerate(plan.epochs, start=1):
        _build_dataset(
            config.out_root / f"epoch_{index:02d}",
            epoch,
            source_roots=source_roots,
            val_scans=val_scans,
            mvg_root=config.mvg_root,
            seed=config.seed,
            trainviews=config.trainviews,
            label=f"epoch_{index:02d}",
            val_metas=val_metas,
            source_identity=source_identity,
        )
    _build_dataset(
        config.out_root / "calibration",
        plan.calibration,
        source_roots=source_roots,
        val_scans=val_scans,
        mvg_root=config.mvg_root,
        seed=config.seed,
        trainviews=config.trainviews,
        label="calibration",
        val_metas=val_metas,
        source_identity=source_identity,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mvg-root", "--mvg_root", type=Path, required=True)
    parser.add_argument("--mvg-list", "--mvg_list", type=Path, required=True)
    parser.add_argument("--mvg-val", "--mvg_val", type=Path, required=True)
    parser.add_argument("--tg-root", "--tg_root", type=Path, required=True)
    parser.add_argument("--tg-list", "--tg_list", type=Path, required=True)
    parser.add_argument("--out-root", "--out_root", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20_260_825)
    parser.add_argument("--trainviews", type=int, default=9)
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--per-domain", "--per_domain", type=int, default=1_774)
    parser.add_argument("--calib-per-domain", "--calib_per_domain", type=int, default=400)
    return parser


def main() -> int:
    args = _parser().parse_args()
    config = Config(**vars(args))
    generate(config)
    print(
        f"generated {config.epochs} epochs x {config.per_domain * 2} metas and "
        f"calibration {config.calib_per_domain * 2} metas at {config.out_root}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
