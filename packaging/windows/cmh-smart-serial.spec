from pathlib import Path

from PyInstaller.utils.hooks import collect_all

root = Path.cwd()
backend = root / "backend"
frontend = root / "frontend" / "dist" / "cmh-smart-serial" / "browser"
model = backend / "data" / "models" / "mms-tts-ben"

if not frontend.joinpath("index.html").is_file():
    raise SystemExit("Prebuilt Angular frontend is missing. Run npm run build first.")
if not model.joinpath("model.safetensors").is_file():
    raise SystemExit("Offline Bengali model is missing. Run BUILD_WINDOWS_INSTALLER.bat online first.")

transformers_datas, transformers_binaries, transformers_hidden = collect_all("transformers")

a = Analysis(
    [str(root / "packaging" / "windows" / "server_entry.py")],
    pathex=[str(backend)],
    binaries=transformers_binaries,
    datas=transformers_datas + [
        (str(frontend), "frontend"),
        (str(backend / "alembic"), "alembic"),
        (str(backend / "alembic.ini"), "."),
        (str(backend / "app" / "audio"), "app/audio"),
        (str(model), "models/mms-tts-ben"),
    ],
    hiddenimports=transformers_hidden + [
        "uvicorn.logging", "uvicorn.loops.auto", "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto", "uvicorn.lifespan.on",
        "sqlalchemy.dialects.sqlite", "scipy.io.wavfile",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name="CMHSmartSerial", console=False, disable_windowed_traceback=False,
    uac_admin=False,
)
coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False, upx=False,
    name="CMH Smart Serial",
)
