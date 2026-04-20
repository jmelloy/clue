import os
import stat
import subprocess
from pathlib import Path


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def test_resize_thumbnails_updates_when_thumbnail_newer(tmp_path: Path) -> None:
    repo_root = tmp_path
    scripts_dir = repo_root / "scripts"
    scripts_dir.mkdir(parents=True)

    source_script = Path(__file__).resolve().parents[2] / "scripts" / "resize_thumbnails.sh"
    (scripts_dir / "resize_thumbnails.sh").write_text(source_script.read_text())

    fake_bin = repo_root / "fake_bin"
    fake_bin.mkdir()
    _write_executable(
        fake_bin / "magick",
        """#!/usr/bin/env bash
set -euo pipefail
cp "$1" "${@: -1}"
""",
    )

    image_dir = repo_root / "frontend" / "public" / "images" / "cards"
    thumbs_dir = image_dir / "thumbnails"
    thumbs_dir.mkdir(parents=True)

    source_image = image_dir / "case.png"
    thumb_image = thumbs_dir / "case.png"
    source_image.write_bytes(b"new image bytes")
    thumb_image.write_bytes(b"old thumbnail bytes")

    os.utime(source_image, (1000, 1000))
    os.utime(thumb_image, (2000, 2000))

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"

    result = subprocess.run(
        ["bash", "scripts/resize_thumbnails.sh"],
        cwd=repo_root,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Updated thumbnail:" in result.stdout
    assert thumb_image.read_bytes() == source_image.read_bytes()
