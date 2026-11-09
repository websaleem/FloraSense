"""The dependency pins, and the one way they can silently go wrong.

These were unpinned until now, so each image rebuild resolved whatever was
current that day. Nothing caught it because an unpinned build still succeeds —
it just builds something different from last time.
"""

import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REQUIREMENTS = os.path.join(ROOT, "backend", "lambda", "requirements.txt")
DOCKERFILE = os.path.join(ROOT, "backend", "lambda", "Dockerfile")


def requirement_lines():
    with open(REQUIREMENTS) as f:
        return [ln.strip() for ln in f
                if ln.strip() and not ln.lstrip().startswith("#")]


def test_every_requirement_is_pinned():
    """No >=, no bare names.

    `torch>=2.0.0` reads like a pin and is not one: it accepts every future
    release, including the next major.
    """
    unpinned = [ln for ln in requirement_lines() if "==" not in ln]
    assert not unpinned, f"unpinned requirements: {unpinned}"


def test_pins_are_exact_versions():
    """`==` with a real version, not a wildcard or a range dressed up as one."""
    bad = [ln for ln in requirement_lines()
           if not re.match(r"^[A-Za-z0-9_.\-]+(\[[a-z,]+\])?==\d+(\.\d+)*$", ln)]
    assert not bad, f"not exact pins: {bad}"


@pytest.mark.parametrize("package", ["torch", "torchvision"])
def test_dockerfile_and_requirements_agree(package):
    """The pin exists in two places and both must say the same thing.

    The Dockerfile installs these first from the CPU-only index, because the
    default wheels carry over a gigabyte of CUDA libraries Lambda can never
    use. requirements.txt is then installed with the default index. If the two
    versions differ, that second install "corrects" the version from PyPI and
    pulls the CUDA build straight back in.

    It fails as a much bigger image and a slower cold start, not as an error,
    which is why it needs a test rather than care.
    """
    with open(REQUIREMENTS) as f:
        req = f.read()
    with open(DOCKERFILE) as f:
        dock = f.read()

    in_req = re.search(rf"^{package}==([0-9][0-9.]*)\s*$", req, re.M)
    assert in_req, f"{package} is not pinned in requirements.txt"

    # The Dockerfile's CPU-index install line.
    in_dock = re.search(rf"{package}==([0-9][0-9.]*)", dock)
    assert in_dock, f"{package} is not pinned in the Dockerfile"

    assert in_req.group(1) == in_dock.group(1), (
        f"{package} pinned to {in_req.group(1)} in requirements.txt but "
        f"{in_dock.group(1)} in the Dockerfile — the mismatch pulls the CUDA "
        f"build from PyPI"
    )


def test_cpu_index_is_still_used_for_torch():
    """If this line goes, the pins above stop protecting anything."""
    with open(DOCKERFILE) as f:
        dock = f.read()
    assert "download.pytorch.org/whl/cpu" in dock, (
        "the CPU-only index is gone from the Dockerfile; torch will come from "
        "PyPI with its CUDA payload"
    )
