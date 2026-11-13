# rdr1-switch-save-converter

Convert **Red Dead Redemption** save files between the **PC version** and the
**Nintendo Switch** version, in both directions. Main game and Undead Nightmare.

- **PC -> Switch: confirmed in game.** Converted main-game and Undead Nightmare saves loaded on a Switch.
- **Switch -> PC:** byte-exact on round trips, but **not yet tested in the PC game with a save that began on the Switch.**
  Back up your PC profile folder first and try a spare slot. Reports welcome.
- Tested with one user's saves, one PC build and one Switch build.

Unofficial fan tool, not affiliated with Rockstar Games or Nintendo. Use at your own risk and keep backups.
Input files are never modified.

## Requirements

- Python 3.8+ (tkinter is included with the normal Windows installer)
- `pip install -r requirements.txt` (pycryptodome)
- For the Switch side: a hacked Switch with [JKSV](https://github.com/J-D-K/JKSV) to back up and restore save data

## GUI

Double-click `rdr_save_gui.bat`, or run `python rdr_save_gui.py`.

1. Pick a source: PC profile folder, a folder of Switch saves, a JKSV backup `.zip`, or individual files.
2. Choose the target (Automatic converts each file to the opposite format).
3. Tick the saves to convert. Double-click an Output name to change its slot.
4. Pick an output folder, optionally tick **Also build JKSV restore zip**, then **Convert**.

## Command line

```
python rdr_save_convert.py convert "C:\path\to\pc\profile" -o out
python rdr_save_convert.py convert switch_backup.zip -o pc_out
python rdr_save_convert.py convert profile -o out --rename RDR2ZOMBIESAVE1.SAV=RDR2ZOMBIESAVE2.SAV
python rdr_save_convert.py convert profile -o out --jksv-base MyBackup.zip --jksv-out restore.zip
python rdr_save_convert.py selftest --saves profile
```

Direction is detected per file; `--to switch|pc` forces it. Folders and zips only pick up `RDR2SAVEn.SAV` and
`RDR2ZOMBIESAVEn.SAV`; name a file explicitly to convert anything else. Garbage, truncated files and `PREBOOT.SAV` are
refused, and nothing is written if any output name clashes or would overwrite an input.

## Moving saves

**PC -> Switch**
1. On the Switch, start a new game, save once, and make a JKSV backup (this supplies the files that belong to your
   Switch/user: `.nx_save_meta.bin`, `PREBOOT.SAV`, `RDR2OPTIONS.SAV`). Copy that zip to the PC.
2. Convert your PC saves with the restore zip option, using that backup as the base.
3. Copy the restore zip to `sdmc:/JKSV/Red Dead Redemption/`.
4. In JKSV, **turn off "auto backup on restore" first**. With it on, the restore does nothing and JKSV overwrites the
   zip with your current save. Then restore the zip and check it kept its original size.

**Switch -> PC**
1. Make a JKSV backup, copy the zip to the PC, convert it (the GUI and CLI accept the zip directly).
2. Close the game, back up your PC profile folder (where the `RDR2SAVE*.SAV` files are), copy the converted `.SAV` files in.

The slot is only the number in the file name, so a save can be renamed into any slot.
`RDR2EXTRAS.SAV` (PC only) and `RDR2OPTIONS.SAV` (Switch only) are not meant to be moved across.

## How it works

See [FORMAT.md](FORMAT.md): the two files are the same layout, the PC one has its body encrypted
(AES-256 ECB, 16 passes, the key the game uses for its archives) and a different checksum input.

## License

MIT, see [LICENSE](LICENSE).
