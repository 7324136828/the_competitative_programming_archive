"""Discover runnable local language toolchains without changing the user's PATH."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
import sys

STRAWBERRY_CPP = r"C:\Strawberry\c\bin\g++.exe"
LANGUAGES = (
    {"id": "python", "label": "Python 3", "editorLanguage": "python"},
    {"id": "cpp", "label": "C++", "editorLanguage": "cpp"},
    {"id": "java", "label": "Java", "editorLanguage": "java"},
)
ALIASES = {"py": "python", "python3": "python", "c++": "cpp", "cxx": "cpp"}


@dataclass(frozen=True)
class Runtime:
    executable: str
    compiler: str | None = None

    def environment(self) -> dict[str, str]:
        """Keep compiler helpers and runtime DLLs discoverable in child processes."""
        environment = os.environ.copy()
        directories = dict.fromkeys(
            str(Path(path).parent) for path in (self.executable, self.compiler) if path
        )
        environment["PATH"] = os.pathsep.join((*directories, environment.get("PATH", "")))
        return environment


def language_id(language: str) -> str:
    name = str(language).lower().strip()
    return ALIASES.get(name, name)


def _usable(path: str | Path | None, arguments: list[str], environment: dict[str, str] | None = None) -> bool:
    if not path or not Path(path).is_file():
        return False
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    try:
        result = subprocess.run(
            [str(path), *arguments],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=environment,
            timeout=3,
            check=False,
            **options,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def discover_runtimes() -> dict[str, Runtime]:
    """Probe current installations so failed executables and incomplete JDKs are omitted."""
    discovered: dict[str, Runtime] = {}
    for executable in dict.fromkeys((sys.executable, shutil.which("python3"), shutil.which("python"))):
        if executable and _usable(executable, ["-c", "import sys; sys.exit(sys.version_info.major != 3)"]):
            discovered["python"] = Runtime(str(Path(executable).absolute()))
            break

    cpp_candidates = [shutil.which("g++"), shutil.which("clang++")]
    if os.name == "nt":
        cpp_candidates.append(STRAWBERRY_CPP)
    for compiler in dict.fromkeys(cpp_candidates):
        if not compiler:
            continue
        runtime = Runtime(str(Path(compiler).absolute()), str(Path(compiler).absolute()))
        if _usable(compiler, ["--version"], runtime.environment()):
            discovered["cpp"] = runtime
            break

    suffix = ".exe" if os.name == "nt" else ""
    javac = shutil.which("javac")
    java_candidates = []
    if javac:
        java_candidates.append((str(Path(javac).with_name("java" + suffix)), javac))
    java_candidates.append((shutil.which("java"), javac))
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        directory = Path(java_home.strip('"')) / "bin"
        java_candidates.append((str(directory / ("java" + suffix)), str(directory / ("javac" + suffix))))
    for executable, compiler in dict.fromkeys(java_candidates):
        if not executable or not compiler:
            continue
        runtime = Runtime(str(Path(executable).absolute()), str(Path(compiler).absolute()))
        environment = runtime.environment()
        if _usable(compiler, ["-version"], environment) and _usable(executable, ["-version"], environment):
            discovered["java"] = runtime
            break
    return discovered


def available_languages() -> list[dict[str, str]]:
    runtimes = discover_runtimes()
    return [dict(language) for language in LANGUAGES if language["id"] in runtimes]

