# iOS development

This directory contains early architecture work and a desktop backend smoke test.
It is not an iOS application or a completed port. The existing Android implementation
and Python gameplay logic are unchanged.

## Layout

- `docs/architecture.md`: backend boundaries, proposed hosting, and feasibility gates.
- `docs/compatibility.md`: Android components and their proposed iOS replacements.
- `tests/smoke_backend.py`: real in-process backend verification using temporary,
  synthetic resources and a tiny authored response; no proprietary game data.
- `requirements-smoke.txt`: desktop test dependencies, not iOS frameworks.
- `.gitignore`: local environments and generated iOS build artifacts.

The standalone summoning prototype is documented in [docs/summoning.md](docs/summoning.md).
Run `prototype/summon_cli.py --demo` using the environment below for the terminal UI.
It calls the existing summon backend; it does not depend on Memorial's summon UI.
`prototype/summon_service.py` is the platform-independent facade and
`prototype/demo_data.py` supplies explicit placeholder metadata when real tables
are absent. `tests/test_summon_service.py` verifies transactions and persistence.

Native bridge code and an Xcode project are later milestones. Do not store IPAs, extracted clients, game assets,
signing identities, or executable dependencies in this source directory. Keep personal
inputs outside the repository; `.local/` is ignored for optional local experiments.

## Desktop smoke test

Python 3.10+ is required. From the repository root on Windows:

```powershell
python -m venv source/ios/.venv
source/ios/.venv/Scripts/python.exe -m pip install -r source/ios/requirements-smoke.txt
source/ios/.venv/Scripts/python.exe -B source/ios/tests/smoke_backend.py
```

On macOS/Linux, replace `Scripts/python.exe` with `bin/python`.
Run the script as its own process; it isolates backend environment settings and
installs a process-lifetime audit hook that rejects socket creation, DNS, bind,
and connect operations. No listener, Android SDK, IPA, or full data download is needed.

Exit 0 means the backend initialized, its pipeline registry validated, a local file
was served, a real encrypted request was decrypted/dispatched/re-encrypted, currency
operations behaved as expected, and a temporary save reloaded with the expected
balance. Exceptions return exit 1 with diagnostics. Temporary data is cleaned on exit.

The authored marker response verifies transport, not original game response content.
Empty master tables plus authored starter-unit/equipment identities exercise
minimal engine initialization; this
does not establish content completeness, playable battles, summon correctness,
fresh-process campaign restart, or iOS compatibility. No gameplay methods are mocked.

Fixtures are created below the ignored `source/ios/.local/` directory and removed
after each run. Keeping them on the checkout's drive avoids existing Windows
cross-drive diagnostic-path limitations. Personal saves are never opened.

