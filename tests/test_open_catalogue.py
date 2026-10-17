import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import main


class DefaultApplicationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "Catalogue café #1 ; notes.csv"
        self.path.touch()

    async def test_windows_uses_default_file_association(self):
        with patch.object(main.sys, "platform", "win32"), patch.object(main.os, "startfile", create=True) as start:
            await main.open_in_default_app(self.path)
        start.assert_called_once_with(str(self.path.resolve()))

    async def test_windows_missing_association_is_reported(self):
        error = OSError("No application is associated with this file")
        with patch.object(main.sys, "platform", "win32"), patch.object(main.os, "startfile", side_effect=error, create=True):
            with self.assertRaises(OSError):
                await main.open_in_default_app(self.path)

    async def test_mac_and_linux_pass_the_exact_path_as_a_single_argument(self):
        for platform, opener in (("darwin", "/usr/bin/open"), ("linux", "xdg-open")):
            with self.subTest(platform=platform):
                process = SimpleNamespace(wait=AsyncMock(return_value=0))
                with patch.object(main.sys, "platform", platform), patch.object(
                    main.asyncio, "create_subprocess_exec", new=AsyncMock(return_value=process)
                ) as launch:
                    await main.open_in_default_app(self.path)
                launch.assert_awaited_once_with(
                    opener, str(self.path.resolve()),
                    stdin=asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )

    async def test_opener_failure_is_reported(self):
        process = SimpleNamespace(wait=AsyncMock(return_value=3))
        with patch.object(main.sys, "platform", "linux"), patch.object(
            main.asyncio, "create_subprocess_exec", new=AsyncMock(return_value=process)
        ):
            with self.assertRaisesRegex(OSError, "status 3"):
                await main.open_in_default_app(self.path)

    async def test_missing_opener_is_reported(self):
        with patch.object(main.sys, "platform", "linux"), patch.object(
            main.asyncio, "create_subprocess_exec", new=AsyncMock(side_effect=FileNotFoundError("xdg-open"))
        ):
            with self.assertRaises(FileNotFoundError):
                await main.open_in_default_app(self.path)

    async def test_foreground_linux_association_is_not_killed_or_reported_as_failure(self):
        process = SimpleNamespace(wait=AsyncMock(side_effect=TimeoutError), kill=Mock(), terminate=Mock())
        with patch.object(main.sys, "platform", "linux"), patch.object(
            main.asyncio, "create_subprocess_exec", new=AsyncMock(return_value=process)
        ):
            await main.open_in_default_app(self.path)
        process.kill.assert_not_called()
        process.terminate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
