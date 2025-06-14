import json
import urllib
from anki.collection import Collection
from aqt import mw
from aqt.operations import CollectionOp, OpChanges, OpChangesWithCount
from aqt.utils import showInfo, showWarning
from aqt.qt import *
from urllib.error import HTTPError, URLError

request_url = "http://127.0.0.1:8766"
request_timeout = 10
ping_timeout = 5

# https://github.com/Kuuuube/yomitan-api/blob/master/docs/api_paths/ankiFields.md
def request_handlebar(expression, reading, handlebar):
    body = {
        "text": expression,
        "type": "term",
        "markers": [handlebar, "reading"],
        "maxEntries": 4 if reading else 1, # should probably be configurable
    }

    req = urllib.request.Request(
        request_url + "/ankiFields",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        response = urllib.request.urlopen(req, timeout=request_timeout)  
        data = json.loads(response.read())
    except HTTPError as e:
        if e.code == 500:
            # this throws if the handlebar does not exist for specified term
            return None
        else:
            raise
    except URLError as e:
        raise ConnectionRefusedError("Unable to reach Yomitan API")

    # prevent cancelling entire batch if request was successful but data is empty
    if not data:
        return None
    
    if reading:
        for entry in data:
            if entry.get("reading") == reading:
                return entry.get(handlebar)
        
        # no entry matching reading, skip by returning None
        return None
    else:
        return data[0].get(handlebar)

def ping_yomitan(): 
    req = urllib.request.Request(request_url + "/yomitanVersion", method="POST")
    try:
        response = urllib.request.urlopen(req, timeout=ping_timeout)  
        data = json.loads(response.read())
        return data
    except Exception:
        return False

def open_dialog():
    if not ping_yomitan():
        showWarning("Unable to reach Yomitan API");
        return
    
    dlg = BackfillDialog(mw)
    dlg.resize(350, dlg.height())

    if hasattr(dlg, "exec_"):
        # qt5
        dlg.exec_()
    else:
        # qt6
        dlg.exec()

class BackfillDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Yomitan Backfill")

        self.decks = QComboBox()
        self.fields = QComboBox()
        self.expression_field = QComboBox()
        self.reading_field = QComboBox()
        self.yomitan_handlebar = QLineEdit()
        self.apply = QPushButton("Run")
        self.cancel = QPushButton("Cancel")
        self.replace = QCheckBox("Replace");

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.addRow(QLabel("Deck:"), self.decks)
        form.addRow(QLabel("Expression Field:"), self.expression_field)
        form.addRow(QLabel("Reading Field:"), self.reading_field)
        form.addRow(QLabel("Field:"), self.fields)
        form.addRow(QLabel("Handlebar:"), self.yomitan_handlebar)

        buttons = QHBoxLayout()
        buttons.addWidget(self.apply)
        buttons.addWidget(self.cancel)

        checkboxes = QHBoxLayout()
        checkboxes.addWidget(self.replace)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addLayout(checkboxes)
        layout.addLayout(buttons)
        self.setLayout(layout)

        self._load_decks()
        self._update_fields()

        self.decks.currentIndexChanged.connect(self._update_fields)
        self.apply.clicked.connect(self._on_run)
        self.cancel.clicked.connect(self.reject)

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
        field = self.fields.currentText()
        handlebar = self.yomitan_handlebar.text()
        should_replace = self.replace.isChecked()
        
        note_ids = mw.col.db.list("SELECT DISTINCT nid FROM cards WHERE did = ?", deck_id)
        
        # https://github.com/wikidattica/reversoanki/pull/1/commits/62f0c9145a5ef7b2bde1dc6dfd5f23a53daac4d0
        def backfill_notes(col):
            notes = []
            for nid in note_ids:
                note = col.get_note(nid)
                if expression_field in note and field in note:
                    current = note[field].strip()
                    if should_replace or not current:
                        reading = note[reading_field] if reading_field else None
                        data = request_handlebar(note[expression_field].strip(), reading, handlebar)
                        if data:
                            note[field] = data
                            notes.append(note)
           
            return OpChangesWithCount(changes=col.update_notes(notes), count=len(notes))

        def on_success(result):
            mw.col.reset()
            showInfo(f"Updated {result.count} cards");
            
        op = CollectionOp(
            parent = mw,
            op = lambda col: backfill_notes(col)
        )
        
        op.success(on_success).run_in_background()

action = QAction("Backfill from Yomitan", mw)
action.triggered.connect(open_dialog)
mw.form.menuTools.addAction(action)