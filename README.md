# VRCFT VIVE Focus Vision Hybrid

VIVE Focus Vision向けに調整した **VRCFaceTracking v5 Custom Module**。HTC `ViveStreamingFaceTrackingModule v1.7` をベースに、左右独立のBlink補助と `[0,1]` Clampを追加しています。

Current version: **v1.0.1**

## Install to VRCFaceTracking

VRCFTのCustom Module Installerを使用します。

1. `VRCFT_VIVE_FocusVision_Hybrid_v1.0.1.zip` を用意する。
2. VRCFaceTrackingを起動。
3. **Module Registry** を開く。
4. **Install Module from .zip** を選択。
5. 上記ZIPを指定する。
6. HTC公式 `ViveStreamingFaceTrackingModule` と同時有効化せず、比較時は片方ずつ有効にする。

### ZIPを用意する方法

**A. Windowsローカル — 推奨**

`Build-Module.ps1` を実行します。公式HTC v1.7を自動取得・SHA-256検証し、`dist/VRCFT_VIVE_FocusVision_Hybrid_v1.0.1.zip` を生成してフォルダを開きます。

**B. GitHub Actions**

`Actions` → **Build installable VRCFT module** → `Run workflow`。完了後、Artifactをダウンロードし、中の `VRCFT_VIVE_FocusVision_Hybrid_v1.0.1.zip` をVRCFTへ入れます。

**C. Private Release**

`Actions` → **Publish private install package** を実行すると、Private Repository内のRelease Assetとしてinstallable ZIPを配置できます。以後は `Releases` からZIPを取得してVRCFTへ入れられます。

> RepositoryがPrivateの間は、VRCFT Module Registryからの自動配布用 `DownloadUrl` は設定していません。Private GitHub AssetにはVRCFTが通常の公開URLとして直接アクセスできないためです。

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

## Repository layout

- `Build-Module.ps1` — Windows用ビルド入口
- `tools/build_module.py` — 公式v1.7取得・検証・パッケージ生成ラッパー
- `source/build_focusvision_v1.0.1.py` — v1.0.1本体パッチビルダー
- `source/FaceData.patch` — C#上での意図した差分
- `module.json` / `package/module.json` — VRCFT module metadata
- `verification/` — v1.0.1検証資料
- `.github/workflows/package.yml` — installable Artifact生成
- `.github/workflows/publish.yml` — Private Release生成

## Pinned upstream

HTC Vive Streaming Face Tracking Module **v1.7**

- Asset: `VRCFT_VSFT_Module_v1.7.zip`
- SHA-256: `5099af633f3206685e53a793ae5842adc3db881f272800407c71996cc3fa087f`

Generated Hybrid DLL expected SHA-256:

`db45ee49f18cd06b2374361777e96148af1b9856f83a1db82ce4e9fd5ec3fae9`

The repository is intentionally private. Upstream VIVE/VRCFT components remain subject to their respective licenses.
