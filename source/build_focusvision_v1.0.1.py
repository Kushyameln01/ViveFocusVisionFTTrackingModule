import struct, json, zipfile, shutil, hashlib
from pathlib import Path

BASE_ZIP = Path('/mnt/data/VRCFT_VSFT_Module_v1.7.zip')
WORK = Path('/mnt/data/fv_v101_work')
BASE = WORK / 'official'
OUTROOT = WORK / 'out'
if WORK.exists(): shutil.rmtree(WORK)
BASE.mkdir(parents=True)
OUTROOT.mkdir(parents=True)
with zipfile.ZipFile(BASE_ZIP) as z: z.extractall(BASE)

SRC = BASE / 'ViveStreamingFaceTrackingModule.dll'
DST_NAME = 'ViveFocusVisionFTTrackingModule.dll'
DST = OUTROOT / DST_NAME
p = bytearray(SRC.read_bytes())

# ---- Small IL assembler ----
code=bytearray(); labels={}; fixups=[]
def emit(*bs): code.extend(bs)
def u32(x): return struct.pack('<I',x)
def i32(x): return struct.pack('<i',x)
def f32(x): return struct.pack('<f',x)
def tok(op,t): emit(op); code.extend(u32(t))
def mark(name): labels[name]=len(code)
def br(op,label):
    emit(op); fixups.append((len(code),label)); code.extend(b'\0\0\0\0')
def ldarg0(): emit(0x02)
def ldarg1(): emit(0x03)
def ldloc(i): emit(0x06+i) if i<=3 else emit(0x11,i)
def stloc(i): emit(0x0A+i) if i<=3 else emit(0x13,i)
def ldloca(i): emit(0x12,i)
def ldc_i4_s(v): emit(0x1F, v & 0xff)
def ldc_r4(v): emit(0x22); code.extend(f32(v))
def ldlen_i4(): emit(0x8E,0x69)
def ldelem_ref(): emit(0x9A)
def call(t): tok(0x28,t)
def ldind_ref(): emit(0x50)
def ldflda(t): tok(0x7C,t)
def stfld(t): tok(0x7D,t)
def sub(): emit(0x59)
def ret(): emit(0x2A)

# Tokens verified against HTC v1.7 supplied binary.
SAFE_PARSE=0x06000009
LEFT=0x0A000014; GAZE=0x0A000015; VX=0x0A000016; VY=0x0A000017
RIGHT=0x0A000018; OPENNESS=0x0A000019; PUPIL=0x0A00001A

def parse(index, local, fail_label):
    ldarg1(); ldc_i4_s(index); ldelem_ref(); ldloca(local); call(SAFE_PARSE); br(0x39,fail_label)

def store_gaze(side_token, lx, ly):
    ldarg0(); ldind_ref(); ldflda(side_token); ldflda(GAZE); ldloc(lx); stfld(VX)
    ldarg0(); ldind_ref(); ldflda(side_token); ldflda(GAZE); ldloc(ly); stfld(VY)

def store_eye_float(side_token, field_token, local):
    ldarg0(); ldind_ref(); ldflda(side_token); ldloc(local); stfld(field_token)

def length_blt(n,label):
    ldarg1(); ldlen_i4(); ldc_i4_s(n); br(0x3F,label)

def length_bne(n,label):
    ldarg1(); ldlen_i4(); ldc_i4_s(n); br(0x40,label)

def clamp01(local, prefix):
    ldloc(local); ldc_r4(0.0); br(0x3C, prefix+'_nonneg')
    ldc_r4(0.0); stloc(local)
    mark(prefix+'_nonneg')
    ldloc(local); ldc_r4(1.0); br(0x3E, prefix+'_done')
    ldc_r4(1.0); stloc(local)
    mark(prefix+'_done')

length_blt(20,'pupils')
parse(9,0,'left_gaze_done'); parse(10,1,'left_gaze_done'); store_gaze(LEFT,0,1)
mark('left_gaze_done')
parse(15,0,'right_gaze_done'); parse(16,1,'right_gaze_done'); store_gaze(RIGHT,0,1)
mark('right_gaze_done')

parse(18,2,'left_open_done')
clamp01(2,'left_open_clamp')
length_blt(37,'left_store')
parse(20,4,'left_store')
clamp01(4,'left_blink_clamp')
ldloc(2); ldc_r4(1.0); ldloc(4); sub(); br(0x3E,'left_store')
ldc_r4(1.0); ldloc(4); sub(); stloc(2)
mark('left_store'); store_eye_float(LEFT,OPENNESS,2); mark('left_open_done')

parse(19,3,'right_open_done')
clamp01(3,'right_open_clamp')
length_blt(37,'right_store')
parse(22,5,'right_store')
clamp01(5,'right_blink_clamp')
ldloc(3); ldc_r4(1.0); ldloc(5); sub(); br(0x3E,'right_store')
ldc_r4(1.0); ldloc(5); sub(); stloc(3)
mark('right_store'); store_eye_float(RIGHT,OPENNESS,3); mark('right_open_done')

mark('pupils')
length_bne(23,'pupil_full_check')
parse(21,4,'pupil23_right'); store_eye_float(LEFT,PUPIL,4)
mark('pupil23_right'); parse(22,4,'done'); store_eye_float(RIGHT,PUPIL,4); br(0x38,'done')
mark('pupil_full_check'); length_blt(37,'done')
parse(35,4,'pupil37_right'); store_eye_float(LEFT,PUPIL,4)
mark('pupil37_right'); parse(36,4,'done'); store_eye_float(RIGHT,PUPIL,4)
mark('done'); ret()

for pos,label in fixups:
    code[pos:pos+4]=i32(labels[label]-(pos+4))

body=bytearray(struct.pack('<HHII',0x3013,3,len(code),0x11000001))+code
while len(body)%4: body.append(0)

def U16(o): return struct.unpack_from('<H',p,o)[0]
def U32(o): return struct.unpack_from('<I',p,o)[0]
def W16(o,v): struct.pack_into('<H',p,o,v)
def W32(o,v): struct.pack_into('<I',p,o,v)
def align(v,a): return (v+a-1)//a*a
pe=U32(0x3c); coff=pe+4; numsec=U16(coff+2); optsz=U16(coff+16); opt=coff+20
assert U16(opt)==0x20b
section_alignment=U32(opt+32); file_alignment=U32(opt+36)
size_of_code_off=opt+4; size_image_off=opt+56; size_headers=U32(opt+60)
sec_table=opt+optsz
secs=[]
for i in range(numsec):
    o=sec_table+i*40
    secs.append((o,bytes(p[o:o+8]).rstrip(b'\0'),U32(o+8),U32(o+12),U32(o+16),U32(o+20)))
last=max(secs,key=lambda x:x[3])
new_va=align(last[3]+max(last[2],last[4]),section_alignment)
new_raw=align(len(p),file_alignment); new_raw_size=align(len(body),file_alignment); new_vs=len(body)
new_sh=sec_table+numsec*40
assert new_sh+40 <= size_headers
if len(p)<new_raw: p.extend(b'\0'*(new_raw-len(p)))
p.extend(body)
if len(p)<new_raw+new_raw_size: p.extend(b'\0'*(new_raw+new_raw_size-len(p)))
p[new_sh:new_sh+8]=b'.fvfix\0\0'
struct.pack_into('<IIIIIIHHI',p,new_sh+8,new_vs,new_va,new_raw_size,new_raw,0,0,0,0,0x60000020)
W16(coff+2,numsec+1); W32(size_of_code_off,U32(size_of_code_off)+new_raw_size); W32(size_image_off,align(new_va+new_vs,section_alignment))

method_row=0x19c8+(6-1)*14
assert U32(method_row)==8344, hex(U32(method_row))
W32(method_row,new_va)

old_name=b'ViveStreamingFaceTrackingModule'
new_name=b'ViveFocusVisionFTTrackingModule'
assert len(old_name)==len(new_name)==31
name_off=p.find(old_name,9356,9356+5040)
assert name_off==0x2a02, hex(name_off)
p[name_off:name_off+31]=new_name

old_mod=b'ViveStreamingFaceTrackingModule.dll'
new_mod=b'ViveFocusVisionFTTrackingModule.dll'
assert len(old_mod)==len(new_mod)==35
mod_off=p.find(old_mod,9356,9356+5040)
assert mod_off==0x3091, hex(mod_off)
p[mod_off:mod_off+35]=new_mod

old_display='ViveStreamingFaceTracking'.encode('utf-16le')
new_display='VIVE Focus Vision Hybrid+'.encode('utf-16le')
assert len(old_display)==len(new_display)
display_off=p.find(old_display)
assert display_off==0x3952, hex(display_off)
p[display_off:display_off+len(old_display)]=new_display

DST.write_bytes(p)

module_id='6c13649b-c38c-4f69-9dc1-d62bb35220cf'
manifest={
  'ModuleId': module_id,
  'LastUpdated': '2026-08-26T03:52:00+09:00',
  'Version': '1.0.1',
  'Downloads': 0,
  'Ratings': 0,
  'Rating': 0.0,
  'AuthorName': 'HTC Corp. base / Focus Vision adaptation',
  'ModuleName': 'VIVE Focus Vision Hybrid',
  'ModuleDescription': 'Focus Vision-oriented fork of HTC VIVE Streaming Face Tracking v1.7. Clamps per-eye Openness/Blink to [0,1] and uses Blink as an independent closure fallback.',
  'UsageInstructions': "Enable 'Streaming avatar data to VRChat via OSC' in VIVE Hub Console. Openness is clamped to [0,1] on supported eye packets. On 37-value packets Blink is also clamped, then corrected openness = min(openness, 1 - blink), independently per eye. 23-value packets use clamped Openness without Blink correction.",
  'DownloadUrl': '',
  'ModulePageUrl': 'https://github.com/ViveSoftware/ViveStreamingFaceTrackingModule',
  'DllFileName': DST_NAME
}
(OUTROOT/'module.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')

libs=OUTROOT/'Libs'; libs.mkdir(exist_ok=True)
for f in (BASE/'Libs').iterdir():
    if f.is_file(): shutil.copy2(f,libs/f.name)
if (BASE/'License.txt').exists(): shutil.copy2(BASE/'License.txt', OUTROOT/'License.txt')

readme=f'''VIVE Focus Vision Hybrid - VRCFT Custom Module v1.0.1\n\nBase: HTC ViveStreamingFaceTrackingModule v1.7\nIndependent ModuleId: {module_id}\n\nv1.0.1 changes:\n  - CLR Module filename identity changed to ViveFocusVisionFTTrackingModule.dll.\n  - Openness is clamped to [0,1] for supported eye packets.\n  - Blink is clamped to [0,1] before hybrid correction on 37-value packets.\n\nEye calculation (per eye, independently):\n  O = clamp(rawOpenness, 0, 1)\n  B = clamp(blink, 0, 1)\n  correctedOpenness = min(O, 1 - B)   [37-value packets]\n  correctedOpenness = O               [23-value packets]\n\nGaze, pupil, EyeWide, EyeSquint, brow and lip mappings are unchanged.\nThe HTC native DLLs are copied unchanged from the official v1.7 package.\n\nThe HTC base software remains subject to its included license.\n'''
(OUTROOT/'README.txt').write_text(readme,encoding='utf-8')

zip_path=Path('/mnt/data/VRCFT_VIVE_FocusVision_Hybrid_v1.0.1.zip')
with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED) as z:
    for f in sorted(OUTROOT.rglob('*')):
        if f.is_file(): z.write(f,f.relative_to(OUTROOT).as_posix())

patch='''--- official FaceData.cs
+++ VIVE Focus Vision Hybrid v1.0.1
@@
- data.Left.Openness = leftOpenness;
+ leftOpenness = Math.Clamp(leftOpenness, 0.0f, 1.0f);
+ if (eyeDataComponent.Length >= (int)EyeDataIndex.MAX &&
+     SafeParse(eyeDataComponent[(int)EyeDataIndex.LEFT_BLINK], out float leftBlink))
+ {
+     leftBlink = Math.Clamp(leftBlink, 0.0f, 1.0f);
+     leftOpenness = Math.Min(leftOpenness, 1.0f - leftBlink);
+ }
+ data.Left.Openness = leftOpenness;
@@
- data.Right.Openness = rightOpenness;
+ rightOpenness = Math.Clamp(rightOpenness, 0.0f, 1.0f);
+ if (eyeDataComponent.Length >= (int)EyeDataIndex.MAX &&
+     SafeParse(eyeDataComponent[(int)EyeDataIndex.RIGHT_BLINK], out float rightBlink))
+ {
+     rightBlink = Math.Clamp(rightBlink, 0.0f, 1.0f);
+     rightOpenness = Math.Min(rightOpenness, 1.0f - rightBlink);
+ }
+ data.Right.Openness = rightOpenness;
'''
verify_path=Path('/mnt/data/VIVE_FocusVision_Hybrid_v1.0.1_Verification.zip')
with zipfile.ZipFile(verify_path,'w',zipfile.ZIP_DEFLATED) as z:
    z.write('/mnt/data/build_focusvision_v101.py','build_focusvision_v1.0.1.py')
    z.writestr('FaceData.patch', patch)
    z.writestr('README.txt', readme)

print('DLL:', DST, DST.stat().st_size)
print('ZIP:', zip_path, zip_path.stat().st_size)
print('VERIFY:', verify_path, verify_path.stat().st_size)
print('IL code bytes:', len(code), 'body bytes:', len(body), 'maxstack=3', 'new RVA:', hex(new_va))
print('SHA256 ZIP:', hashlib.sha256(zip_path.read_bytes()).hexdigest())
print('SHA256 DLL:', hashlib.sha256(DST.read_bytes()).hexdigest())
