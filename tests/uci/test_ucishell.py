import paramiko
import unittest
from unittest.mock import patch

from uci.engine import UciShell, WindowsShellType


class SshShellMock:
    def __init__(*args, **kwargs):
        pass

    def close(self):
        return 42


class TestUciShell(unittest.TestCase):
    def test_no_hostname(self):
        uci_shell = UciShell()
        self.assertIsNone(uci_shell.get())

    @patch("spur.SshShell")
    def test_password_authentication(self, sshshell_mock):
        uci_shell = UciShell(hostname="test", username="user", password="pass")
        kwargs = sshshell_mock.call_args.kwargs
        self.assertEqual(kwargs["hostname"], "test")
        self.assertEqual(kwargs["username"], "user")
        self.assertEqual(kwargs["password"], "pass")
        self.assertTrue(isinstance(kwargs["missing_host_key"], paramiko.AutoAddPolicy))
        self.assertIsNone(kwargs.get("private_key_file"))
        self.assertIsNone(kwargs.get("shell_type"))
        self.assertIsNotNone(uci_shell.get())

    @patch("spur.SshShell")
    def test_private_key_authentication(self, sshshell_mock):
        uci_shell = UciShell(hostname="test", username="user", key_file="key")
        kwargs = sshshell_mock.call_args.kwargs
        self.assertEqual(kwargs["hostname"], "test")
        self.assertEqual(kwargs["username"], "user")
        self.assertIsNone(kwargs.get("password"))
        self.assertTrue(isinstance(kwargs["missing_host_key"], paramiko.AutoAddPolicy))
        self.assertEqual(kwargs["private_key_file"], "key")
        self.assertIsNone(kwargs.get("shell_type"))
        self.assertIsNotNone(uci_shell.get())

    @patch("spur.SshShell")
    def test_windows_shell(self, sshshell_mock):
        uci_shell = UciShell(hostname="test", username="user", password="pass", windows=True)
        kwargs = sshshell_mock.call_args.kwargs
        self.assertEqual(kwargs["hostname"], "test")
        self.assertEqual(kwargs["username"], "user")
        self.assertEqual(kwargs["password"], "pass")
        self.assertTrue(isinstance(kwargs["missing_host_key"], paramiko.AutoAddPolicy))
        self.assertIsNone(kwargs.get("private_key_file"))
        self.assertTrue(isinstance(kwargs["shell_type"], WindowsShellType))
        self.assertIsNotNone(uci_shell.get())

    @patch("spur.SshShell", new=SshShellMock)
    def test_call_redirection(self):
        uci_shell = UciShell(hostname="test", username="user", password="pass")
        self.assertEqual(uci_shell.get().close(), 42)
