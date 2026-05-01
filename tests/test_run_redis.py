"""Tests for Redis auto-start behavior in run.py."""

import io
import unittest
from unittest.mock import MagicMock, patch

import run


class RedisAutoStartTests(unittest.TestCase):
    def test_auto_start_redis_uses_wsl_root_service(self) -> None:
        with (
            patch("run.shutil.which") as mock_which,
            patch("run.subprocess.run") as mock_run,
            patch("run.time.sleep") as mock_sleep,
        ):
            def which_side_effect(name: str):
                if name in ("wsl.exe", "wsl"):
                    return r"C:\\Windows\\System32\\wsl.exe"
                return None

            mock_which.side_effect = which_side_effect
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            self.assertTrue(run.auto_start_redis())
            mock_run.assert_called_once_with(
                [
                    r"C:\\Windows\\System32\\wsl.exe",
                    "-u",
                    "root",
                    "--",
                    "sh",
                    "-lc",
                    "service redis-server start",
                ],
                capture_output=True,
                timeout=15,
                text=True,
            )
            mock_sleep.assert_called_once()

    def test_auto_start_redis_falls_back_to_windows_binary(self) -> None:
        with (
            patch("run.shutil.which") as mock_which,
            patch("run.subprocess.Popen") as mock_popen,
            patch("run.time.sleep") as mock_sleep,
        ):
            def which_side_effect(name: str):
                if name in ("wsl.exe", "wsl"):
                    return None
                if name in ("redis-server.exe", "redis-server"):
                    return r"C:\\Redis\\redis-server.exe"
                return None

            mock_which.side_effect = which_side_effect
            mock_popen.return_value = MagicMock()

            self.assertTrue(run.auto_start_redis())
            mock_popen.assert_called_once()
            self.assertEqual(
                mock_popen.call_args.args[0],
                [r"C:\\Redis\\redis-server.exe"],
            )
            mock_sleep.assert_called_once()

    def test_check_env_accepts_groq_key_without_openai_key(self) -> None:
        with (
            patch("run.Path.exists", return_value=True),
            patch.dict(
                "run.os.environ",
                {"REDIS_URL": "redis://localhost:6379/0", "GROQ_API_KEY": "gsk-test"},
                clear=True,
            ),
            patch("sys.stdout", new_callable=io.StringIO) as stdout,
        ):
            self.assertTrue(run.check_env())
            self.assertNotIn("Missing env vars", stdout.getvalue())

    def test_check_env_guides_legacy_openai_key_users(self) -> None:
        with (
            patch("run.Path.exists", return_value=True),
            patch.dict(
                "run.os.environ",
                {"REDIS_URL": "redis://localhost:6379/0", "OPENAI_API_KEY": "sk-legacy"},
                clear=True,
            ),
            patch("sys.stdout", new_callable=io.StringIO) as stdout,
        ):
            self.assertTrue(run.check_env())
            output = stdout.getvalue()
            self.assertIn("GROQ_API_KEY", output)
            self.assertIn("OPENAI_API_KEY is a legacy variable", output)


if __name__ == "__main__":
    unittest.main()
