"""Exercise the generated Windows launcher with a compiled executable stub."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import build


STUB_SOURCE = r"""
using System;
using System.Collections.Generic;
using System.IO;
using System.Web.Script.Serialization;

class LauncherStub
{
    static readonly JavaScriptSerializer Json = new JavaScriptSerializer();

    static string Env(string name)
    {
        return Environment.GetEnvironmentVariable(name);
    }

    static int ExitCode(string name)
    {
        string value = Env(name);
        return String.IsNullOrEmpty(value) ? 0 : Int32.Parse(value);
    }

    static int Main(string[] args)
    {
        bool prepare = Array.IndexOf(args, "--prepare-settings") >= 0;
        string record = Env("STUB_RECORD");
        File.WriteAllText(record + (prepare ? ".prepare.json" : ".serve.json"), Json.Serialize(args));
        if (!prepare)
            return ExitCode("STUB_SERVE_EXIT");

        string settings = Path.Combine(Env("APPDATA"), "the_study_platform", "settings.json");
        if (!File.Exists(settings))
        {
            Console.Error.WriteLine("The batch launcher did not create settings.json.");
            return 90;
        }
        string original = File.ReadAllText(settings);
        File.WriteAllText(record + ".before-settings.json", original);
        if (Env("STUB_EXPECT_EMPTY") == "1" && original.Trim() != "{}")
        {
            Console.Error.WriteLine("New settings.json did not contain an empty object.");
            return 91;
        }
        int failure = ExitCode("STUB_PREP_EXIT");
        if (failure != 0)
            return failure;

        string mapping = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "port_mapping.json");
        var defaults = Json.Deserialize<Dictionary<string, object>>(File.ReadAllText(mapping));
        var values = Json.Deserialize<Dictionary<string, object>>(original);
        if (!values.ContainsKey("frontend_port"))
            values["frontend_port"] = defaults["frontend_port"];
        if (!values.ContainsKey("backend_port"))
            values["backend_port"] = defaults["backend_port"];
        File.WriteAllText(settings, Json.Serialize(values));
        values = Json.Deserialize<Dictionary<string, object>>(File.ReadAllText(settings));

        int option = Array.IndexOf(args, "--ports-file");
        if (option < 0 || option + 1 >= args.Length)
        {
            Console.Error.WriteLine("The batch launcher did not request a ports file.");
            return 92;
        }
        File.WriteAllText(args[option + 1],
            "frontend_port=" + values["frontend_port"] + "\r\n" +
            "backend_port=" + values["backend_port"] + "\r\n");
        return 0;
    }
}
"""


@unittest.skipUnless(os.name == "nt", "Windows batch launcher")
class GeneratedBatchLauncherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        windows = Path(os.environ.get("WINDIR", r"C:\Windows"))
        compiler = next((path for path in (
            windows / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe",
            windows / "Microsoft.NET" / "Framework" / "v4.0.30319" / "csc.exe",
        ) if path.is_file()), None)
        if compiler is None:
            raise unittest.SkipTest("Windows .NET Framework C# compiler is unavailable")
        validation = build.ROOT / "build" / "validation"
        validation.mkdir(parents=True, exist_ok=True)
        cls.fixture = tempfile.TemporaryDirectory(prefix="batch-launcher-", dir=validation)
        cls.addClassCleanup(cls.fixture.cleanup)
        cls.fixture_root = Path(cls.fixture.name)
        source = cls.fixture_root / "LauncherStub.cs"
        source.write_text(STUB_SOURCE, encoding="utf-8")
        cls.executable = cls.fixture_root / "server.exe"
        compiled = subprocess.run(
            [str(compiler), "/nologo", "/target:exe", "/reference:System.Web.Extensions.dll",
             "/out:" + str(cls.executable), str(source)],
            capture_output=True, text=True, check=False, timeout=30,
        )
        if compiled.returncode:
            raise AssertionError("Could not compile launcher stub:\n" + compiled.stdout + compiled.stderr)

    def setUp(self):
        # Every launcher, settings, and temporary path exercises cmd.exe quoting.
        self.directory = tempfile.TemporaryDirectory(
            prefix="paths with spaces & (parentheses)!-", dir=self.fixture_root,
        )
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.package = self.root / "application & (portable)!"
        self.package.mkdir()
        shutil.copy2(self.executable, self.package / "server.exe")
        self.mapping = self.package / "port_mapping.json"
        shutil.copy2(build.ROOT / "port_mapping.json", self.mapping)
        self.launcher = self.package / "run.bat"
        self.launcher.write_text(build.LAUNCHER, encoding="ascii", newline="\r\n")
        self.appdata = self.root / "profile & (roaming)!"
        self.appdata.mkdir()
        self.temp = self.root / "temporary & (files)!"
        self.temp.mkdir()
        self.settings = self.appdata / "the_study_platform" / "settings.json"
        self.record = self.root / "stub-record"
        self.env = os.environ.copy()
        self.env.update({
            "APPDATA": str(self.appdata), "TEMP": str(self.temp), "TMP": str(self.temp),
            "STUB_RECORD": str(self.record),
        })
        for key in ("STUB_EXPECT_EMPTY", "STUB_PREP_EXIT", "STUB_SERVE_EXIT"):
            self.env.pop(key, None)

    def run_launcher(self, arguments=()):
        command_processor = os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe")
        tail = " " + subprocess.list2cmdline(list(arguments)) if arguments else ""
        # /s strips this outer pair, retaining the quoted batch path for cmd.exe.
        command = '"{}" /d /s /c ""{}"{}"'.format(command_processor, self.launcher, tail)
        result = subprocess.run(
            command, cwd=self.root, env=self.env, capture_output=True,
            text=True, check=False, timeout=15,
        )
        self.assertFalse(list(self.temp.iterdir()), "Launcher left its temporary ports file behind")
        return result

    def recorded(self, suffix):
        return json.loads(Path(str(self.record) + suffix).read_text(encoding="utf-8-sig"))

    def write_settings(self, values):
        self.settings.parent.mkdir(parents=True, exist_ok=True)
        self.settings.write_text(json.dumps(values), encoding="utf-8")

    def write_mapping(self, values):
        self.mapping.write_text(json.dumps(values), encoding="utf-8")

    def test_first_start_creates_empty_json_and_passes_prepared_default_ports(self):
        self.env["STUB_EXPECT_EMPTY"] = "1"
        result = self.run_launcher()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.recorded(".before-settings.json"), {})
        self.assertEqual(json.loads(self.settings.read_text()), {
            "frontend_port": 5100, "backend_port": 8011,
        })
        self.assertEqual(self.recorded(".serve.json"), [
            "--frontend-port", "5100", "--backend-port", "8011",
        ])

    def test_first_start_passes_defaults_from_mapping_beside_executable(self):
        defaults = {"frontend_port": 5402, "backend_port": 8042}
        self.write_mapping(defaults)
        self.env["STUB_EXPECT_EMPTY"] = "1"
        result = self.run_launcher()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.recorded(".before-settings.json"), {})
        self.assertEqual(json.loads(self.settings.read_text()), defaults)
        self.assertEqual(self.recorded(".serve.json"), [
            "--frontend-port", "5402", "--backend-port", "8042",
        ])

    def test_partial_saved_ports_keep_user_values_and_fill_from_mapping(self):
        self.write_mapping({"frontend_port": 5502, "backend_port": 8052})
        settings = {
            "frontend_port": 5602, "data_dir": r"D:\storage & (data)!",
            "future_setting": {"enabled": True},
        }
        self.write_settings(settings)
        result = self.run_launcher()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.recorded(".before-settings.json"), settings)
        self.assertEqual(json.loads(self.settings.read_text()), {**settings, "backend_port": 8052})
        self.assertEqual(self.recorded(".serve.json"), [
            "--frontend-port", "5602", "--backend-port", "8052",
        ])

    def test_saved_ports_and_other_settings_survive_with_explicit_overrides_last(self):
        settings = {
            "frontend_port": 5202, "backend_port": 8022,
            "data_dir": r"D:\storage & (data)!", "future_setting": {"enabled": True},
        }
        self.write_settings(settings)
        arguments = ["--frontend", "5302", "--backend-port", "8032", "--host", "127.0.0.1"]
        result = self.run_launcher(arguments)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.recorded(".before-settings.json"), settings)
        self.assertEqual(json.loads(self.settings.read_text()), settings)
        self.assertEqual(self.recorded(".serve.json"), [
            "--frontend-port", "5202", "--backend-port", "8022", *arguments,
        ])

    def test_preparation_failure_aborts_before_starting_services(self):
        self.env.update({"STUB_EXPECT_EMPTY": "1", "STUB_PREP_EXIT": "20"})
        result = self.run_launcher()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(Path(str(self.record) + ".prepare.json").is_file())
        self.assertFalse(Path(str(self.record) + ".serve.json").exists())
        self.assertEqual(json.loads(self.settings.read_text()), {})

    def test_service_exit_code_is_returned_to_caller(self):
        self.env["STUB_SERVE_EXIT"] = "17"
        result = self.run_launcher()
        self.assertEqual(result.returncode, 17, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
