import importlib.util
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "upgrade_env", Path(__file__).with_name("upgrade_env_stage02.py")
)
upgrade_env = importlib.util.module_from_spec(spec)
spec.loader.exec_module(upgrade_env)


class Stage02EnvironmentTests(unittest.TestCase):
    def test_appends_once_and_preserves_original_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            original = upgrade_env.ROOT
            upgrade_env.ROOT = Path(directory)
            try:
                target = upgrade_env.ROOT / ".env"
                old = "POSTGRES_PASSWORD=existing-secret\nPUBLIC_ORIGIN=http://localhost:3000\n"
                target.write_text(old, encoding="utf-8")
                upgrade_env.main()
                first = target.read_text(encoding="utf-8")
                self.assertTrue(first.startswith(old))
                values = dict(
                    line.split("=", 1) for line in first.splitlines() if "=" in line
                )
                self.assertEqual(len(values["MIGRATOR_PASSWORD"]), 64)
                self.assertEqual(len(values["RUNTIME_PASSWORD"]), 64)
                self.assertNotEqual(
                    values["MIGRATOR_PASSWORD"], values["RUNTIME_PASSWORD"]
                )
                upgrade_env.main()
                self.assertEqual(target.read_text(encoding="utf-8"), first)
            finally:
                upgrade_env.ROOT = original


if __name__ == "__main__":
    unittest.main()
