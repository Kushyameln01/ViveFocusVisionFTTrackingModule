VIVE Focus Vision Hybrid - VRCFT Custom Module v1.0.3

IMPORTANT
Do NOT enable this module together with HTC's original ViveStreamingFaceTrackingModule.
Both modules use the same VIVE Streaming native SDK / IPC (VS_PC_SDK.dll, RRServerManageAPI.dll, VSWPipeVarClient64U_MT.dll, RRPipeClient). In real-device testing, loading both caused repeated "VS_PC_SDK: [RRPipeClient] Not Connect" messages. Hybrid worked normally when the original HTC module was disabled/removed.

Before use:
  1. Disable or remove HTC ViveStreamingFaceTrackingModule.
  2. Connect Focus Vision through VIVE Hub / SteamVR.
  3. Enable 'Streaming avatar data to VRChat via OSC' in VIVE Hub Console.
  4. Enable and calibrate Eye Tracking on Focus Vision.

Base: HTC ViveStreamingFaceTrackingModule v1.7
Independent ModuleId: 6c13649b-c38c-4f69-9dc1-d62bb35220cf

v1.0.3 changes:
  - Replaces the v1.0.2 Mono.Cecil rewrite with a byte-level PE patch based on the exact verified v1.0.1 DLL.
  - Preserves all existing section payloads; only two existing MethodDef RVA cells are changed and a new .fvwdog code section is appended.
  - Adds a 5-second callback watchdog for initialized Eye and Lip tracking streams.
  - If either initialized stream stops receiving callbacks while the HMD streaming connection remains active, the module resets Face Tracking and lets the existing StartFaceTracking() path initialize it again.
  - No Eye/Lip mapping, Blink/Openness calculation, or native VIVE Streaming SDK library is changed.

Existing v1.0.1 eye calculation remains unchanged:
  O = clamp(rawOpenness, 0, 1)
  B = clamp(blink, 0, 1)
  correctedOpenness = min(O, 1 - B)   [37-value packets]
  correctedOpenness = O               [23-value packets]

Gaze, pupil, EyeWide, EyeSquint, brow and lip mappings are unchanged.
The HTC native DLLs are copied unchanged from the official v1.7 package.

The HTC base software remains subject to its included license.
