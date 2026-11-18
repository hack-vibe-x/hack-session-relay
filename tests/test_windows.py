"""The Windows parts of the client, checked from any computer: nothing here needs Windows.

What cannot be checked this way is Task Scheduler and cmd.exe themselves; see the README ("Windows").
"""
import os
import sys
import unittest
import xml.etree.ElementTree as ET
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "client"))
import relay  # noqa: E402
import sources  # noqa: E402

NS = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}


class TaskXml(unittest.TestCase):
    def parse(self, **kw):
        text = relay.task_xml(r"C:\Users\김지호\Python\pythonw.exe", r'"C:\Users\김지호\.session-relay\app\relay.py" tick',
                              r"DESKTOP-A&B\김지호", **kw)
        return ET.fromstring(text.split("\n", 1)[1])  # ElementTree refuses a str with an encoding declaration.

    def test_well_formed_with_both_triggers(self):
        root = self.parse()
        self.assertIsNotNone(root.find("t:Triggers/t:LogonTrigger", NS))
        self.assertEqual(root.find("t:Triggers/t:TimeTrigger/t:Repetition/t:Interval", NS).text, "PT1H")
        self.assertEqual(root.find("t:Actions/t:Exec/t:Command", NS).text, r"C:\Users\김지호\Python\pythonw.exe")
        self.assertEqual(root.find("t:Actions/t:Exec/t:Arguments", NS).text,
                         r'"C:\Users\김지호\.session-relay\app\relay.py" tick')
        self.assertEqual(root.find("t:Principals/t:Principal/t:UserId", NS).text, r"DESKTOP-A&B\김지호")  # & escaped
        self.assertEqual(root.find("t:Settings/t:StartWhenAvailable", NS).text, "true")

    def test_without_logon_trigger(self):
        root = self.parse(logon=False)
        self.assertIsNone(root.find("t:Triggers/t:LogonTrigger", NS))
        self.assertIsNotNone(root.find("t:Triggers/t:TimeTrigger", NS))

    def test_encodes_as_utf16(self):
        text = relay.task_xml("a", "b", "c")
        text.encode("utf-16")
        self.assertTrue(text.startswith('<?xml version="1.0" encoding="UTF-16"?>'))


class Wrapper(unittest.TestCase):
    def test_script_is_found_next_to_the_file(self):
        out = relay.windows_wrapper(r"C:\Python313\python.exe")
        self.assertEqual(out, '@echo off\n"C:\\Python313\\python.exe" "%~dp0app\\relay.py" %*\n')

    def test_non_ascii_profile_becomes_a_variable(self):
        with mock.patch.dict(os.environ, {"USERPROFILE": "/Users/김지호"}):
            out = relay.windows_wrapper("/Users/김지호/AppData/python.exe")
        self.assertTrue(out.isascii(), out)
        self.assertIn("%USERPROFILE%/AppData/python.exe", out)


class Localize(unittest.TestCase):
    def test_unchanged_off_windows(self):
        self.assertEqual(relay.localize("run ~/.session-relay/relay status"), "run ~/.session-relay/relay status")

    def test_command_and_folder_on_windows(self):
        with mock.patch.object(relay, "windows", return_value=True), \
                mock.patch.dict(os.environ, {"SESSION_RELAY_HOME": "/h/.session-relay"}):
            self.assertEqual(relay.localize("~/.session-relay/relay status; see ~/.session-relay/logs"),
                             "/h/.session-relay/relay.cmd status; see /h/.session-relay/logs")


class Job(unittest.TestCase):
    def run_install(self, results):
        import subprocess
        import tempfile
        calls = []

        def fake(*args):
            calls.append(args)
            if args[0] == "/Create":
                with open(args[args.index("/XML") + 1], encoding="utf-16") as f:
                    calls[-1] = args + ("LOGON" if "LogonTrigger" in f.read() else "HOURLY",)
                return subprocess.CompletedProcess(args, results.pop(0), "", "Access is denied")
            return subprocess.CompletedProcess(args, 0, "", "")

        with tempfile.TemporaryDirectory() as home, mock.patch.object(relay, "windows", return_value=True), \
                mock.patch.dict(os.environ, {"SESSION_RELAY_HOME": home, "SESSION_RELAY_LANG": "en"}), \
                mock.patch.object(relay, "schtasks", fake):
            ok, msg = relay.install_job()
            self.assertFalse(os.path.exists(os.path.join(home, "task.xml")))
        return ok, msg, calls

    def test_creates_the_task_and_starts_it(self):
        ok, msg, calls = self.run_install([0])
        self.assertTrue(ok, msg)
        self.assertEqual([c[0] for c in calls], ["/Create", "/Run"])
        self.assertEqual(calls[0][-1], "LOGON")

    def test_falls_back_to_hourly_when_logon_trigger_is_refused(self):
        ok, msg, calls = self.run_install([1, 0])
        self.assertTrue(ok, msg)
        self.assertEqual([c[-1] for c in calls if c[0] == "/Create"], ["LOGON", "HOURLY"])

    def test_reports_failure(self):
        ok, msg, calls = self.run_install([1, 1])
        self.assertFalse(ok)
        self.assertIn("Access is denied", msg)
        self.assertNotIn("/Run", [c[0] for c in calls])


class Roots(unittest.TestCase):
    """The daily job has no terminal environment variables; the folders found at install time are saved."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.custom = os.path.join(self.tmp.name, "custom-claude")
        os.makedirs(os.path.join(self.custom, "projects", "p"))
        with open(os.path.join(self.custom, "projects", "p", "11111111-2222-3333-4444-555555555555.jsonl"), "w") as f:
            f.write("{}\n")
        self.home = os.path.join(self.tmp.name, "home")
        os.makedirs(self.home)

    def clean_env(self, **extra):
        env = {k: v for k, v in os.environ.items() if not k.startswith(("SESSION_RELAY_", "CLAUDE_", "CODEX_", "XDG_"))}
        env.update(HOME=self.home, USERPROFILE=self.home, **extra)
        return mock.patch.dict(os.environ, env, clear=True)

    def test_discover_sees_the_environment_variable_and_saved_roots_outlive_it(self):
        with self.clean_env(CLAUDE_CONFIG_DIR=self.custom):
            roots = sources.discover()
            self.assertEqual(roots["claude"], [os.path.join(self.custom, "projects")])
            self.assertEqual(len(sources.find_session_files(roots)), 1)
        with self.clean_env():  # The job: no CLAUDE_CONFIG_DIR.
            self.assertEqual(sources.find_session_files(), [])
            self.assertEqual(len(sources.find_session_files(roots)), 1)

    def test_nothing_found_lists_the_places_looked_in(self):
        with self.clean_env():
            self.assertEqual(sources.discover(), {"claude": [], "codex": []})
            self.assertTrue(all(self.home in d for d in sources.claude_project_dirs() + sources.codex_homes()))


class Python(unittest.TestCase):
    def test_pythonw_swaps_back_to_python(self):
        with mock.patch.object(relay, "windows", return_value=True), \
                mock.patch.object(sys, "executable", "/x/pythonw.exe"), \
                mock.patch("os.path.exists", return_value=True):
            self.assertEqual(relay.python_console(), "/x/python.exe")
            self.assertEqual(relay.python_background(), "/x/pythonw.exe")

    def test_streams_exist_without_a_console(self):
        with mock.patch.object(sys, "stdout", None), mock.patch.object(sys, "stderr", None):
            relay.fix_streams()
            print("fine")  # Would raise under pythonw.exe without the fix.


if __name__ == "__main__":
    unittest.main()
