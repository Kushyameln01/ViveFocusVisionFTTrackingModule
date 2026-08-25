from pathlib import Path
import hashlib
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
STAGING = Path(os.environ.get("VRCFT_BUILD_STAGING", ROOT / ".build-staging")).resolve()
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

# The archived v1.0.1 verification builder intentionally uses /mnt/data paths.
# Generate a temporary copy with only that staging prefix rewritten, preserving
# the actual PE/IL patch logic byte-for-byte.
source_builder = ROOT / "source" / "build_focusvision_v1.0.1.py"
builder_text = source_builder.read_text(encoding="utf-8")
builder_text = builder_text.replace("/mnt/data", STAGING.as_posix())
portable_builder = STAGING / "build_focusvision_v101.py"
portable_builder.write_text(builder_text, encoding="utf-8")

subprocess.run([sys.executable, str(portable_builder)], cwd=ROOT, check=True)

generated = STAGING / MODULE_NAME
if not generated.exists():
    raise RuntimeError(f"Builder did not produce {generated}")

with zipfile.ZipFile(generated, "r") as z:
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

# Keep the verified binary produced by the archived builder, but replace public
# distribution metadata/docs with the canonical repository files. This allows
# registry URLs and operational warnings to be updated without touching the
# verified PE/IL patch.
manifest_bytes = (ROOT / "module.json").read_bytes()
readme_bytes = (ROOT / "package" / "README.txt").read_bytes()

dist = ROOT / "dist"
dist.mkdir(exist_ok=True)
out = dist / MODULE_NAME

with zipfile.ZipFile(generated, "r") as src, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
    for info in src.infolist():
        data = src.read(info.filename)
        if info.filename == "module.json":
            data = manifest_bytes
        elif info.filename == "README.txt":
            data = readme_bytes
        dst.writestr(info, data)

# Final package validation.
with zipfile.ZipFile(out, "r") as z:
    final_dll = z.read("ViveFocusVisionFTTrackingModule.dll")
    final_manifest = z.read("module.json")
    final_readme = z.read("README.txt")

if hashlib.sha256(final_dll).hexdigest() != EXPECTED_DLL_SHA256:
    raise RuntimeError("Final package DLL changed during metadata repack")

expected_download_url = (
    "https://github.com/Kushyameln01/ViveFocusVisionFTTrackingModule/"
    "releases/download/v1.0.1/VRCFT_VIVE_FocusVision_Hybrid_v1.0.1.zip"
).encode("utf-8")
if expected_download_url not in final_manifest:
    raise RuntimeError("Final module.json does not contain the public release DownloadUrl")
if b"Do NOT enable this module together" not in final_readme:
    raise RuntimeError("Final README.txt does not contain the native SDK conflict warning")

print(f"Installable module: {out}")
print(f"DLL SHA-256: {actual_dll}")
print(f"Package SHA-256: {hashlib.sha256(out.read_bytes()).hexdigest()}")
print("Install in VRCFaceTracking: Module Registry -> Install Module from .zip")
