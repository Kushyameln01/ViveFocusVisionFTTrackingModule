from __future__ import annotations
import hashlib
import struct
import sys
from pathlib import Path

EXPECTED_SHA256 = "db45ee49f18cd06b2374361777e96148af1b9856f83a1db82ce4e9fd5ec3fae9"
TIMEOUT_MS = 5000
TICK_MS = 11


def align(value: int, alignment: int) -> int:
    return (value + alignment - 1) // alignment * alignment


class PE:
    def __init__(self, data: bytearray):
        self.p = data
        self.u16 = lambda o: struct.unpack_from("<H", self.p, o)[0]
        self.u32 = lambda o: struct.unpack_from("<I", self.p, o)[0]
        self.u64 = lambda o: struct.unpack_from("<Q", self.p, o)[0]

        self.pe = self.u32(0x3C)
        self.coff = self.pe + 4
        self.numsec = self.u16(self.coff + 2)
        self.optsz = self.u16(self.coff + 16)
        self.opt = self.coff + 20
        if self.u16(self.opt) != 0x20B:
            raise RuntimeError("Expected PE32+ managed module")

        self.section_alignment = self.u32(self.opt + 32)
        self.file_alignment = self.u32(self.opt + 36)
        self.size_code_off = self.opt + 4
        self.size_image_off = self.opt + 56
        self.size_headers = self.u32(self.opt + 60)
        self.sec_table = self.opt + self.optsz
        self.dd = self.opt + 112

        self.sections = []
        for i in range(self.numsec):
            o = self.sec_table + i * 40
            self.sections.append(
                {
                    "o": o,
                    "name": bytes(self.p[o:o + 8]).rstrip(b"\0").decode(errors="replace"),
                    "vs": self.u32(o + 8),
                    "va": self.u32(o + 12),
                    "rs": self.u32(o + 16),
                    "rp": self.u32(o + 20),
                }
            )

    def rva2off(self, rva: int) -> int:
        for s in self.sections:
            if s["va"] <= rva < s["va"] + max(s["vs"], s["rs"]):
                return s["rp"] + (rva - s["va"])
        raise RuntimeError(f"RVA not mapped: {rva:#x}")

    def w16(self, offset: int, value: int) -> None:
        struct.pack_into("<H", self.p, offset, value)

    def w32(self, offset: int, value: int) -> None:
        struct.pack_into("<I", self.p, offset, value)


def parse_metadata(pe: PE):
    p = pe.p
    u16, u32, u64 = pe.u16, pe.u32, pe.u64

    cli_rva = u32(pe.dd + 14 * 8)
    cli = pe.rva2off(cli_rva)
    metadata_root = pe.rva2off(u32(cli + 8))
    if p[metadata_root:metadata_root + 4] != b"BSJB":
        raise RuntimeError("Invalid CLR metadata root")

    version_length = u32(metadata_root + 12)
    pos = align(metadata_root + 16 + version_length, 4)
    stream_count = u16(pos + 2)
    pos += 4

    streams = {}
    for _ in range(stream_count):
        rel = u32(pos)
        size = u32(pos + 4)
        start = pos + 8
        end = p.index(0, start)
        name = bytes(p[start:end]).decode()
        streams[name] = (metadata_root + rel, size)
        pos = align(end + 1, 4)

    tables_off, _ = streams["#~"]
    heap_sizes = p[tables_off + 6]
    valid = u64(tables_off + 8)
    pos = tables_off + 24
    rows = {}
    for table in range(64):
        if valid >> table & 1:
            rows[table] = u32(pos)
            pos += 4

    str_size = 4 if heap_sizes & 1 else 2
    guid_size = 4 if heap_sizes & 2 else 2
    blob_size = 4 if heap_sizes & 4 else 2

    def index_size(table: int) -> int:
        return 2 if rows.get(table, 0) < 65536 else 4

    def coded_size(bits: int, *tables: int) -> int:
        max_rows = max([rows.get(t, 0) for t in tables] or [0])
        return 2 if max_rows < (1 << (16 - bits)) else 4

    sizes = {
        0: 2 + str_size + guid_size * 3,
        1: coded_size(2, 0, 26, 35, 1) + str_size * 2,
        2: 4 + str_size * 2 + coded_size(2, 2, 1, 27) + index_size(4) + index_size(6),
        3: index_size(4),
        4: 2 + str_size + blob_size,
        5: index_size(6),
        6: 4 + 2 + 2 + str_size + blob_size + index_size(8),
        7: index_size(8),
        8: 2 + 2 + str_size,
        9: index_size(2) + coded_size(2, 2, 1, 27),
        10: coded_size(3, 2, 1, 26, 6, 27) + str_size + blob_size,
    }

    starts = {}
    cur = pos
    for table in range(11):
        if table in rows:
            if table not in sizes:
                raise RuntimeError(f"Unsupported metadata table before MemberRef: {table}")
            starts[table] = cur
            cur += rows[table] * sizes[table]

    strings_off, _ = streams["#Strings"]

    def get_string(index: int) -> str:
        if index == 0:
            return ""
        end = p.index(0, strings_off + index)
        return bytes(p[strings_off + index:end]).decode(errors="replace")

    methods = {}
    for rid in range(1, rows.get(6, 0) + 1):
        row = starts[6] + (rid - 1) * sizes[6]
        name_index = int.from_bytes(p[row + 8:row + 8 + str_size], "little")
        methods[get_string(name_index)] = {
            "rid": rid,
            "row": row,
            "rva": u32(row),
            "token": 0x06000000 | rid,
        }

    fields = {}
    for rid in range(1, rows.get(4, 0) + 1):
        row = starts[4] + (rid - 1) * sizes[4]
        name_index = int.from_bytes(p[row + 2:row + 2 + str_size], "little")
        fields[get_string(name_index)] = {
            "rid": rid,
            "row": row,
            "token": 0x04000000 | rid,
        }

    members = {}
    member_parent_size = coded_size(3, 2, 1, 26, 6, 27)
    for rid in range(1, rows.get(10, 0) + 1):
        row = starts[10] + (rid - 1) * sizes[10]
        name_index = int.from_bytes(
            p[row + member_parent_size:row + member_parent_size + str_size], "little"
        )
        members.setdefault(get_string(name_index), []).append(
            {"rid": rid, "row": row, "token": 0x0A000000 | rid}
        )

    return {
        "methods": methods,
        "fields": fields,
        "members": members,
        "rows": rows,
        "streams": streams,
        "metadata_root": metadata_root,
    }


class IL:
    def __init__(self):
        self.data = bytearray()
        self.labels = {}
        self.fixups = []

    def op(self, *values: int) -> None:
        self.data.extend(values)

    def token(self, opcode: int, token: int) -> None:
        self.op(opcode)
        self.data.extend(struct.pack("<I", token))

    def mark(self, name: str) -> None:
        self.labels[name] = len(self.data)

    def branch(self, opcode: int, label: str) -> None:
        self.op(opcode)
        self.fixups.append((len(self.data), label))
        self.data.extend(b"\0\0\0\0")

    def finish(self) -> bytes:
        for pos, label in self.fixups:
            struct.pack_into("<i", self.data, pos, self.labels[label] - (pos + 4))
        return bytes(self.data)


def make_watchdog_helper(metadata) -> bytes:
    fields = metadata["fields"]
    methods = metadata["methods"]
    members = metadata["members"]

    required_fields = [
        "MAX_RETRY_COUNT",
        "FACE_TRACKER_DATA_TIMEOUT_MS",
        "retryCount",
        "NewEyeData",
        "NewLipData",
        "EyeTrackerInited",
        "LipTrackerInited",
        "InitFaceTrackerWorker",
    ]
    for name in required_fields:
        if name not in fields:
            raise RuntimeError(f"Missing field {name}")
    if "StopFaceTracking" not in methods:
        raise RuntimeError("Missing StopFaceTracking")

    is_alive = members.get("get_IsAlive", [])
    if len(is_alive) != 1:
        raise RuntimeError(f"Expected one Thread.get_IsAlive MemberRef, got {len(is_alive)}")

    il = IL()

    def ldsfld(name: str) -> None:
        il.token(0x7E, fields[name]["token"])

    def stsfld(name: str) -> None:
        il.token(0x80, fields[name]["token"])

    # Native OnVSSettingChange callbacks pass a non-null setting string.
    # Only the internal Update() call uses null, so native callback semantics remain no-op.
    il.op(0x02)  # ldarg.0
    il.branch(0x3A, "ret")  # brtrue

    # retryCount == -1 is the private watchdog-mode marker.
    ldsfld("retryCount")
    il.op(0x15)  # ldc.i4.m1
    il.branch(0x3B, "watch")  # beq

    # Before/after tracking initialization, keep the original init constants restored.
    ldsfld("EyeTrackerInited")
    il.branch(0x3A, "maybe_mode")
    ldsfld("LipTrackerInited")
    il.branch(0x3A, "maybe_mode")
    il.op(0x1B)  # ldc.i4.5
    stsfld("MAX_RETRY_COUNT")
    il.op(0x20)
    il.data.extend(struct.pack("<i", 3000))
    stsfld("FACE_TRACKER_DATA_TIMEOUT_MS")
    il.branch(0x38, "ret")

    # Enter watchdog mode only after InitFaceTrackerWorker has finished.
    il.mark("maybe_mode")
    ldsfld("InitFaceTrackerWorker")
    il.branch(0x39, "set_mode")  # brfalse
    ldsfld("InitFaceTrackerWorker")
    il.token(0x6F, is_alive[0]["token"])  # callvirt Thread.get_IsAlive()
    il.branch(0x3A, "ret")
    il.mark("set_mode")
    il.op(0x15)
    stsfld("retryCount")
    il.op(0x16)
    stsfld("MAX_RETRY_COUNT")
    il.op(0x16)
    stsfld("FACE_TRACKER_DATA_TIMEOUT_MS")
    il.branch(0x38, "ret")

    # Eye heartbeat. NewEyeData is observed before the original Update() clears it.
    il.mark("watch")
    ldsfld("EyeTrackerInited")
    il.branch(0x39, "lip")
    ldsfld("NewEyeData")
    il.branch(0x39, "eye_inc")
    il.op(0x16)
    stsfld("FACE_TRACKER_DATA_TIMEOUT_MS")
    il.branch(0x38, "eye_test")
    il.mark("eye_inc")
    ldsfld("FACE_TRACKER_DATA_TIMEOUT_MS")
    il.op(0x1F, TICK_MS)
    il.op(0x58)
    stsfld("FACE_TRACKER_DATA_TIMEOUT_MS")
    il.mark("eye_test")
    ldsfld("FACE_TRACKER_DATA_TIMEOUT_MS")
    il.op(0x20)
    il.data.extend(struct.pack("<i", TIMEOUT_MS))
    il.branch(0x3D, "restart")  # bgt

    # Lip heartbeat, independently.
    il.mark("lip")
    ldsfld("LipTrackerInited")
    il.branch(0x39, "ret")
    ldsfld("NewLipData")
    il.branch(0x39, "lip_inc")
    il.op(0x16)
    stsfld("MAX_RETRY_COUNT")
    il.branch(0x38, "lip_test")
    il.mark("lip_inc")
    ldsfld("MAX_RETRY_COUNT")
    il.op(0x1F, TICK_MS)
    il.op(0x58)
    stsfld("MAX_RETRY_COUNT")
    il.mark("lip_test")
    ldsfld("MAX_RETRY_COUNT")
    il.op(0x20)
    il.data.extend(struct.pack("<i", TIMEOUT_MS))
    il.branch(0x3D, "restart")
    il.branch(0x38, "ret")

    il.mark("restart")
    il.token(0x28, methods["StopFaceTracking"]["token"])
    il.op(0x1B)
    stsfld("MAX_RETRY_COUNT")
    il.op(0x20)
    il.data.extend(struct.pack("<i", 3000))
    stsfld("FACE_TRACKER_DATA_TIMEOUT_MS")

    il.mark("ret")
    il.op(0x2A)
    return il.finish()


def make_fat_body(
    code: bytes,
    max_stack: int,
    local_sig: int = 0,
    init_locals: bool = False,
    extra_sections: bytes = b"",
) -> bytes:
    flags = 0x3
    if init_locals:
        flags |= 0x10
    if extra_sections:
        flags |= 0x8
    header = flags | (3 << 12)

    body = bytearray(struct.pack("<HHII", header, max_stack, len(code), local_sig))
    body.extend(code)
    while len(body) % 4:
        body.append(0)
    body.extend(extra_sections)
    return bytes(body)


def read_method_body(pe: PE, rva: int):
    p = pe.p
    offset = pe.rva2off(rva)
    first = p[offset]

    if first & 3 == 2:
        code_size = first >> 2
        return {
            "flags": 2,
            "max_stack": 8,
            "local_sig": 0,
            "code": bytes(p[offset + 1:offset + 1 + code_size]),
            "extra": b"",
        }

    flags_and_size = pe.u16(offset)
    flags = flags_and_size & 0x0FFF
    header_size = ((flags_and_size >> 12) & 0xF) * 4
    max_stack = pe.u16(offset + 2)
    code_size = pe.u32(offset + 4)
    local_sig = pe.u32(offset + 8)
    code = bytes(p[offset + header_size:offset + header_size + code_size])

    pos = align(offset + header_size + code_size, 4)
    extra = b""
    if flags & 0x8:
        start = pos
        more = True
        while more:
            kind = p[pos]
            fat = bool(kind & 0x40)
            more = bool(kind & 0x80)
            if fat:
                data_size = p[pos + 1] | (p[pos + 2] << 8) | (p[pos + 3] << 16)
            else:
                data_size = p[pos + 1]
            pos += align(data_size, 4)
        extra = bytes(p[start:pos])

    return {
        "flags": flags,
        "max_stack": max_stack,
        "local_sig": local_sig,
        "code": code,
        "extra": extra,
    }


def shift_exception_offsets(extra: bytes, delta: int) -> bytes:
    if not extra:
        return b""

    data = bytearray(extra)
    pos = 0
    while pos < len(data):
        kind = data[pos]
        fat = bool(kind & 0x40)
        more = bool(kind & 0x80)

        if fat:
            data_size = data[pos + 1] | (data[pos + 2] << 8) | (data[pos + 3] << 16)
            count = (data_size - 4) // 24
            for i in range(count):
                row = pos + 4 + i * 24
                flags = struct.unpack_from("<I", data, row)[0]
                for field_offset in (row + 4, row + 12):
                    old = struct.unpack_from("<I", data, field_offset)[0]
                    struct.pack_into("<I", data, field_offset, old + delta)
                if flags & 1:  # filter clause
                    old = struct.unpack_from("<I", data, row + 20)[0]
                    struct.pack_into("<I", data, row + 20, old + delta)
        else:
            data_size = data[pos + 1]
            count = (data_size - 4) // 12
            for i in range(count):
                row = pos + 4 + i * 12
                flags = struct.unpack_from("<H", data, row)[0]
                struct.pack_into(
                    "<H", data, row + 2, struct.unpack_from("<H", data, row + 2)[0] + delta
                )
                struct.pack_into(
                    "<H", data, row + 5, struct.unpack_from("<H", data, row + 5)[0] + delta
                )
                if flags & 1:
                    old = struct.unpack_from("<I", data, row + 8)[0]
                    struct.pack_into("<I", data, row + 8, old + delta)

        pos += align(data_size, 4)
        if not more:
            break

    return bytes(data)


def main(path: Path) -> None:
    original = path.read_bytes()
    baseline_hash = hashlib.sha256(original).hexdigest()
    if baseline_hash != EXPECTED_SHA256:
        raise RuntimeError(
            f"Input must be the exact verified v1.0.1 DLL: {baseline_hash}"
        )

    image = bytearray(original)
    pe = PE(image)
    metadata = parse_metadata(pe)

    for name in ("OnVSSettingChange", "Update", "StopFaceTracking"):
        if name not in metadata["methods"]:
            raise RuntimeError(f"Missing method {name}")

    helper_code = make_watchdog_helper(metadata)
    helper_body = make_fat_body(helper_code, max_stack=4)

    update = read_method_body(pe, metadata["methods"]["Update"]["rva"])
    prefix = (
        bytes([0x14, 0x28])
        + struct.pack("<I", metadata["methods"]["OnVSSettingChange"]["token"])
    )
    updated_update_code = prefix + update["code"]
    updated_extra = shift_exception_offsets(update["extra"], len(prefix))
    updated_update_body = make_fat_body(
        updated_update_code,
        max_stack=max(1, update["max_stack"]),
        local_sig=update["local_sig"],
        init_locals=bool(update["flags"] & 0x10),
        extra_sections=updated_extra,
    )

    # Append one new executable section. Existing section payloads remain in place.
    last = max(pe.sections, key=lambda s: s["va"])
    new_va = align(last["va"] + max(last["vs"], last["rs"]), pe.section_alignment)
    new_raw = align(len(image), pe.file_alignment)

    payload = bytearray(helper_body)
    while len(payload) % 4:
        payload.append(0)
    update_offset = len(payload)
    payload.extend(updated_update_body)

    new_virtual_size = len(payload)
    new_raw_size = align(new_virtual_size, pe.file_alignment)

    if len(image) < new_raw:
        image.extend(b"\0" * (new_raw - len(image)))
    image.extend(payload)
    image.extend(b"\0" * (new_raw + new_raw_size - len(image)))

    new_section_header = pe.sec_table + pe.numsec * 40
    if new_section_header + 40 > pe.size_headers:
        raise RuntimeError("No PE header room for watchdog section")

    image[new_section_header:new_section_header + 8] = b".fvwdog\0"
    struct.pack_into(
        "<IIIIIIHHI",
        image,
        new_section_header + 8,
        new_virtual_size,
        new_va,
        new_raw_size,
        new_raw,
        0,
        0,
        0,
        0,
        0x60000020,
    )

    pe.p = image
    pe.w16(pe.coff + 2, pe.numsec + 1)
    pe.w32(pe.size_code_off, pe.u32(pe.size_code_off) + new_raw_size)
    pe.w32(pe.size_image_off, align(new_va + new_virtual_size, pe.section_alignment))

    # Only these two existing metadata cells change: MethodDef RVA for helper and Update.
    pe.w32(metadata["methods"]["OnVSSettingChange"]["row"], new_va)
    pe.w32(metadata["methods"]["Update"]["row"], new_va + update_offset)

    patched = bytes(image)

    # Verify original section payloads. The only permitted in-section changes are
    # the two 4-byte MethodDef RVA fields in CLR metadata.
    allowed = set()
    for row in (
        metadata["methods"]["OnVSSettingChange"]["row"],
        metadata["methods"]["Update"]["row"],
    ):
        allowed.update(range(row, row + 4))

    for section in pe.sections:
        before = original[section["rp"]:section["rp"] + section["rs"]]
        after = patched[section["rp"]:section["rp"] + section["rs"]]
        if before == after:
            continue

        changed = [
            section["rp"] + i
            for i, (a, b) in enumerate(zip(before, after))
            if a != b
        ]
        unexpected = [offset for offset in changed if offset not in allowed]
        if unexpected:
            raise RuntimeError(
                f"Unexpected mutation inside existing section {section['name']}: "
                f"{unexpected[:8]}"
            )

    path.write_bytes(patched)

    print("Applied PE-preserving callback watchdog.")
    print(f"v1.0.1 baseline SHA-256: {baseline_hash}")
    print(f"Patched DLL SHA-256: {hashlib.sha256(patched).hexdigest()}")
    print(
        f"Added section .fvwdog RVA={new_va:#x} raw={new_raw:#x} "
        f"size={new_virtual_size}"
    )
    print(
        "Existing section payloads preserved; only two MethodDef RVA cells changed "
        "inside metadata."
    )
    print(
        "No metadata rows, strings, GUIDs, blobs, AssemblyRefs, Fields, or Methods "
        "were added."
    )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(
            "Usage: pe_watchdog_patcher.py <ViveFocusVisionFTTrackingModule.dll>"
        )
    main(Path(sys.argv[1]))
