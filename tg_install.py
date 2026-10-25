"""不依賴 Telegram 套件的專案安裝及啟動入口。

Project installation and bootstrap without Telegram package dependencies."""
import argparse
import contextlib
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys

# 套件及外部 symlink 載入時，先定位檔案實體目錄的共用模組。
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_i18n import tr, language_errors, configure_language, LanguageError, LanguageArgumentParser, save_language, language

UV_GUIDE = "https://docs.astral.sh/uv/getting-started/installation/"


def find_uv(environ=None):
    values = os.environ if environ is None else environ
    selected = values.get("UV_BIN")
    return shutil.which(selected if selected else "uv", path=values.get("PATH", ""))


def project_environment(root, *, install=False):
    values = dict(os.environ)
    values["UV_PROJECT_ENVIRONMENT"] = str(root / ".venv")
    if install:
        values = {key: value for key, value in values.items() if not key.startswith("TG_")}
    else:
        values["TG_LANGUAGE"] = language()
    return values


def _ready(root):
    venv = root / ".venv"
    return (not venv.is_symlink() and (venv / "pyvenv.cfg").is_file()
            and (venv / "bin" / "python").is_file())


def _guidance():
    print(tr('install_uv_required_guidance'), file=sys.stderr)
    print(tr('install_uv_guide_prefix') + UV_GUIDE, file=sys.stderr)


@language_errors
def main(argv=None, *, runner=None, project_dir=None):
    root = Path(project_dir).resolve() if project_dir else ROOT
    try:
        argv = configure_language(argv, root=root, menu=True)
    except LanguageError as error:
        print(str(error), file=sys.stderr)
        return 2
    parser = LanguageArgumentParser(description=tr('install_help_description'))
    parser.add_argument("--offline", action="store_true", help=tr('install_offline_help'))
    # 避免 argparse 回映使用者誤貼的秘密參數。 / Prevent argparse from echoing accidentally pasted secret arguments.
    parse_exit = None
    with contextlib.redirect_stderr(io.StringIO()):
        try:
            args = parser.parse_args(argv)
        except SystemExit as error:
            parse_exit = int(error.code)
    if parse_exit is not None:
        if parse_exit:
            print(tr('install_arguments_invalid'), file=sys.stderr)
        return parse_exit
    uv = find_uv()
    if not uv:
        print(tr('install_uv_not_found'), file=sys.stderr)
        _guidance()
        return 1
    if (root / ".venv").is_symlink():
        print(tr('install_venv_symlink_refused'), file=sys.stderr)
        return 1
    command = [uv, "sync", "--frozen", "--project", str(root), "--python", "3.12"]
    if args.offline:
        command.append("--offline")
    try:
        result = (runner or subprocess.run)(command, env=project_environment(root, install=True),
                                            capture_output=True, check=False)
        if result.returncode != 0 or not _ready(root):
            print(tr('install_dependencies_incomplete'), file=sys.stderr)
            _guidance()
            return 1
    except (OSError, subprocess.SubprocessError, KeyboardInterrupt):
        print(tr('install_dependencies_interrupted'), file=sys.stderr)
        _guidance()
        return 1
    try:
        save_language(root)
    except LanguageError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(tr('install_complete'))
    return 0


@language_errors
def setup_main(argv=None, *, project_dir=None, executor=None):
    """保留 stdin／TTY，以專案環境完成您自己的 Telegram 帳號登入驗證。

Preserve stdin/TTY and verify sign-in to your own Telegram account in the project environment."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    root = Path(project_dir).resolve() if project_dir else ROOT
    try:
        arguments = configure_language(arguments, root=root)
    except LanguageError as error:
        print(str(error), file=sys.stderr)
        return 2
    import tg_setup

    if "--help" in arguments or "-h" in arguments:
        return tg_setup.main(["--language", language(), "--help"])
    invalid = False
    with contextlib.redirect_stderr(io.StringIO()):
        try:
            tg_setup.parser().parse_args(arguments)
        except SystemExit:
            invalid = True
    if invalid:
        print(tr('install_setup_arguments_invalid'), file=sys.stderr)
        return 2
    uv = find_uv()
    if not uv or not _ready(root):
        print(tr('install_environment_not_ready'), file=sys.stderr)
        if not uv:
            _guidance()
        return 1
    command = [uv, "run", "--frozen", "--no-sync", "--project", str(root),
               "python", str(root / "tg_setup.py"), *arguments]
    try:
        (executor or os.execvpe)(uv, command, project_environment(root))
    except OSError:
        print(tr('install_environment_launch_failed'), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
