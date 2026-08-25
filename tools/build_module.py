from pathlib import Path
import hashlib
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
STAGING = Path(os.environ.get("VRCFT_BUILD_STAGING", "/mnt/data"))
UPSTREAM_URL = "https://github.com/ViveSoftware/ViveStreamingFaceTrackingModule/releases/download/v1.7/VRCFT_VSFT_Module_v1.7.zip"
UPSTREAM_SHA256 = "5099af633f3206685e53a793ae5842adc3db881f272800407c71996cc3fa087f"
EXPECTED_DLL_SHA256 = "db45ee49f18cd06b2374361777e96148af1b9856f83a1db82ce4e9fd5ec3fae9"
MODULE_NAME = "VRCFT_VIVE_FocusVision_Hybrid_v1.0.1.zip"

STAGING.mkdir(parents=True, exist_ok=True)
base_zip = STAGING / "VRCFT_VSFT_Module_v1.7.zip"

if not base_zip.exists():
    print("Downloading pinned HTC ViveStreamingFaceTrackingModule v1.7...")
    urllib.request.urlretrieve(UPSTREAM_URL, base_zip)

actual_upstream = hashlib.sha256(base_zip.read_bytes()).hexdigest()
if actual_upstream != UPSTREAM_SHA256:
    raise RuntimeError(
        f"Upstream v1.7 SHA-256 mismatch: {actual_upstream} (expected {UPSTREAM_SHA256})"
    )

source_builder = ROOT / "source" / "build_focusvision_v1.0.1.py"
expected_builder_copy = STAGING / "build_focusvision_v101.py"
shutil.copy2(source_builder, expected_builder_copy)

subprocess.run([sys.executable, str(source_builder)], cwd=ROOT, check=True)

generated = STAGING / MODULE_NAME
if not generated.exists():
    raise RuntimeError(f"Builder did not produce {generated}")

with zipfile.ZipFile(generated) as z:
    required = {
        "ViveFocusVisionFTTrackingModule.dll",
        "module.json",
        "README.txt",
        "Libs/RRServerManageAPI.dll",
        "Libs/VSWPipeVarClient64U_MT.dll",
        "Libs/VS_PC_SDK.dll",
    }
    missing = required.difference(z.namelist())
    if missing:
        raise RuntimeError(f"Generated module is missing: {sorted(missing)}")
    dll = z.read("ViveFocusVisionFTTrackingModule.dll")

actual_dll = hashlib.sha256(dll).hexdigest()
if actual_dll != EXPECTED_DLL_SHA256:
    raise RuntimeError(
        f"Generated DLL SHA-256 mismatch: {actual_dll} (expected {EXPECTED_DLL_SHA256})"
    )

dist = ROOT / "dist"
dist.mkdir(exist_ok=True)
out = dist / MODULE_NAME
shutil.copy2(generated, out)

print(f"Installable module: {out}")
print(f"DLL SHA-256: {actual_dll}")
print(f"Package SHA-256: {hashlib.sha256(out.read_bytes()).hexdigest()}")
print("Install in VRCFaceTracking: Module Registry -> Install Module from .zip")
