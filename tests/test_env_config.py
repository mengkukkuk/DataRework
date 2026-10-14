import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import env_config
import envcrypt

KEYS = ("DB_HOST", "DB_NAME", "DB_PASSWORD")


class EnvConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.bundled_dir = root / "bundle"
        self.exe_dir = root / "exe"
        self.bundled_dir.mkdir()
        self.exe_dir.mkdir()
        self.key = envcrypt.Fernet.generate_key()
        env = {k: v for k, v in os.environ.items() if k not in KEYS}
        p = mock.patch.dict(os.environ, env, clear=True)
        p.start()
        self.addCleanup(p.stop)

    def _load(self):
        with mock.patch.object(env_config, "__file__", str(self.bundled_dir / "env_config.py")), \
             mock.patch.object(sys, "frozen", True, create=True), \
             mock.patch.object(sys, "executable", str(self.exe_dir / "app.exe")), \
             mock.patch.object(envcrypt, "ensure_key", return_value=self.key):
            env_config.load_env()

    def test_external_overrides_embedded_and_falls_back(self):
        (self.bundled_dir / ".env").write_text("DB_HOST=embedded\nDB_NAME=embdb\n")
        (self.exe_dir / ".env").write_text("DB_HOST=external\n")
        self._load()
        self.assertEqual(os.environ["DB_HOST"], "external")
        self.assertEqual(os.environ["DB_NAME"], "embdb")

    def test_os_env_beats_both(self):
        (self.bundled_dir / ".env").write_text("DB_HOST=embedded\n")
        (self.exe_dir / ".env").write_text("DB_HOST=external\n")
        os.environ["DB_HOST"] = "real"
        self._load()
        self.assertEqual(os.environ["DB_HOST"], "real")

    def test_missing_external_uses_embedded(self):
        (self.bundled_dir / ".env").write_text("DB_HOST=embedded\n")
        self._load()
        self.assertEqual(os.environ["DB_HOST"], "embedded")

    def test_encrypted_password_is_decrypted(self):
        token = envcrypt.encrypt("s3cret!", key=self.key)
        (self.bundled_dir / ".env").write_text("DB_PASSWORD=plain\n")
        (self.exe_dir / ".env").write_text(f"DB_PASSWORD={token}\n")
        self._load()
        self.assertEqual(os.environ["DB_PASSWORD"], "s3cret!")

    def test_plain_password_still_works(self):
        (self.bundled_dir / ".env").write_text("DB_PASSWORD=plain\n")
        self._load()
        self.assertEqual(os.environ["DB_PASSWORD"], "plain")

    def test_tampered_token_raises_without_leaking(self):
        (self.exe_dir / ".env").write_text("DB_PASSWORD=enc:not-a-token\n")
        with self.assertRaises(RuntimeError) as ctx:
            self._load()
        self.assertIn("DB_PASSWORD", str(ctx.exception))
        self.assertNotIn("not-a-token", str(ctx.exception))

    def test_not_frozen_reads_single_source_env(self):
        (self.bundled_dir / ".env").write_text("DB_HOST=source\n")
        with mock.patch.object(env_config, "__file__", str(self.bundled_dir / "env_config.py")), \
             mock.patch.object(sys, "frozen", False, create=True):
            env_config.load_env()
        self.assertEqual(os.environ["DB_HOST"], "source")


class EnvCryptTests(unittest.TestCase):
    def test_round_trip_and_passthrough(self):
        key = envcrypt.Fernet.generate_key()
        token = envcrypt.encrypt("pässword", key=key)
        self.assertTrue(token.startswith("enc:"))
        self.assertEqual(envcrypt.decrypt(token, key=key), "pässword")
        self.assertEqual(envcrypt.decrypt("plain", key=key), "plain")

    def test_wrong_key_fails(self):
        token = envcrypt.encrypt("x", key=envcrypt.Fernet.generate_key())
        with self.assertRaises(ValueError):
            envcrypt.decrypt(token, key=envcrypt.Fernet.generate_key())


if __name__ == "__main__":
    unittest.main()
