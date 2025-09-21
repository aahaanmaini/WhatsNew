from __future__ import annotations

from whatsnew.git.diffs import _score_hunk, _should_include_path


def test_should_ignore_vendor_paths():
    assert not _should_include_path("vendor/module/app.py")
    assert _should_include_path("src/app.py")


def test_score_prefers_function_definitions():
    hunk_feature = """@@ -1,0 +1,5 @@\n+def public_api():\n+    return True"""
    hunk_plain = """@@ -1,0 +1,3 @@\n+x = 1"""

    score_feature = _score_hunk("src/api/service.py", hunk_feature)
    score_plain = _score_hunk("src/api/service.py", hunk_plain)
    assert score_feature > score_plain
