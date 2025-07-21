import base64
from aqt import mw
from aqt.operations import CollectionOp, OpChangesWithCount
from aqt.utils import showInfo, showWarning
from aqt.qt import *
from . import yomitan_api  

class ToolsBackfill:
    def __init__(self):
        action = QAction("Backfill from Yomitan", mw)
        action.triggered.connect(self.open_dialog)
        mw.form.menuTools.addAction(action)

    def open_dialog(self):
        if not yomitan_api.ping_yomitan():
            showWarning("Unable to reach Yomitan API")
            return
        
        dlg = self.ToolsDialog(mw)
        dlg.resize(350, dlg.height())

        if hasattr(dlg, "exec_"):
            # qt5
            dlg.exec_()
        else:
            # qt6
            dlg.exec()

    class ToolsDialog(QDialog):
        def __init__(self, parent):
            super().__init__(parent)
            self.setWindowTitle("Yomitan Backfill")

            self.decks = QComboBox()
            self.fields = QComboBox()
            self.expression_field = QComboBox()
            self.reading_field = QComboBox()
            self.yomitan_handlebar = QLineEdit()
            self.apply = QPushButton("Run")
            self.cancel = QPushButton("Cancel")
            self.replace = QCheckBox("Replace")

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
            
            def write_media(file):
                try:
                    content = file.get("content")
                    filename = file.get("ankiFilename")
                    anki_media_dir = mw.col.media.dir()
                    decoded = base64.b64decode(content)

                    target_path = os.path.join(anki_media_dir, filename)

                    with open(target_path, "wb") as f:
                        f.write(decoded)
                    
                    return True
                except Exception:
                    return False

            def get_field_from_request(fields, reading):
                if reading:
                    for entry in fields:
                        if entry.get("reading") == reading:
                            return entry.get(handlebar)
                    return None
                else:
                    return fields[0].get(handlebar)

            # https://github.com/wikidattica/reversoanki/pull/1/commits/62f0c9145a5ef7b2bde1dc6dfd5f23a53daac4d0
            def backfill_notes(col):
                notes = []
                for nid in note_ids:
                    note = col.get_note(nid)
                    if not expression_field in note or not field in note:
                        continue

                    current = note[field].strip()
                    if should_replace or not current:
                        reading = note[reading_field] if reading_field else None
                        api_request = yomitan_api.request_handlebar(note[expression_field].strip(), reading, handlebar)
                        if not api_request:
                            continue

                        fields = api_request.get("fields")
                        if not fields:
                            continue

                        data = get_field_from_request(fields, reading)
                        if not data:
                            continue

                        # checks if handlebar data contains filename and writes it to anki if present
                        dictionary_media = api_request.get("dictionaryMedia", [])
                        for file in dictionary_media:
                            filename = file.get("ankiFilename")
                            if filename in data:
                                write_media(file)
                        
                        audio_media = api_request.get("audioMedia", [])
                        for file in audio_media:
                            filename = file.get("ankiFilename")
                            # if audio handlebar is requested, handlebar data contains the relevant audio filename, write only that file
                            if filename in data:
                                write_media(file)
                                break

                        note[field] = data
                        notes.append(note)
            
                return OpChangesWithCount(changes=col.update_notes(notes), count=len(notes))
            
            def on_success(result):
                mw.col.reset()
                showInfo(f"Updated {result.count} cards")
                
            op = CollectionOp(
                parent = mw,
                op = lambda col: backfill_notes(col)
            )
            
            op.success(on_success).run_in_background()