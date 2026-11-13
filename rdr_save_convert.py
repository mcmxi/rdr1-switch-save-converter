#!/usr/bin/env python3
r"""Red Dead Redemption save converter, PC <-> Nintendo Switch. Format: FORMAT.md

Needs Python 3.8+ and pycryptodome (pip install pycryptodome).

  convert  Convert saves. Direction is detected per file (plain record list = Switch, else PC).
           INPUT may be .SAV files, folders (only RDR2SAVEn / RDR2ZOMBIESAVEn are taken) or a JKSV
           backup .zip (same name filter). Never modifies or overwrites an input; writes nothing on failure.
             rdr_save_convert.py convert "C:\path\to\pc\profile" -o switch_out
             rdr_save_convert.py convert switch_backup.zip -o pc_out
             rdr_save_convert.py convert profile -o out --to switch --rename RDR2ZOMBIESAVE1.SAV=RDR2ZOMBIESAVE2.SAV
           Add --jksv-base MY_BACKUP.zip --jksv-out restore.zip to also build a JKSV restore zip
           (your own Switch backup supplies .nx_save_meta.bin, PREBOOT.SAV, RDR2OPTIONS.SAV).
  zip      Build a JKSV restore zip from already converted Switch files.
  selftest Cipher known-answer test; with --saves FOLDER_OR_ZIP also byte-exact round trips on your saves.
"""
import argparse, hashlib, os, re, struct, sys, zipfile, zlib

try:
    from Crypto.Cipher import AES
except ImportError:
    sys.exit('Missing pycryptodome. Install it with:  pip install pycryptodome')

KEY = bytes.fromhex('b762dfb6e2b2c6deaf722a32d2fb6f0c98a3217462c9c4edadaa2ed0ddf92f10')
PASSES = 16
HEADER = 0x540
NAME = re.compile(rb'[A-Za-z_][A-Za-z0-9_]{0,78}\Z')
SAVE_NAME = re.compile(r'RDR2(ZOMBIE)?SAVE\d\.SAV\Z', re.I)


class SaveError(Exception):
    pass


def crypt(data, decrypt):
    """RAGE cipher on all whole 16-byte blocks; a trailing partial block is left unchanged."""
    whole = len(data) - len(data) % 16
    aes = AES.new(KEY, AES.MODE_ECB)
    step = aes.decrypt if decrypt else aes.encrypt
    block = bytes(data[:whole])
    for _ in range(PASSES):
        block = step(block)
    return block + bytes(data[whole:])


def count_records(buf):
    """Record count if the list from HEADER ends exactly at EOF, else None."""
    p, n, size = HEADER, 0, len(buf)
    while p < size:
        if p + 9 > size:
            return None
        ln = struct.unpack_from('<I', buf, p)[0]
        if not 1 <= ln <= 80 or p + 9 + ln > size or not NAME.match(buf[p + 4:p + 4 + ln]):
            return None
        if buf[p + 4 + ln] > 20:
            return None
        p += 9 + ln + struct.unpack_from('<I', buf, p + 5 + ln)[0]
        if p > size:
            return None
        n += 1
    return n if n else None


def finish(header, body, marker):
    out = bytearray(header + body)
    out[0x53A] = out[0x53B] = marker
    struct.pack_into('<I', out, 4, zlib.crc32(bytes(out[0x20:])) & 0xFFFFFFFF)
    return bytes(out)


def detect(data):
    """Return ('switch'|'pc', plain_file_bytes, record_count). Raises SaveError."""
    if len(data) <= HEADER or data[0x20:0x28] != b'METAXTR\0':
        raise SaveError('not a Red Dead Redemption save (no METAXTR header)')
    n = count_records(data)
    if n is not None:
        return 'switch', data, n
    plain = data[:HEADER] + crypt(data[HEADER:], True)
    n = count_records(plain)
    if n is None:
        raise SaveError('record list does not parse as Switch or PC format (damaged or not a save)')
    return 'pc', plain, n


def to_switch(data):
    kind, plain, n = detect(data)
    if kind != 'switch':
        plain = finish(plain[:HEADER], plain[HEADER:], 0x00)
    return kind, plain, n


def to_pc(data):
    kind, plain, n = detect(data)
    if kind == 'pc':
        return kind, data, n
    enc = finish(plain[:HEADER], crypt(plain[HEADER:], False), 0x77)
    return kind, enc, n


def convert_bytes(data, target):
    """target 'switch' | 'pc' | None (auto: opposite of detected). Returns (src_kind, dst_kind, out, n)."""
    kind, _, _ = detect(data)
    dst = target or ('pc' if kind == 'switch' else 'switch')
    out = (to_switch if dst == 'switch' else to_pc)(data)[1]
    return kind, dst, out, detect(out)[2]


# ---------------------------------------------------------------- input gathering
def gather(inputs):
    """Yield (display_name, file_name, bytes). Explicit files are taken as is; folders/zips are name-filtered."""
    for src in inputs:
        if os.path.isdir(src):
            for f in sorted(os.listdir(src)):
                if SAVE_NAME.match(f):
                    yield os.path.join(src, f), f, open(os.path.join(src, f), 'rb').read()
        elif zipfile.is_zipfile(src):
            with zipfile.ZipFile(src) as z:
                for i in sorted(z.namelist()):
                    if SAVE_NAME.match(i):
                        yield '%s!%s' % (src, i), i, z.read(i)
        elif os.path.isfile(src):
            yield src, os.path.basename(src), open(src, 'rb').read()
        else:
            print('FAIL  %s: not found' % src)
            yield src, None, None


def build_zip(base, out, files):
    """files: {name_in_zip: bytes}, all Switch format. Base zip supplies the Switch/user-owned files."""
    for name, data in files.items():
        if detect(data)[0] != 'switch' or struct.unpack_from('<I', data, 4)[0] != zlib.crc32(data[0x20:]) & 0xFFFFFFFF:
            raise SaveError('%s is not a valid Switch-format save' % name)
    tmp = out + '.part'
    with zipfile.ZipFile(base) as zin, zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            if item.filename not in files:
                zout.writestr(item.filename, zin.read(item.filename))
        for name, data in files.items():
            zout.writestr(name, data)
    os.replace(tmp, out)
    with zipfile.ZipFile(out) as z:
        for i in z.infolist():
            print('  %-26s %d' % (i.filename, i.file_size))


def same_path(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


# ---------------------------------------------------------------- commands
def cmd_convert(a):
    target = {'switch': 'switch', 'pc': 'pc'}.get(a.to)
    renames = dict(r.split('=', 1) for r in a.rename or [])
    results, failed = [], 0
    for disp, name, data in gather(a.inputs):
        if name is None:
            failed += 1
            continue
        try:
            src, dst, out, n = convert_bytes(data, target)
        except SaveError as e:
            print('FAIL  %s: %s' % (disp, e))
            failed += 1
            continue
        name = renames.get(name, name)
        results.append((disp, name, src, dst, out, n, data))
    if not results:
        print('Nothing converted.')
        return 1
    if a.jksv_out and not a.jksv_base or a.jksv_base and not a.jksv_out:
        sys.exit('--jksv-base and --jksv-out go together')
    if a.jksv_out and any(r[3] != 'switch' for r in results):
        sys.exit('JKSV zip needs Switch-format output: use --to switch (inputs must not be mixed)')
    seen, clash = set(), False
    for disp, name, *_ in results:
        dest = os.path.join(a.out, name)
        if dest.lower() in seen:
            print('FAIL  %s: output name %s used twice (check --rename)' % (disp, name))
            clash = True
        seen.add(dest.lower())
        if os.path.isfile(disp) and same_path(dest, disp):
            print('FAIL  %s: output would overwrite the input; pick another -o folder' % disp)
            clash = True
    if clash:
        print('Nothing written.')
        return 1
    os.makedirs(a.out, exist_ok=True)
    for disp, name, src, dst, out, n, data in results:
        dest = os.path.join(a.out, name)
        if src == dst:
            print('NOTE  %s is already %s format; copied unchanged' % (disp, dst))
            out = data
        with open(dest, 'wb') as f:
            f.write(out)
        print('OK    %s (%s) -> %s (%s, %d bytes, %d records)' % (disp, src, dest, dst, len(out), n))
    if a.jksv_out and failed:
        print('JKSV zip not built because some inputs failed.')
    elif a.jksv_out:
        files = {name: out for _, name, _, _, out, _, _ in results}
        if any(same_path(a.jksv_out, p) for p in (a.jksv_base,)):
            sys.exit('--jksv-out must differ from --jksv-base')
        print('JKSV zip:')
        build_zip(a.jksv_base, a.jksv_out, files)
        print('wrote', a.jksv_out)
    return 1 if failed else 0


def cmd_zip(a):
    files = {}
    for s in a.saves:
        path, _, name = s.partition('=')
        files[name or os.path.basename(path)] = open(path, 'rb').read()
    if same_path(a.out, a.base):
        sys.exit('--out must differ from --base')
    try:
        build_zip(a.base, a.out, files)
    except SaveError as e:
        sys.exit('FAIL: %s' % e)
    print('wrote', a.out)
    return 0


def cmd_selftest(a):
    ok = True

    def check(label, cond):
        nonlocal ok
        print('%s  %s' % ('PASS' if cond else 'FAIL', label))
        ok &= bool(cond)

    kat = crypt(b'\0' * 16, False)
    check('cipher known-answer (16 passes of zero block)', kat.hex().upper() == '1BDACADA1EFD71EF39B9E613FCCF3D85')
    check('decrypt inverts encrypt', crypt(crypt(bytes(range(48)) + b'tail', False), True) == bytes(range(48)) + b'tail')
    for label, d in {'garbage': os.urandom(4096), 'truncated file': b'\0' * 100}.items():
        try:
            detect(d)
            check('%s refused' % label, False)
        except SaveError:
            check('%s refused' % label, True)
    if a.saves:
        for disp, name, data in gather([a.saves]):
            try:
                kind, _, n = detect(data)
            except SaveError as e:
                check('%s parses' % name, False)
                continue
            other = 'pc' if kind == 'switch' else 'switch'
            mid = convert_bytes(data, other)[2]
            back = convert_bytes(mid, kind)[2]
            check('%s (%s, %d records): round trip %s -> %s -> %s byte-exact' % (name, kind, n, kind, other, kind), back == data)
    else:
        print('SKIP  round trips (pass --saves FOLDER_OR_ZIP with your own saves to run them)')
    print('ALL PASSED' if ok else 'SOME TESTS FAILED')
    return 0 if ok else 1

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('convert', help='convert saves (direction auto-detected)')
    c.add_argument('inputs', nargs='+', help='.SAV files, folders, or a JKSV backup .zip')
    c.add_argument('-o', '--out', default='converted', help='output folder (default ./converted)')
    c.add_argument('--to', choices=['auto', 'switch', 'pc'], default='auto', help='force target format')
    c.add_argument('--rename', action='append', metavar='NAME=NEW', help='write input NAME as NEW (slot change); repeatable')
    c.add_argument('--jksv-base', help='your own JKSV backup zip; with --jksv-out also builds a restore zip')
    c.add_argument('--jksv-out', help='restore zip to write')
    c.set_defaults(fn=cmd_convert)
    z = sub.add_parser('zip', help='build JKSV restore zip from converted Switch saves')
    z.add_argument('--base', required=True)
    z.add_argument('--out', required=True)
    z.add_argument('saves', nargs='+', help='PATH or PATH=NAME_IN_ZIP')
    z.set_defaults(fn=cmd_zip)
    t = sub.add_parser('selftest', help='run known-answer and round-trip tests')
    t.add_argument('--saves', help='folder or JKSV zip of your saves for round-trip tests')
    t.set_defaults(fn=cmd_selftest)
    a = ap.parse_args()
    sys.exit(a.fn(a))


if __name__ == '__main__':
    main()
