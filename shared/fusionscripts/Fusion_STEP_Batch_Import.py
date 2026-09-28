# -*- coding: utf-8 -*-
"""Import local STEP files as separate native Fusion designs in a project root.

Run this file INSIDE Autodesk Fusion using Scripts and Add-Ins, not with
Windows Python or FreeCAD. No third-party Python packages are required.

The source STEP files are never modified. Existing cloud designs are never
updated or overwritten. The target is frozen at startup: the root folder of
the project then displayed in the Fusion Data Panel, NOT the active document's
folder. Each save must complete before the script closes its own document.

API references (checked 2026-09-22):
https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/ImportManager_importToNewDocument.htm
https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/Document_saveAs.htm
https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/DataFile_isComplete.htm
https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/DataProject_rootFolder.htm
"""

from pathlib import Path
import time
import traceback
import uuid
from datetime import datetime

import adsk.core
import adsk.fusion

# --------------------------- USER SETTINGS ---------------------------
SOURCE_DIR = r"D:\steps"
INCLUDE_SUBFOLDERS = False
CLOSE_AFTER_SAVE = True
SAVE_TIMEOUT_SECONDS = 300.0
POLL_INTERVAL_SECONDS = 0.15
# Same-name files are deliberately skipped, never overwritten or versioned.
# Extensions .step/.stp are removed; the rest of each filename is unchanged.
# ---------------------------------------------------------------------

TITLE = "STEP batch -> Fusion project-root"
_running = False
_stop_requested = False
_handlers = []


class SaveNotConfirmed(RuntimeError):
    """The save started, but completion could not be confirmed safely."""


class StopRequested(RuntimeError):
    """User requested a stop before the next cloud write."""


class RunLog:
    """Append-only, flushed text log. No model bytes are written here."""

    def __init__(self, source, project, target):
        logdir = source / "_fusion_import_logs"
        logdir.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.path = logdir / ("import_" + stamp + "_" + uuid.uuid4().hex[:6] + ".log")
        self.stream = self.path.open("x", encoding="utf-8")
        self.write("START", "", "Project: " + project.name)
        self.write("TARGET", "", "Root folder ID: " + target.id)
        self.write("SOURCE", "", str(source))

    def write(self, status, filename, detail=""):
        line = "{} | {} | {} | {}\n".format(
            datetime.now().isoformat(timespec="seconds"), status, filename, detail
        )
        self.stream.write(line)
        self.stream.flush()

    def close(self):
        self.stream.close()


def discover_steps(source, recursive=False):
    """Return deterministic case-insensitive .step/.stp matches."""
    source = Path(source)
    if not source.is_dir():
        raise ValueError("De invoermap bestaat niet: " + str(source))
    candidates = source.rglob("*") if recursive else source.iterdir()
    return sorted(
        (p for p in candidates if p.is_file() and p.suffix.lower() in {".step", ".stp"}),
        key=lambda p: (str(p.relative_to(source)).casefold(), str(p)),
    )


def root_file_names(folder):
    """Fail rather than silently bypassing a failed duplicate check."""
    result = {}
    collection = folder.dataFiles
    for index in range(collection.count):
        item = collection.item(index)
        if item is None:
            raise RuntimeError("Fusion kon de bestaande bestanden niet volledig lezen.")
        result.setdefault(item.name.casefold(), item.name)
    return result


def plan_import(paths, existing):
    """Keep only the first local file for each case-insensitive target name."""
    seen = set(existing)
    plan = []
    for path in paths:
        name = path.stem
        if not name.strip():
            raise ValueError("Ongeldige lege ontwerpnaam: " + path.name)
        key = name.casefold()
        if key in seen:
            reason = (
                "Naam bestaat al in de project-root; inhoud wordt niet vergeleken."
                if key in existing else
                "Een ander lokaal STEP-bestand heeft dezelfde ontwerpnaam."
            )
            plan.append((path, name, reason))
        else:
            plan.append((path, name, ""))
            seen.add(key)
    return plan


def _cancelled(progress):
    return _stop_requested or bool(progress.wasCancelled)


def _status(progress, message):
    progress.message = message
    adsk.doEvents()


class SaveCompletedHandler(adsk.core.DataEventHandler):
    """Only records cloud completion; never imports/saves inside the event."""

    def __init__(self):
        super().__init__()
        self.completed_ids = set()

    def notify(self, args):
        try:
            data_file = args.file
            if data_file:
                self.completed_ids.add(data_file.id)
        except Exception:
            # Polling isComplete remains the fallback if an event is unusable.
            pass


def wait_for_save(app, document, target, handler, progress, name, log):
    """Bounded wait. A stop request lets the current save finish first.

    A timeout does NOT close the design: the upload may still be in progress.
    Native STEP translation itself is a blocking Autodesk API call and cannot
    be interrupted by this polling timeout.
    """
    start = time.monotonic()
    next_progress = 0.0
    next_refresh = 12.0
    last_poll_error = ""
    while True:
        adsk.doEvents()
        elapsed = time.monotonic() - start
        if not document.isValid:
            raise SaveNotConfirmed("Het importdocument werd gesloten tijdens het opslaan.")
        if app.isOffLine:
            raise SaveNotConfirmed("Fusion ging offline. Het document blijft open.")

        try:
            data_file = document.dataFile
            if data_file and (
                data_file.id in handler.completed_ids or data_file.isComplete
            ):
                if data_file.parentFolder.id != target.id:
                    raise SaveNotConfirmed("Opgeslagen map wijkt af van de bevestigde project-root.")
                if data_file.name != name:
                    raise SaveNotConfirmed(
                        "Fusion wijzigde de naam naar {!r}; controleer het open document."
                        .format(data_file.name)
                    )
                return data_file
        except SaveNotConfirmed:
            raise
        except Exception as exc:
            last_poll_error = str(exc)

        if elapsed >= SAVE_TIMEOUT_SECONDS:
            raise SaveNotConfirmed(
                "Cloudopslag niet bevestigd na {:.0f} s. Het document blijft open. "
                "Controleer de uploadstatus voordat je opnieuw start. {}"
                .format(SAVE_TIMEOUT_SECONDS, last_poll_error)
            )
        if elapsed >= next_progress:
            state = "Stop gevraagd; huidige opslag afronden" if _cancelled(progress) else "Cloudopslag"
            _status(progress, "{}: {}\nWachten: {:.0f} s / {:.0f} s".format(
                state, name, elapsed, SAVE_TIMEOUT_SECONDS
            ))
            next_progress = elapsed + 1.0
        if elapsed >= next_refresh:
            # Folder enumeration refreshes the local DataFile cache. Do not
            # refresh on every polling tick or hold up the Fusion UI needlessly.
            try:
                _ = target.dataFiles.count
            except Exception as exc:
                log.write("REFRESH_WARNING", name, str(exc))
            next_refresh = elapsed + 12.0
        time.sleep(POLL_INTERVAL_SECONDS)


def _restore_document(document):
    try:
        if document and document.isValid:
            document.activate()
    except Exception:
        pass


def run(context):
    """Fusion script entry point; one import/new design per source file."""
    global _running, _stop_requested
    app = adsk.core.Application.get()
    ui = app.userInterface
    if _running:
        ui.messageBox("Deze batch is al bezig.", TITLE)
        return

    _running = True
    _stop_requested = False
    original_document = app.activeDocument
    current_document = None
    progress = None
    handler = None
    event_registered = False
    log = None
    saved = skipped = errors = processed = 0
    stopped = False
    problem = ""
    paths = []
    started = False
    keep_current_open = False

    try:
        if app.isOffLine:
            raise ValueError("Fusion staat offline. Ga online en start opnieuw.")
        if SAVE_TIMEOUT_SECONDS <= 0 or POLL_INTERVAL_SECONDS <= 0:
            raise ValueError("De wachttijden moeten groter zijn dan nul.")
        source = Path(SOURCE_DIR)
        paths = discover_steps(source, INCLUDE_SUBFOLDERS)
        if not paths:
            ui.messageBox("Geen .step- of .stp-bestanden in:\n" + str(source), TITLE)
            return

        project = app.data.activeProject
        if not project:
            raise ValueError(
                "Open eerst het gewenste project in het Fusion Data Panel. "
                "De bestanden worden in de root van dat project opgeslagen."
            )
        target = project.rootFolder
        if not target or not target.isRoot:
            raise ValueError("De hoofdmap van het actieve project kon niet worden bepaald.")
        existing = root_file_names(target)
        plan = plan_import(paths, existing)
        eligible = sum(not reason for _, _, reason in plan)
        try:
            project_label = project.parentHub.name + " / " + project.name
        except Exception:
            project_label = project.name

        answer = ui.messageBox(
            "Bron: {}\n\nDoel: {}\nMap: ROOT (geen submap)\n\n"
            "STEP-bestanden gevonden: {}\nNieuw te importeren: {}\n"
            "Over te slaan wegens naamconflict: {}\n\n"
            "Elk bestand wordt een afzonderlijk Fusion-ontwerp, met dezelfde "
            "naam zonder .step/.stp. Bestaande ontwerpen blijven ongemoeid.\n\n"
            "Starten?".format(source, project_label, len(paths), eligible, len(paths)-eligible),
            TITLE,
            adsk.core.MessageBoxButtonTypes.YesNoButtonType,
            adsk.core.MessageBoxIconTypes.QuestionIconType,
        )
        if answer != adsk.core.DialogResults.DialogYes:
            return

        # Create the log before any cloud writes. If this fails, stop safely.
        log = RunLog(source, project, target)
        started = True
        progress = ui.createProgressDialog()
        progress.isCancelButtonShown = True
        progress.cancelButtonText = "Stop na huidig bestand"
        progress.isBackgroundTranslucent = False
        progress.show(TITLE, "Voorbereiden...", 0, len(plan), 0)
        handler = SaveCompletedHandler()
        event_registered = bool(app.dataFileComplete.add(handler))
        if event_registered:
            _handlers.append(handler)
        else:
            log.write("WARNING", "", "Geen completion-event; polling isComplete wordt gebruikt.")

        for index, (path, name, reason) in enumerate(plan, 1):
            progress.progressValue = index - 1
            _status(progress, "Bestand {} / {}\n{}".format(index, len(plan), path.name))
            if _cancelled(progress):
                stopped = True
                break
            if reason:
                log.write("SKIPPED", path.name, reason)
                skipped += 1
                processed += 1
                progress.progressValue = index
                continue

            current_document = None
            try:
                if app.isOffLine:
                    raise RuntimeError("Fusion staat offline; de batch wordt gestopt.")
                if path.stat().st_size == 0:
                    raise ValueError("STEP-bestand is leeg.")
                log.write("IMPORT_START", path.name, "Fusion name: " + name)
                options = app.importManager.createSTEPImportOptions(str(path))
                if not options:
                    raise RuntimeError("Fusion kon geen STEP-importopties maken.")
                options.isViewFit = True
                current_document = app.importManager.importToNewDocument(options)
                if not current_document:
                    raise RuntimeError("STEP-import leverde geen document op.")
                keep_current_open = True
                log.write("IMPORT_OK", path.name)
                _status(progress, "Opslaan in project-root:\n" + name)
                if _cancelled(progress):
                    raise StopRequested("Gestopt voor opslag; geimporteerd document blijft open.")
                description = "Imported from STEP: " + path.name
                log.write("SAVE_START", path.name, "Target root: " + target.id)
                if not current_document.saveAs(name, target, description, ""):
                    raise SaveNotConfirmed("Fusion saveAs gaf False terug; controleer het open document.")
                data_file = wait_for_save(app, current_document, target, handler, progress, name, log)
                log.write("SAVED", path.name, "Cloud ID: " + data_file.id)
                saved += 1
                processed += 1
                if CLOSE_AFTER_SAVE:
                    if current_document.isModified:
                        raise RuntimeError(
                            "Het document werd na saveAs opnieuw gewijzigd. "
                            "Het blijft open; wijzigingen worden niet weggegooid."
                        )
                    if not current_document.close(False):
                        raise RuntimeError("Het opgeslagen document kon niet worden gesloten.")
                keep_current_open = False
                current_document = None
                progress.progressValue = index
                adsk.doEvents()
                if _cancelled(progress):
                    stopped = True
                    break
            except StopRequested as exc:
                stopped = True
                problem = str(exc)
                log.write("STOPPED_UNSAVED", path.name, problem)
                break
            except Exception as exc:
                errors += 1
                problem = "{}: {}".format(path.name, exc)
                log.write("ERROR", path.name, traceback.format_exc())
                # Never discard a document with uncertain save state. Stop on
                # the first error; already confirmed saves remain available.
                break

        log.write("SUMMARY", "", "Saved={}; skipped={}; errors={}; processed={}/{}; stopped={}".format(
            saved, skipped, errors, processed, len(paths), stopped
        ))
    except Exception as exc:
        problem = str(exc)
        errors += 1
        if log:
            log.write("FATAL", "", traceback.format_exc())
        else:
            ui.messageBox("Niet gestart:\n" + problem, TITLE)
    finally:
        if event_registered:
            try:
                app.dataFileComplete.remove(handler)
            except Exception:
                pass
        _handlers.clear()
        if progress:
            try:
                progress.hide()
            except Exception:
                pass
        if log:
            log.close()
        # Show an uncertain import rather than hiding it behind the old tab.
        if not keep_current_open:
            _restore_document(original_document)
        _running = False
        if started:
            heading = "Batch onderbroken" if (stopped or errors) else "Batch afgerond"
            summary = (
                "{}\n\nOpgeslagen: {}\nOvergeslagen: {}\nFouten: {}\n"
                "Niet afgehandeld: {}\n\nLogbestand:\n{}"
            ).format(heading, saved, skipped, errors, max(0, len(paths)-processed), log.path)
            if problem:
                summary += "\n\n" + problem
            if keep_current_open:
                summary += "\n\nControleer het open document en de uploadstatus voor een herstart."
            ui.messageBox(summary, TITLE)


def stop(context):
    """Best-effort request; prefer the progress dialog's Stop button."""
    global _stop_requested
    _stop_requested = True
