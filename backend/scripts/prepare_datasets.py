from __future__ import annotations

import argparse
import shutil
from pathlib import Path


APPROVED_FILES = {
    "cpu.json",
    "memory.json",
    "motherboard.json",
    "video-card.json",
    "power-supply.json",
    "case.json",
    "cpu-cooler.json",
    "internal-hard-drive.json",
}


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def prepare_pc_part_dataset(source_dir: Path, target_dir: Path, files: list[str] | None = None) -> int:
    selected = files or sorted(APPROVED_FILES)
    unknown = sorted(set(selected) - APPROVED_FILES)
    if unknown:
        raise ValueError(f"unsupported pc-part-dataset file(s): {', '.join(unknown)}")
    target_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for filename in selected:
        source = source_dir / filename
        if not source.is_file():
            continue
        shutil.copy2(source, target_dir / filename)
        copied += 1
    return copied


def main() -> None:
    parser = argparse.ArgumentParser(description="Copy approved pc-part-dataset JSON files into backend imports.")
    parser.add_argument(
        "--source-dir",
        default=str(BACKEND_ROOT / "pc-part-dataset" / "data" / "json"),
        help="Directory containing pc-part-dataset data/json files.",
    )
    parser.add_argument(
        "--target-dir",
        default=str(BACKEND_ROOT / "data" / "imports" / "datasets" / "pc-part-dataset"),
        help="Backend import target directory.",
    )
    parser.add_argument("--file", action="append", dest="files", help="Approved file to copy. Repeatable.")
    args = parser.parse_args()
    copied = prepare_pc_part_dataset(Path(args.source_dir), Path(args.target_dir), args.files)
    print(f"copied_files={copied}")


if __name__ == "__main__":
    main()
