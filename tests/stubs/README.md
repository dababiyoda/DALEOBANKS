# Offline test stubs

Minimal stand-ins for third-party packages (`dotenv`, `numpy`, `openai`,
`tenacity`) so the test suite can run in environments where the real
dependencies are not installed.

They are loaded as a **fallback only**: the root `conftest.py` appends this
directory to the end of `sys.path`, so a real installed package always wins.
These packages must never live at the repository root — there they would
shadow the real libraries for any process started from the root, including
the production app.
