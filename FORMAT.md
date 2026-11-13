# Red Dead Redemption save format, PC <-> Switch

Everything is little-endian. The reference implementation is `rdr_save_convert.py`.

## What is verified

| Claim | Status |
|---|---|
| PC -> Switch conversion as described here | Confirmed in game (main game and Undead Nightmare saves loaded on a Switch) |
| Cipher, key, pass count | Known-answer test below; all PC saves tried decrypt to valid record lists |
| Header checksum rule, both platforms | Matches every PC and Switch file tried |
| Switch -> PC | Exact inverse; byte-exact on PC -> Switch -> PC round trips |
| PC game loading a save that began on the Switch | **Not tested** |

## The two formats

Same file; only these differ:

| | PC | Switch |
|---|---|---|
| Body (offset `0x540` to end) | encrypted | plain |
| Bytes `0x53A-0x53B` | `77 77` | `00 00` |
| Checksum at offset 4 | CRC32 of the file as stored (encrypted body) | CRC32 of the file as stored (plain body) |

### Header (`0x000-0x53F`, never encrypted)

| Offset | Size | Meaning |
|---|---|---|
| `0x00` | u32 | `1` |
| `0x04` | u32 | **CRC32 of `file[0x20:]`** (zlib CRC32) of the file exactly as written to disk |
| `0x08` | u32 | file length minus `0x20` |
| `0x0C` | u32 | same value again |
| `0x10` | 16 bytes | junk, outside the CRC range; differs per platform. Copied unchanged |
| `0x20` | 8 bytes | `METAXTR\0` magic |
| `0x28` | 4 bytes | `01 A0 09 00` |
| `0x2C` | u32 | `0x518` (header ends at `0x28 + 0x518 = 0x540`) |
| `0x30` | ... | save metadata (timestamp-like value, UTF-16 date/title text, filler). Copied unchanged |
| `0x538` | u16 | `7` in game saves, `5` in options/extras files |
| `0x53A` | u16 | **`0x7777` on PC, `0x0000` on Switch** |
| `0x53C` | u32 | record count (`83` in a game save) |

### Body (`0x540` to end of file)

Records back to back, ending exactly at end of file:

```
u32  name_length        (1..80)
char name[name_length]  (ASCII identifier, e.g. gbGameProgression)
u8   type               (<= 20 in all files seen)
u32  data_size
u8   data[data_size]
```

The record count equals the u32 at `0x53C`. Record order differs between saves. A game save is 113071 bytes.

### Encryption (PC only)

- AES-256, ECB, no IV, no padding.
- **The block cipher is applied 16 times** to every block (the usual RAGE engine scheme). A single pass gives garbage.
- Key (fixed; it is the game's RPF archive key, published in open-source RAGE tools):
  `B762DFB6E2B2C6DEAF722A32D2FB6F0C98A3217462C9C4EDADAA2ED0DDF92F10`
- Applies to `file[0x540:]`, whole 16-byte blocks only. **The trailing partial block (15 bytes in a game save) is stored plain** on PC; copy it unchanged in both directions.

Known-answer test: 16 encrypt passes of 16 zero bytes = `1BDACADA1EFD71EF39B9E613FCCF3D85`.

## PC -> Switch

1. Require length > `0x540` and `file[0x20:0x28] == "METAXTR\0"`.
2. `out = file[0:0x540] + decrypt16(file[0x540:])` (tail unchanged).
3. Set `out[0x53A] = out[0x53B] = 0x00`.
4. Write `CRC32(out[0x20:])` as u32 at offset 4.
5. Walk the records from `0x540`: they must end exactly at end of file. If not, refuse.

## Switch -> PC

1. Same magic check; validate the plain record list first.
2. `out = file[0:0x540] + encrypt16(file[0x540:])` (tail unchanged).
3. Set `out[0x53A] = out[0x53B] = 0x77`.
4. Write `CRC32(out[0x20:])` at offset 4 (over the encrypted file, after step 3).

## Telling the formats apart

A file is Switch format if its record list parses to end of file as-is; otherwise decrypt and require the list to parse.
`77 77` vs `00 00` at `0x53A` is only a hint.

## Files

| File | PC | Switch | Convert? |
|---|---|---|---|
| `RDR2SAVE0-3.SAV` | yes | yes | yes (main game) |
| `RDR2ZOMBIESAVE0-3.SAV` | yes | yes | yes (Undead Nightmare) |
| `RDR2EXTRAS.SAV` | yes | no | no (PC only) |
| `RDR2OPTIONS.SAV` | no | yes | no (Switch only) |
| `PREBOOT.SAV`, `.nx_save_meta.bin` | no | yes | no (belong to the Switch user; no METAXTR in PREBOOT) |

- PC: the folder holding the `RDR2SAVE*.SAV` files (your PC profile folder)
- Switch: via JKSV backup/restore zips; the zip is flat with the files above at the top level.
- The slot is only the number in the file name.

## Open risks (Switch -> PC)

A save created on the Switch differs from a PC one in two header areas that the conversion copies unchanged: the junk at
`0x10-0x1F` and the metadata from `0x30` (a timestamp-like value on PC, a small number on Switch). If the PC game rejects
such a save or shows a wrong date, look there first. Whether the PC game needs `77 77` at `0x53A` is unknown; writing it
reproduces PC files exactly.
