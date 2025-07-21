from aqt import gui_hooks, mw
from aqt.utils import showWarning
from aqt.qt import *
from aqt.browser import Browser

class BrowserBackfill:
    def __init__(self):
        gui_hooks.browser_menus_did_init.append(self._add_to_browser)

    def _open_browser_dialog(self, browser: Browser):
        selected_note_ids = list(browser.selectedNotes())
        if not selected_note_ids:
            showWarning("No notes selected")
            return
        
        note = mw.col.get_note(selected_note_ids[0])
        card = note.cards()[0]
        deck_id = card.did
        deck_name = mw.col.decks.name(deck_id)

        dlg = self.BrowserDialog(browser, deck_name)
        dlg._update_fields(deck_id)
        dlg.resize(350, dlg.height())

        if hasattr(dlg, "exec_"):
            # qt5
            dlg.exec_()
        else:
            # qt6
            dlg.exec()

    def _add_to_browser(self, browser: Browser):
        action = QAction("Backfill from Yomitan", browser)
        action.triggered.connect(lambda: self._open_browser_dialog(browser))
        browser.form.menuEdit.addAction(action)
    
    class BrowserDialog(QDialog):
        def __init__(self, parent, deck_name):
            super().__init__(parent)
            self.setWindowTitle("Yomitan Backfill")

            self.decks = QLineEdit()
            self.fields = QComboBox()
            self.expression_field = QComboBox()
            self.reading_field = QComboBox()
            self.yomitan_handlebar = QLineEdit()
            self.apply = QPushButton("Run")
            self.cancel = QPushButton("Cancel")
            self.replace = QCheckBox("Replace")

            self.decks.setText(deck_name)
            self.decks.setReadOnly(True)

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

            self.cancel.clicked.connect(self.reject)

        def _update_fields(self, deck_id):
            self.fields.clear()
            self.expression_field.clear()
            self.reading_field.clear()

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