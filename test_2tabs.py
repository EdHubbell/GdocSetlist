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

import sys
from datetime import datetime

from google_auth import get_docs_service
from process_setlist import (
    extract_setlist,
    extract_charts,
    match_songs_to_charts,
    execute_with_retry,
    is_chord_line,
    build_tab_requests,
)


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
