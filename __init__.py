import urllib
import json
from anki.collection import Collection
from aqt.operations import CollectionOp, OpChanges, OpChangesWithCount
from aqt import mw
from aqt.utils import showInfo
from aqt.qt import *

request_url = "http://127.0.0.1:8766"
request_timeout = 10

def request_handlebar(expression, handlebar):
    body = {
        "text": expression,
        "type": "term",
        "markers": [handlebar],
        "maxEntries": 1,
    }

    req = urllib.request.Request(
        request_url + "/ankiFields",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    
    response = urllib.request.urlopen(req, timeout=request_timeout)  
    data = json.loads(response.read())

    return data[0].get(handlebar)

def open_dialog():
    dlg = BackfillDialog(mw)
    dlg.exec()

class BackfillDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Yomitan Backfill")

        self.decks = QComboBox()
        self.fields = QComboBox()
        self.expression_field = QComboBox()
        self.yomitan_handlebar = QLineEdit()
        self.apply = QPushButton("Run")
        self.cancel = QPushButton("Cancel")
        self.replace = QCheckBox("Replace");
        
        form = QFormLayout()
        form.addRow(QLabel("Deck:"), self.decks)
        form.addRow(QLabel("Expression Field:"), self.expression_field)
        form.addRow(QLabel("Field:"), self.fields)
        form.addRow(QLabel("Handlebar:"), self.yomitan_handlebar)
        form.addRow(self.replace)
        
        buttons = QHBoxLayout()
        buttons.addWidget(self.apply)
        buttons.addWidget(self.cancel)

        layout = QVBoxLayout()
        layout.addLayout(form)
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
    
    def _on_run(self):
        deck_id = self.decks.currentData()
        expression_field = self.expression_field.currentText()
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
                        data = request_handlebar(note[expression_field].strip(), handlebar)
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