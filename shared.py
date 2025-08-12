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
from . import yomitan_api


logger = logging.getLogger(__name__)

addon_folder = os.path.join(mw.pm.addonFolder(), "backfill-anki-yomitan")

file_handler = logging.FileHandler(os.path.join(addon_folder, "addon.log"))
file_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)

logger.addHandler(file_handler)

# --- Constants and API Communication ---

request_url = "http://127.0.0.1:8766"
request_timeout = 10
ping_timeout = 5

def run_backfill_operation(parent, note_ids, expression_field, reading_field, targets, should_replace):
    """
    The core operation to backfill notes. Can be called by manual or preset mode.
    - parent: The parent window for the CollectionOp (usually mw or a dialog).
    - deck_id: The ID of the deck to process.
    - expression_field: The note field with the term.
    - reading_field: The note field with the reading (can be None).
    - targets: A list of dicts, e.g., [{"fieldToFill": "Field1", "handlebar": "{hb1}"}, ...].
    - should_replace: Boolean flag to overwrite existing content.
    """
    logger.info(f"Running backfill operation for {len(note_ids)} notes.")

    def on_success(result):
        if result.count > 0:
            showInfo(f"Successfully updated {result.count} notes.")
        else:
            showInfo("No notes were updated.")
        mw.col.reset()
        
    # should_replace = any(target.get("replaceExisting", False) for target in targets) if should_replace is None else should_replace

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

        reading = note[reading_field] if reading_field and reading_field in note else None
        
        fields_to_fill = []
        for target in targets:
            field_to_fill = target["fieldToFill"]
            handlebar = target["handlebar"]
            should_replace_field = target.get("replaceExisting", should_replace)
            
            logger.info(f"Processing target: {field_to_fill} with handlebar: {handlebar}")

            if field_to_fill not in note:
                continue
            
            if not field_to_fill or not handlebar:
                # Just Empty fields, skip this target
                continue
            
            # Skip if field is already filled and we shouldn't replace
            if not should_replace_field and note[field_to_fill].strip():
                continue
            fields_to_fill.append({"field_to_fill": field_to_fill, "handlebar": handlebar.replace("{", "").replace("}", "")})

        logger.info(f"Found Targets: {fields_to_fill}")

        # --- API Request and Processing ---
        api_response = yomitan_api.request_handlebar(expression, reading, [field["handlebar"] for field in fields_to_fill])
        logger.info(f"Requesting Yomitan data for: {expression} (Reading: {reading}, Handlebar: {handlebar})")
        # logger.info(f"API Response: {api_response}")
        
        # showInfo(f"Requesting Yomitan data for: {expression} (Reading: {reading}, Handlebar: {handlebar})")
        # showInfo(f"API Response: {api_response}")
        if not api_response:
            continue

        fields_data = api_response.get("fields")
        if not fields_data:
            continue
        
        for field in fields_to_fill:
            field_to_fill = field["field_to_fill"]
            new_value = get_field_from_response(fields_data, reading, field["handlebar"])

            logger.info(f"New value for field '{field_to_fill}': {new_value}")
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
        
        note.add_tag("yomitan-backfill")

        if note_was_modified:
            notes_to_update.append(note)

    return OpChangesWithCount(changes=col.update_notes(notes_to_update), count=len(notes_to_update))