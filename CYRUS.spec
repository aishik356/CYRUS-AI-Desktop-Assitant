from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


project_root = Path(SPECPATH)

datas = collect_data_files("piper", include_py_files=False)
datas += [
    (str(project_root / "voices" / asset_name), "voices")
    for asset_name in (
        "en_GB-alan-medium.onnx",
        "en_GB-alan-medium.onnx.json",
    )
]
datas.append((str(project_root / "assets" / "reminder_alarm.wav"), "assets"))
binaries = []
hiddenimports = [
    "piper.espeakbridge",
    "onnxruntime.capi.onnxruntime_pybind11_state",
    "speech_recognition.recognizers.google",
]
hiddenimports += collect_submodules("holidays.countries")
excludes = [
    "speech_recognition.recognizers.whisper_local",
    "faster_whisper",
    "whisper",
    "torch",
    "transformers",
    "ctranslate2",
    "av",
]

analysis = Analysis(
    [str(project_root / "main.py")],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="CYRUS",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    icon=str(project_root / "assets" / "cyrus.ico"),
    console=False,
    disable_windowed_traceback=False,
)
collection = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="CYRUS",
)
