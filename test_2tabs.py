#!/usr/bin/env python3
"""
2-Tab Formatting Test
=====================
Creates a Google Doc with 2 tabs to verify formatting:
- Consolas 12pt on all text
- Bold chord lines
- Centered title and notes

Uses a single batchUpdate per tab (insert + all formatting in one API call).
"""

import re
import sys
from datetime import datetime

from google_auth import get_docs_service
from process_setlist import (
    extract_setlist,
    extract_charts,
    match_songs_to_charts,
    execute_with_retry,
)

# Chord pattern: root note optionally followed by quality/extensions, optional slash bass
# Matches: A, Am, D7, G/B, Cmaj7, F#m, Bb, Ebm7, Dsus4, Aadd9, etc.
CHORD_RE = re.compile(
    r'^[A-G][b#]?'                      # root: A-G with optional sharp/flat
    r'(m|min|maj|dim|aug|sus|add)?'      # quality
    r'[0-9]?'                            # extension (7, 9, etc.)
    r'(sus[24]|add[0-9]+|maj[0-9]+)?'   # additional modifiers
    r'(/[A-G][b#]?)?$'                   # optional slash bass
)


def is_chord_line(line):
    """Return True if 80%+ of whitespace-separated tokens are chord symbols or TACET."""
    tokens = line.split()
    if not tokens:
        return False
    chord_count = 0
    for token in tokens:
        # Strip trailing punctuation that might appear (e.g., trailing comma)
        clean = token.strip('(),|[]')
        if clean.upper() == 'TACET':
            chord_count += 1
        elif CHORD_RE.match(clean):
            chord_count += 1
    return (chord_count / len(tokens)) >= 0.8


def build_tab_requests(tab_id, title, notes, body_text):
    """
    Build all requests for a single tab's content and formatting.

    Returns a list of Google Docs API request dicts to be sent in ONE batchUpdate.
    Inserts the full text at index 1, then applies formatting using pre-calculated indices.
    """
    # Build the full text block
    full_text = title + '\n' + notes + '\n\n' + body_text + '\n'

    requests = []

    # 1) Insert all text at once
    requests.append({
        'insertText': {
            'location': {'tabId': tab_id, 'index': 1},
            'text': full_text,
        }
    })

    # 2) Consolas 12pt on the entire text
    text_end = 1 + len(full_text)
    requests.append({
        'updateTextStyle': {
            'range': {
                'tabId': tab_id,
                'startIndex': 1,
                'endIndex': text_end,
            },
            'textStyle': {
                'weightedFontFamily': {'fontFamily': 'Consolas'},
                'fontSize': {'magnitude': 12, 'unit': 'PT'},
            },
            'fields': 'weightedFontFamily,fontSize',
        }
    })

    # Pre-calculate line positions
    # cursor tracks our position in the document (starts at 1, after the implicit newline)
    cursor = 1

    # Title line
    title_start = cursor
    cursor += len(title) + 1  # +1 for '\n'
    title_end = cursor

    # 3) Center the title
    requests.append({
        'updateParagraphStyle': {
            'range': {
                'tabId': tab_id,
                'startIndex': title_start,
                'endIndex': title_end,
            },
            'paragraphStyle': {'alignment': 'CENTER'},
            'fields': 'alignment',
        }
    })

    # Notes line
    notes_start = cursor
    cursor += len(notes) + 1  # +1 for '\n'
    notes_end = cursor

    # 4) Center the notes
    requests.append({
        'updateParagraphStyle': {
            'range': {
                'tabId': tab_id,
                'startIndex': notes_start,
                'endIndex': notes_end,
            },
            'paragraphStyle': {'alignment': 'CENTER'},
            'fields': 'alignment',
        }
    })

    # Blank line between notes and body
    cursor += 1  # the '\n' for the blank line

    # Body lines — bold any chord lines
    for line in body_text.split('\n'):
        line_start = cursor
        cursor += len(line) + 1  # +1 for '\n'
        line_end = cursor

        if is_chord_line(line):
            # 5) Bold this chord line
            requests.append({
                'updateTextStyle': {
                    'range': {
                        'tabId': tab_id,
                        'startIndex': line_start,
                        'endIndex': line_end,
                    },
                    'textStyle': {'bold': True},
                    'fields': 'bold',
                }
            })

    return requests


def main():
    SETLIST_PDF = "Yonder 7th Feb setlist.pdf"
    CHARTS_PDF = "Lapin Bleu Jan 28th charts.pdf"

    print("=" * 60)
    print("2-TAB FORMATTING TEST")
    print("=" * 60)

    # 1) Extract songs and charts from existing PDFs
    songs = extract_setlist(SETLIST_PDF)
    if not songs:
        print("[ERROR] No songs found")
        return 1

    charts = extract_charts(CHARTS_PDF)
    if not charts:
        print("[ERROR] No charts found")
        return 1

    matches = match_songs_to_charts(songs, charts)

    # 2) Take first 2 matched songs
    matched_songs = [(song, data) for song, data in matches.items() if data['matched']]
    if len(matched_songs) < 2:
        print(f"[ERROR] Need at least 2 matched songs, got {len(matched_songs)}")
        return 1
    test_songs = matched_songs[:2]

    print(f"\nTest songs:")
    for song, data in test_songs:
        print(f"  - {song} (matched to page {data['page']}, score {data['score']})")

    # 3) Create Google Doc
    service = get_docs_service()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    doc_title = f"2Tab_Test_{timestamp}"

    print(f"\n[STEP 1] Creating document: {doc_title}")
    doc = service.documents().create(body={'title': doc_title}).execute()
    doc_id = doc.get('documentId')
    doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
    print(f"  Document ID: {doc_id}")

    # Create 2 tabs in a single batchUpdate
    print("[STEP 2] Creating 2 tabs...")
    tab_requests = []
    for song, data in test_songs:
        tab_name = song[:47] + "..." if len(song) > 50 else song
        tab_requests.append({
            'addDocumentTab': {'tabProperties': {'title': tab_name}}
        })
    execute_with_retry(service, doc_id, {'requests': tab_requests})

    # Get tab IDs
    print("[STEP 3] Getting tab IDs...")
    doc = service.documents().get(documentId=doc_id, includeTabsContent=True).execute()
    tabs = doc.get('tabs', [])
    print(f"  Found {len(tabs)} tabs")

    # Delete default Tab 1 (always the first one)
    print("[STEP 4] Deleting default Tab 1...")
    first_tab_id = tabs[0].get('tabProperties', {}).get('tabId')
    execute_with_retry(service, doc_id, {
        'requests': [{'deleteTab': {'tabId': first_tab_id}}]
    })

    # Re-fetch to get the remaining tabs
    print("[STEP 5] Getting updated tabs...")
    doc = service.documents().get(documentId=doc_id, includeTabsContent=True).execute()
    tabs = doc.get('tabs', [])
    print(f"  Remaining tabs: {len(tabs)}")

    for i, tab in enumerate(tabs):
        tab_title = tab.get('tabProperties', {}).get('title', '(untitled)')
        tab_id = tab.get('tabProperties', {}).get('tabId')
        print(f"  Tab {i+1}: '{tab_title}' (id: {tab_id})")

    # 4) Insert + format each tab in a single batchUpdate
    for idx, (song, data) in enumerate(test_songs):
        if idx >= len(tabs):
            print(f"[WARNING] No tab for song #{idx+1}, skipping")
            continue

        tab_id = tabs[idx].get('tabProperties', {}).get('tabId')
        title = data.get('title', '')
        notes = data.get('notes', '')
        body = data.get('body', '')

        print(f"\n[STEP {6 + idx}] Formatting tab: {song}")
        print(f"  Title: {title}")
        print(f"  Notes: {notes}")
        print(f"  Body lines: {len(body.split(chr(10)))}")

        # Count chord lines for reporting
        chord_lines = [l for l in body.split('\n') if is_chord_line(l)]
        print(f"  Chord lines detected: {len(chord_lines)}")

        reqs = build_tab_requests(tab_id, title, notes, body)
        print(f"  Requests in batch: {len(reqs)}")

        execute_with_retry(service, doc_id, {'requests': reqs})
        print(f"  Done!")

    # 5) Print results
    print("\n" + "=" * 60)
    print("[SUCCESS] 2-Tab test complete!")
    print(f"  Document URL: {doc_url}")
    print("=" * 60)
    print("\nVerification checklist:")
    print("  [ ] Both tabs exist with correct song names")
    print("  [ ] All text is Consolas 12pt")
    print("  [ ] Title and notes lines are centered")
    print("  [ ] Chord lines are bold, non-chord lines are not")

    return 0


if __name__ == "__main__":
    sys.exit(main())
