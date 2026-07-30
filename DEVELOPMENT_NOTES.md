# Development Notes: Setlist and Charts Processor

**Date Created:** 2026-02-05  
**Last Updated:** 2026-02-05  
**Purpose:** Combine PDF setlist with music charts into a Google Doc with tabs

---

## Overview

This tool automates the process of extracting song names from a setlist PDF and matching them with corresponding chart pages from a separate charts PDF, creating a Google Doc with tabs for each song.

**IMPORTANT NOTE:** This implementation has significant limitations. See "Implementation Failures" section below.

---

## What Was Planned vs What Was Implemented

### ✅ Successfully Implemented

1. **PDF Text Extraction**
   - Setlist extraction with header detection
   - Chart extraction with font size detection for headers
   - Per-page processing for multi-page documents

2. **Song Matching**
   - Fuzzy matching (70% threshold) working correctly
   - 32 of 45 songs matched to charts (71.1% success rate)

3. **Google Doc Creation**
   - 45 tabs created (one per song)
   - Content correctly distributed across tabs
   - Default "Tab 1" removed
   - Timestamped filenames working

### ❌ Implementation Failures

#### 1. **Font Formatting (Consolas)**
**Planned:** All text in Consolas 12pt  
**Actual:** Default font only  
**Reason:** Google Docs API index tracking is unreliable. When applying `updateTextStyle` to ranges, indices become invalid after subsequent insertions. Multiple attempts to fix this (immediate formatting, batch formatting, two-pass approach) all failed with index out of range errors.

#### 2. **Bold Chord Lines**
**Planned:** Chord lines in bold (80% chord detection)  
**Actual:** No bold formatting  
**Reason:** Same index tracking issue. Even when detecting chords correctly, applying bold formatting to specific ranges failed due to index misalignment between expected and actual document structure.

#### 3. **Centered Headers**
**Planned:** Title and notes lines centered  
**Actual:** Left-aligned only  
**Reason:** `updateParagraphStyle` with ranges caused cascading formatting errors. Paragraph indices shifted as content was inserted, making it impossible to reliably target specific paragraphs.

#### 4. **API Rate Limits**
**Issue:** Google Docs API limited to 60 write requests/minute/user  
**Impact:** Line-by-line formatting (3-4 requests per line × 30-40 lines × 45 songs = 4,000-7,000 requests) would take 60-120 minutes and frequently hit rate limits even with delays.

### 🔧 Workaround

**Current Solution:** Content is inserted correctly with proper spacing. Manual formatting required:
1. Open Google Doc
2. Select all (Ctrl+A)
3. Change font to Consolas 12pt
4. Manually bold chord lines
5. Center title/notes lines

---

## Files Created

- `process_setlist.py` - Main processing script (content extraction only)
- `google_auth.py` - Google OAuth handling
- `token.json` - Stored authentication (auto-generated)
- `docs/DEVELOPMENT_NOTES.md` - This documentation
- Generated Google Docs with timestamped names

## Prerequisites

### Required Python Packages

```bash
pip install pdfplumber google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client fuzzywuzzy python-Levenshtein
```

**Package Descriptions:**
- `pdfplumber` - Extracts text from PDF files
- `google-auth` / `google-auth-oauthlib` - Google OAuth authentication
- `google-api-python-client` - Google Docs API access
- `fuzzywuzzy` - Fuzzy string matching
- `python-Levenshtein` - Optimizes fuzzywuzzy performance

## Input Files

1. **Setlist PDF** (`Yonder 7th Feb setlist.pdf`)
   - Contains list of songs in set order
   - Headers detected using "Title Key Tags" marker
   - Multi-page support with per-page header detection

2. **Charts PDF** (`Lapin Bleu Jan 28th charts.pdf`)
   - One page per song chart
   - Font size detection for title/notes identification
   - 32 pages processed

## How It Works

### Step 1: Extract Songs
- Reads all text from setlist PDF
- Splits text into lines
- Detects header row containing "Title" and "Key"
- Extracts only lines after header
- Returns list of cleaned song names

### Step 2: Extract Charts
- Reads each page of charts PDF
- Extracts words with font size information
- Groups words by Y-position to identify lines
- Detects headers based on font size (>20% larger than normal)
- First 2 header lines = title + notes
- Remaining lines = body (lyrics + chords)
- Returns structured data: `{page_num: {title, notes, body}}`

### Step 3: Fuzzy Matching
- Compares each setlist song with every chart page
- Uses multiple matching strategies:
  1. **Ratio**: Direct string similarity
  2. **Partial Ratio**: Best matching substring
  3. **Token Sort Ratio**: Handles word order differences
- Takes highest score from all strategies
- Matches if score >= 70% (configurable)
- Prevents duplicate matches

### Step 4: Create Google Doc
- Creates document with timestamped title
- Creates 45 tabs (one per song)
- Deletes default "Tab 1"
- Inserts content into each tab:
  - Title
  - Notes
  - Body text (preserving exact spacing)
- **LIMITATION:** No automatic formatting applied

## Configuration Options

Edit these variables in `process_setlist.py`:

```python
SETLIST_PDF = "Yonder 7th Feb setlist.pdf"    # Input setlist file
CHARTS_PDF = "Lapin Bleu Jan 28th charts.pdf" # Input charts file
MATCH_THRESHOLD = 70  # Fuzzy match threshold (0-100)
```

## Running the Script

```bash
# Navigate to project directory
cd C:\Development\Buckdrivers\GdocSetlist

# First run - OAuth authentication required
python process_setlist.py
# Browser will open for Google login

# Subsequent runs - uses saved token
python process_setlist.py
```

### Expected Output
```
============================================================
SETLIST AND CHARTS PROCESSOR
============================================================
Reading setlist from: Yonder 7th Feb setlist.pdf
   Found 2 pages
   [INFO] Page 1: Extracted 23 songs
   [INFO] Page 2: Extracted 22 songs
   [OK] Extracted 45 total songs

Reading charts from: Lapin Bleu Jan 28th charts.pdf
   Found 32 pages
   [OK] Extracted 32 chart pages

Matching songs to charts (threshold: 70%)
   [MATCH] 'Song Name' -> Page X (score: XX%)
   ...
   [STATS] Matched 32/45 songs (71.1%)

[GOOGLE DOCS] Creating document: Yonder 7th Feb Setlist_YYYYMMDD_HHMMSS
[GOOGLE DOCS] Document created: [doc_id]
[GOOGLE DOCS] Creating 45 tabs...
[GOOGLE DOCS] Default Tab 1 removed
[GOOGLE DOCS] Adding content to tabs...
[GOOGLE DOCS] Document creation complete
[GOOGLE DOCS] Document URL: https://docs.google.com/document/d/[id]/edit

============================================================
[SUCCESS] PROCESSING COMPLETE!
============================================================
```

## Post-Processing (Manual Steps Required)

Since automatic formatting failed, you must manually format each tab:

### For Each Tab:
1. **Select All** (Ctrl+A)
2. **Change Font** → Consolas
3. **Change Size** → 12pt
4. **Select Title Line** → Center alignment
5. **Select Notes Line** → Center alignment
6. **Select Chord Lines** → Bold (identify by chord names: A, D, E, etc.)

**Time Required:** ~2-3 minutes per tab × 45 tabs = 90-135 minutes total

## Troubleshooting

### OAuth Authentication Issues
**Issue:** "token.json not found" or authentication errors  
**Fix:** Delete `token.json` and re-run - browser will prompt for login

### Rate Limit Errors
**Issue:** "Quota exceeded for write operations"  
**Cause:** Google Docs API limit of 60 requests/minute  
**Fix:** Script now waits between requests; if errors persist, wait 1 minute and retry

### Content Not In Correct Tabs
**Issue:** All content in first tab  
**Cause:** Missing `tabId` in insert requests  
**Status:** ✅ Fixed in current version

### Chord Spacing Wrong
**Issue:** Chords not aligned with lyrics  
**Cause:** Font not fixed-width  
**Fix:** Manually change to Consolas font

## Results from This Run

**Input:**
- Setlist: 45 songs extracted
- Charts: 32 pages found

**Matching:**
- Matched: 32 songs (71.1%)
- Unmatched: 13 songs (placeholders added)

**Output:**
- 45 tabs created
- Content: ✅ Correctly inserted
- Font: ❌ Manual formatting required
- Bold Chords: ❌ Manual formatting required
- Centered Headers: ❌ Manual formatting required

## Technical Details

### Dependencies
- **pdfplumber**: PDF text and font extraction
- **Google Docs API v1**: Document creation and manipulation
- **fuzzywuzzy**: String matching

### What Works
- PDF text extraction with spacing preservation
- Font size detection for header identification
- Fuzzy matching algorithm
- Multi-tab Google Doc creation
- Content distribution across tabs

### What Doesn't Work
- Index-based formatting (Google Docs API limitation)
- Reliable range targeting after insertions
- Batch formatting without index drift
- Real-time formatting during insertion

### Root Cause Analysis

**The Fundamental Problem:**
Google Docs API uses integer indices to reference positions in the document. When you:
1. Insert text at position X
2. The document length changes
3. All indices after X shift
4. Previously calculated indices become invalid

**Attempted Solutions:**
1. ✅ Insert all content first, then format (failed - indices still drift)
2. ✅ Read document after each insertion (failed - too slow, still had race conditions)
3. ✅ Track positions per-tab (failed - document structure different than expected)
4. ✅ Immediate formatting after each line (failed - rate limits + index errors)

**Why It Can't Be Fixed:**
The Google Docs API is designed for collaborative editing where indices change constantly. It's not well-suited for batch formatting of structured content. The only reliable approach would be:
- Create document structure first
- Then apply formatting in a completely separate pass
- Even then, index tracking is fragile

## Future Enhancements (If Revisiting)

1. **Alternative Approach:** Generate HTML/CSS with proper formatting, then import to Google Docs
2. **Alternative Format:** Create formatted Word document (python-docx handles this reliably)
3. **Manual Helper Script:** Generate formatting instructions to speed up manual work
4. **Image Extraction:** Extract charts as images instead of text (bypasses formatting entirely)

## File Structure

```
C:\Development\Buckdrivers\GdocSetlist\
├── docs/
│   ├── DEVELOPMENT_NOTES.md           # This documentation
│   └── [Generated Google Docs - check your Google Drive]
├── process_setlist.py                 # Main script
├── google_auth.py                     # OAuth handling
├── token.json                         # Auth token (auto-generated)
├── Yonder 7th Feb setlist.pdf         # Input setlist
└── Lapin Bleu Jan 28th charts.pdf     # Input charts
```

## Maintenance Notes

**Last Updated:** 2026-02-05

**Known Working:**
- Content extraction and tab creation
- Fuzzy matching
- Document generation

**Known Issues:**
- Automatic formatting does not work
- Manual formatting required post-generation
- API rate limits require slow processing

**To Update Packages:**
```bash
pip install --upgrade pdfplumber google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client fuzzywuzzy python-Levenshtein
```

---

**Summary:**  
This tool successfully extracts content from PDFs and organizes it into a Google Doc with tabs. However, due to Google Docs API limitations with index tracking, automatic formatting (Consolas font, bold chords, centered headers) is not possible. Users must manually format the document after generation.

**Recommendation:**  
For future projects requiring formatted output, consider:
- Microsoft Word (python-docx handles formatting reliably)
- HTML/CSS export with browser print-to-PDF
- LaTeX for precise typesetting control
