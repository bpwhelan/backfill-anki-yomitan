import base64
import json
import logging
import urllib
import os
from anki.collection import Collection
from aqt import mw
from aqt.operations import CollectionOp, OpChangesWithCount
from aqt.utils import showInfo, showWarning
from aqt.qt import *
from urllib.error import HTTPError, URLError


logger = logging.getLogger(__name__)

addon_folder = os.path.join(mw.pm.addonFolder(), "pre_backfill")

file_handler = logging.FileHandler(os.path.join(addon_folder, "addon.log"))
file_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)

logger.addHandler(file_handler)

# --- Constants and API Communication ---

request_url = "http://127.0.0.1:8766"
request_timeout = 10
ping_timeout = 5


def ping_yomitan():
    """Pings the Yomitan server to check if it's running."""
    req = urllib.request.Request(request_url + "/yomitanVersion", method="POST")
    try:
        urllib.request.urlopen(req, timeout=ping_timeout)
        return True
    except Exception:
        return False

def request_yomitan_data(expression, reading, handlebar):
    """Requests data for a single term and handlebar from Yomitan."""
    body = {
        "text": expression,
        "type": "term",
        "markers": [handlebar, "reading"],
        "maxEntries": 4 if reading else 1,
        "includeMedia": True
    }

    req = urllib.request.Request(
        request_url + "/ankiFields",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        response = urllib.request.urlopen(req, timeout=request_timeout)
        return json.loads(response.read())
    except HTTPError as e:
        if e.code == 500: # Thrown if handlebar does not exist for the term
            return None
        else:
            showWarning(f"Yomitan API returned an error: {e}")
            return None
    except URLError as e:
        raise ConnectionRefusedError(f"Request to Yomitan API failed: {e.reason}")

# --- Core Backfill Logic (Refactored) ---

def run_backfill_operation(parent, deck_id, expression_field, reading_field, targets, should_replace):
    """
    The core operation to backfill notes. Can be called by manual or preset mode.
    - parent: The parent window for the CollectionOp (usually mw or a dialog).
    - deck_id: The ID of the deck to process.
    - expression_field: The note field with the term.
    - reading_field: The note field with the reading (can be None).
    - targets: A list of dicts, e.g., [{"fieldToFill": "Field1", "handlebar": "{hb1}"}, ...].
    - should_replace: Boolean flag to overwrite existing content.
    """
    note_ids = mw.col.db.list("SELECT DISTINCT nid FROM cards WHERE did = ?", deck_id)
    
    logger.info(f"Running backfill operation for deck ID {deck_id} with {len(note_ids)} notes.")

    def on_success(result):
        if result.count > 0:
            showInfo(f"Successfully updated {result.count} notes.")
        else:
            showInfo("No notes were updated.")
        mw.col.reset()

    op = CollectionOp(
        parent=parent,
        op=lambda col: _backfill_op(col, note_ids, expression_field, reading_field, targets, should_replace)
    )
    op.success(on_success).run_in_background()

def _backfill_op(col: Collection, note_ids, expression_field, reading_field, targets, should_replace):
    """The actual operation run by CollectionOp."""
    notes_to_update = []
    anki_media_dir = col.media.dir()

    logger.info(f"Starting backfill operation with parameters: {locals()}")

    def write_media_file(file_info):
        try:
            filename = file_info.get("ankiFilename")
            target_path = os.path.join(anki_media_dir, filename)
            # Avoid re-writing existing files
            if os.path.exists(target_path):
                return True
            
            content = file_info.get("content")
            decoded = base64.b64decode(content)

            with open(target_path, "wb") as f:
                f.write(decoded)
            return True
        except Exception as e:
            print(f"Failed to write media file {filename}: {e}")
            return False

    def get_field_from_response(fields, reading, handlebar):
        if reading:
            for entry in fields:
                if entry.get("reading") == reading:
                    return entry.get(handlebar)
            return None
        else:
            return fields[0].get(handlebar)

    for nid in note_ids:
        logger.info(f"Processing note ID: {nid}")
        note = col.get_note(nid)
        note_was_modified = False

        if expression_field not in note:
            continue
        
        expression = note[expression_field].strip()
        if not expression:
            continue


        for key, value in note.items():
            logger.info(f"Note field '{key}': {value}")

        logger.info(reading_field)
        logger.info(note[expression_field])
        logger.info(note[reading_field])

        reading = note[reading_field] if reading_field and reading_field in note else None

        for target in targets:
            field_to_fill = target["fieldToFill"]
            handlebar = target["handlebar"]
            should_replace_target = target.get("replaceExisting", should_replace)
            
            logger.info(f"Processing target: {field_to_fill} with handlebar: {handlebar}")

            if field_to_fill not in note:
                continue
            
            if not field_to_fill or not handlebar:
                # Just Empty fields, skip this target
                continue
            
            # Skip if field is already filled and we shouldn't replace
            if not should_replace_target and note[field_to_fill].strip():
                continue

            # --- API Request and Processing ---
            api_response = request_yomitan_data(expression, reading, handlebar.replace("{", "").replace("}", ""))
            
            logger.info(f"Requesting Yomitan data for: {expression} (Reading: {reading}, Handlebar: {handlebar})")
            logger.info(f"API Response: {api_response}")
            
            # showInfo(f"Requesting Yomitan data for: {expression} (Reading: {reading}, Handlebar: {handlebar})")
            # showInfo(f"API Response: {api_response}")
            if not api_response:
                continue

            fields_data = api_response.get("fields")
            if not fields_data:
                continue

            new_value = get_field_from_response(fields_data, reading, handlebar.replace("{", "").replace("}", ""))
            if new_value is None: # Use None check to allow empty string values
                continue
            
            # --- Media Handling ---
            all_media = api_response.get("dictionaryMedia", []) + api_response.get("audioMedia", [])
            for file_info in all_media:
                filename = file_info.get("ankiFilename")
                # Write file only if its name appears in the new field value
                if filename and filename in new_value:
                    write_media_file(file_info)

            # --- Update Note ---
            if note[field_to_fill] != new_value:
                note[field_to_fill] = new_value
                note_was_modified = True

        if note_was_modified:
            notes_to_update.append(note)

    return OpChangesWithCount(changes=col.update_notes(notes_to_update), count=len(notes_to_update))


# --- Manual Backfill Dialog ---

class BackfillDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Yomitan Backfill (Manual)")
        self.setWindowModality(Qt.WindowModality.WindowModal)

        self.decks = QComboBox()
        self.fields = QComboBox()
        self.expression_field = QComboBox()
        self.reading_field = QComboBox()
        self.yomitan_handlebar = QLineEdit()
        self.apply = QPushButton("Run")
        self.cancel = QPushButton("Cancel")
        self.replace = QCheckBox("Replace existing content")

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.addRow(QLabel("Deck:"), self.decks)
        form.addRow(QLabel("Expression Field:"), self.expression_field)
        form.addRow(QLabel("Reading Field:"), self.reading_field)
        form.addRow(QLabel("Field to Fill:"), self.fields)
        form.addRow(QLabel("Yomitan Handlebar:"), self.yomitan_handlebar)
        
        self.yomitan_handlebar.setPlaceholderText("e.g., {glossary-brief}")

        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(self.apply)
        buttons.addWidget(self.cancel)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(self.replace)
        layout.addLayout(buttons)
        self.setLayout(layout)

        self._load_decks()
        self._update_fields()

        self.decks.currentIndexChanged.connect(self._update_fields)
        self.apply.clicked.connect(self._on_run)
        self.cancel.clicked.connect(self.reject)
        
        self.resize(450, self.height())

    def _load_decks(self):
        self.decks.clear()
        decks = mw.col.decks.all()
        for deck in decks:
            name = deck.get("name")
            deck_id = deck.get("id")
            self.decks.addItem(name, deck_id)

    def _update_fields(self):
        self.fields.clear()
        self.expression_field.clear()
        self.reading_field.clear()

        deck_id = self.decks.currentData()
        if deck_id is None:
            return

        model_ids = mw.col.db.list("SELECT DISTINCT n.mid FROM notes n JOIN cards c ON n.id = c.nid WHERE c.did = ?", deck_id)

        field_names = set()
        for mid in model_ids:
            model = mw.col.models.get(mid)
            for fld in model.get('flds', []):
                field_names.add(fld.get('name'))

        for name in sorted(field_names):
            self.fields.addItem(name)
            self.expression_field.addItem(name)
            self.reading_field.addItem(name)

        self.reading_field.setCurrentIndex(-1)

    def _on_run(self):
        deck_id = self.decks.currentData()
        expression_field = self.expression_field.currentText()
        reading_field = self.reading_field.currentText()
        field_to_fill = self.fields.currentText()
        handlebar = self.yomitan_handlebar.text()
        should_replace = self.replace.isChecked()

        if not all([deck_id, expression_field, field_to_fill, handlebar]):
            showWarning("Please fill out all required fields.")
            return

        targets = [{"fieldToFill": field_to_fill, "handlebar": handlebar}]
        
        # We accept the dialog to close it before the operation starts
        self.accept()
        
        run_backfill_operation(mw, deck_id, expression_field, reading_field, targets, should_replace)

def open_manual_dialog():
    if not ping_yomitan():
        showWarning("Could not connect to the Yomitan server. Please ensure it's running.")
        return
    
    dlg = BackfillDialog(mw)
    dlg.exec()

# --- Preset Backfill Dialog ---

class PresetDialog(QDialog):
    def __init__(self, parent, presets):
        super().__init__(parent)
        self.presets = presets
        self.setWindowTitle("Yomitan Backfill (Preset)")
        self.setWindowModality(Qt.WindowModality.WindowModal)

        self.preset_selector = QComboBox()
        for preset in self.presets:
            self.preset_selector.addItem(preset.get("name", "Unnamed Preset"), preset)

        self.run_button = QPushButton("Run Preset")
        self.cancel_button = QPushButton("Cancel")
        
        form = QFormLayout()
        form.addRow("Select Preset:", self.preset_selector)

        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(self.run_button)
        buttons.addWidget(self.cancel_button)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addLayout(buttons)
        self.setLayout(layout)
        
        self.run_button.clicked.connect(self._on_run)
        self.cancel_button.clicked.connect(self.reject)
        
        self.resize(400, self.height())
        
    def _on_run(self):
        preset = self.preset_selector.currentData()
        if not preset:
            return

        deck_name = preset.get("deckName")
        deck_id = mw.col.decks.id_for_name(deck_name)
        if not deck_id:
            showWarning(f"Deck '{deck_name}' from the preset could not be found.")
            return

        expression_field = preset.get("expressionField")
        reading_field = preset.get("readingField") # Can be None/empty
        targets = preset.get("targets", [])
        should_replace = preset.get("replaceExisting", False)

        if not all([expression_field, targets]):
            showWarning("The selected preset is misconfigured. It's missing 'expressionField' or 'targets'.")
            return
        
        self.accept() # Close dialog before starting the long operation
        
        run_backfill_operation(mw, deck_id, expression_field, reading_field, targets, should_replace)

def open_preset_dialog():
    if not ping_yomitan():
        showWarning("Could not connect to the Yomitan server. Please ensure it's running.")
        return
    
    config = mw.addonManager.getConfig(__name__)
    presets = config.get("presets")
    
    if not presets:
        showInfo("No presets found in the add-on's config.json file.")
        return
        
    dlg = PresetDialog(mw, presets)
    dlg.exec()

# --- Anki Menu Setup ---

logger.info("Setting up Anki menu actions for Yomitan Backfill")

mw.addonManager.setWebExports(__name__, r"web/.*")

manual_action = QAction("Yomitan Backfill (Manual)...", mw)
manual_action.triggered.connect(open_manual_dialog)

preset_action = QAction("Yomitan Backfill (Preset)...", mw)
preset_action.triggered.connect(open_preset_dialog)

mw.form.menuTools.addSeparator()
mw.form.menuTools.addAction(manual_action)
mw.form.menuTools.addAction(preset_action)
from .browser import BrowserBackfill
from .tools import ToolsBackfill

tools_menu = ToolsBackfill()
browser_menu = BrowserBackfill()
