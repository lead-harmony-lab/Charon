# Charon: Versioning, Artifact Management & Testing Architecture

## 1. Overview

This document specifies Charon's code binding, version tracking, artifact isolation, and automated release pipeline. It guarantees that test runs, generated logs, and system outputs are deterministically tied to exact Git commits, global Semantic Versions, and individual file revisions.

---

## 2. Versioning Architecture

### Single Source of Truth

* **`charon/__version__.py`**: Contains system-level `__version__ = "X.Y.Z"`.
* **`../../pyproject.toml`**: Configured with `dynamic = ["version"]` via setuptools attribute resolution referencing `charon.__version__.__version__`.

### Runtime Resolution (`../../charon/core/version.py`)

At runtime, Charon dynamically inspects the environment via Git subprocess calls:

* **Commit SHA**: Short 7-character Git hash (`git rev-parse --short HEAD`).
* **Branch**: Current checked-out branch (`git rev-parse --abbrev-ref HEAD`).
* **Dirty Flag**: Boolean indicator tracking uncommitted changes (`git status --porcelain`).
* **Version String Format**: `vX.Y.Z-g<commit_sha> (dirty)`

### Dual-Version File Headers

To prevent AI code generation or localized module updates from triggering unintended project-wide major/minor version bumps, every Python module in `../../charon` maintains a dual-version header docstring:

