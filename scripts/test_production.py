import argparse
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from load_check import local_origin
from local_ops import SERVICES, assess, initialize, verify_manifest


class ProductionTests(unittest.TestCase):
    def test_monitor_reports_failure_disk_and_stale_backup(self):
        healthy = [{"Service": name, "State": "running", "Health": "healthy"} for name in SERVICES]
        self.assertEqual(assess(healthy, .5, {"completed_at": 100}, 101), [])
        self.assertIn("backup_missing_or_older_than_26h", assess(healthy, .5, None, 101))
        healthy[0]["Health"] = "unhealthy"
        findings = assess(healthy, .1, {"completed_at": 1}, 100000)
        self.assertEqual(len(findings), 3)
        self.assertIn("disk_free_below_20_percent", findings)

    def test_backup_init_never_overwrites_existing_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            marker = Path(temp) / "password"
            marker.write_text("existing")
            with self.assertRaises(FileExistsError):
                initialize(temp)
            self.assertEqual(marker.read_text(), "existing")

    def test_manifest_rejects_path_injection_and_tampering(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            (path / "manifest.json").write_text('{"../outside": "x"}')
            with self.assertRaises(RuntimeError):
                verify_manifest(path)
            (path / "database.dump").write_bytes(b"tampered")
            (path / "manifest.json").write_text('{"database.dump":"bad", "media.tar":"bad"}')
            with self.assertRaises(RuntimeError):
                verify_manifest(path)

    def test_load_target_rejects_external_credentials_and_path(self):
        for value in ["https://example.com", "http://8.8.8.8", "http://localhost/path",
                      "http://user:pass@127.0.0.1", "http://localhost.evil.test"]:
            with self.assertRaises(argparse.ArgumentTypeError):
                local_origin(value)
        self.assertEqual(local_origin("http://127.0.0.1:8083"), "http://127.0.0.1:8083")

    def test_production_secrets_independent_and_never_overwritten(self):
        source = Path(__file__).with_name("init_production_env.py")
        spec = importlib.util.spec_from_file_location("prod_init", source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(module, "__file__", str(root / "scripts" / source.name)):
                module.main()
                values = dict(line.split("=", 1) for line in
                              (root / ".env.production").read_text().splitlines())
                secrets = [v for k, v in values.items() if "PASSWORD" in k or k == "APP_SECRET"]
                self.assertEqual(len(set(secrets)), 5)
                self.assertTrue(all(len(value) == 64 for value in secrets))
                with self.assertRaises(FileExistsError):
                    module.main()
                self.assertEqual(values, dict(line.split("=", 1) for line in
                                 (root / ".env.production").read_text().splitlines()))


if __name__ == "__main__":
    unittest.main()
