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
EXPECTED_V101_DLL_SHA256 = "db45ee49f18cd06b2374361777e96148af1b9856f83a1db82ce4e9fd5ec3fae9"
BASE_MODULE_NAME = "VRCFT_VIVE_FocusVision_Hybrid_v1.0.1.zip"
MODULE_NAME = "VRCFT_VIVE_FocusVision_Hybrid_v1.0.3.zip"

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

# Reproduce the verified v1.0.1 Hybrid DLL first. This preserves the existing
# Focus Vision eye-data changes byte-for-byte before the watchdog is added.
source_builder = ROOT / "source" / "build_focusvision_v1.0.1.py"
builder_text = source_builder.read_text(encoding="utf-8")
builder_text = builder_text.replace("/mnt/data", STAGING.as_posix())
portable_builder = STAGING / "build_focusvision_v101.py"
portable_builder.write_text(builder_text, encoding="utf-8")

subprocess.run([sys.executable, str(portable_builder)], cwd=ROOT, check=True)

generated = STAGING / BASE_MODULE_NAME
if not generated.exists():
    raise RuntimeError(f"Builder did not produce {generated}")

package_root = STAGING / "watchdog-package"
if package_root.exists():
    shutil.rmtree(package_root)
package_root.mkdir(parents=True)

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
    z.extractall(package_root)

dll_path = package_root / "ViveFocusVisionFTTrackingModule.dll"
pre_watchdog_hash = hashlib.sha256(dll_path.read_bytes()).hexdigest()
if pre_watchdog_hash != EXPECTED_V101_DLL_SHA256:
    raise RuntimeError(
        f"Generated v1.0.1 DLL SHA-256 mismatch: {pre_watchdog_hash} "
        f"(expected {EXPECTED_V101_DLL_SHA256})"
    )

# Apply the callback-stall watchdog without rebuilding the managed assembly.
# The patcher requires the exact verified v1.0.1 DLL, preserves every existing
# section payload, appends only a new .fvwdog code section, and changes only the
# two existing MethodDef RVA cells needed to redirect Update()/OnVSSettingChange().
patcher = ROOT / "tools" / "pe_watchdog_patcher.py"
subprocess.run([sys.executable, str(patcher), str(dll_path)], cwd=ROOT, check=True)

post_watchdog_hash = hashlib.sha256(dll_path.read_bytes()).hexdigest()
if post_watchdog_hash == pre_watchdog_hash:
    raise RuntimeError("Watchdog patch did not change the managed module DLL")

# Replace only public distribution metadata/docs after patching the DLL.
(package_root / "module.json").write_bytes((ROOT / "module.json").read_bytes())
(package_root / "README.txt").write_bytes((ROOT / "package" / "README.txt").read_bytes())

dist = ROOT / "dist"
dist.mkdir(exist_ok=True)
out = dist / MODULE_NAME

with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
    for file in sorted(package_root.rglob("*")):
        if file.is_file():
            dst.write(file, file.relative_to(package_root).as_posix())

# Final package validation.
with zipfile.ZipFile(out, "r") as z:
    final_dll = z.read("ViveFocusVisionFTTrackingModule.dll")
    final_manifest = z.read("module.json")
    final_readme = z.read("README.txt")

if hashlib.sha256(final_dll).hexdigest() != post_watchdog_hash:
    raise RuntimeError("Final package DLL changed during metadata repack")

expected_download_url = (
    "https://github.com/Kushyameln01/ViveFocusVisionFTTrackingModule/"
    "releases/download/v1.0.3/VRCFT_VIVE_FocusVision_Hybrid_v1.0.3.zip"
).encode("utf-8")
if expected_download_url not in final_manifest:
    raise RuntimeError("Final module.json does not contain the v1.0.3 DownloadUrl")
if b"Do NOT enable this module together" not in final_readme:
    raise RuntimeError("Final README.txt does not contain the native SDK conflict warning")
if b"5-second callback watchdog" not in final_readme:
    raise RuntimeError("Final README.txt does not document the callback watchdog")

print(f"Installable module: {out}")
print(f"Pre-watchdog v1.0.1 DLL SHA-256: {pre_watchdog_hash}")
print(f"Patched v1.0.3 DLL SHA-256: {post_watchdog_hash}")
print(f"Package SHA-256: {hashlib.sha256(out.read_bytes()).hexdigest()}")
print("Install in VRCFaceTracking: Module Registry -> Install Module from .zip")
