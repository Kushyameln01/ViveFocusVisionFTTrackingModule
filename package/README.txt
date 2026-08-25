VIVE Focus Vision Hybrid - VRCFT Custom Module v1.0.1

Base: HTC ViveStreamingFaceTrackingModule v1.7
Independent ModuleId: 6c13649b-c38c-4f69-9dc1-d62bb35220cf

v1.0.1 changes:
  - CLR Module filename identity changed to ViveFocusVisionFTTrackingModule.dll.
  - Openness is clamped to [0,1] for supported eye packets.
  - Blink is clamped to [0,1] before hybrid correction on 37-value packets.

Eye calculation (per eye, independently):
  O = clamp(rawOpenness, 0, 1)
  B = clamp(blink, 0, 1)
  correctedOpenness = min(O, 1 - B)   [37-value packets]
  correctedOpenness = O               [23-value packets]

Gaze, pupil, EyeWide, EyeSquint, brow and lip mappings are unchanged.
The HTC native DLLs are copied unchanged from the official v1.7 package.

The HTC base software remains subject to its included license.
