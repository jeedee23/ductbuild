# 2026_09_26_@_21-51-25
"""Standalone Allshield project GUI with an isolated FreeCAD build worker."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse
import urllib.request
import uuid
import webbrowser
import weakref
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from PIL import Image, ImageTk


sys.dont_write_bytecode = True
PACKAGE_DIR = Path(__file__).resolve().parent
if str(PACKAGE_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGE_DIR))

from airkan_builder.rules import (
    CAT,
    FAMILIES,
    InputError,
    defaults,
    resolve,
)
from airkan_builder.pricing import rectangular_priced_thicknesses
from allshield_project import ProjectStore, area_text, pricing_values, rate_text, size_text, total_price_text


APP_TITLE = "AAVDS-duct-builder"
APP_VERSION = "AAVDS-2026-V01"
UPDATE_ENDPOINT = "https://qui-sed-quod.tiiny.site/version.json"
SETTINGS_PATH = Path(os.environ.get("APPDATA", Path.home())) / APP_TITLE / "settings.json"
LEGACY_SETTINGS_PATH = Path(os.environ.get("APPDATA", Path.home())) / "Allshield" / "project_gui.json"
WORKER_PATH = PACKAGE_DIR / "Allshield_FreeCAD_Worker.py"
TYPE_PREVIEW_DIR = PACKAGE_DIR / "assets" / "type_previews"
DEFAULT_HELP_TEXT = "Hover over or focus a control for more information."
TOOLTIP_DELAY_MS = 400
TOOLTIP_DISPLAY_MS = 2000
TOOLTIP_COOLDOWN_SECONDS = 5.0

FIELD_HELP = {
    "a_mm": "Clear internal duct size along the X axis.",
    "actual_bore_mm": "Confirmed clear bore of the roof passage.",
    "actual_id_mm": "Confirmed actual internal diameter.",
    "actual_od_mm": "Confirmed actual external diameter.",
    "airflow_role": "Choose whether the purchased component is used for intake or exhaust.",
    "airkan_a_mm": "Legacy compatibility field. Automatic thickness uses the duct dimensions.",
    "airtightness_class": "Requested duct airtightness class.",
    "angle_deg": "Bend angle in degrees.",
    "area_rate_eur_per_m2": "Comparison rate in EUR per square metre.",
    "article_code": "Supplier article or order code.",
    "b_mm": "Clear internal duct size along the Y axis.",
    "base_x_mm": "Confirmed mounting-base dimension along the X axis.",
    "base_y_mm": "Confirmed mounting-base dimension along the Y axis.",
    "branch_a_mm": "Clear branch width in the XZ plane.",
    "branch_length_mm": "Clear branch extension above the main duct wall.",
    "branch_z_mm": "Branch centre position measured from the inlet flange.",
    "c_mm": "Clear internal outlet size along the X axis.",
    "d_mm": "Clear internal outlet size along the Y axis.",
    "depth_mm": "Coordination depth used by the model.",
    "description": "Short recognisable component description.",
    "diameter_mm": "Nominal round diameter or clear internal diameter.",
    "drain_id_mm": "Confirmed internal drain diameter.",
    "drain_length_mm": "Drain projection length.",
    "drain_od_mm": "Confirmed external drain diameter.",
    "e_mm": "Outlet edge offset along the X axis.",
    "f_mm": "Outlet edge offset along the Y axis.",
    "frames": "Choose whether connection frames are included.",
    "h_mm": "Catalogue height.",
    "hole_clock_deg": "Angular orientation of the bolt-hole pattern.",
    "insertion_mm": "Manual axial sheet insertion into the frame profile.",
    "insertion_mode": "Choose the standard frame boundary or a confirmed manual insertion.",
    "length_basis": "Choose whether length is measured between flange faces or profile entries.",
    "length_mm": "Component length in millimetres.",
    "material": "Material used for catalogue selection and pricing.",
    "offset_x_mm": "Outlet centreline displacement along the X axis.",
    "offset_y_mm": "Outlet centreline displacement along the Y axis.",
    "outer_a_mm": "Confirmed outside size 1; zero uses the catalogue table where supported.",
    "outer_b_mm": "Confirmed outside size 2; zero uses the catalogue table where supported.",
    "outer_diameter_mm": "Confirmed outside diameter of the enclosure.",
    "pitch_override_mm": "Manual pitch-circle correction; use zero for the catalogue value.",
    "price_source": "Reference to the quotation, catalogue page or supplier URL.",
    "price_status": "Choose On request or Confirmed.",
    "radius_mm": "Internal radius of the clear airflow path.",
    "segments": "Number of straight segments used for the round bend.",
    "shoulder_radius_mm": "Internal transition radius at the branch shoulder.",
    "size_a_mm": "First catalogue order dimension.",
    "size_b_mm": "Second catalogue order dimension.",
    "source_step": "Choose the supplier or custom STEP file to import unchanged.",
    "straight_in_mm": "Straight length before the bend.",
    "straight_out_mm": "Straight length after the bend.",
    "supplier": "Supplier or manufacturer of the purchased component.",
    "t_mm": "Duct sheet thickness; this is not the frame profile thickness.",
    "thickness_mm": "Sheet thickness in millimetres.",
    "thickness_mode": "Choose automatic thickness from duct dimensions or select it manually.",
    "turn": "Bend direction in the XZ plane.",
    "unit_price_eur": "Confirmed price per item. Keep zero when the price is On request.",
    "variant": "Select the catalogue execution or product variant.",
    "visual_wall_mm": "Visual wall thickness only; not certified material data.",
}

REGISTER_HELP = {
    "#1": "Unique component ID.",
    "#2": "Main dimensions of the component.",
    "#3": "Technical component family code.",
    "#4": "Connected upstream component or external point.",
    "#5": "Connected downstream component or external point.",
    "#6": "Current build, validation or connection issue.",
    "#7": "Measured pricing area in m². An asterisk marks a manual override.",
    "#8": "Current catalogue rate per m² or confirmed price per item.",
    "#9": "Current calculated total. Area-based totals are calculated on demand.",
}

FAMILY_NAMES = {
    "FRAME": "Connection frame",
    "BU": "Rectangular straight duct",
    "BEND_RECT": "Rectangular bend",
    "REDUCER_RECT": "Rectangular reducer",
    "VER": "Offset rectangular transition",
    "RECT_ROUND": "Rectangular-to-round transition",
    "TEE_RECT": "Rectangular tee",
    "TAKEOFF_RECT": "Rectangular take-off",
    "S": "Round spiral duct",
    "BEND_ROUND": "Round segmented bend",
    "REG": "Damper",
    "SL_RECT": "Rectangular flexible connector",
    "FLEX_ROUND": "Round flexible connector",
    "CONNECTOR_ROUND": "Round connector",
    "FLANGE_ROUND": "Round flange",
    "COVER_ROUND": "Round cover",
    "INSPECTION": "Inspection hatch",
    "SUPPORT_PL": "Support plate",
    "HOOD": "Roof hood",
    "ROOF": "Roof passage",
    "GRILLE_FIRE": "Fire-resistant wall grille",
    "CM": "Custom STEP component",
    "BUY": "Purchased STEP component",
    "AP_APA_PSA": "Round branch families",
    "PR_PRA": "Rectangular branch on round duct",
    "TEE_SPECIAL": "Special tee families",
    "SUPPORT_AT": "Additional support families",
    "COMPOSITE": "Composite components",
}

FIELD_LABELS = {
    "a_mm": "A - clear width (mm)",
    "b_mm": "B - clear height (mm)",
    "c_mm": "C - outlet width (mm)",
    "d_mm": "D - outlet height (mm)",
    "t_mm": "Duct sheet thickness (mm)",
    "airkan_a_mm": "Legacy compatibility value",
    "thickness_mode": "Sheet thickness selection",
    "insertion_mode": "Sheet-to-frame connection",
    "insertion_mm": "Frame insertion depth (mm)",
    "length_mm": "Length (mm)",
    "diameter_mm": "Nominal diameter (mm)",
    "area_rate_eur_per_m2": "Area rate (EUR/m²)",
    "source_step": "Source STEP file",
}

CHOICE_LABELS = {
    "HANDMATIG": "Choose manually",
    "AIRKAN_BC": "Automatically from duct dimensions",
    "BOM_REFERENTIE": "Sheet stops at frame (default)",
    "HANDMATIGE_INSTEEK": "Insert sheet into frame manually",
    "PROJECT_AUTO": "Automatic project frame",
    "GEEN": "None",
    "LINKS": "Left",
    "RECHTS": "Right",
    "FLENSVLAKKEN": "Between flange faces",
    "PROFIELINVOER": "Between profile entries",
    "AANZUIG": "Intake",
    "AFBLAAS": "Exhaust",
    "KIES": "Select...",
    "ON_REQUEST": "On request",
    "BEVESTIGD": "Confirmed",
}


def english_field_label(field):
    key = field["key"]
    if key in FIELD_LABELS:
        return FIELD_LABELS[key]
    words = key.removesuffix("_mm").replace("_", " ").title()
    words = words.replace(" Id", " ID").replace(" Od", " OD").replace(" Eur", " EUR")
    return words + (" (mm)" if key.endswith("_mm") else "")


def english_choice_label(value):
    return CHOICE_LABELS.get(value, str(value))


def english_choice_value(label):
    return next((value for value, text in CHOICE_LABELS.items() if text == label), label)


def release_key(value):
    match = re.fullmatch(r"AAVDS-(\d{4})-V(\d+)", str(value or ""))
    return (int(match.group(1)), int(match.group(2))) if match else None


def is_newer_release(latest, current=APP_VERSION):
    latest_key = release_key(latest)
    current_key = release_key(current)
    return bool(latest_key and current_key and latest_key > current_key)


def load_settings():
    for path in (SETTINGS_PATH, LEGACY_SETTINGS_PATH):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
        except (OSError, json.JSONDecodeError):
            pass
    return {}


def save_settings(values):
    merged = load_settings()
    merged.update(values)
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = SETTINGS_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, SETTINGS_PATH)


def default_project_path():
    configured = load_settings().get("last_project")
    if configured:
        return Path(configured)
    return Path.home() / "Documents" / "AAVDSProjects"


def find_freecad_python():
    candidates = [
        os.environ.get("FREECAD_PYTHON"),
        PACKAGE_DIR.parent / "FreeCAD" / "bin" / "python.exe",
        r"C:\Program Files\FreeCAD 1.1\bin\python.exe",
        r"C:\Program Files\FreeCAD 1.0\bin\python.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate))
    raise FileNotFoundError("FreeCAD Python was not found. Set FREECAD_PYTHON or repair the AAVDS installation.")


def registered_application(names):
    if os.name != "nt":
        return None
    try:
        import winreg
    except ImportError:
        return None
    views = [0, getattr(winreg, "KEY_WOW64_64KEY", 0), getattr(winreg, "KEY_WOW64_32KEY", 0)]
    for name in names:
        key_name = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths" + "\\" + name
        for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for view in views:
                try:
                    with winreg.OpenKey(root, key_name, 0, winreg.KEY_READ | view) as key:
                        candidate = Path(winreg.QueryValue(key, None).strip('"'))
                    if candidate.is_file():
                        return candidate
                except OSError:
                    pass
    return None


def format_value(value):
    if isinstance(value, float):
        return ("%.3f" % value).rstrip("0").rstrip(".")
    return str(value)


def status_text(value):
    return {
        "Gebouwd": "built",
        "Gewijzigd": "changed",
        "Fout": "error",
    }.get(str(value), str(value).lower())


class TooltipManager:
    def __init__(self, root, help_variable):
        self.root = root
        self.help_variable = help_variable
        self.help_by_widget = weakref.WeakKeyDictionary()
        self.cooldown_until = weakref.WeakKeyDictionary()
        self.hovered_widget = None
        self.focused_widget = None
        self.pending_job = None
        self.hide_job = None
        self.popup = None

    def add(self, widget, text):
        self.help_by_widget[widget] = str(text)
        widget.bind("<Enter>", lambda event, target=widget: self._enter(target), add="+")
        widget.bind("<Leave>", lambda event, target=widget: self._leave(target), add="+")
        widget.bind("<FocusIn>", lambda event, target=widget: self._focus(target), add="+")
        widget.bind("<FocusOut>", lambda event, target=widget: self._blur(target), add="+")
        return widget

    def has_help(self, widget):
        return widget in self.help_by_widget

    def add_with_children(self, widget, text):
        self.add(widget, text)
        for child in widget.winfo_children():
            self.add_with_children(child, text)
        return widget

    def update(self, widget, text):
        self.help_by_widget[widget] = str(text)
        if self.hovered_widget is widget:
            self._set_help(widget)

    def _set_help(self, widget):
        self.help_variable.set(DEFAULT_HELP_TEXT if widget is None else self.help_by_widget.get(widget, DEFAULT_HELP_TEXT))

    def _cancel_pending(self):
        if self.pending_job is not None:
            self.root.after_cancel(self.pending_job)
            self.pending_job = None

    def _hide_popup(self):
        if self.hide_job is not None:
            self.root.after_cancel(self.hide_job)
            self.hide_job = None
        if self.popup is not None:
            self.popup.destroy()
            self.popup = None

    def _enter(self, widget):
        self.hovered_widget = widget
        self._set_help(widget)
        self._cancel_pending()
        self._hide_popup()
        if time.monotonic() >= self.cooldown_until.get(widget, 0.0):
            self.pending_job = self.root.after(TOOLTIP_DELAY_MS, lambda: self._show(widget))

    def _leave(self, widget):
        if self.hovered_widget is widget:
            self.hovered_widget = None
        self._cancel_pending()
        self._hide_popup()
        self.cooldown_until[widget] = time.monotonic() + TOOLTIP_COOLDOWN_SECONDS
        self._set_help(self.focused_widget)

    def _focus(self, widget):
        self.focused_widget = widget
        if self.hovered_widget is None:
            self._set_help(widget)

    def _blur(self, widget):
        if self.focused_widget is widget:
            self.focused_widget = None
        if self.hovered_widget is None:
            self._set_help(None)

    def _show(self, widget):
        self.pending_job = None
        try:
            exists = widget.winfo_exists()
            text = self.help_by_widget.get(widget)
        except (tk.TclError, TypeError):
            return
        if self.hovered_widget is not widget or not exists or not text:
            return
        popup = tk.Toplevel(self.root)
        popup.wm_overrideredirect(True)
        popup.attributes("-topmost", True)
        label = tk.Label(
            popup,
            text=text,
            justify="left",
            wraplength=360,
            background="#172127",
            foreground="#ffffff",
            borderwidth=1,
            relief="solid",
            padx=8,
            pady=5,
            font=("Segoe UI", 9),
        )
        label.pack()
        popup.geometry("+%d+%d" % (self.root.winfo_pointerx() + 14, self.root.winfo_pointery() + 18))
        self.popup = popup
        self.hide_job = self.root.after(TOOLTIP_DISPLAY_MS, self._hide_popup)


class ConnectionDialog:
    def __init__(self, application, item_id):
        self.application = application
        self.store = application.store
        self.tooltips = application.tooltips
        self.item_id = item_id
        self.window = tk.Toplevel(application.root)
        self.window.title("Connections " + item_id)
        self.window.geometry("820x610")
        self.window.minsize(720, 520)
        self.window.transient(application.root)
        self.window.grab_set()

        body = ttk.Frame(self.window, padding=14)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)
        title = ttk.Label(body, text="Connections " + item_id, font=("Segoe UI Semibold", 13))
        title.grid(row=0, column=0, sticky="w")
        self.tooltips.add(title, "Connections for the current component.")

        columns = ("Local", "Direction", "Peer", "PeerPort", "Fit")
        self.tree = ttk.Treeview(body, columns=columns, show="headings", height=9, selectmode="browse")
        headings = {"Local": "Local port", "Direction": "Direction", "Peer": "Connected to", "PeerPort": "Peer port", "Fit": "Fit"}
        widths = {"Local": 130, "Direction": 90, "Peer": 180, "PeerPort": 130, "Fit": 180}
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=widths[column], minwidth=80, stretch=column in ("Peer", "Fit"))
        self.tree.grid(row=1, column=0, sticky="nsew", pady=(10, 6))
        self.tree.bind("<<TreeviewSelect>>", lambda event: self._update_action_states())
        self.tooltips.add(self.tree, "Inspect the local port, direction, connected endpoint and dimensional fit.")

        actions = ttk.Frame(body)
        actions.grid(row=2, column=0, sticky="ew")
        self.remove_button = ttk.Button(actions, text="Remove connection", command=self.remove_connection, state="disabled")
        self.remove_button.pack(side="left")
        self.tooltips.add(self.remove_button, "Remove the selected logical connection.")
        self.override_button = ttk.Button(actions, text="Accept fit", command=self.accept_override, state="disabled")
        self.override_button.pack(side="left", padx=6)
        self.tooltips.add(self.override_button, "Accept this current mismatch without changing geometry.")

        ttk.Separator(body).grid(row=3, column=0, sticky="ew", pady=14)
        new_connection_label = ttk.Label(body, text="New connection", font=("Segoe UI Semibold", 11))
        new_connection_label.grid(row=4, column=0, sticky="w", pady=(0, 6))
        self.tooltips.add(new_connection_label, "Create a new connection from one free port to another endpoint.")
        form = ttk.Frame(body)
        form.grid(row=5, column=0, sticky="ew")
        self.local_port = tk.StringVar()
        self.endpoint_kind = tk.StringVar(value="Project component")
        self.peer_item = tk.StringVar()
        self.peer_port = tk.StringVar()
        self.external_name = tk.StringVar()
        self.connection_hint = tk.StringVar()
        self.local_box = self._combo_row(form, 0, "Local port", self.local_port, [], "Connection port on the current component.")
        self.kind_box = self._combo_row(form, 1, "Endpoint kind", self.endpoint_kind, ("Project component", "External"), "Connect to another project component or an external point.")
        self.peer_box = self._combo_row(form, 2, "Project component", self.peer_item, [], "Choose the component at the other end of the connection.")
        self.peer_port_box = self._combo_row(form, 3, "Peer port", self.peer_port, [], "Choose the port on the connected component.")
        external_label = ttk.Label(form, text="External point", width=18)
        external_label.grid(row=4, column=0, sticky="w", pady=4)
        self.external_entry = ttk.Entry(form, textvariable=self.external_name)
        self.external_entry.grid(row=4, column=1, sticky="ew", pady=4)
        external_help = "Enter a recognisable external name, such as AHU or Outside."
        self.tooltips.add(external_label, external_help)
        self.tooltips.add(self.external_entry, external_help)
        hint_label = ttk.Label(form, textvariable=self.connection_hint, style="Muted.TLabel", wraplength=560)
        hint_label.grid(row=5, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self.tooltips.add(hint_label, "Guidance for the currently selected connection endpoints.")
        form.columnconfigure(1, weight=1)
        self.local_box.bind("<<ComboboxSelected>>", lambda event: self._refresh_local_selection())
        self.kind_box.bind("<<ComboboxSelected>>", lambda event: self._refresh_target_mode())
        self.peer_box.bind("<<ComboboxSelected>>", lambda event: self._refresh_peer_ports())
        self.external_entry.bind("<KeyRelease>", lambda event: self._update_connect_state())

        footer = ttk.Frame(body)
        footer.grid(row=6, column=0, sticky="ew", pady=(12, 0))
        self.ok_button = ttk.Button(footer, text="OK", command=self.close)
        self.ok_button.pack(side="right")
        self.tooltips.add(self.ok_button, "Close this dialog and keep the saved connections.")
        self.connect_button = ttk.Button(footer, text="Connect", style="Accent.TButton", command=self.add_connection)
        self.connect_button.pack(side="right", padx=6)
        self.tooltips.add(self.connect_button, "Create the connection and check dimensional compatibility.")
        self.refresh()
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda event: self.close())

    def _combo_row(self, parent, row, label, variable, values, help_text):
        label_widget = ttk.Label(parent, text=label, width=18)
        label_widget.grid(row=row, column=0, sticky="w", pady=4)
        widget = ttk.Combobox(parent, textvariable=variable, values=values, state="readonly")
        widget.grid(row=row, column=1, sticky="ew", pady=4)
        self.tooltips.add(label_widget, help_text)
        self.tooltips.add(widget, help_text)
        return widget

    def _local_endpoint(self, connection):
        if connection["from"].get("kind") == "item" and connection["from"].get("id") == self.item_id:
            return connection["from"], connection["to"], "out"
        return connection["to"], connection["from"], "in"

    def refresh(self):
        selected = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        issues = {issue["connection_id"]: issue for issue in self.store.connection_issues(self.item_id) if issue["connection_id"]}
        for connection in self.store.connections_for(self.item_id):
            local, peer, direction = self._local_endpoint(connection)
            issue = issues.get(connection["id"])
            if issue and issue["accepted"]:
                fit = "Accepted"
            elif issue:
                fit = "Does not fit"
            elif peer["kind"] == "external":
                fit = "External"
            else:
                fit = "Fits"
            self.tree.insert("", "end", iid=connection["id"], values=(
                local["port"], "From" if direction == "in" else "To", peer["id"], peer.get("port", ""), fit,
            ))
        if selected and self.tree.exists(selected[0]):
            self.tree.selection_set(selected[0])
        used = {local["port"] for connection in self.store.connections_for(self.item_id) for local, _, _ in (self._local_endpoint(connection),)}
        local_ports = [port["name"] for port in self.store.ports(self.item_id) if port["name"] not in used]
        self.local_box.configure(values=local_ports)
        if self.local_port.get() not in local_ports:
            self.local_port.set(local_ports[0] if local_ports else "")
        peers = [item["id"] for item in self.store.items if item["id"] != self.item_id]
        self.peer_box.configure(values=peers)
        if self.peer_item.get() not in peers:
            self.peer_item.set(peers[0] if peers else "")
        self._refresh_local_selection()
        self._update_action_states()

    def _refresh_local_selection(self):
        external_only = bool(self.local_port.get()) and self.store.port(self.item_id, self.local_port.get())["external_only"]
        if external_only:
            self.endpoint_kind.set("External")
        self.kind_box.configure(state="disabled" if external_only else "readonly")
        self._refresh_target_mode()

    def _refresh_target_mode(self):
        internal = self.endpoint_kind.get() == "Project component"
        self.peer_box.configure(state="readonly" if internal else "disabled")
        self.peer_port_box.configure(state="readonly" if internal else "disabled")
        self.external_entry.configure(state="disabled" if internal else "normal")
        self._refresh_peer_ports()

    def _refresh_peer_ports(self):
        values = []
        internal = self.endpoint_kind.get() == "Project component"
        if internal and self.local_port.get() and self.peer_item.get():
            local = self.store.port(self.item_id, self.local_port.get())
            remote_direction = "out" if local["direction"] == "in" else "in"
            used = {
                endpoint["port"]
                for connection in self.store.connections_for(self.peer_item.get())
                for endpoint in (connection["from"], connection["to"])
                if endpoint.get("kind") == "item" and endpoint.get("id") == self.peer_item.get()
            }
            values = [port["name"] for port in self.store.ports(self.peer_item.get(), remote_direction) if port["name"] not in used and not port["external_only"]]
        self.peer_port_box.configure(values=values)
        if self.peer_port.get() not in values:
            self.peer_port.set(values[0] if values else "")
        if not self.local_port.get():
            self.connection_hint.set("This component has no free local ports.")
        elif not internal:
            local = self.store.port(self.item_id, self.local_port.get())
            if local["external_only"]:
                self.connection_hint.set("This is a wall side of a passive fire grille. Enter an external name such as Outside or Room.")
            else:
                self.connection_hint.set("Enter a recognisable external name such as AHU, Outside or Room.")
        elif not self.peer_item.get():
            self.connection_hint.set("Choose another project component first.")
        elif not values:
            peer = self.store.item(self.peer_item.get())
            if peer["parameters"]["family"] == "GRILLE_FIRE":
                self.connection_hint.set(self.peer_item.get()+" is a passive GE60/GE60K/GE60XL wall grille. The catalogue does not permit a mechanical ventilation connection; use external points only.")
            else:
                self.connection_hint.set("The selected component has no free peer port in the required direction.")
        else:
            self.connection_hint.set("Choose the peer port; dimensional fit is checked when you connect it.")
        self._update_connect_state()

    def _update_connect_state(self):
        ready = bool(self.local_port.get())
        if self.endpoint_kind.get() == "External":
            ready = ready and bool(self.external_name.get().strip())
        else:
            ready = ready and bool(self.peer_item.get()) and bool(self.peer_port.get())
        self.connect_button.configure(state="normal" if ready else "disabled")

    def add_connection(self):
        try:
            local = self.store.port(self.item_id, self.local_port.get())
            local_endpoint = {"kind": "item", "id": self.item_id, "port": local["name"]}
            if self.endpoint_kind.get() == "External":
                peer = {"kind": "external", "id": self.external_name.get(), "port": ""}
            else:
                if not self.peer_port.get():
                    raise InputError(self.connection_hint.get() or "Choose a valid peer port.")
                peer = {"kind": "item", "id": self.peer_item.get(), "port": self.peer_port.get()}
            source, target = (peer, local_endpoint) if local["direction"] == "in" else (local_endpoint, peer)
            self.store.add_connection(source, target)
            self.external_name.set("")
            self.refresh()
            self.application.refresh_register()
            self.application.load_connection_summaries(self.item_id)
        except Exception as error:
            messagebox.showerror("Not connected", str(error), parent=self.window)

    def remove_connection(self):
        selection = self.tree.selection()
        if not selection:
            return
        if not messagebox.askyesno("Remove connection", "Remove the selected port connection?", parent=self.window):
            return
        self.store.remove_connection(selection[0])
        self.refresh()
        self.application.refresh_register()
        self.application.load_connection_summaries(self.item_id)

    def accept_override(self):
        selection = self.tree.selection()
        if not selection:
            return
        connection = self.store.connection(selection[0])
        text = ("These connection dimensions do not fit. The STEP build may continue without changing the geometry.\n\n"
                + self.store.endpoint_text(connection["from"]) + " -> " + self.store.endpoint_text(connection["to"])
            + "\n\nThis acceptance expires when either component changes. Accept the fit anyway?")
        if messagebox.askyesno("Accept fit manually", text, parent=self.window):
            self.store.accept_fit_override(connection["id"])
            self.refresh()
            self.application.refresh_register()

    def _update_action_states(self):
        selection = self.tree.selection()
        self.remove_button.configure(state="normal" if selection else "disabled")
        overrideable = False
        if selection:
            overrideable = any(issue["connection_id"] == selection[0] and issue["overrideable"] for issue in self.store.connection_issues(self.item_id))
        self.override_button.configure(state="normal" if overrideable else "disabled")

    def close(self):
        self.window.grab_release()
        self.window.destroy()


class ProjectApplication:
    def __init__(self, root, project_path, remember_project=True):
        self.root = root
        self.remember_project = remember_project
        self.root.title(APP_TITLE)
        width = min(1450, max(980, self.root.winfo_screenwidth() - 40))
        height = min(850, max(640, self.root.winfo_screenheight() - 90))
        self.root.geometry(str(width) + "x" + str(height) + "+10+10")
        self.root.minsize(min(1050, width), min(640, height))
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.settings = load_settings()
        self.store = None
        self.current_id = None
        self.field_variables = {}
        self.field_widgets = {}
        self.field_labels = {}
        self.family_labels = {}
        self.family_ids = {}
        self.process = None
        self.pending_job = None
        self.worker_log = None
        self.build_started = None
        self.cancel_reason = ""
        self.type_browser = None
        self.type_browser_tree = None
        self.preview_photo = None
        self.update_check_running = False
        self.help_text = tk.StringVar(value=DEFAULT_HELP_TEXT)
        self.tooltips = TooltipManager(root, self.help_text)
        self._style()
        self._build_ui()
        self.open_project(project_path)
        if os.name == "nt":
            self.root.state("zoomed")
        self.root.after_idle(self._position_split)
        if self.remember_project:
            self.root.after(750, self.check_for_updates)

    def _style(self):
        self.root.configure(background="#eef2f4")
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", background="#f7f9fa", foreground="#172127", fieldbackground="#ffffff", bordercolor="#aeb8be", lightcolor="#dfe5e8", darkcolor="#8f9ba2")
        style.configure("TFrame", background="#f7f9fa")
        style.configure("Header.TFrame", background="#e7edef")
        style.configure("TLabel", background="#f7f9fa", foreground="#172127", font=("Segoe UI", 10))
        style.configure("Title.TLabel", background="#e7edef", foreground="#172127", font=("Segoe UI Semibold", 15))
        style.configure("Muted.TLabel", foreground="#5e6b72")
        style.configure("TButton", font=("Segoe UI Semibold", 9), padding=(10, 7))
        style.configure("Accent.TButton", background="#216b5a", foreground="#ffffff")
        style.map("Accent.TButton", background=[("active", "#2b806c"), ("disabled", "#c7d0d3")], foreground=[("disabled", "#6d787e")])
        style.configure("TEntry", padding=5)
        style.configure("TCombobox", padding=4)
        style.configure("Treeview", background="#ffffff", fieldbackground="#ffffff", foreground="#172127", rowheight=30, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", background="#dfe6e9", foreground="#172127", font=("Segoe UI Semibold", 10), padding=7)
        style.map("Treeview", background=[("selected", "#2f7d67")], foreground=[("selected", "#ffffff")])

    def _build_ui(self):
        header = ttk.Frame(self.root, style="Header.TFrame", padding=(14, 10))
        header.pack(fill="x")
        title_label = ttk.Label(header, text=APP_TITLE, style="Title.TLabel")
        title_label.pack(side="left")
        self.tooltips.add(title_label, "AAVDS duct component and STEP project builder.")
        self.project_label = ttk.Label(header, text="", style="Muted.TLabel")
        self.project_label.pack(side="left", padx=(18, 0))
        self.tooltips.add(self.project_label, "Current project folder.")
        update_button = ttk.Button(header, text="Check for updates", command=lambda: self.check_for_updates(show_current=True))
        update_button.pack(side="right")
        self.tooltips.add(update_button, "Check the public version endpoint for a newer signed AAVDS release.")
        project_button = ttk.Button(header, text="Project folder", command=self.choose_project)
        project_button.pack(side="right")
        self.tooltips.add(project_button, "Choose or create the folder that stores the project, STEP files and logs.")

        self.main_pane = ttk.Panedwindow(self.root, orient="horizontal")
        self.main_pane.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        left = ttk.Frame(self.main_pane, padding=12)
        right = ttk.Frame(self.main_pane, padding=(10, 12))
        self.main_pane.add(left, weight=4)
        self.main_pane.add(right, weight=7)
        self._build_editor(left)
        self._build_register(right)

        footer = ttk.Frame(self.root, padding=(12, 6))
        footer.pack(fill="x")
        status_row = ttk.Frame(footer)
        status_row.pack(fill="x")
        self.status = tk.StringVar(value="Ready")
        status_label = ttk.Label(status_row, textvariable=self.status, style="Muted.TLabel")
        status_label.pack(side="left", fill="x", expand=True)
        self.tooltips.add(status_label, "Current project or build status.")
        self.progress = ttk.Progressbar(footer, mode="indeterminate", length=220)
        self.progress.pack(in_=status_row, side="right")
        self.tooltips.add(self.progress, "FreeCAD is currently building and validating component geometry.")
        self.help_label = ttk.Label(footer, textvariable=self.help_text, style="Muted.TLabel")
        self.help_label.pack(fill="x", pady=(4, 0))
        self.tooltips.add(self.help_label, "Context-sensitive help for the control under the pointer or keyboard focus.")

    def _position_split(self):
        width = max(self.root.winfo_width(), 980)
        self.main_pane.sashpos(0, min(560, max(430, int(width * 0.40))))

    def _build_editor(self, parent):
        component_label = ttk.Label(parent, text="Component", font=("Segoe UI Semibold", 12))
        component_label.pack(anchor="w", pady=(0, 10))
        self.tooltips.add(component_label, "Edit the selected project component.")
        identity = ttk.Frame(parent)
        identity.pack(fill="x")
        self.prefix = tk.StringVar()
        self.item_id = tk.StringVar()
        self.from_ref = tk.StringVar()
        self.to_ref = tk.StringVar()
        self._entry_row(identity, 0, "Project prefix", self.prefix, help_text="Prefix used in generated file names and project identification.")
        self._entry_row(identity, 1, "ID", self.item_id, help_text="Unique component ID, for example A-10 or B-20.")
        self._entry_row(identity, 2, "From", self.from_ref, "readonly", "Components or external points connected to this component's inputs.")
        self._entry_row(identity, 3, "To", self.to_ref, "readonly", "Components or external points connected to this component's outputs.")
        self.connections_button = ttk.Button(identity, text="Connections...", command=self.open_connections)
        self.connections_button.grid(row=2, column=2, rowspan=2, sticky="n", padx=(8, 0), pady=4)
        self.tooltips.add(self.connections_button, "Create, inspect or remove component connections.")

        type_label = ttk.Label(parent, text="Type", padding=(0, 12, 0, 4))
        type_label.pack(anchor="w")
        type_help = "Select the component family. The input fields below adapt automatically."
        self.tooltips.add(type_label, type_help)
        for family_id, specification in FAMILIES.items():
            suffix = "" if specification["status"] == "IMPLEMENTED" else " [source register only]"
            label = family_id + " - " + FAMILY_NAMES.get(family_id, family_id) + suffix
            self.family_labels[family_id] = label
            self.family_ids[label] = family_id
        self.family_options = sorted(self.family_ids, key=str.casefold)
        self.family = tk.StringVar()
        self.family_box = ttk.Combobox(parent, textvariable=self.family, values=self.family_options, state="normal")
        self.family_box.pack(fill="x")
        self.tooltips.add(self.family_box, type_help)
        self.family_box.bind("<<ComboboxSelected>>", self.family_changed)
        self.family_box.bind("<KeyRelease>", self.family_typed)
        self.family_box.bind("<Return>", self.family_typed_commit)

        preview_row = ttk.Frame(parent)
        preview_row.pack(fill="x", pady=(7, 0))
        self.preview_canvas = tk.Canvas(
            preview_row,
            width=320,
            height=160,
            background="#ffffff",
            highlightthickness=1,
            highlightbackground="#c8d1d6",
        )
        self.preview_canvas.pack(side="left", fill="x", expand=True)
        self.preview_canvas.bind("<Configure>", lambda event: self.refresh_type_preview())
        self.tooltips.add(self.preview_canvas, "Technical drawing for the selected component type.")
        type_actions = ttk.Frame(preview_row)
        type_actions.pack(side="right", fill="y", padx=(8, 0))
        self.show_types_button = ttk.Button(type_actions, text="Show all types", command=self.show_all_types)
        self.show_types_button.pack(fill="x")
        self.tooltips.add(self.show_types_button, "Open an overview of every available component type.")
        self.open_pdf_button = ttk.Button(type_actions, text="Open PDF", command=self.open_pdf, state="disabled")
        self.open_pdf_button.pack(fill="x", pady=(6, 0))
        self.tooltips.add(self.open_pdf_button, "Open the primary catalogue PDF for the selected component type.")

        ttk.Separator(parent).pack(fill="x", pady=12)
        canvas_frame = ttk.Frame(parent)
        canvas_frame.pack(fill="both", expand=True)
        self.parameter_canvas = tk.Canvas(canvas_frame, height=130, background="#f7f9fa", highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=self.parameter_canvas.yview)
        self.parameter_canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.parameter_canvas.pack(side="left", fill="both", expand=True)
        self.tooltips.add(self.parameter_canvas, "Parameters for the selected component type.")
        self.tooltips.add(scrollbar, "Scroll through the component parameters.")
        self.parameter_form = ttk.Frame(self.parameter_canvas)
        self.parameter_window = self.parameter_canvas.create_window((0, 0), window=self.parameter_form, anchor="nw")
        self.parameter_form.bind("<Configure>", lambda event: self.parameter_canvas.configure(scrollregion=self.parameter_canvas.bbox("all")))
        self.parameter_canvas.bind("<Configure>", lambda event: self.parameter_canvas.itemconfigure(self.parameter_window, width=event.width))

        controls = ttk.Frame(parent)
        controls.pack(fill="x", pady=(12, 0))
        new_button = ttk.Button(controls, text="New", command=self.new_item)
        new_button.pack(side="left")
        self.tooltips.add(new_button, "Start a new component using the next available ID.")
        save_button = ttk.Button(controls, text="Save", command=self.save_current)
        save_button.pack(side="left", padx=6)
        self.tooltips.add(save_button, "Validate and save this component in the project register.")
        self.build_selected_button = ttk.Button(controls, text="Build selection", style="Accent.TButton", command=self.build_selected)
        self.build_selected_button.pack(side="right")
        self.tooltips.add(self.build_selected_button, "Save and build the selected components as validated STEP files.")
        self.cancel_button = ttk.Button(controls, text="Stop build", command=self.cancel_build, state="disabled")
        self.cancel_button.pack(side="right", padx=6)
        self.tooltips.add(self.cancel_button, "Stop the active FreeCAD build. Accepted files remain unchanged.")

    def _entry_row(self, parent, row, label, variable, state="normal", help_text=""):
        label_widget = ttk.Label(parent, text=label, width=16)
        label_widget.grid(row=row, column=0, sticky="w", pady=4)
        entry = ttk.Entry(parent, textvariable=variable, state=state)
        entry.grid(row=row, column=1, sticky="ew", pady=4)
        self.tooltips.add(label_widget, help_text)
        self.tooltips.add(entry, help_text)
        parent.columnconfigure(1, weight=1)

    def _build_register(self, parent):
        app_selector = ttk.Frame(parent)
        app_selector.pack(fill="x", pady=(0, 8))
        app_label = ttk.Label(app_selector, text="My 3D app:")
        app_label.pack(side="left")
        app_help = "Choose which application opens accepted STEP files. The selection is saved for your next session."
        self.tooltips.add(app_label, app_help)
        selected_app = self.settings.get("3d_app", "FreeCAD")
        if selected_app not in ("Inventor", "Fusion 360", "FreeCAD"):
            selected_app = "FreeCAD"
        self.preferred_3d_app = tk.StringVar(value=selected_app)
        self.app_radios = []
        for name in ("Inventor", "Fusion 360", "FreeCAD"):
            radio = ttk.Radiobutton(app_selector, text=name, value=name, variable=self.preferred_3d_app, command=self.save_3d_app)
            radio.pack(side="left", padx=(10, 0))
            self.tooltips.add(radio, app_help)
            self.app_radios.append(radio)

        heading = ttk.Frame(parent)
        heading.pack(fill="x", pady=(0, 10))
        register_label = ttk.Label(heading, text="Project register", font=("Segoe UI Semibold", 12))
        register_label.pack(side="left")
        self.tooltips.add(register_label, "All components in the current project.")
        self.build_changed_button = ttk.Button(heading, text="Build changed", style="Accent.TButton", command=self.build_changed)
        self.build_changed_button.pack(side="right")
        self.tooltips.add(self.build_changed_button, "Build every component that changed since its last accepted build.")
        open_step_button = ttk.Button(heading, text="Open STEP", command=self.open_step)
        open_step_button.pack(side="right", padx=6)
        self.tooltips.add(open_step_button, "Open the selected STEP using your chosen 3D application.")
        self.area_button = ttk.Button(heading, text="Change area...", command=self.edit_area, state="disabled")
        self.area_button.pack(side="right")
        self.tooltips.add(self.area_button, "Override the measured pricing area, or clear it to restore the measured value.")
        remove_button = ttk.Button(heading, text="Remove", command=self.delete_selected)
        remove_button.pack(side="right")
        self.tooltips.add(remove_button, "Remove selected components and their registered output files.")

        columns = ("ID", "Size", "Type", "From", "To", "Error", "Area", "Rate", "Total")
        table = ttk.Frame(parent)
        table.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(table, columns=columns, show="headings", selectmode="extended")
        widths = {"ID": 80, "Size": 190, "Type": 115, "From": 110, "To": 110, "Error": 220, "Area": 90, "Rate": 115, "Total": 100}
        for column in columns:
            self.tree.heading(column, text=column, command=lambda name=column: self.sort_register(name))
            self.tree.column(column, width=widths[column], minwidth=70, stretch=column in ("Size", "From", "To", "Error"), anchor="e" if column in ("Area", "Rate", "Total") else "w")
        vertical = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        horizontal = ttk.Scrollbar(table, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        table.rowconfigure(0, weight=1)
        table.columnconfigure(0, weight=1)
        self.tree.bind("<<TreeviewSelect>>", self.selection_changed)
        self.tree.bind("<Double-1>", self.register_double_click)
        self.tree.bind("<Motion>", self.register_pointer_help, add="+")
        self.tooltips.add(self.tree, "Select a component to edit it. Move across columns for specific details.")
        self.tooltips.add(vertical, "Scroll through the project register.")
        self.tooltips.add(horizontal, "Scroll through the project register columns.")
        self.tree.tag_configure("dirty", foreground="#8a5b00")
        self.tree.tag_configure("error", foreground="#b42318")
        self.tree.tag_configure("built", foreground="#176b4d")

    def open_project(self, path):
        try:
            self.store = ProjectStore(path)
            self.project_label.configure(text=str(self.store.root))
            self.prefix.set(self.store.prefix)
            if self.remember_project:
                save_settings({"last_project": str(self.store.root)})
            self.refresh_register()
            if self.store.items:
                self.select_item(self.store.items[0]["id"])
            else:
                self.new_item()
            self.status.set("Project loaded: " + self.store.data["name"])
        except Exception as error:
            messagebox.showerror(APP_TITLE, str(error), parent=self.root)

    def choose_project(self):
        if self.process is not None:
            return
        initial = str(self.store.root if self.store else default_project_path())
        selected = filedialog.askdirectory(title="Choose AAVDS project folder", initialdir=initial)
        if selected:
            self.open_project(selected)

    def save_3d_app(self):
        selected = self.preferred_3d_app.get()
        self.settings["3d_app"] = selected
        save_settings({"3d_app": selected})

    def _family_pdf(self, family_id):
        sources = FAMILIES.get(family_id, {}).get("sources", [])
        if not sources:
            return None
        source = CAT.get("sources", {}).get(sources[0].get("source_id"), {})
        filename = source.get("filename")
        return PACKAGE_DIR / "sources" / filename if filename else None

    def open_pdf(self):
        family_id = self.family_ids.get(self.family.get())
        path = self._family_pdf(family_id)
        if path is None:
            messagebox.showinfo(APP_TITLE, "No catalogue PDF is registered for this component type.", parent=self.root)
            return
        if not path.is_file():
            messagebox.showerror("PDF not opened", "The catalogue PDF is missing from the installation:\n" + str(path), parent=self.root)
            return
        try:
            if os.name == "nt":
                os.startfile(str(path))
            else:
                webbrowser.open(path.as_uri())
        except OSError as error:
            messagebox.showerror("PDF not opened", str(error), parent=self.root)

    def _application_executable(self, application):
        key = "inventor_path" if application == "Inventor" else "fusion_path"
        configured = Path(self.settings.get(key, ""))
        if configured.is_file():
            return configured
        if application == "Inventor":
            found = registered_application(("Inventor.exe",))
            if found is None:
                root = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Autodesk"
                candidates = sorted(root.glob("Inventor */Bin/Inventor.exe"), reverse=True)
                found = candidates[0] if candidates else None
        else:
            found = registered_application(("FusionLauncher.exe", "Autodesk Fusion 360.exe"))
            if found is None:
                root = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Autodesk" / "webdeploy" / "production"
                candidates = sorted(root.glob("*/FusionLauncher.exe"), reverse=True)
                found = candidates[0] if candidates else None
        if found is None:
            found_name = filedialog.askopenfilename(
                title="Locate " + application,
                filetypes=(("Applications", "*.exe"), ("All files", "*.*")),
                parent=self.root,
            )
            if not found_name:
                return None
            found = Path(found_name)
        self.settings[key] = str(found)
        save_settings({key: str(found)})
        return found

    def check_for_updates(self, show_current=False):
        if self.update_check_running:
            return
        self.update_check_running = True

        def fetch():
            try:
                request = urllib.request.Request(UPDATE_ENDPOINT, headers={"Accept": "application/json"})
                with urllib.request.urlopen(request, timeout=4) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                if payload.get("schema") != "aavds-public-update-v1" or payload.get("product") != APP_TITLE:
                    raise ValueError("The public update response is not valid for this product.")
                self.root.after(0, lambda: self._handle_update_result(payload, show_current))
            except Exception as error:
                self.root.after(0, lambda message=str(error): self._handle_update_error(message, show_current))

        threading.Thread(target=fetch, name="AAVDS update check", daemon=True).start()

    def _handle_update_result(self, payload, show_current):
        self.update_check_running = False
        latest = payload.get("latestVersion")
        if is_newer_release(latest):
            text = "A newer AAVDS release is available: " + str(latest) + ".\n\nRequest this update by email?"
            if messagebox.askyesno("Update available", text, parent=self.root):
                self.request_update(latest)
        elif show_current:
            message = "No published update is currently available." if not latest else "You are using the latest AAVDS release."
            messagebox.showinfo("AAVDS updates", message, parent=self.root)

    def _handle_update_error(self, message, show_current):
        self.update_check_running = False
        if show_current:
            messagebox.showwarning("Update check unavailable", "The update service could not be reached.\n\n" + message, parent=self.root)

    def request_update(self, latest):
        recipient = os.environ.get("AAVDS_UPDATE_EMAIL", "").strip()
        if not recipient:
            messagebox.showinfo(
                "Update request not configured",
                "No update-request email address is configured. Set AAVDS_UPDATE_EMAIL and try again.",
                parent=self.root,
            )
            return
        query = urllib.parse.urlencode({
            "subject": "AAVDS update request: " + str(latest),
            "body": "Please provide the " + str(latest) + " update for " + APP_TITLE + ".\nCurrent version: " + APP_VERSION,
        })
        webbrowser.open("mailto:" + urllib.parse.quote(recipient, safe="@,+") + "?" + query)

    def family_typed(self, event=None):
        if event is not None and event.keysym in ("Return", "Escape", "Tab", "Up", "Down", "Left", "Right"):
            return
        query = self.family.get().strip().casefold()
        self.family_box.configure(values=self._family_matches(query))

    def _family_matches(self, query):
        query = str(query).strip().casefold()
        if not query:
            return list(self.family_options)
        return [
            label
            for label in self.family_options
            for family_id in (self.family_ids[label],)
            if family_id.casefold().startswith(query)
            or FAMILY_NAMES.get(family_id, family_id).casefold().startswith(query)
        ]

    def select_family(self, family_id):
        self.family.set(self.family_labels[family_id])
        self.family_changed()
        self.family_box.icursor("end")

    def refresh_type_preview(self):
        if not hasattr(self, "preview_canvas"):
            return
        canvas = self.preview_canvas
        canvas.delete("all")
        self.preview_photo = None
        family_id = self.family_ids.get(self.family.get())
        width = max(canvas.winfo_width(), int(canvas["width"]))
        height = max(canvas.winfo_height(), int(canvas["height"]))
        if family_id is None:
            canvas.create_text(width / 2, height / 2, text="Select a component type", fill="#65727a")
            return
        path = TYPE_PREVIEW_DIR / (family_id + ".png")
        if not path.is_file():
            canvas.create_text(
                width / 2,
                height / 2,
                text="Technical preview not available\n" + family_id,
                fill="#65727a",
                justify="center",
            )
            return
        try:
            with Image.open(path) as source:
                image = source.convert("RGBA")
            image.thumbnail((max(width - 16, 1), max(height - 16, 1)), Image.Resampling.LANCZOS)
            self.preview_photo = ImageTk.PhotoImage(image)
            canvas.create_image(width / 2, height / 2, image=self.preview_photo, anchor="center")
        except (OSError, ValueError) as error:
            canvas.create_text(
                width / 2,
                height / 2,
                text="Preview could not be loaded\n" + str(error),
                fill="#b42318",
                justify="center",
                width=max(width - 20, 20),
            )

    def show_all_types(self):
        if self.type_browser is not None and self.type_browser.winfo_exists():
            self.type_browser.deiconify()
            self.type_browser.lift()
            self.type_browser.focus_force()
            return
        window = tk.Toplevel(self.root)
        self.type_browser = window
        window.title("All component types")
        window.transient(self.root)
        window.minsize(620, 420)
        window.geometry("760x560")
        window.protocol("WM_DELETE_WINDOW", self.close_type_browser)

        body = ttk.Frame(window, padding=12)
        body.pack(fill="both", expand=True)
        heading = ttk.Label(body, text="All component types", font=("Segoe UI Semibold", 13))
        heading.pack(anchor="w", pady=(0, 8))
        self.tooltips.add(heading, "Double-click a row to select that component type.")

        table = ttk.Frame(body)
        table.pack(fill="both", expand=True)
        columns = ("Code", "Type", "Build support")
        tree = ttk.Treeview(table, columns=columns, show="headings", selectmode="browse")
        self.type_browser_tree = tree
        tree.heading("Code", text="Code")
        tree.heading("Type", text="Type")
        tree.heading("Build support", text="Build support")
        tree.column("Code", width=150, minwidth=110, stretch=False)
        tree.column("Type", width=360, minwidth=220, stretch=True)
        tree.column("Build support", width=150, minwidth=130, stretch=False)
        scrollbar = ttk.Scrollbar(table, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.tooltips.add(tree, "All component types. Double-click a row to select it.")
        self.tooltips.add(scrollbar, "Scroll through all component types.")
        for family_id in sorted(FAMILIES, key=str.casefold):
            specification = FAMILIES[family_id]
            build_support = "Implemented" if specification["status"] == "IMPLEMENTED" else "Reference only"
            tree.insert("", "end", iid=family_id, values=(family_id, FAMILY_NAMES.get(family_id, family_id), build_support))
        current_id = self.family_ids.get(self.family.get())
        if current_id and tree.exists(current_id):
            tree.selection_set(current_id)
            tree.focus(current_id)
            tree.see(current_id)
        tree.bind("<Double-1>", self.accept_type_browser)
        tree.bind("<Return>", self.accept_type_browser)

        actions = ttk.Frame(body)
        actions.pack(fill="x", pady=(10, 0))
        cancel = ttk.Button(actions, text="Cancel", command=self.close_type_browser)
        cancel.pack(side="right")
        select = ttk.Button(actions, text="Select type", style="Accent.TButton", command=self.accept_type_browser)
        select.pack(side="right", padx=(0, 6))
        self.tooltips.add(cancel, "Close the type overview without changing the selection.")
        self.tooltips.add(select, "Select the highlighted component type.")
        tree.focus_set()

    def accept_type_browser(self, event=None):
        if self.type_browser_tree is None:
            return
        if event is not None and event.type == tk.EventType.ButtonPress and self.type_browser_tree.identify_region(event.x, event.y) != "cell":
            return
        selection = self.type_browser_tree.selection()
        if not selection:
            self.root.bell()
            return
        self.select_family(selection[0])
        self.close_type_browser()

    def close_type_browser(self):
        if self.type_browser is not None and self.type_browser.winfo_exists():
            self.type_browser.destroy()
        self.type_browser = None
        self.type_browser_tree = None

    def family_typed_commit(self, event=None):
        query = self.family.get().strip().casefold()
        exact_code = self.family_labels.get(query.upper())
        matches = self._family_matches(query) if query else []
        selected = exact_code or (matches[0] if len(matches) == 1 else None)
        if selected is None:
            self.root.bell()
            return "break"
        self.select_family(self.family_ids[selected])
        return "break"

    def family_changed(self, event=None, parameters=None):
        family_id = self.family_ids.get(self.family.get())
        if family_id is None:
            self.open_pdf_button.configure(state="disabled")
            self.refresh_type_preview()
            return
        self.open_pdf_button.configure(state="normal" if self._family_pdf(family_id) else "disabled")
        self.refresh_type_preview()
        self.family_box.configure(values=self.family_options)
        for child in self.parameter_form.winfo_children():
            child.destroy()
        self.field_variables = {}
        self.field_widgets = {}
        self.field_labels = {}
        values = defaults(family_id) if parameters is None else parameters
        for row, field in enumerate(FAMILIES[family_id]["fields"]):
            label = ttk.Label(self.parameter_form, text=english_field_label(field), wraplength=210)
            label.grid(row=row, column=0, sticky="w", padx=(0, 10), pady=4)
            value = values.get(field["key"], field["default"])
            display_value = english_choice_label(value) if field["kind"] == "choice" else format_value(value)
            variable = tk.StringVar(value=display_value)
            thicknesses = rectangular_priced_thicknesses(family_id, values.get("material")) if field["key"] == "t_mm" else ()
            if thicknesses:
                choices = [format_value(value) for value in thicknesses]
                if variable.get() not in choices:
                    variable.set("")
                widget = ttk.Combobox(self.parameter_form, textvariable=variable, values=choices, state="readonly")
            elif field["kind"] == "choice":
                choices = [english_choice_label(choice) for choice in field["choices"]]
                widget = ttk.Combobox(self.parameter_form, textvariable=variable, values=choices, state="readonly")
            elif field["kind"] == "file":
                widget = ttk.Frame(self.parameter_form)
                entry = ttk.Entry(widget, textvariable=variable)
                entry.pack(side="left", fill="x", expand=True)
                ttk.Button(widget, text="Choose...", command=lambda key=field["key"]: self.choose_parameter_file(key)).pack(side="left", padx=(6, 0))
            else:
                widget = ttk.Entry(self.parameter_form, textvariable=variable)
            widget.grid(row=row, column=1, sticky="ew", pady=4)
            help_text = FIELD_HELP.get(field["key"], "Enter the value for " + english_field_label(field) + ".")
            self.tooltips.add(label, help_text)
            self.tooltips.add_with_children(widget, help_text)
            self.field_variables[field["key"]] = variable
            self.field_widgets[field["key"]] = widget
            self.field_labels[field["key"]] = label
        self.parameter_form.columnconfigure(1, weight=1)
        if "t_mm" in self.field_widgets and "material" in self.field_widgets:
            self.field_widgets["material"].bind("<<ComboboxSelected>>", self.refresh_thickness_choices, add="+")
        for field_key in ("thickness_mode", "insertion_mode"):
            if field_key in self.field_widgets:
                self.field_widgets[field_key].bind("<<ComboboxSelected>>", self.refresh_field_visibility, add="+")
        self.refresh_field_visibility()

    def register_pointer_help(self, event):
        column_help = REGISTER_HELP.get(self.tree.identify_column(event.x))
        if column_help:
            self.tooltips.update(self.tree, column_help)

    def refresh_field_visibility(self, event=None):
        def set_visible(field_key, visible):
            if field_key not in self.field_widgets:
                return
            if visible:
                self.field_labels[field_key].grid()
                self.field_widgets[field_key].grid()
            else:
                self.field_labels[field_key].grid_remove()
                self.field_widgets[field_key].grid_remove()

        if "thickness_mode" in self.field_variables:
            thickness_mode = english_choice_value(self.field_variables["thickness_mode"].get())
            set_visible("t_mm", thickness_mode != "AIRKAN_BC")
            set_visible("airkan_a_mm", False)
        if "insertion_mode" in self.field_variables:
            insertion_mode = english_choice_value(self.field_variables["insertion_mode"].get())
            set_visible("insertion_mm", insertion_mode == "HANDMATIGE_INSTEEK")

    def refresh_thickness_choices(self, event=None):
        family_id = self.family_ids.get(self.family.get())
        if family_id is None or "t_mm" not in self.field_widgets or "material" not in self.field_variables:
            return
        choices = [format_value(value) for value in rectangular_priced_thicknesses(family_id, self.field_variables["material"].get())]
        if not choices:
            return
        self.field_widgets["t_mm"].configure(values=choices)
        if self.field_variables["t_mm"].get() not in choices:
            self.field_variables["t_mm"].set("")

    def choose_parameter_file(self, field_key):
        current = Path(self.field_variables[field_key].get()).expanduser()
        initial = str(current.parent) if current.parent.is_dir() else str(self.store.root if self.store else PACKAGE_DIR)
        selected = filedialog.askopenfilename(
            title="Choose STEP file",
            initialdir=initial,
            filetypes=(("STEP files", "*.step *.stp"), ("All files", "*.*")),
        )
        if selected:
            self.field_variables[field_key].set(selected)

    def collect_parameters(self):
        family_id = self.family_ids.get(self.family.get())
        if family_id is None:
            raise InputError("Choose a component type.")
        parameters = {"family": family_id, "prefix": self.prefix.get().strip()}
        for field in FAMILIES[family_id]["fields"]:
            raw = self.field_variables[field["key"]].get().strip()
            if field["kind"] == "choice":
                parameters[field["key"]] = english_choice_value(raw)
            elif field["kind"] in ("text", "file"):
                parameters[field["key"]] = raw
            else:
                if field["key"] == "t_mm" and not raw and parameters.get("thickness_mode") == "AIRKAN_BC":
                    parameters[field["key"]] = 0.0
                    continue
                if field["key"] == "insertion_mm" and parameters.get("insertion_mode") == "BOM_REFERENTIE":
                    parameters[field["key"]] = 0.0
                    continue
                try:
                    parameters[field["key"]] = float(raw.replace(",", "."))
                except ValueError as error:
                    raise InputError(english_field_label(field) + ": enter a number.") from error
        return resolve(parameters)["params"]

    def new_item(self):
        if self.store is None:
            return
        self.current_id = None
        self.item_id.set(self.store.next_id())
        self.from_ref.set("")
        self.to_ref.set("")
        family_id = "FRAME" if "FRAME" in FAMILIES else next(iter(FAMILIES))
        self.family.set(self.family_labels[family_id])
        self.family_changed(parameters=defaults(family_id))
        self.status.set("New component " + self.item_id.get())

    def save_current(self, silent=False):
        if self.store is None:
            return None
        try:
            entered_prefix = self.prefix.get().strip()
            if entered_prefix != self.store.prefix:
                text = ("Change the project prefix from " + self.store.prefix + " to " + entered_prefix + "?\n\n"
                    "All rows will be marked as changed. Existing STEP and JSON files remain available "
                    "until the new build results are accepted.")
                if not messagebox.askyesno("Change project prefix", text, parent=self.root):
                    self.prefix.set(self.store.prefix)
                    return None
                self.store.set_prefix(entered_prefix)
            item = self.store.save_item(
                self.item_id.get(),
                self.collect_parameters(),
            )
            self.current_id = item["id"]
            self.item_id.set(item["id"])
            self.refresh_register()
            self.select_item(item["id"], load=False)
            self.status.set(item["id"] + " saved; " + status_text(item["status"]))
            if not silent:
                messagebox.showinfo(APP_TITLE, item["id"] + " was saved in the project register.", parent=self.root)
            return item
        except Exception as error:
            if not silent:
                messagebox.showerror("Not saved", str(error), parent=self.root)
            else:
                self.status.set("Not saved: " + str(error))
            return None

    def refresh_register(self):
        selected = set(self.tree.selection())
        self.tree.delete(*self.tree.get_children())
        if self.store is None:
            return
        dirty_ids = {item["id"] for item in self.store.dirty_items()}
        for item in self.store.items:
            error = self.store.error_text(item["id"])
            tag = "error" if error else ("dirty" if item["id"] in dirty_ids else "built")
            self.tree.insert("", "end", iid=item["id"], values=(
                item["id"],
                size_text(item["parameters"]),
                item["parameters"]["family"],
                self.store.connection_summary(item["id"], "in"),
                self.store.connection_summary(item["id"], "out"),
                error,
                area_text(item),
                rate_text(item),
                total_price_text(item),
            ), tags=(tag,))
        for item_id in selected:
            if self.tree.exists(item_id):
                self.tree.selection_add(item_id)

    def select_item(self, item_id, load=True):
        if self.tree.exists(item_id):
            self.tree.selection_set(item_id)
            self.tree.focus(item_id)
            self.tree.see(item_id)
        if load:
            self.load_item(item_id)

    def selection_changed(self, event=None):
        selection = self.tree.selection()
        self.update_area_button()
        if len(selection) == 1:
            self.load_item(selection[0])

    def update_area_button(self):
        selection = self.tree.selection()
        editable_area = len(selection) == 1 and pricing_values(self.store.item(selection[0]))["rate_eur_per_m2"] is not None
        self.area_button.configure(state="normal" if editable_area and self.process is None else "disabled")

    def register_double_click(self, event):
        if self.tree.identify_region(event.x, event.y) != "cell":
            return
        if self.tree.identify_column(event.x) == "#7":
            self.edit_area()
        else:
            self.open_step()

    def edit_area(self):
        selection = self.tree.selection()
        if len(selection) != 1 or self.process is not None:
            return
        item = self.store.item(selection[0])
        pricing = pricing_values(item)
        if pricing["rate_eur_per_m2"] is None:
            messagebox.showinfo(APP_TITLE, "This component does not have area-based pricing.", parent=self.root)
            return
        current = item.get("area_override_m2", pricing["area_m2"])
        entered = simpledialog.askstring(
            "Change area",
            "Area in m². Leave blank to restore the measured area:",
            initialvalue="" if current is None else format_value(float(current)),
            parent=self.root,
        )
        if entered is None:
            return
        try:
            value = entered.strip()
            self.store.set_area_override(item["id"], None if not value else value.replace(",", "."))
            self.refresh_register()
            self.select_item(item["id"], load=False)
            self.status.set(item["id"] + (": measured area restored." if not value else ": manual area applied."))
        except Exception as error:
            messagebox.showerror("Area not changed", str(error), parent=self.root)

    def load_item(self, item_id):
        try:
            item = self.store.item(item_id)
            self.current_id = item["id"]
            self.item_id.set(item["id"])
            self.load_connection_summaries(item["id"])
            family_id = item["parameters"]["family"]
            self.family.set(self.family_labels[family_id])
            self.family_changed(parameters=item["parameters"])
            self.prefix.set(self.store.prefix)
            self.status.set(item["id"] + " loaded; " + status_text(item.get("status", "unknown")))
        except Exception as error:
            messagebox.showerror(APP_TITLE, str(error), parent=self.root)

    def load_connection_summaries(self, item_id):
        self.from_ref.set(self.store.connection_summary(item_id, "in"))
        self.to_ref.set(self.store.connection_summary(item_id, "out"))

    def open_connections(self):
        if self.process is not None:
            return
        item = self.save_current(silent=True)
        if item is not None:
            ConnectionDialog(self, item["id"])

    def build_selected(self):
        item = self.save_current(silent=True)
        if item is None:
            messagebox.showerror("Not built", "The component could not be saved. Correct the input and try again.", parent=self.root)
            return
        selection = list(self.tree.selection())
        if item["id"] not in selection:
            selection.append(item["id"])
        self.start_build(selection)

    def build_changed(self):
        if self.current_id:
            self.save_current(silent=True)
        item_ids = [item["id"] for item in self.store.dirty_items()]
        if not item_ids:
            messagebox.showinfo(APP_TITLE, "There are no changed components.", parent=self.root)
            return
        self.start_build(item_ids)

    def start_build(self, item_ids):
        if self.process is not None:
            return
        try:
            freecad_python = find_freecad_python()
            items = []
            for item_id in item_ids:
                item = self.store.item(item_id)
                resolve(item["parameters"])
                items.append({
                    "id": item["id"],
                    "parameters": item["parameters"],
                    "connections": self.store.connection_payload(item["id"]),
                    "connection_fingerprint": item.get("connection_fingerprint", ""),
                    "from": self.store.connection_summary(item["id"], "in"),
                    "to": self.store.connection_summary(item["id"], "out"),
                    "connection_errors": self.store.error_text(item["id"]),
                })
            job_directory = self.store.staging_dir / (datetime.now().strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:8])
            job_directory.mkdir(parents=True)
            job_path = job_directory / "job.json"
            job_path.write_text(json.dumps({"schema": "allshield-freecad-job-v1", "items": items}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            log_path = job_directory / "worker.log"
            self.worker_log = log_path.open("w", encoding="utf-8")
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            self.process = subprocess.Popen(
                [freecad_python, str(WORKER_PATH), str(job_path)],
                cwd=str(PACKAGE_DIR),
                stdout=self.worker_log,
                stderr=subprocess.STDOUT,
                creationflags=creation_flags,
            )
            self.pending_job = {"directory": job_directory, "ids": item_ids, "log": log_path}
            self.build_started = time.monotonic()
            self.cancel_reason = ""
            self.set_busy(True)
            self.status.set("FreeCAD is building " + str(len(item_ids)) + " component(s)...")
            self.root.after(200, self.poll_build)
        except Exception as error:
            if self.worker_log:
                self.worker_log.close()
            self.worker_log = None
            self.process = None
            self.pending_job = None
            self.set_busy(False)
            messagebox.showerror("FreeCAD not started", str(error), parent=self.root)

    def poll_build(self):
        if self.process is None:
            return
        if self.build_started is not None and time.monotonic() - self.build_started > 1800 and self.process.poll() is None:
            self.cancel_reason = "The FreeCAD build stopped after the maximum runtime of 30 minutes."
            self.process.kill()
        exit_code = self.process.poll()
        if exit_code is None:
            self.root.after(200, self.poll_build)
            return
        self.worker_log.close()
        self.worker_log = None
        job = self.pending_job
        self.process = None
        self.pending_job = None
        self.build_started = None
        self.set_busy(False)
        result_path = job["directory"] / "result.json"
        try:
            report = json.loads(result_path.read_text(encoding="utf-8"))
            successful = [row for row in report["items"] if row.get("passed")]
            failed = [row for row in report["items"] if not row.get("passed")]
            for row in failed:
                self.store.set_error(row["id"], row.get("error", "Unknown FreeCAD error"))
            if successful:
                old_files = self.store.old_artifacts([row["id"] for row in successful])
                text = str(len(successful)) + " STEP file(s) were built and validated."
                if old_files:
                    text += "\n\nAccepting the result replaces these registered files:\n" + "\n".join(path.name for path in old_files)
                text += "\n\nAccept the new results?"
                if messagebox.askyesno("Accept build result", text, parent=self.root):
                    for row in successful:
                        self.store.commit_build(row["id"], row["paths"]["step"], row["paths"]["parameters"])
                    self.status.set(str(len(successful)) + " build result(s) accepted.")
                else:
                    self.status.set("New build results rejected; existing files were retained.")
            if failed:
                messagebox.showerror("FreeCAD build partially failed", "\n".join(row["id"] + ": " + row.get("error", "error") for row in failed), parent=self.root)
            elif not successful:
                messagebox.showerror("FreeCAD build failed", "No valid result was received.", parent=self.root)
        except Exception as error:
            message = self.cancel_reason or ("The worker result could not be processed: " + str(error))
            for item_id in job["ids"]:
                self.store.set_error(item_id, message)
            self.status.set(message)
            messagebox.showerror("FreeCAD build stopped", message, parent=self.root)
        finally:
            self.cancel_reason = ""
            try:
                destination = self.store.log_dir / (job["directory"].name + ".log")
                shutil.copy2(job["log"], destination)
            except OSError:
                pass
            shutil.rmtree(job["directory"], ignore_errors=True)
            self.refresh_register()

    def set_busy(self, busy):
        state = "disabled" if busy else "normal"
        self.build_selected_button.configure(state=state)
        self.build_changed_button.configure(state=state)
        self.connections_button.configure(state=state)
        self.area_button.configure(state="disabled")
        if not busy:
            self.update_area_button()
        self.cancel_button.configure(state="normal" if busy else "disabled")
        if busy:
            self.progress.start(12)
        else:
            self.progress.stop()

    def cancel_build(self):
        if self.process is None:
            return
        if messagebox.askyesno("Stop build", "Stop the active FreeCAD process? Existing accepted files will be retained.", parent=self.root):
            self.cancel_reason = "The FreeCAD build was stopped by the user."
            self.process.kill()
            self.status.set("Stopping the FreeCAD build...")

    def delete_selected(self):
        selection = list(self.tree.selection())
        if not selection or self.process is not None:
            return
        text = "Remove the selected project rows and their registered JSON/STEP files?\n\n" + ", ".join(selection)
        if not messagebox.askyesno("Remove components", text, parent=self.root):
            return
        for item_id in selection:
            self.store.remove_item(item_id)
        self.refresh_register()
        self.new_item()

    def open_step(self):
        try:
            selection = self.tree.selection()
            if len(selection) != 1:
                messagebox.showinfo(APP_TITLE, "Select one built component.", parent=self.root)
                return
            item = self.store.item(selection[0])
            if not item.get("step_file"):
                messagebox.showinfo(APP_TITLE, "This component does not have an accepted STEP file yet.", parent=self.root)
                return
            path = (self.store.root / item["step_file"]).resolve()
            application = self.preferred_3d_app.get()
            if application == "FreeCAD":
                executable = Path(find_freecad_python()).with_name("FreeCAD.exe")
                if not executable.is_file():
                    raise FileNotFoundError("FreeCAD.exe was not found in the AAVDS installation.")
                subprocess.Popen([str(executable), str(path)])
            elif application == "Inventor":
                executable = self._application_executable(application)
                if executable:
                    subprocess.Popen([str(executable), str(path)])
            else:
                executable = self._application_executable(application)
                if not executable:
                    return
                self.root.clipboard_clear()
                self.root.clipboard_append(str(path))
                self.root.update()
                subprocess.Popen([str(executable)])
                messagebox.showinfo(
                    "Import STEP in Fusion 360",
                    "The STEP path has been copied to the clipboard:\n\n" + str(path)
                    + "\n\nIn Fusion 360:\n1. Select File > Open.\n2. Select Open from my computer."
                    + "\n3. Paste the copied path and open the STEP file.",
                    parent=self.root,
                )
        except Exception as error:
            messagebox.showerror("STEP not opened", str(error), parent=self.root)

    def sort_register(self, column):
        rows = [(self.tree.set(item_id, column), item_id) for item_id in self.tree.get_children("")]
        rows.sort(key=lambda pair: pair[0].casefold())
        for index, (_, item_id) in enumerate(rows):
            self.tree.move(item_id, "", index)

    def close(self):
        if self.process is not None:
            messagebox.showwarning(APP_TITLE, "Wait for FreeCAD to finish before closing the application.", parent=self.root)
            return
        self.root.destroy()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Open the standalone Allshield project builder.")
    parser.add_argument("--project", default=str(default_project_path()), help="Fixed project directory")
    parser.add_argument("--smoke-test", action="store_true", help=argparse.SUPPRESS)
    arguments = parser.parse_args(argv)
    settings_before = SETTINGS_PATH.read_bytes() if arguments.smoke_test and SETTINGS_PATH.is_file() else None
    root = tk.Tk()
    if arguments.smoke_test:
        root.withdraw()
    application = ProjectApplication(root, arguments.project, remember_project=not arguments.smoke_test)
    if arguments.smoke_test:
        root.update_idletasks()
        built_ids = []
        application.start_build = lambda item_ids: built_ids.extend(item_ids)
        application.build_selected()
        item = application.store.item(application.current_id)
        dialog = ConnectionDialog(application, item["id"])
        root.update_idletasks()
        tooltip_manager = application.tooltips
        tooltip_manager._enter(application.family_box)
        immediate_help = application.help_text.get() == "Select the component family. The input fields below adapt automatically."
        first_hover_scheduled = tooltip_manager.pending_job is not None
        tooltip_manager._leave(application.family_box)
        cooldown_applied = tooltip_manager.cooldown_until.get(application.family_box, 0.0) > time.monotonic()
        tooltip_manager._enter(application.family_box)
        repeated_hover_suppressed = tooltip_manager.pending_job is None
        tooltip_manager._leave(application.family_box)
        tooltip_manager._enter(application.help_label)
        tooltip_manager._cancel_pending()
        tooltip_manager._show(application.help_label)
        root.update_idletasks()
        popup_created = tooltip_manager.popup is not None and tooltip_manager.popup.winfo_exists()
        popup_has_timed_hide = tooltip_manager.hide_job is not None
        tooltip_manager._hide_popup()
        popup_closed = tooltip_manager.popup is None and tooltip_manager.hide_job is None
        tooltip_manager._leave(application.help_label)

        def help_targets(parent):
            result = []
            target_types = (ttk.Label, ttk.Button, ttk.Entry, ttk.Combobox, ttk.Radiobutton, ttk.Treeview, ttk.Scrollbar, ttk.Progressbar, tk.Canvas)
            for child in parent.winfo_children():
                if isinstance(child, target_types):
                    result.append(child)
                result.extend(help_targets(child))
            return result

        all_field_keys = {field["key"] for family in FAMILIES.values() for field in family["fields"]}
        checks = {
            "window": root.winfo_exists() == 1,
            "aavds_title": root.title() == APP_TITLE == "AAVDS-duct-builder",
            "build_selection_saves_new_item": built_ids == [item["id"]] and len(application.store.items) == 1,
            "standard_piece_price_visible": bool(rate_text(item)) and application.tree.set(item["id"], "Rate") == rate_text(item),
            "columns": application.tree["columns"] == ("ID", "Size", "Type", "From", "To", "Error", "Area", "Rate", "Total"),
            "three_d_app_choices": [radio["text"] for radio in application.app_radios] == ["Inventor", "Fusion 360", "FreeCAD"],
            "three_d_app_default_valid": application.preferred_3d_app.get() in ("Inventor", "Fusion 360", "FreeCAD"),
            "open_pdf_available": application.open_pdf_button.instate(("!disabled",)),
            "type_preview_visible": application.preview_canvas.winfo_ismapped() and application.preview_canvas.winfo_height() >= 150,
            "release_comparison": is_newer_release("AAVDS-2026-V02") and not is_newer_release(APP_VERSION),
            "project_loaded": application.store is not None,
            "worker_exists": WORKER_PATH.is_file(),
            "connection_columns": dialog.tree["columns"] == ("Local", "Direction", "Peer", "PeerPort", "Fit"),
            "connection_ports": set(dialog.local_box["values"]) == {"JO_IN", "JO_DUCT_ENTRY"},
            "light_theme": ttk.Style(root).lookup("TFrame", "background") == "#f7f9fa",
            "ok_visible": dialog.ok_button["text"] == "OK" and 0 <= dialog.ok_button.winfo_rooty() - dialog.window.winfo_rooty() and dialog.ok_button.winfo_rooty() + dialog.ok_button.winfo_height() <= dialog.window.winfo_rooty() + dialog.window.winfo_height(),
            "smoke_preserves_project_setting": (SETTINGS_PATH.read_bytes() if SETTINGS_PATH.is_file() else None) == settings_before,
            "tooltip_timing": TOOLTIP_DELAY_MS == 400 and TOOLTIP_DISPLAY_MS == 2000 and TOOLTIP_COOLDOWN_SECONDS == 5.0,
            "tooltip_immediate_help_line": immediate_help,
            "tooltip_first_hover_scheduled": first_hover_scheduled,
            "tooltip_cooldown_applied": cooldown_applied,
            "tooltip_repeated_hover_suppressed": repeated_hover_suppressed,
            "tooltip_popup_created": popup_created,
            "tooltip_popup_has_timed_hide": popup_has_timed_hide,
            "tooltip_popup_closed": popup_closed,
            "tooltip_all_field_keys_documented": all_field_keys == set(FIELD_HELP),
            "tooltip_all_visible_controls_registered": all(tooltip_manager.has_help(widget) for widget in help_targets(root)),
            "tooltip_connection_controls_registered": all(tooltip_manager.has_help(widget) for widget in help_targets(dialog.window)),
            "tooltip_help_line_visible": application.help_label.winfo_ismapped(),
        }
        dialog.close()
        family_options = list(application.family_box["values"])
        checks["family_alphabetical"] = family_options == sorted(family_options, key=str.casefold)
        checks["family_editable"] = application.family_box.instate(("!readonly", "!disabled"))
        application.family.set("b")
        application.family_typed()
        checks["family_prefix_filter"] = list(application.family_box["values"]) == [
            application.family_labels[family_id]
            for family_id in ("BEND_RECT", "BEND_ROUND", "BU", "BUY")
        ]
        application.family.set("fire-resistant")
        application.family_typed()
        checks["family_type_filter"] = list(application.family_box["values"]) == [application.family_labels["GRILLE_FIRE"]]
        application.show_all_types()
        root.update_idletasks()
        browser = application.type_browser
        checks["all_types_browser_complete"] = len(application.type_browser_tree.get_children("")) == len(FAMILIES)
        application.type_browser_tree.selection_set("BEND_RECT")
        application.accept_type_browser()
        checks["all_types_double_click_selection"] = (
            application.family.get() == application.family_labels["BEND_RECT"]
            and application.type_browser is None
            and not browser.winfo_exists()
        )
        checks["bend_preview_loaded"] = application.preview_photo is not None
        application.family.set(application.family_labels["BU"])
        application.family_changed(parameters=dict(defaults("BU"), t_mm=1.5))
        root.update_idletasks()
        checks["tooltip_dynamic_fields_registered"] = all(
            tooltip_manager.has_help(application.field_labels[key])
            and tooltip_manager.has_help(application.field_widgets[key])
            for key in application.field_widgets
        )
        checks["plain_language_thickness_mode"] = list(application.field_widgets["thickness_mode"]["values"]) == [
            "Choose manually",
            "Automatically from duct dimensions",
        ]
        checks["expert_fields_hidden_by_default"] = (
            application.field_widgets["t_mm"].winfo_ismapped()
            and not application.field_widgets["airkan_a_mm"].winfo_ismapped()
            and not application.field_widgets["insertion_mm"].winfo_ismapped()
        )
        application.field_variables["thickness_mode"].set("Automatically from duct dimensions")
        application.refresh_field_visibility()
        root.update_idletasks()
        checks["automatic_mode_needs_no_extra_size"] = (
            not application.field_widgets["t_mm"].winfo_ismapped()
            and not application.field_widgets["airkan_a_mm"].winfo_ismapped()
            and application.collect_parameters()["thickness_mode"] == "AIRKAN_BC"
            and application.collect_parameters()["airkan_a_mm"] == 0
        )
        application.field_variables["thickness_mode"].set("Choose manually")
        application.refresh_field_visibility()
        checks["rectangular_thickness_dropdown"] = (
            isinstance(application.field_widgets["t_mm"], ttk.Combobox)
            and application.field_widgets["t_mm"].instate(("readonly",))
            and list(application.field_widgets["t_mm"]["values"]) == ["0.75", "0.95", "1.2", "1.5"]
        )
        application.field_variables["material"].set("INOX316")
        application.refresh_thickness_choices()
        checks["thickness_dropdown_follows_material_prices"] = (
            list(application.field_widgets["t_mm"]["values"]) == ["0.75", "0.95"]
            and application.field_variables["t_mm"].get() == ""
        )
        application.family.set("CM")
        application.family_typed_commit()
        checks["family_type_commit"] = application.family.get() == application.family_labels["CM"] and "source_step" in application.field_variables
        cm_parameters = dict(defaults("CM"), source_step=str(Path(arguments.project) / "eigen_plenum.step"), description="Eigen plenum")
        application.family.set(application.family_labels["CM"])
        application.family_changed(parameters=cm_parameters)
        collected_cm = application.collect_parameters()
        checks.update({
            "cm_file_picker": isinstance(application.field_widgets["source_step"], ttk.Frame),
            "cm_text_value": collected_cm["description"] == "Eigen plenum",
            "cm_step_value": collected_cm["source_step"] == cm_parameters["source_step"],
            "cm_rate_value": collected_cm["area_rate_eur_per_m2"] == 33.8,
            "tooltip_composite_file_control_registered": all(
                tooltip_manager.has_help(widget)
                for widget in [application.field_widgets["source_step"], *application.field_widgets["source_step"].winfo_children()]
            ),
        })
        application.family.set(application.family_labels["BUY"])
        application.family_changed(parameters=defaults("BUY"))
        checks["buy_fields_start_unfilled"] = (
            all(not application.field_variables[key].get() for key in ("supplier", "article_code", "description", "source_step", "price_source"))
            and application.field_variables["a_mm"].get() == "0"
            and application.field_variables["b_mm"].get() == "0"
            and application.field_variables["airflow_role"].get() == "Select..."
            and application.field_variables["price_status"].get() == "Select..."
            and application.field_variables["unit_price_eur"].get() == "0"
        )
        buy_parameters = dict(defaults("BUY"), supplier="Renson", article_code="411/900", description="Buitenrooster",
                              source_step=str(Path(arguments.project) / "buitenrooster.step"), a_mm=900, b_mm=700,
                              airflow_role="AANZUIG", price_status="ON_REQUEST", unit_price_eur=0,
                              price_source="Leverancierspagina")
        application.family_changed(parameters=buy_parameters)
        collected_buy = application.collect_parameters()
        checks.update({
            "buy_file_picker": isinstance(application.field_widgets["source_step"], ttk.Frame),
            "buy_supplier_value": collected_buy["supplier"] == "Renson",
            "buy_article_value": collected_buy["article_code"] == "411/900",
            "buy_price_status": collected_buy["price_status"] == "ON_REQUEST",
        })
        application.store.save_item("A-10", defaults("GRILLE_FIRE"))
        application.store.save_item("A-20", dict(defaults("BU"), t_mm=0.95))
        restricted_dialog = ConnectionDialog(application, "A-20")
        restricted_dialog.peer_item.set("A-10")
        restricted_dialog._refresh_peer_ports()
        checks.update({
            "passive_grille_has_no_mechanical_peer_port": not restricted_dialog.peer_port.get(),
            "passive_grille_disables_connect": restricted_dialog.connect_button.instate(("disabled",)),
            "passive_grille_explains_restriction": "passive" in restricted_dialog.connection_hint.get() and "mechanical ventilation" in restricted_dialog.connection_hint.get(),
        })
        restricted_dialog.close()
        grille_dialog = ConnectionDialog(application, "A-10")
        checks.update({
            "passive_grille_forces_external": grille_dialog.endpoint_kind.get() == "External" and grille_dialog.kind_box.instate(("disabled",)),
            "external_name_initially_disables_connect": grille_dialog.connect_button.instate(("disabled",)),
        })
        grille_dialog.external_name.set("Room")
        grille_dialog._update_connect_state()
        checks["external_name_enables_connect"] = grille_dialog.connect_button.instate(("!disabled",))
        grille_dialog.close()
        root.destroy()
        print(json.dumps(checks, sort_keys=True))
        return 0 if all(checks.values()) else 1
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())