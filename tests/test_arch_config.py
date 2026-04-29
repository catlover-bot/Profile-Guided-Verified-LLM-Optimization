from __future__ import annotations

from pathlib import Path

from vallmopt.arch import load_architectures


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_architecture_yaml_can_be_loaded() -> None:
    architectures = load_architectures(REPO_ROOT / "configs" / "architectures.yaml")

    assert set(architectures) == {"snb-avx", "hsw-avx2", "skx-avx512", "icl-avx512"}
    assert architectures["hsw-avx2"].isa == "avx2"
    assert architectures["skx-avx512"].cflags_extra == ["-march=native"]
