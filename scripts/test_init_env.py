import importlib.util
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "init_env", Path(__file__).with_name("init_env.py")
)
init_env = importlib.util.module_from_spec(spec)
spec.loader.exec_module(init_env)


class EnvironmentTests(unittest.TestCase):
    def test_unique_secrets_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            original = init_env.ROOT
            init_env.ROOT = Path(directory)
            try:
                (init_env.ROOT / ".env.example").write_text(
                    "APP_SECRET=GENERATE_ME\nPOSTGRES_PASSWORD=GENERATE_ME\n"
                    "REDIS_PASSWORD=GENERATE_ME\n",
                    encoding="utf-8",
                )
                init_env.main()
                content = (init_env.ROOT / ".env").read_text()
                values = [line.split("=", 1)[1] for line in content.splitlines()]
                self.assertEqual(len(set(values)), 3)
                self.assertTrue(all(len(value) == 64 for value in values))
                with self.assertRaises(SystemExit):
                    init_env.main()
                self.assertEqual((init_env.ROOT / ".env").read_text(), content)
            finally:
                init_env.ROOT = original


if __name__ == "__main__":
    unittest.main()
