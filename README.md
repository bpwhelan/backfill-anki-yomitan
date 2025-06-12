# backfill-anki-yomitan

This is a basic add-on to backfill fields using [Yomitan's API](https://github.com/Kuuuube/yomitan-api).
## Installation
1. Install the Yomitan API like specified in the README.
2. Install the add-on from [AnkiWeb](https://ankiweb.net/shared/info/1184164376)
3. Restart Anki

## Usage
1. **Create a Backup of your profile/deck**
2. Go to `Tools -> Backfill from Yomitan` in the top bar
3. Select your deck in the `Deck` dropdown
4. For `Expression Field` choose the expression field (e.g. `Expression` in Lapis, `word` in Senren) of your note type, this is the field that will be queried into Yomitan
5. For `Field` choose the field which is to be backfilled
6. In `Handlebar` type in the Yomitan handlebar, from which you wish to pull data from, without the {} brackets (e.g. frequency-harmonic-rank) 
7. Optionally tick `Replace Current` if you wish to replace the current content of the field for every card
8. Press Run

Changes can be undone with `Edit -> Undo` or with `CTRL + Z`

## Issues
The add-on currently only pulls the first result from the API and can therefore not handle different readings (it will fill identical expressions with the same data).
