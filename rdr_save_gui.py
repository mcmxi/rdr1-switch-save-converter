#!/usr/bin/env python3
"""GUI for the Red Dead Redemption save converter (PC <-> Switch). Engine: rdr_save_convert.py (same folder).

Run:  python rdr_save_gui.py      (needs Python 3.8+ with tkinter, and pycryptodome)
"""
import os, sys, tkinter as tk, zipfile
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rdr_save_convert as eng

PC_PROFILE = ''
LABEL = {'pc': 'PC', 'switch': 'Switch'}


class App:
    def __init__(self, root):
        self.root = root
        root.title('Red Dead Redemption save converter')
        root.geometry('860x620')
        self.rows = {}  # iid -> dict(disp, name, data, kind, n, include, out_name)
        self.src = tk.StringVar(value=PC_PROFILE if os.path.isdir(PC_PROFILE) else '')
        self.out = tk.StringVar(value=os.path.join(os.path.expanduser('~'), 'Desktop', 'RDR converted'))
        self.mode = tk.StringVar(value='auto')
        self.zip_on = tk.BooleanVar(value=False)
        self.zip_base = tk.StringVar()
        self.zip_out = tk.StringVar()
        self.build()
        if self.src.get():
            self.load()

    # ------------------------------------------------------------ layout
    def build(self):
        p = {'padx': 8, 'pady': 4}
        f = ttk.LabelFrame(self.root, text='1. Source (PC profile folder, Switch folder, JKSV backup .zip, or save files)')
        f.pack(fill='x', **p)
        ttk.Entry(f, textvariable=self.src).pack(side='left', fill='x', expand=True, padx=6, pady=6)
        for text, cmd in (('Folder...', self.pick_folder), ('Zip...', self.pick_zip), ('Files...', self.pick_files)):
            ttk.Button(f, text=text, command=cmd).pack(side='left', padx=2)
        ttk.Button(f, text='Reload', command=self.load).pack(side='left', padx=6)

        f = ttk.LabelFrame(self.root, text='2. Convert to')
        f.pack(fill='x', **p)
        for text, val in (('Automatic (opposite of each file)', 'auto'), ('Switch', 'switch'), ('PC', 'pc')):
            ttk.Radiobutton(f, text=text, value=val, variable=self.mode, command=self.refresh).pack(side='left', padx=8, pady=4)

        f = ttk.LabelFrame(self.root, text='3. Saves found  (click the first column to include/exclude; double-click the last to change the slot name)')
        f.pack(fill='both', expand=True, **p)
        cols = ('use', 'file', 'format', 'records', 'result', 'out')
        self.tree = ttk.Treeview(f, columns=cols, show='headings', height=9, selectmode='browse')
        for c, t, w in (('use', 'Use', 40), ('file', 'File', 260), ('format', 'Is', 70), ('records', 'Records', 70),
                        ('result', 'Becomes', 80), ('out', 'Output name', 250)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor='w')
        self.tree.pack(fill='both', expand=True, padx=6, pady=6)
        self.tree.bind('<Button-1>', self.on_click)
        self.tree.bind('<Double-1>', self.on_double)

        f = ttk.LabelFrame(self.root, text='4. Output')
        f.pack(fill='x', **p)
        r = ttk.Frame(f)
        r.pack(fill='x')
        ttk.Label(r, text='Folder:').pack(side='left', padx=6)
        ttk.Entry(r, textvariable=self.out).pack(side='left', fill='x', expand=True, pady=4)
        ttk.Button(r, text='Browse...', command=lambda: self.pick_dir(self.out)).pack(side='left', padx=6)
        r = ttk.Frame(f)
        r.pack(fill='x')
        ttk.Checkbutton(r, text='Also build JKSV restore zip (Switch output only)', variable=self.zip_on,
                        command=self.refresh).pack(side='left', padx=6)
        self.zip_frame = ttk.Frame(f)
        self.zip_frame.pack(fill='x')
        for label, var, cmd in (('Your Switch backup zip:', self.zip_base, self.pick_zip_base),
                                ('Restore zip to write:', self.zip_out, self.pick_zip_out)):
            r = ttk.Frame(self.zip_frame)
            r.pack(fill='x')
            ttk.Label(r, text=label, width=22).pack(side='left', padx=6)
            ttk.Entry(r, textvariable=var).pack(side='left', fill='x', expand=True, pady=2)
            ttk.Button(r, text='Browse...', command=cmd).pack(side='left', padx=6)

        r = ttk.Frame(self.root)
        r.pack(fill='x', **p)
        self.go = ttk.Button(r, text='Convert', command=self.convert)
        self.go.pack(side='left')
        ttk.Button(r, text='Open output folder', command=self.open_out).pack(side='left', padx=8)
        self.log = tk.Text(self.root, height=7, state='disabled', wrap='word')
        self.log.pack(fill='x', **p)
        self.say('Inputs are never modified. Close the game before copying converted files into the PC profile folder.')

    # ------------------------------------------------------------ helpers
    def say(self, msg):
        self.log.config(state='normal')
        self.log.insert('end', msg + '\n')
        self.log.see('end')
        self.log.config(state='disabled')

    def pick_folder(self):
        d = filedialog.askdirectory(initialdir=self.src.get() or None)
        if d:
            self.src.set(d)
            self.load()

    def pick_zip(self):
        f = filedialog.askopenfilename(filetypes=[('JKSV backup', '*.zip')])
        if f:
            self.src.set(f)
            self.load()

    def pick_files(self):
        fs = filedialog.askopenfilenames(filetypes=[('Saves', '*.SAV'), ('All', '*.*')])
        if fs:
            self.src.set(';'.join(fs))
            self.load()

    def pick_dir(self, var):
        d = filedialog.askdirectory()
        if d:
            var.set(d)

    def pick_zip_base(self):
        f = filedialog.askopenfilename(filetypes=[('JKSV backup', '*.zip')])
        if f:
            self.zip_base.set(f)
            if not self.zip_out.get():
                self.zip_out.set(os.path.join(self.out.get(), 'restore.zip'))

    def pick_zip_out(self):
        f = filedialog.asksaveasfilename(defaultextension='.zip', filetypes=[('Zip', '*.zip')])
        if f:
            self.zip_out.set(f)

    def open_out(self):
        d = self.out.get()
        if os.path.isdir(d):
            os.startfile(d)
        else:
            messagebox.showinfo('Output folder', 'Nothing converted yet: the folder does not exist.')

    # ------------------------------------------------------------ rows
    def load(self):
        self.rows.clear()
        self.tree.delete(*self.tree.get_children())
        sources = [s for s in self.src.get().split(';') if s]
        for disp, name, data in eng.gather(sources):
            if name is None:
                self.say('Not found: %s' % disp)
                continue
            try:
                kind, _, n = eng.detect(data)
            except eng.SaveError as e:
                self.say('Skipped %s: %s' % (name, e))
                continue
            iid = self.tree.insert('', 'end')
            self.rows[iid] = dict(disp=disp, name=name, data=data, kind=kind, n=n, include=True, out_name=name)
        self.refresh()
        self.say('%d save(s) found.' % len(self.rows) if self.rows else 'No convertible saves found in that source.')

    def target(self, row):
        m = self.mode.get()
        return row['kind'] == 'pc' and 'switch' or 'pc' if m == 'auto' else m

    def refresh(self):
        for iid, r in self.rows.items():
            self.tree.item(iid, values=('[x]' if r['include'] else '[ ]', r['name'], LABEL[r['kind']], r['n'],
                                        LABEL[self.target(r)], r['out_name']))
        state = 'normal' if self.zip_on.get() else 'disabled'
        for w in self.zip_frame.winfo_children():
            for c in w.winfo_children():
                try:
                    c.config(state=state)
                except tk.TclError:
                    pass

    def on_click(self, ev):
        iid = self.tree.identify_row(ev.y)
        if iid and self.tree.identify_column(ev.x) == '#1':
            self.rows[iid]['include'] ^= True
            self.refresh()

    def on_double(self, ev):
        iid = self.tree.identify_row(ev.y)
        if not iid or self.tree.identify_column(ev.x) != '#6':
            return
        r = self.rows[iid]
        top = tk.Toplevel(self.root)
        top.title('Output name')
        top.transient(self.root)
        ttk.Label(top, text='File name to write (change the slot digit to move it, e.g. RDR2ZOMBIESAVE2.SAV):').pack(padx=10, pady=6)
        v = tk.StringVar(value=r['out_name'])
        e = ttk.Entry(top, textvariable=v, width=40)
        e.pack(padx=10)
        e.focus()

        def ok(_=None):
            n = v.get().strip()
            if n:
                r['out_name'] = n
            top.destroy()
            self.refresh()
        e.bind('<Return>', ok)
        ttk.Button(top, text='OK', command=ok).pack(pady=8)

    # ------------------------------------------------------------ convert
    def plan(self):
        """Return (list of (row, target)), error string or None."""
        use = [r for r in self.rows.values() if r['include']]
        if not use:
            return None, 'Nothing selected.'
        out = self.out.get().strip()
        if not out:
            return None, 'Choose an output folder.'
        seen = set()
        for r in use:
            dest = os.path.join(out, r['out_name']).lower()
            if dest in seen:
                return None, 'Two saves would be written as %s. Change one output name.' % r['out_name']
            seen.add(dest)
            if os.path.isfile(r['disp']) and eng.same_path(os.path.join(out, r['out_name']), r['disp']):
                return None, '%s would overwrite its own input. Pick a different output folder.' % r['name']
        if self.zip_on.get():
            if any(self.target(r) != 'switch' for r in use):
                return None, 'The JKSV zip needs Switch output for every selected save.'
            if not zipfile.is_zipfile(self.zip_base.get()):
                return None, 'Pick your own JKSV backup zip as the base.'
            if not self.zip_out.get().strip():
                return None, 'Choose where to write the restore zip.'
            if eng.same_path(self.zip_out.get(), self.zip_base.get()):
                return None, 'The restore zip must be a different file from the base zip.'
        return use, None

    def convert(self):
        use, err = self.plan()
        if err:
            messagebox.showwarning('Cannot convert', err)
            return
        results = []
        for r in use:
            try:
                src, dst, data, n = eng.convert_bytes(r['data'], self.target(r))
            except eng.SaveError as e:
                self.say('FAIL  %s: %s' % (r['name'], e))
                continue
            results.append((r, src, dst, data, n))
        if len(results) != len(use):
            self.say('Nothing written because some saves failed.')
            return
        if any(r['kind'] == 'pc' and self.target(r) == 'pc' for r in use):
            self.say('Note: a save that is already in the target format is copied unchanged.')
        os.makedirs(self.out.get(), exist_ok=True)
        files = {}
        for r, src, dst, data, n in results:
            out = r['data'] if src == dst else data
            with open(os.path.join(self.out.get(), r['out_name']), 'wb') as f:
                f.write(out)
            files[r['out_name']] = out
            self.say('OK    %s (%s) -> %s (%s, %d records)' % (r['name'], LABEL[src], r['out_name'], LABEL[dst], n))
        if self.zip_on.get():
            try:
                eng.build_zip(self.zip_base.get(), self.zip_out.get(), files)
                self.say('Restore zip written: %s' % self.zip_out.get())
                self.say('JKSV: turn "auto backup on restore" OFF, copy the zip to sdmc:/JKSV/Red Dead Redemption/, restore it.')
            except (eng.SaveError, OSError, zipfile.BadZipFile) as e:
                self.say('FAIL  restore zip: %s' % e)
                return
        self.say('Done. Files are in %s' % self.out.get())


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == '__main__':
    main()
