import json

import test_launch


class PluginSnapshotTests(test_launch.LaunchTests):
    def configure_plugin(self, method, root):
        self.marker = root / "executed"
        (method.parent / "helper.py").write_text("value = 0\n", encoding="utf-8")
        (method.parent / "resource.txt").write_text("0", encoding="utf-8")
        method.write_text(
            "from helper import value\nfrom pathlib import Path\n"
            "def fit_predict(X, y, test, **kw):\n"
            f"    Path({str(self.marker)!r}).touch()\n"
            "    return {'predictions': [value + int(Path('resource.txt').read_text())] * len(test)}\n",
            encoding="utf-8")

    def check_frozen_plugin(self, cli, run, method):
        for filename in ("helper.py", "resource.txt"):
            path = method.parent / filename
            original = path.read_bytes()
            path.write_bytes(original + b" ")
            cli("run", expect=2)
            self.assertFalse(self.marker.exists())
            path.write_bytes(original)
        path = run / "freeze.json"
        original = path.read_bytes()
        for field in ("plugins", "environment"):
            frozen = json.loads(original)
            frozen[field] = {}
            path.write_text(json.dumps(frozen), encoding="utf-8")
            cli("run", expect=2)
            self.assertFalse(self.marker.exists())
            path.write_bytes(original)

    def after_package(self, cli, run):
        self.assertTrue(self.marker.exists())
        packet = json.loads((run / "review-package.json").read_bytes())["packet"]
        self.assertTrue(packet["environment_sha256"].startswith("sha256:"))
        self.assertTrue(packet["rows"][0]["plugin_sha256"].startswith("sha256:"))
        self.assertNotIn("resource.txt", json.dumps(packet))
