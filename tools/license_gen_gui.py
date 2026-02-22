import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import license as lic


def _current_secret_warning():
    try:
        secret = lic._get_secret()
        if secret == lic.DEFAULT_SECRET:
            return "WARNING: Using DEFAULT_SECRET. Set SYSTEM_LICENSE_SECRET or change DEFAULT_SECRET."
    except Exception:
        pass
    return ""


def _suggest_filename(machine_id, days):
    safe_mid = "".join([c for c in machine_id if c.isalnum()])
    if not safe_mid:
        safe_mid = "machine"
    return f"license_code_{safe_mid}_{days}d.txt"


def main():
    root = tk.Tk()
    root.title("License Generator")
    root.geometry("680x520")

    user_var = tk.StringVar()
    days_var = tk.StringVar(value="30")
    mid_var = tk.StringVar()
    autosave_var = tk.BooleanVar(value=True)
    status_var = tk.StringVar(value="")
    warn_text = _current_secret_warning()

    frm = ttk.Frame(root, padding=14)
    frm.pack(fill="both", expand=True)

    row = 0
    ttk.Label(frm, text="User label (optional):").grid(row=row, column=0, sticky="w")
    ttk.Entry(frm, textvariable=user_var, width=50).grid(row=row, column=1, sticky="we", padx=8)

    row += 1
    ttk.Label(frm, text="Days (positive integer):").grid(row=row, column=0, sticky="w", pady=8)
    days_box = ttk.Combobox(frm, textvariable=days_var, values=["1", "30", "365"], width=10)
    days_box.grid(row=row, column=1, sticky="w", padx=8, pady=8)

    row += 1
    ttk.Label(frm, text="Target machine ID:").grid(row=row, column=0, sticky="w")
    ttk.Entry(frm, textvariable=mid_var, width=50).grid(row=row, column=1, sticky="we", padx=8)

    row += 1
    ttk.Checkbutton(frm, text="Auto-save to file", variable=autosave_var).grid(row=row, column=1, sticky="w", padx=8, pady=6)

    row += 1
    btn_frame = ttk.Frame(frm)
    btn_frame.grid(row=row, column=1, sticky="w", padx=8)

    code_text = tk.Text(frm, height=8, wrap="word")

    def generate():
        machine_id = mid_var.get().strip()
        if not machine_id:
            messagebox.showerror("Error", "Machine ID is required.")
            return
        try:
            days = int(days_var.get().strip())
        except Exception:
            messagebox.showerror("Error", "Days must be a positive integer.")
            return
        if days <= 0:
            messagebox.showerror("Error", "Days must be a positive integer.")
            return

        payload = lic.build_payload(user_var.get().strip(), days, machine_id=machine_id)
        sig = lic.sign_payload(payload)
        code = lic.encode_license(payload, sig)

        code_text.delete("1.0", "end")
        code_text.insert("1.0", code)

        if autosave_var.get():
            filename = _suggest_filename(machine_id, days)
            out_path = os.path.join(ROOT, filename)
            try:
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(code)
                status_var.set(f"Saved to: {out_path}")
            except Exception as exc:
                status_var.set(f"Save failed: {exc}")
        else:
            status_var.set("Generated. Use Save As to export.")

    def save_as():
        code = code_text.get("1.0", "end").strip()
        if not code:
            messagebox.showerror("Error", "No activation code to save.")
            return
        machine_id = mid_var.get().strip() or "machine"
        try:
            days = int(days_var.get().strip())
        except Exception:
            days = 30
        filename = _suggest_filename(machine_id, days)
        path = filedialog.asksaveasfilename(
            title="Save activation code",
            defaultextension=".txt",
            initialdir=ROOT,
            initialfile=filename,
            filetypes=[("Text Files", "*.txt"), ("All Files", "*")],
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(code)
            status_var.set(f"Saved to: {path}")
        except Exception as exc:
            status_var.set(f"Save failed: {exc}")

    def copy_code():
        code = code_text.get("1.0", "end").strip()
        if not code:
            messagebox.showerror("Error", "No activation code to copy.")
            return
        root.clipboard_clear()
        root.clipboard_append(code)
        status_var.set("Activation code copied to clipboard.")

    ttk.Button(btn_frame, text="Generate", command=generate).pack(side="left")
    ttk.Button(btn_frame, text="Save As", command=save_as).pack(side="left", padx=6)
    ttk.Button(btn_frame, text="Copy", command=copy_code).pack(side="left")

    row += 1
    ttk.Label(frm, text="Activation code:").grid(row=row, column=0, sticky="nw", pady=6)
    code_text.grid(row=row, column=1, sticky="we", padx=8, pady=6)

    row += 1
    if warn_text:
        warn_label = ttk.Label(frm, text=warn_text, foreground="#c05000")
        warn_label.grid(row=row, column=1, sticky="w", padx=8)
    else:
        ttk.Label(frm, text="").grid(row=row, column=1)

    row += 1
    ttk.Label(frm, textvariable=status_var, foreground="#1a7f37").grid(row=row, column=1, sticky="w", padx=8, pady=8)

    frm.columnconfigure(1, weight=1)
    root.mainloop()


if __name__ == "__main__":
    main()
