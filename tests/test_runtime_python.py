"""Voice setup must not use a system Python that has no pip."""

from __future__ import annotations

import hashlib
import subprocess
import tarfile
import textwrap
from pathlib import Path

from ai_assistant import runtime_python
from ai_assistant.hearing import HearingEngine
from ai_assistant.providers import _models_from_openai_payload
from ai_assistant.service import AssistantService
from ai_assistant.store import Store
from ai_assistant.vision import model_can_see, row_sees_images


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _python_archive(directory: Path) -> Path:
    script = textwrap.dedent(
        """\
        #!/bin/sh
        if [ "$1" = "-c" ]; then
          exit 0
        fi
        if [ "$1" = "-m" ] && [ "$2" = "venv" ]; then
          dest="$3"
          mkdir -p "$dest/bin"
          cp "$0" "$dest/bin/python"
          chmod +x "$dest/bin/python"
          exit 0
        fi
        if [ "$1" = "-m" ] && [ "$2" = "pip" ]; then
          printf '%s\\n' "$*" >> "${DECKLING_PIP_LOG:?}"
          exit 0
        fi
        echo "No module named pip" >&2
        exit 1
        """
    )
    root = directory / "stage" / "python" / "bin"
    root.mkdir(parents=True)
    binary = root / "python3"
    binary.write_text(script, encoding="utf-8")
    binary.chmod(0o755)
    archive = directory / "cpython-test.tar.gz"
    with tarfile.open(archive, "w:gz") as handle:
        handle.add(directory / "stage" / "python", arcname="python")
    return archive


def test_standalone_python_is_checksummed_and_used_instead_of_system_pip(tmp_path, monkeypatch) -> None:
    archive = _python_archive(tmp_path)
    digest = _sha256(archive)
    filename = "cpython-3.11.17+20261003-x86_64-unknown-linux-gnu-install_only.tar.gz"
    monkeypatch.setitem(runtime_python._BUILDS, "x86_64", (filename, digest))
    system = tmp_path / "system-python3"
    system.write_text("#!/bin/sh\necho 'No module named pip' >&2\nexit 1\n", encoding="utf-8")
    system.chmod(0o755)
    log = tmp_path / "pip.log"
    monkeypatch.setenv("DECKLING_PIP_LOG", str(log))
    calls: list[str] = []

    def fetch(url: str, dest: str, progress=None) -> None:
        calls.append(url)
        assert filename in url
        Path(dest).write_bytes(archive.read_bytes())
        if progress:
            progress("Downloading Python", 0.1)

    store = Store(str(tmp_path / "settings"), str(tmp_path / "runtime"))
    engine = HearingEngine(store, fetch=fetch, machine="x86_64")
    engine.autostart = False

    def fake_download(url: str, dest: str, progress=None) -> None:
        if "python-build-standalone" in url:
            fetch(url, dest, progress)
            return
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(b"model")

    engine.fetch = fake_download
    engine._download_wake_files = lambda _model: None
    engine._install_stt = lambda _model: "whisper.cpp"
    engine.install()
    pip_log = log.read_text(encoding="utf-8")
    assert "install" in pip_log
    assert "openwakeword==0.4.0" in pip_log
    venv_python = tmp_path / "runtime" / "hearing" / "venv" / "bin" / "python"
    assert venv_python.is_file()
    assert engine.python == str(venv_python)
    assert system.read_text(encoding="utf-8").startswith("#!/bin/sh")
    assert not (tmp_path / "system-used").exists()
    # A second install reuses the interpreter and does not download Python again.
    before = len(calls)
    engine.install()
    assert len(calls) == before


def test_python_archive_rejects_a_symlink_that_leaves_the_tree(tmp_path) -> None:
    archive = tmp_path / "escape.tar.gz"
    with tarfile.open(archive, "w:gz") as handle:
        info = tarfile.TarInfo("python/bin/python3")
        info.type = tarfile.SYMTYPE
        info.linkname = "../../../etc/passwd"
        handle.addfile(info)
    try:
        runtime_python._extract_python(str(archive), str(tmp_path / "out"))
    except ValueError as exc:
        assert "not safe" in str(exc)
    else:
        raise AssertionError("escaping symlink was extracted")


def test_bad_python_checksum_is_deleted(tmp_path, monkeypatch) -> None:
    archive = _python_archive(tmp_path)
    filename = "cpython-3.11.17+20261003-x86_64-unknown-linux-gnu-install_only.tar.gz"
    monkeypatch.setitem(runtime_python._BUILDS, "x86_64", (filename, "0" * 64))

    def fetch(url: str, dest: str, progress=None) -> None:
        del url, progress
        Path(dest).write_bytes(archive.read_bytes())

    try:
        runtime_python.ensure_runtime_python(str(tmp_path / "runtime"), fetch, machine="x86_64")
    except RuntimeError as exc:
        assert "checksum" in str(exc)
    else:
        raise AssertionError("checksum mismatch was accepted")
    assert list((tmp_path / "runtime" / "python").glob("*.tar.gz")) == []


def test_system_python_without_pip_cannot_import_pip() -> None:
    """The failure from the Deck photo, reproduced with a stub interpreter."""
    script = (
        "import sys\n"
        "if '-m' in sys.argv and 'pip' in sys.argv:\n"
        "    sys.stderr.write('No module named pip\\n')\n"
        "    raise SystemExit(1)\n"
    )
    completed = subprocess.run(["python3", "-c", script, "-m", "pip"], check=False, capture_output=True, text=True)
    assert completed.returncode == 1
    assert "No module named pip" in completed.stderr


def test_llamacpp_capabilities_and_props_mark_vision_and_override_wins(tmp_path) -> None:
    payload = {
        "models": [
            {
                "name": "qwen3.8-flash-next",
                "capabilities": ["completion", "multimodal"],
            }
        ]
    }
    ids, seen = _models_from_openai_payload(payload, None)
    assert ids == ["qwen3.8-flash-next"]
    assert seen == ["qwen3.8-flash-next"]
    assert row_sees_images({"name": "plain"}, True) is True
    assert row_sees_images({"name": "plain", "capabilities": ["completion"]}, False) is False
    provider = {"vision_override": {"qwen3.8-flash-next": False, "text-only": True}}
    assert model_can_see(provider, "qwen3.8-flash-next", {"qwen3.8-flash-next"}) is False
    assert model_can_see(provider, "text-only", set()) is True

    service = AssistantService(str(tmp_path / "settings"), str(tmp_path / "runtime"))
    saved = service.save_provider(
        {"kind": "llamacpp", "name": "Home", "base_url": "http://127.0.0.1:9/v1", "default_model": "qwen3.8-flash-next"}
    )
    updated = service.set_model_vision(saved["provider"]["id"], "qwen3.8-flash-next", True)
    assert updated["provider"]["vision_override"]["qwen3.8-flash-next"] is True
    stored = service.store.get_provider(saved["provider"]["id"])
    assert model_can_see(stored, "qwen3.8-flash-next", set()) is True
