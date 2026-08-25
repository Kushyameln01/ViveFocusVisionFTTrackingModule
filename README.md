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

## Design philosophy

### Parameter model first, headset model second

このModuleでは、**HMD名ごとに別処理を持たせるのではなく、VIVE Streamingから実際に得られるFace/Eyeパラメータの能力に応じて処理する**方針を採っています。

VIVE Focus Vision、VIVE Focus 3、VIVE XR Eliteではセンサー構成は異なりますが、対応環境ではOpenXR/VIVE側のFace Trackingパラメータ体系は共通です。

- Eye Expression: `XrEyeExpressionHTC` の14値
- Lip Expression: `XrLipExpressionHTC` 系の37値
- Eye gaze / eye openness / pupil diameter はEye Trackingデータとして別途取得

代表的なハードウェア構成は次の通りです。

| Device | Eye Tracking | Lower Face Tracking |
|---|---|---|
| VIVE Focus Vision | HMD内蔵Eye Tracking | Facial Tracker for VIVE Focus Series |
| VIVE Focus 3 | VIVE Focus 3 Eye Tracker | Facial Tracker for VIVE Focus Series |
| VIVE XR Elite | VIVE Full Face Tracker側のEye Tracking | VIVE Full Face Tracker |

したがって本Moduleは、**Focus Vision専用のパラメータセットを定義しているわけではありません**。Focus Visionで確認されたEye Opennessの問題を起点にしていますが、同じ37-value Eye packetを出力するVIVE系構成であれば、同じ補正ロジックを利用できる設計です。

### Capability detection by packet format

HTC公式 `ViveStreamingFaceTrackingModule v1.7` はEye dataを複数形式で扱います。

| Eye packet | Available data | Hybrid behavior |
|---|---|---|
| 37 values | Gaze + Openness + 14 Eye Expressions + Pupil | Openness + Blink Hybrid |
| 23 values | Gaze + Openness + Pupil | Clamped Openness only |
| 21 values | Legacy Gaze + Openness | Upstream-compatible fallback |

重要なのは、これらを**特定HMDに固定して判定しない**ことです。VIVE Hub / VIVE Business Streaming / runtime / firmware側の対応状況によって利用可能データが変わる可能性があるため、Module側では受信packetの能力を基準にします。

### Why Blink is used

Focus Vision実機では、片眼がClosedへ近づいた状態で反対眼の `Eye Openness` の反応が悪化するケースを確認しました。一方、VIVE Streamingの37-value packetには左右独立した `LEFT_BLINK` / `RIGHT_BLINK` が存在します。

そのため本Moduleでは、BlinkをOpennessの代替ではなく**閉眼側の補助信号**として利用します。

```text
O = clamp(rawOpenness, 0, 1)
B = clamp(blink, 0, 1)
correctedOpenness = min(O, 1 - B)
```

これは次の思想に基づきます。

- 左右眼は完全に独立して処理する。
- 通常のOpenness情報を捨てない。
- Blinkがより強い閉眼を示した場合だけ閉眼側へ補正する。
- Blinkが存在しないpacketでは従来のOpennessへ安全にフォールバックする。
- EyeWide / EyeSquint / Brow / Gaze / Pupil / Lip mappingには不要な変更を加えない。

つまり本Moduleの目的は、**VIVE独自パラメータを作り直すことではなく、既存のVIVE Streamingデータを可能な限り保持したまま、利用可能な追加情報でEye Opennessの堅牢性を上げること**です。

### Scope

名称は `VIVE Focus Vision Hybrid` ですが、設計上は **VIVE Streaming 37-value Eye Expression packetに対するHybrid Openness処理**です。

Focus Visionはこの補正が必要になった実機・主要ターゲットですが、他のVIVE構成でも同じpacketと意味論を提供する限り、HMD名による特別扱いなしで動作することを意図しています。

References:

- HTC VIVE Streaming Face Tracking Module: https://github.com/ViveSoftware/ViveStreamingFaceTrackingModule
- HTC upstream `FaceData.cs`: https://github.com/ViveSoftware/ViveStreamingFaceTrackingModule/blob/main/ViveStreamingFaceTrackingModule/FaceData.cs
- Khronos `XrEyeExpressionHTC`: https://registry.khronos.org/OpenXR/specs/1.0/man/html/XrEyeExpressionHTC.html

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
