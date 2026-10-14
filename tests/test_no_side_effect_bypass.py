"""Bypass guard: every call to a platform write method is accounted for.

The first loop's publish path is mediated at one seam
(BaseSocialClient.publish → services/publish_authority.py). This test
reads the source, finds every call to a platform write method, and fails
on any call site not listed below. A new direct call — the classic way a
governed system quietly grows an ungoverned path — breaks the build until
it is either routed through a gate or consciously listed here with its
reason.
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

WRITE_METHODS = {
    "create_tweet", "_publish_impl", "send_dm", "like", "unlike",
    "repost", "retweet", "follow", "follow_user", "upload_media",
}

# The transport module defines the raw writes; calls inside it are the
# transport talking to the platform SDK, not a new path.
TRANSPORT = {"services/x_client.py"}

# (file, method, enclosing function) -> why it is allowed.
ALLOWED = {
    ("services/social_base.py", "_publish_impl", "publish"):
        "the seam itself; reached only after publish_authority grants",
    ("services/multiplexer.py", "create_tweet", "_publish_impl"):
        "X adapter implementation; only reachable through the seam",
    ("services/multiplexer.py", "upload_media", "_publish_impl"):
        "media upload inside the gated X adapter",
    # Not part of the first loop; held by LIVE=false today and gated
    # through the Kernel by DALEOBANKS #73 when adopted.
    ("runner.py", "like", "search_and_engage_job"): "UNMEDIATED (not first loop) — #73",
    ("runner.py", "repost", "search_and_engage_job"): "UNMEDIATED (not first loop) — #73",
    ("runner.py", "send_dm", "value_dm_job"): "UNMEDIATED (not first loop) — #73",
}


def _call_sites():
    sites = set()
    for path in ROOT.rglob("*.py"):
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith(("tests/", "node_modules/", "client/", ".")) or rel in TRANSPORT:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        stack = []

        def visit(node):
            is_func = isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            if is_func:
                stack.append(node.name)
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in WRITE_METHODS):
                sites.add((rel, node.func.attr, stack[-1] if stack else "<module>"))
            for child in ast.iter_child_nodes(node):
                visit(child)
            if is_func:
                stack.pop()

        visit(tree)
    return sites


def test_every_platform_write_call_site_is_accounted_for():
    unexpected = _call_sites() - set(ALLOWED)
    assert not unexpected, (
        "platform write called outside the governed seam; route it through "
        f"a gate or list it in ALLOWED with its reason: {sorted(unexpected)}"
    )


def test_the_allowlist_has_no_stale_entries():
    stale = set(ALLOWED) - _call_sites()
    assert not stale, f"allowlisted call sites no longer exist; remove them: {sorted(stale)}"


def test_publish_seam_consults_authority_before_the_platform():
    source = (ROOT / "services/social_base.py").read_text(encoding="utf-8")
    assert source.index("authorize_publish(") < source.index("self._publish_impl(")
