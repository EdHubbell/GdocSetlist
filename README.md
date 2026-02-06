# GdocSetlist

Extracts songs from a setlist PDF, matches them to chart pages in a charts PDF using fuzzy title matching, and creates a formatted Google Doc with one tab per song.

## What it does

1. **Extracts song titles** from a setlist PDF (e.g. `Yonder 7th Feb setlist.pdf`)
2. **Extracts charts** (title, key/tags, chord+lyric body) from a charts PDF (e.g. `Lapin Bleu Jan 28th charts.pdf`), preserving horizontal chord alignment using character-level PDF positions
3. **Fuzzy-matches** setlist songs to chart pages by title (default threshold: 70%)
4. **Creates a Google Doc** with a tab for each song, formatted:
   - Consolas 12pt monospace throughout
   - Title and key/tags lines centered
   - Chord lines auto-detected and bolded
   - Chord symbols aligned over the correct lyrics (spacing preserved from the original PDF)

All formatting for each tab is applied in a single `batchUpdate` API call (insert text + font + alignment + bold in one request).

## Setup

### Dependencies

```
pip install pdfplumber fuzzywuzzy python-Levenshtein google-auth-oauthlib google-api-python-client
```

### Google OAuth

1. Create a Google Cloud project with the Docs and Drive APIs enabled
2. Download the OAuth client secret JSON and place it in the project directory
3. On first run, a browser window opens for authentication; the token is cached to `token.json`

## Usage

```
python process_setlist.py
```

Place your setlist and charts PDFs in the project directory. Edit the `SETLIST_PDF` and `CHARTS_PDF` variables in `main()` to point to your files.

The script prints a Google Docs URL when complete.

### Test mode

```
python test_2tabs.py
```

Creates a doc with only the first 2 matched songs for quick verification of formatting.

## Files

| File | Purpose |
|------|---------|
| `process_setlist.py` | Main pipeline: extract, match, create formatted Google Doc |
| `test_2tabs.py` | 2-tab test for verifying formatting |
| `google_auth.py` | OAuth2 authentication for Google APIs |

