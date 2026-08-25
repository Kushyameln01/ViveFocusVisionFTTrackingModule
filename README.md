# VRCFT VIVE Focus Vision Hybrid

Private archive for the custom VRCFaceTracking module derived from VIVE Streaming Face Tracking Module v1.7 and adjusted for VIVE Focus Vision.

## Current version

**v1.0.1**

Eye openness handling:

- Clamp `Openness` to `[0, 1]`.
- Clamp `Blink` to `[0, 1]` when the 37-value eye packet is available.
- Use `Openness' = min(Openness, 1 - Blink)` independently for left and right eyes.
- Fall back to clamped `Openness` for legacy packets without Blink values.
- Keep gaze, eye-expression, lip mapping, and VIVE native SDK libraries aligned with the v1.7 base.
- Use a separate module ID, assembly name, namespace, DLL name, and CLR module name from the original VIVE module.

## Files

- `dist/VRCFT_VIVE_FocusVision_Hybrid_v1.0.1.zip` — installable VRCFT module package.
- `verification/VIVE_FocusVision_Hybrid_v1.0.1_Verification.zip` — build/verification package.
- `source/` — extracted verification/build materials.

## SHA-256

- Module package: `f0342ec44e6a011cfa9095196dc0a7bf03250514d0cf6c154dfae036902f64bb`
- Verification package: `da055b42d010bc1cbb765353fcc4f752079cc619ea133dc5801bfca9409553a2`

This repository is intentionally private. Upstream VIVE/VRCFT components remain subject to their respective licenses.
