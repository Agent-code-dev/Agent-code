# Agent Code 2.2.0 — Test Results

- `python -m compileall -q src tests`: passed.
- Focused tests (`test_advanced_features.py`, `test_doctor.py`, `test_model_protocols.py`): 31 passed.
- Runnable suite excluding two Skill Store modules that cannot import without `customtkinter`: **205 passed, 2 skipped**.
- Full unfiltered collection is blocked in this environment because `customtkinter` is not installed; `tests/test_skill_store_auth_flow.py` and `tests/test_skill_store_safety.py` fail during collection for that missing dependency.
- The wheel was built and its package metadata/version and import of the new project-analysis helper were verified.
- The standard source distribution was built with setuptools.
- GUI runtime, real provider API calls, PyPI publication, and GitHub Actions execution have not been performed in this environment.

Do not interpret this as complete cross-platform release certification. The CI workflow installs project dependencies and runs the full test suite on GitHub Actions after the release tag is pushed.
