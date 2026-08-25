# VRCFT VIVE Focus Vision Hybrid

VIVE Focus Vision向けに調整した **VRCFaceTracking v5 Custom Module**。HTC `ViveStreamingFaceTrackingModule v1.7` をベースに、左右独立のBlink補助と `[0,1]` Clampを追加しています。

Current version: **v1.0.1**

## Important: do not enable together with HTC's original module

**HTC公式 `ViveStreamingFaceTrackingModule` と本Moduleを同時に有効化しないでください。**

両Moduleは同じVIVE Streaming native SDK / IPC (`VS_PC_SDK.dll`, `RRServerManageAPI.dll`, `VSWPipeVarClient64U_MT.dll`, `RRPipeClient`) を使用します。実機確認では両方を同時ロードすると `VS_PC_SDK: [RRPipeClient] Not Connect` が連続し、Hybrid単体にすると正常接続しました。

- HTC公式Moduleを無効化または削除してからHybridを有効化してください。
- 比較テストする場合も、常に片方だけを有効にしてください。

## Install to VRCFaceTracking

### Module Registry（登録承認後）

VRCFaceTracking → **Module Registry** → `VIVE Focus Vision Hybrid` → **Install**。

### Manual ZIP install

1. Releasesから `VRCFT_VIVE_FocusVision_Hybrid_v1.0.1.zip` を取得。
2. VRCFaceTrackingを起動。
3. **Module Registry** を開く。
4. **Install Module from .zip** を選択。
5. ZIPを指定する。
6. HTC公式 `ViveStreamingFaceTrackingModule` は無効化する。

## VIVE Hub requirements

- Focus VisionをVIVE Hub / SteamVRへ正常接続する。
- VIVE Hub Consoleで **Streaming avatar data to VRChat via OSC** を有効化する。
- Focus Vision本体のEye Trackingを有効化し、Calibrationを完了する。

## Focus Vision changes

Per eye, independently:

```text
O = clamp(rawOpenness, 0, 1)
B = clamp(blink, 0, 1)
correctedOpenness = min(O, 1 - B)   # 37-value packet
correctedOpenness = O               # 23-value packet
```

- Left / Rightは相互参照しない。
- Gaze / Pupil / EyeWide / EyeSquint / Brow / Lip mappingはHTC v1.7のまま。
- HTC native DLL 3個は公式v1.7から無改変で使用。
- 独立したModuleId / Assembly / namespace / DLL / CLR Module名を使用。

## Build

**Windows:** `Build-Module.ps1`

**GitHub Actions:** `Actions` → **Build installable VRCFT module** → `Run workflow`

Release生成は `.github/workflows/publish.yml` を使用します。

## Repository layout

- `Build-Module.ps1` — Windows用ビルド入口
- `tools/build_module.py` — 公式v1.7取得・検証・パッケージ生成ラッパー
- `source/build_focusvision_v1.0.1.py` — v1.0.1本体パッチビルダー
- `source/FaceData.patch` — C#上での意図した差分
- `module.json` / `package/module.json` — VRCFT module metadata
- `verification/` — v1.0.1検証資料
- `.github/workflows/package.yml` — installable Artifact生成
- `.github/workflows/publish.yml` — Release生成

## Pinned upstream

HTC Vive Streaming Face Tracking Module **v1.7**

- Asset: `VRCFT_VSFT_Module_v1.7.zip`
- SHA-256: `5099af633f3206685e53a793ae5842adc3db881f272800407c71996cc3fa087f`

Generated Hybrid DLL expected SHA-256:

`db45ee49f18cd06b2374361777e96148af1b9856f83a1db82ce4e9fd5ec3fae9`

## License / attribution

This project is derived from HTC's VIVE Streaming Face Tracking Module v1.7. HTC's original `License.txt` is retained in binary distributions. The upstream license permits use, distribution, and modification for legitimate software development, subject to its copyright, disclaimer, and attribution requirements.

VRCFaceTracking and its SDK remain subject to their respective licenses.
