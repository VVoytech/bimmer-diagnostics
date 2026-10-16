"""Desktop GUI with start menu, vehicle-aware profiles, and separate history screen."""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .bmw_service import BmwDiagnosticsService


class HoverInfo:
    def __init__(self, widget: tk.Widget, text: str) -> None:
        self.widget = widget
        self.text = text
        self.tip_window: tk.Toplevel | None = None
        self._after_id: str | None = None
        self.widget.bind("<Enter>", self._schedule_show, add="+")
        self.widget.bind("<Leave>", self._hide, add="+")
        self.widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule_show(self, _event=None) -> None:
        self._cancel_scheduled()
        self._after_id = self.widget.after(300, self._show)

    def _cancel_scheduled(self) -> None:
        if self._after_id is not None:
            self.widget.after_cancel(self._after_id)
            self._after_id = None

    def _show(self) -> None:
        self._after_id = None
        if self.tip_window is not None:
            return

        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
        self.tip_window = tk.Toplevel(self.widget)
        self.tip_window.wm_overrideredirect(True)
        self.tip_window.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            self.tip_window,
            text=self.text,
            justify="left",
            bg="#1f2937",
            fg="#f9fafb",
            relief="solid",
            borderwidth=1,
            padx=8,
            pady=6,
            wraplength=420,
            font=("Segoe UI", 9),
        )
        label.pack()

    def _hide(self, _event=None) -> None:
        self._cancel_scheduled()
        if self.tip_window is not None:
            self.tip_window.destroy()
            self.tip_window = None


class DiagnosticsGui(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Bimmer Diagnostics")
        self.geometry("1200x760")

        self.project_root = Path.cwd()
        self.reports_dir = self.project_root / "reports"
        self.reports_dir.mkdir(parents=True, exist_ok=True)

        self.service = BmwDiagnosticsService()
        self.vehicles = self.service.list_vehicles()
        self.vehicle_by_display = {vehicle.display_name: vehicle for vehicle in self.vehicles}

        self.selected_vehicle_id: str | None = None
        self.profile_by_display: dict[str, str] = {}

        self.vehicle_display_var = tk.StringVar(value=self.vehicles[0].display_name if self.vehicles else "")
        self.profile_display_var = tk.StringVar(value="")
        self.lang_var = tk.StringVar(value="en")
        self.status_var = tk.StringVar(value="Ready")
        self.start_status_var = tk.StringVar(value="Select a vehicle to continue")

        self.single_ecu_var = tk.StringVar(value="EHC2RR4")
        self.single_job_var = tk.StringVar(value="STATUS_LESEN")
        self.single_para_var = tk.StringVar(value="")
        self.single_result_var = tk.StringVar(value="")

        self.history_filter_var = tk.StringVar(value="")
        self.history_paths: list[Path] = []
        self.last_report_path: Path | None = None
        self._tooltips: list[HoverInfo] = []

        self._configure_styles()
        self._build_layout()
        self._load_profiles_for_current_vehicle()
        self.refresh_history_list()
        self.show_page("start")

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        self.configure(bg="#eef3fb")
        style.configure("TFrame", background="#eef3fb")
        style.configure("TLabelframe", background="#eef3fb", bordercolor="#d5deed")
        style.configure("TLabelframe.Label", background="#eef3fb", font=("Segoe UI Semibold", 10))
        style.configure("TLabel", background="#eef3fb", font=("Segoe UI", 9))
        style.configure("Title.TLabel", background="#eef3fb", font=("Segoe UI Semibold", 16), foreground="#1f2937")
        style.configure("Subtitle.TLabel", background="#eef3fb", font=("Segoe UI", 10), foreground="#374151")
        style.configure("Status.TLabel", background="#eef3fb", foreground="#0b7a5a", font=("Segoe UI", 9, "bold"))
        style.configure("Primary.TButton", font=("Segoe UI", 9, "bold"), padding=(10, 6))

    def _add_info_badge(self, parent: tk.Widget, row: int, column: int, text: str) -> None:
        badge = tk.Label(
            parent,
            text="i",
            bg="#dbeafe",
            fg="#1d4ed8",
            font=("Segoe UI", 9, "bold"),
            width=2,
            relief="ridge",
            borderwidth=1,
            cursor="hand2",
        )
        badge.grid(row=row, column=column, padx=(4, 10), sticky="w")
        self._tooltips.append(HoverInfo(badge, text))

    def _build_layout(self) -> None:
        container = ttk.Frame(self, padding=14)
        container.pack(fill="both", expand=True)

        self.pages: dict[str, ttk.Frame] = {}
        self.pages["start"] = self._build_start_page(container)
        self.pages["scan"] = self._build_scan_page(container)
        self.pages["history"] = self._build_history_page(container)

        for frame in self.pages.values():
            frame.pack(fill="both", expand=True)

    def _build_start_page(self, parent: ttk.Frame) -> ttk.Frame:
        frame = ttk.Frame(parent)

        header = ttk.Frame(frame)
        header.pack(fill="x", pady=(10, 18))
        ttk.Label(header, text="Bimmer Diagnostics", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Choose vehicle first. Scan and history are separate screens.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        vehicle_box = ttk.LabelFrame(frame, text="Vehicle Selection", padding=14)
        vehicle_box.pack(fill="x", pady=(0, 12))
        vehicle_box.columnconfigure(8, weight=1)

        ttk.Label(vehicle_box, text="Vehicle:").grid(row=0, column=0, sticky="w")
        self.vehicle_combo = ttk.Combobox(vehicle_box, textvariable=self.vehicle_display_var, state="readonly", width=44)
        self.vehicle_combo["values"] = [vehicle.display_name for vehicle in self.vehicles]
        self.vehicle_combo.grid(row=0, column=1, sticky="w", padx=(6, 10))
        self.vehicle_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_vehicle_selected())
        self._add_info_badge(vehicle_box, 0, 2, "Select target chassis/engine. Available scan profiles update for this vehicle.")

        self.detect_btn = ttk.Button(vehicle_box, text="Detect via OBD", style="Primary.TButton", command=self.detect_vehicle)
        self.detect_btn.grid(row=0, column=3, sticky="w", padx=(4, 8))
        self._add_info_badge(vehicle_box, 0, 4, "Tries to read VIN over OBD and match supported vehicle catalog.")

        self.enter_scan_btn = ttk.Button(vehicle_box, text="Open Scan Screen", style="Primary.TButton", command=self.open_scan_screen)
        self.enter_scan_btn.grid(row=0, column=5, sticky="w", padx=(4, 8))

        self.enter_history_btn = ttk.Button(vehicle_box, text="Open History Screen", command=lambda: self.show_page("history"))
        self.enter_history_btn.grid(row=0, column=6, sticky="w", padx=(4, 8))

        ttk.Label(frame, textvariable=self.start_status_var, style="Status.TLabel").pack(fill="x", pady=(2, 10))

        self.vehicle_modules_tree = ttk.Treeview(frame, columns=("group", "modules"), show="headings", height=12)
        self.vehicle_modules_tree.heading("group", text="System Group")
        self.vehicle_modules_tree.heading("modules", text="Typical E60 Modules")
        self.vehicle_modules_tree.column("group", width=220, anchor="w")
        self.vehicle_modules_tree.column("modules", width=900, anchor="w")
        self.vehicle_modules_tree.pack(fill="both", expand=True)
        self._tooltips.append(
            HoverInfo(self.vehicle_modules_tree, "Reference module map for selected vehicle: engine, chassis, body, comfort.")
        )

        return frame

    def _build_scan_page(self, parent: ttk.Frame) -> ttk.Frame:
        frame = ttk.Frame(parent)

        nav = ttk.Frame(frame)
        nav.pack(fill="x", pady=(0, 8))
        ttk.Button(nav, text="Back to Start", command=lambda: self.show_page("start")).pack(side="left")
        ttk.Button(nav, text="History", command=lambda: self.show_page("history")).pack(side="left", padx=(8, 0))
        ttk.Label(nav, textvariable=self.status_var, style="Status.TLabel").pack(side="right")

        controls = ttk.LabelFrame(frame, text="Vehicle-Specific Scan", padding=10)
        controls.pack(fill="x", pady=(0, 8))
        controls.columnconfigure(12, weight=1)

        ttk.Label(controls, text="Vehicle:").grid(row=0, column=0, sticky="w")
        self.scan_vehicle_label = ttk.Label(controls, text="-")
        self.scan_vehicle_label.grid(row=0, column=1, sticky="w", padx=(6, 12))

        ttk.Label(controls, text="Profile:").grid(row=0, column=2, sticky="w")
        self.profile_combo = ttk.Combobox(controls, textvariable=self.profile_display_var, state="readonly", width=42)
        self.profile_combo.grid(row=0, column=3, sticky="w", padx=(6, 10))
        self._add_info_badge(controls, 0, 4, "Profiles are filtered by currently selected vehicle.")

        ttk.Label(controls, text="Language:").grid(row=0, column=5, sticky="w")
        self.lang_combo = ttk.Combobox(controls, textvariable=self.lang_var, state="readonly", width=10)
        self.lang_combo["values"] = ["raw", "en"]
        self.lang_combo.grid(row=0, column=6, sticky="w", padx=(6, 12))

        self.run_btn = ttk.Button(controls, text="Run Profile Scan", style="Primary.TButton", command=self.run_profile_scan)
        self.run_btn.grid(row=0, column=7, sticky="w", padx=(4, 8))

        ttk.Button(controls, text="Open JSON", command=self.open_report).grid(row=0, column=8, sticky="w", padx=(4, 8))
        ttk.Button(controls, text="Reload Last", command=self.reload_last_report).grid(row=0, column=9, sticky="w", padx=(4, 8))

        single = ttk.LabelFrame(frame, text="Single BMW Job", padding=10)
        single.pack(fill="x", pady=(0, 8))
        single.columnconfigure(11, weight=1)

        ttk.Label(single, text="ECU:").grid(row=0, column=0, sticky="w")
        ttk.Entry(single, textvariable=self.single_ecu_var, width=16).grid(row=0, column=1, sticky="w", padx=(6, 10))
        self._add_info_badge(single, 0, 2, "Module/SGBD name, eg EHC2RR4, ME9N62.")

        ttk.Label(single, text="Job:").grid(row=0, column=3, sticky="w")
        ttk.Entry(single, textvariable=self.single_job_var, width=20).grid(row=0, column=4, sticky="w", padx=(6, 10))
        ttk.Label(single, text="Para:").grid(row=0, column=5, sticky="w")
        ttk.Entry(single, textvariable=self.single_para_var, width=20).grid(row=0, column=6, sticky="w", padx=(6, 10))
        ttk.Label(single, text="Result:").grid(row=0, column=7, sticky="w")
        ttk.Entry(single, textvariable=self.single_result_var, width=20).grid(row=0, column=8, sticky="w", padx=(6, 10))

        self.single_run_btn = ttk.Button(single, text="Run Single Job", command=self.run_single_job)
        self.single_run_btn.grid(row=0, column=9, sticky="w", padx=(4, 8))

        body = ttk.Panedwindow(frame, orient="horizontal")
        body.pack(fill="both", expand=True)

        left = ttk.LabelFrame(body, text="Scan Summary", padding=8)
        right = ttk.LabelFrame(body, text="Raw JSON", padding=8)
        body.add(left, weight=1)
        body.add(right, weight=2)

        self.modules_tree = ttk.Treeview(left, columns=("module", "status", "job", "attempts"), show="headings", height=10)
        self.modules_tree.heading("module", text="Module")
        self.modules_tree.heading("status", text="Status")
        self.modules_tree.heading("job", text="Selected Job")
        self.modules_tree.heading("attempts", text="Attempts")
        self.modules_tree.column("module", width=140, anchor="w")
        self.modules_tree.column("status", width=90, anchor="w")
        self.modules_tree.column("job", width=170, anchor="w")
        self.modules_tree.column("attempts", width=80, anchor="center")
        self.modules_tree.pack(fill="x", pady=(0, 8))

        self.summary_text = tk.Text(left, wrap="word", height=16)
        self.summary_text.pack(fill="both", expand=True)
        self.summary_text.configure(state="disabled")

        self.json_text = tk.Text(right, wrap="none", height=16)
        self.json_text.pack(fill="both", expand=True)
        self.json_text.configure(state="disabled")

        return frame

    def _build_history_page(self, parent: ttk.Frame) -> ttk.Frame:
        frame = ttk.Frame(parent)

        nav = ttk.Frame(frame)
        nav.pack(fill="x", pady=(0, 8))
        ttk.Button(nav, text="Back to Start", command=lambda: self.show_page("start")).pack(side="left")
        ttk.Button(nav, text="Back to Scan", command=lambda: self.show_page("scan")).pack(side="left", padx=(8, 0))

        box = ttk.LabelFrame(frame, text="Reports History", padding=10)
        box.pack(fill="x", pady=(0, 8))
        box.columnconfigure(1, weight=1)

        ttk.Label(box, text="Filter:").grid(row=0, column=0, sticky="w")
        filter_entry = ttk.Entry(box, textvariable=self.history_filter_var, width=40)
        filter_entry.grid(row=0, column=1, sticky="ew", padx=(6, 8))
        filter_entry.bind("<Return>", lambda _e: self.refresh_history_list())

        self.history_refresh_btn = ttk.Button(box, text="Refresh", command=self.refresh_history_list)
        self.history_refresh_btn.grid(row=0, column=2, padx=(0, 8))
        self.history_load_btn = ttk.Button(box, text="Load Selected", command=self.load_selected_report)
        self.history_load_btn.grid(row=0, column=3)

        self.history_listbox = tk.Listbox(box, height=8, exportselection=False)
        self.history_listbox.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        self.history_listbox.bind("<Double-Button-1>", lambda _e: self.load_selected_report())

        viewer = ttk.Panedwindow(frame, orient="horizontal")
        viewer.pack(fill="both", expand=True)

        left = ttk.LabelFrame(viewer, text="History Summary", padding=8)
        right = ttk.LabelFrame(viewer, text="History JSON", padding=8)
        viewer.add(left, weight=1)
        viewer.add(right, weight=2)

        self.history_summary_text = tk.Text(left, wrap="word", height=20)
        self.history_summary_text.pack(fill="both", expand=True)
        self.history_summary_text.configure(state="disabled")

        self.history_json_text = tk.Text(right, wrap="none", height=20)
        self.history_json_text.pack(fill="both", expand=True)
        self.history_json_text.configure(state="disabled")

        return frame

    def show_page(self, page_name: str) -> None:
        for name, frame in self.pages.items():
            if name == page_name:
                frame.pack(fill="both", expand=True)
            else:
                frame.pack_forget()

    def _on_vehicle_selected(self) -> None:
        vehicle = self.vehicle_by_display.get(self.vehicle_display_var.get())
        if not vehicle:
            return
        self.selected_vehicle_id = vehicle.vehicle_id
        self.start_status_var.set(f"Selected vehicle: {vehicle.display_name}")
        self._render_vehicle_modules(vehicle)
        self._load_profiles_for_current_vehicle()

    def _load_profiles_for_current_vehicle(self) -> None:
        vehicle = self.vehicle_by_display.get(self.vehicle_display_var.get())
        if not vehicle:
            self.profile_combo["values"] = []
            self.profile_display_var.set("")
            return

        self.selected_vehicle_id = vehicle.vehicle_id
        profiles = self.service.list_profiles_for_vehicle(vehicle.vehicle_id)
        self.profile_by_display = {profile.display_name: profile.profile_id for profile in profiles}
        display_values = list(self.profile_by_display.keys())
        self.profile_combo["values"] = display_values
        self.profile_display_var.set(display_values[0] if display_values else "")
        self.scan_vehicle_label.configure(text=vehicle.display_name)
        self._render_vehicle_modules(vehicle)

    def _refresh_vehicle_choices(self) -> None:
        self.vehicles = self.service.list_vehicles()
        self.vehicle_by_display = {vehicle.display_name: vehicle for vehicle in self.vehicles}
        self.vehicle_combo["values"] = [vehicle.display_name for vehicle in self.vehicles]

    def _render_vehicle_modules(self, vehicle) -> None:
        for item in self.vehicle_modules_tree.get_children():
            self.vehicle_modules_tree.delete(item)
        for group_name, modules in vehicle.module_groups.items():
            self.vehicle_modules_tree.insert("", tk.END, values=(group_name, ", ".join(modules)))

    def detect_vehicle(self) -> None:
        self.start_status_var.set("Detecting vehicle over OBD...")
        self.detect_btn.configure(state="disabled")

        def worker() -> None:
            try:
                result = self.service.detect_vehicle_via_obd()
                self.after(0, self._on_detect_finished, result)
            except Exception as exc:  # pylint: disable=broad-except
                self.after(0, self._on_detect_failed, str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _on_detect_finished(self, result: dict[str, str | None]) -> None:
        self.detect_btn.configure(state="normal")
        self._refresh_vehicle_choices()
        vin = result.get("vin")
        make = result.get("make")
        vehicle_id = result.get("vehicle_id")

        if vehicle_id:
            vehicle = self.service.get_vehicle(vehicle_id)
            if vehicle is not None:
                self.vehicle_display_var.set(vehicle.display_name)
                self._on_vehicle_selected()
        status_bits = ["OBD detection complete"]
        if make:
            status_bits.append(f"make={make}")
        if vin:
            status_bits.append(f"vin={vin}")
        if not vehicle_id:
            status_bits.append("catalog match not found")
        self.start_status_var.set(" | ".join(status_bits))

    def _on_detect_failed(self, message: str) -> None:
        self.detect_btn.configure(state="normal")
        self.start_status_var.set("OBD detection failed")
        messagebox.showerror("OBD detection error", message)

    def open_scan_screen(self) -> None:
        self._on_vehicle_selected()
        if not self.profile_combo["values"]:
            messagebox.showerror("No profiles", "No scan profiles available for selected vehicle.")
            return
        self.show_page("scan")

    def run_profile_scan(self) -> None:
        profile_display = self.profile_display_var.get().strip()
        profile_id = self.profile_by_display.get(profile_display)
        if not profile_id:
            messagebox.showerror("Missing profile", "Select a profile first.")
            return

        stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        report_path = self.reports_dir / f"gui_profile_scan_{profile_id}_{stamp}.json"
        selected_lang = self.lang_var.get().strip()

        self._set_busy(True, "Running profile scan...")

        def worker() -> None:
            try:
                raw_report, _ = self.service.run_profile_scan(profile_id)
                payload = self.service.render_profile_output(raw_report, selected_lang)
                saved_path = self.service.save_report(payload, str(report_path), prefix="profile_scan_bmw")
                self.after(0, self._on_scan_finished, 0, str(saved_path))
            except Exception as exc:  # pylint: disable=broad-except
                self.after(0, self._on_scan_failed, str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def run_single_job(self) -> None:
        ecu = self.single_ecu_var.get().strip()
        job = self.single_job_var.get().strip()
        para = self.single_para_var.get().strip()
        result = self.single_result_var.get().strip()
        if not ecu or not job:
            messagebox.showerror("Missing fields", "ECU and Job are required.")
            return

        stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        report_path = self.reports_dir / f"gui_single_job_{ecu}_{job}_{stamp}.json"
        selected_lang = self.lang_var.get().strip()

        self._set_busy(True, "Running single job...")

        def worker() -> None:
            try:
                raw_payload = self.service.run_job_raw(ecu=ecu, job=job, para=para, result=result)
                payload = self.service.render_job_output(raw_payload, selected_lang)
                saved_path = self.service.save_report(payload, str(report_path), prefix="bmw_job")
                self.after(0, self._on_scan_finished, 0, str(saved_path))
            except Exception as exc:  # pylint: disable=broad-except
                self.after(0, self._on_scan_failed, str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _on_scan_finished(self, returncode: int, report_path: str) -> None:
        self._set_busy(False, "Ready")
        report = Path(report_path)
        if not report.exists():
            messagebox.showerror("Scan failed", f"Report file was not created.\nExit code: {returncode}")
            return

        self.last_report_path = report
        self.status_var.set(f"Scan finished (exit={returncode}). Loaded: {report}")
        self._load_report_file(report, target="scan")
        self.refresh_history_list()

    def _on_scan_failed(self, message: str) -> None:
        self._set_busy(False, "Ready")
        messagebox.showerror("Execution error", message)

    def open_report(self) -> None:
        path = filedialog.askopenfilename(
            title="Open JSON report",
            initialdir=str(self.reports_dir),
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        report_path = Path(path)
        self.last_report_path = report_path
        self._load_report_file(report_path, target="scan")

    def reload_last_report(self) -> None:
        if self.last_report_path is None:
            messagebox.showinfo("No report", "Run a scan or open a report first.")
            return
        self._load_report_file(self.last_report_path, target="scan")

    def refresh_history_list(self) -> None:
        raw_filter = self.history_filter_var.get().strip().lower()
        all_files = sorted(self.reports_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        filtered: list[Path] = []
        for path in all_files:
            name = path.name.lower()
            if raw_filter and raw_filter not in name:
                continue
            filtered.append(path)
        self.history_paths = filtered
        self.history_listbox.delete(0, tk.END)
        for path in filtered:
            modified = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            label = f"{modified} | {path.name}"
            self.history_listbox.insert(tk.END, label)

    def load_selected_report(self) -> None:
        selection = self.history_listbox.curselection()
        if not selection:
            messagebox.showinfo("No selection", "Select a report from history first.")
            return
        index = selection[0]
        if index < 0 or index >= len(self.history_paths):
            messagebox.showerror("Invalid selection", "Selected report index is out of range.")
            return
        path = self.history_paths[index]
        self.last_report_path = path
        self._load_report_file(path, target="history")

    def _load_report_file(self, path: Path, target: str) -> None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # pylint: disable=broad-except
            messagebox.showerror("Invalid JSON", f"Could not parse report:\n{exc}")
            return

        if target == "scan":
            self._render_json_to_widget(self.json_text, data)
            self._render_summary_to_widget(self.summary_text, data, path)
            self._render_modules_table(data)
        else:
            self._render_json_to_widget(self.history_json_text, data)
            self._render_summary_to_widget(self.history_summary_text, data, path)

    def _render_json_to_widget(self, widget: tk.Text, data: dict) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", tk.END)
        widget.insert("1.0", json.dumps(data, indent=2, ensure_ascii=False))
        widget.configure(state="disabled")

    def _render_summary_to_widget(self, widget: tk.Text, data: dict, path: Path) -> None:
        localized = data.get("localized") if isinstance(data, dict) else None
        payload = localized if isinstance(localized, dict) else data

        lines = [f"File: {path}"]
        if isinstance(payload, dict):
            if "profile_id" in payload:
                lines.append(f"Profile: {payload.get('profile_id')} ({payload.get('profile_name')})")
                lines.append(f"Generated: {payload.get('generated_at')}")
                lines.append(f"Modules: {payload.get('total_modules')} total, {payload.get('failed_modules')} failed")
                lines.append("")
                for module in payload.get("modules", []):
                    lines.append(
                        f"- {module.get('module')}: status={module.get('status')}, job={module.get('selected_job')}"
                    )
            else:
                lines.append("Single-job payload loaded.")
                lines.append(f"Top-level keys: {', '.join(payload.keys())}")
        else:
            lines.append("Unsupported report structure.")

        widget.configure(state="normal")
        widget.delete("1.0", tk.END)
        widget.insert("1.0", "\n".join(lines))
        widget.configure(state="disabled")

    def _render_modules_table(self, data: dict) -> None:
        for item in self.modules_tree.get_children():
            self.modules_tree.delete(item)

        localized = data.get("localized") if isinstance(data, dict) else None
        payload = localized if isinstance(localized, dict) else data
        if not isinstance(payload, dict):
            return

        modules = payload.get("modules")
        if not isinstance(modules, list):
            return

        for module_item in modules:
            if not isinstance(module_item, dict):
                continue
            module_name = module_item.get("module", "(unknown)")
            status = module_item.get("status", "?")
            selected_job = module_item.get("selected_job") or "-"
            attempts = module_item.get("attempts")
            attempts_count = len(attempts) if isinstance(attempts, list) else 0
            self.modules_tree.insert("", tk.END, values=(module_name, status, selected_job, attempts_count))

    def _set_busy(self, busy: bool, status: str) -> None:
        self.status_var.set(status)
        state = "disabled" if busy else "normal"
        self.run_btn.configure(state=state)
        self.single_run_btn.configure(state=state)
        self.detect_btn.configure(state=state)
        self.enter_scan_btn.configure(state=state)
        self.enter_history_btn.configure(state=state)
        self.history_refresh_btn.configure(state=state)
        self.history_load_btn.configure(state=state)


def main() -> int:
    app = DiagnosticsGui()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
