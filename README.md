# backfill-anki-yomitan

This is a basic Anki add-on to backfill fields including media and audio using [Yomitan's API](https://github.com/Kuuuube/yomitan-api).
## Installation
1. Install the Yomitan API like specified in the README.
2. Install the add-on from [AnkiWeb](https://ankiweb.net/shared/info/1184164376)
3. Restart Anki

## Usage
1.  **Create a Backup of your profile/deck**
2. Make sure your Browser is running and the API is working.
3. Go to `Tools -> Backfill from Yomitan` in the top bar.
4. Select your deck in the `Deck` dropdown.
5. For `Expression Field` choose the expression field (e.g. `Expression` in Lapis) of your note type, this is the field that will be queried into Yomitan.
6. Optionally choose a `Reading Field` (e.g. ExpressionReading in Lapis) to differentiate expressions using their reading. If left blank, the add-on uses the first result Yomitan returns.
7. For `Field` choose the field to be backfilled.
8. In `Handlebar` type in the Yomitan handlebar, from which you wish to pull data from, without brackets (e.g. `frequency-harmonic-rank`).
9. Optionally tick `Replace` if you wish to replace the current content of the field in every card.
10. Press `Run`.

Changes can be undone with `Edit -> Undo` or with `CTRL + Z`.

## Issues
The addon has been updated to support the changes to the API in Yomitan 25.7.14.1, previous versions of Yomitan are not supported anymore.

The add-on can currently only run on the entire deck.

If you're backfilling audio, please be aware that retrieving audio - depending on the audio sources configured in Yomitan - can be quite slow.

## Screenshot
![screenshot](https://github.com/Manhhao/backfill-anki-yomitan/blob/main/screenshot/image.png?raw=true)
