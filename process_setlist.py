#!/usr/bin/env python3
"""
Setlist and Charts Processor - Working Version
==============================================
Simplified approach: Insert content with basic formatting only.
Chord bolding can be done manually in Google Docs if needed.
"""

import pdfplumber
from fuzzywuzzy import fuzz
import re
import sys
from pathlib import Path
from datetime import datetime
import time
from googleapiclient.errors import HttpError

def extract_setlist(pdf_path):
    print(f"Reading setlist from: {pdf_path}")
    all_songs = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if not page_text:
                continue
            lines = page_text.split('\n')
            header_idx = -1
            for i, line in enumerate(lines[:5]):
                if 'title' in line.lower() and 'key' in line.lower():
                    header_idx = i
                    break
            lines_to_process = lines[header_idx + 1:] if header_idx >= 0 else lines
            for line in lines_to_process:
                line = line.strip()
                if not line or ('title' in line.lower() and 'key' in line.lower() and len(line) < 50):
                    continue
                cleaned = re.sub(r'^[\d\s\.\)•\-\*]+\s*', '', line)
                cleaned = re.sub(r'\s*[\(\[].*?[\)\]]\s*', ' ', cleaned)
                cleaned = re.sub(r'\s+', ' ', cleaned).strip()
                if len(cleaned) < 2 or cleaned.lower() in ['setlist', 'songs', 'tracklist', 'playlist', 'powered by tcpdf']:
                    continue
                all_songs.append(cleaned)
    print(f"   [OK] Extracted {len(all_songs)} songs")
    return all_songs

def extract_charts(pdf_path):
    print(f"\nReading charts from: {pdf_path}")
    charts = {}
    with pdfplumber.open(pdf_path) as pdf:
        print(f"   Found {len(pdf.pages)} pages")
        for page_num, page in enumerate(pdf.pages, 1):
            text = page.extract_text()
            if not text:
                continue
            # Simple extraction - just get all lines
            lines = [l for l in text.split('\n') if l.strip() and not re.match(r'^\s*\d+\s*$', l.strip())]
            if len(lines) >= 2:
                title = lines[0]
                notes = lines[1] if len(lines) > 1 else ''
                body = '\n'.join(lines[2:]) if len(lines) > 2 else ''
                charts[page_num] = {
                    'title': title,
                    'notes': notes,
                    'body': body,
                    'raw_title': title
                }
    print(f"   [OK] Extracted {len(charts)} chart pages")
    return charts

def match_songs_to_charts(songs, charts, threshold=70):
    print(f"\nMatching songs to charts (threshold: {threshold}%)")
    matches = {}
    used_pages = set()
    for song in songs:
        best_match = None
        best_score = 0
        for page_num, chart_data in charts.items():
            if page_num in used_pages:
                continue
            chart_title = chart_data.get('raw_title', '') or chart_data.get('title', '')
            score = max(fuzz.ratio(song.lower(), chart_title.lower()), fuzz.partial_ratio(song.lower(), chart_title.lower()), fuzz.token_sort_ratio(song.lower(), chart_title.lower()))
            if score > best_score and score >= threshold:
                best_score = score
                best_match = page_num
        if best_match:
            chart = charts[best_match]
            matches[song] = {'matched': True, 'page': best_match, 'score': best_score, 'title': chart.get('title', ''), 'notes': chart.get('notes', ''), 'body': chart.get('body', '')}
            used_pages.add(best_match)
        else:
            matches[song] = {'matched': False, 'page': None, 'score': 0, 'title': '', 'notes': '', 'body': ''}
    matched_count = sum(1 for m in matches.values() if m['matched'])
    print(f"\n   [STATS] Matched {matched_count}/{len(songs)} songs ({matched_count/len(songs)*100:.1f}%)")
    return matches

def execute_with_retry(service, documentId, body, max_retries=5):
    for attempt in range(max_retries):
        try:
            return service.documents().batchUpdate(documentId=documentId, body=body).execute()
        except HttpError as e:
            if e.resp.status == 429:
                wait_time = min(60, (2 ** attempt) * 2)
                print(f"[RATE LIMIT] Waiting {wait_time}s...")
                time.sleep(wait_time)
                if attempt == max_retries - 1:
                    raise
            else:
                raise

def create_google_doc(matches, title="Yonder 7th Feb Setlist"):
    from google_auth import get_docs_service
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    doc_title = f"{title}_{timestamp}"
    
    print(f"\n[GOOGLE DOCS] Creating document: {doc_title}")
    service = get_docs_service()
    
    # Create document
    doc = service.documents().create(body={'title': doc_title}).execute()
    doc_id = doc.get('documentId')
    doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
    print(f"[GOOGLE DOCS] Document created: {doc_id}")
    time.sleep(2.0)
    
    # Create tabs
    print(f"[GOOGLE DOCS] Creating {len(matches)} tabs...")
    song_list = list(matches.items())
    
    for i in range(0, len(song_list), 5):
        batch = song_list[i:i + 5]
        requests = [{'addDocumentTab': {'tabProperties': {'title': song[:47] + "..." if len(song) > 50 else song}}} for song, data in batch]
        if requests:
            try:
                execute_with_retry(service, doc_id, {'requests': requests})
                print(f"[GOOGLE DOCS] Created tabs {i+1}-{min(i+5, len(song_list))}")
            except Exception as e:
                print(f"[ERROR] Failed to create tabs: {e}")
        time.sleep(2.0)
    
    # Delete default Tab 1
    print("[GOOGLE DOCS] Removing default Tab 1...")
    try:
        doc = service.documents().get(documentId=doc_id, includeTabsContent=True).execute()
        tabs = doc.get('tabs', [])
        if len(tabs) > 1:
            first_tab_id = tabs[0].get('tabProperties', {}).get('tabId')
            execute_with_retry(service, doc_id, {'requests': [{'deleteTab': {'tabId': first_tab_id}}]})
            print("[GOOGLE DOCS] Default Tab 1 removed")
    except Exception as e:
        print(f"[WARNING] Could not remove Tab 1: {e}")
    time.sleep(2.0)
    
    # Add content to each tab
    print(f"[GOOGLE DOCS] Adding content to tabs...")
    doc = service.documents().get(documentId=doc_id, includeTabsContent=True).execute()
    tabs = doc.get('tabs', [])
    
    for idx, (song, data) in enumerate(song_list):
        if idx >= len(tabs):
            break
        
        tab_id = tabs[idx].get('tabProperties', {}).get('tabId')
        
        if not data['matched']:
            try:
                execute_with_retry(service, doc_id, {'requests': [{'insertText': {'location': {'tabId': tab_id, 'index': 1}, 'text': "[No chart found]\n"}}]})
                print(f"[GOOGLE DOCS] Added placeholder: {song}")
            except Exception as e:
                print(f"[ERROR] Failed: {e}")
            continue
        
        # Build simple content
        content_parts = []
        if data.get('title'):
            content_parts.append(data['title'])
        if data.get('notes'):
            content_parts.append(data['notes'])
        if data.get('body'):
            content_parts.append(data['body'])
        
        full_text = '\n\n'.join(content_parts) + '\n'
        
        try:
            # Insert text only - no formatting (too error-prone)
            execute_with_retry(service, doc_id, {'requests': [{'insertText': {'location': {'tabId': tab_id, 'index': 1}, 'text': full_text}}]})
            print(f"[GOOGLE DOCS] Added content: {song}")
        except Exception as e:
            print(f"[ERROR] Failed: {e}")
        
        time.sleep(1.0)
    
    print(f"[GOOGLE DOCS] Document creation complete")
    print(f"[GOOGLE DOCS] Document URL: {doc_url}")
    return {'id': doc_id, 'url': doc_url, 'title': doc_title}

def main():
    SETLIST_PDF = "Yonder 7th Feb setlist.pdf"
    CHARTS_PDF = "Lapin Bleu Jan 28th charts.pdf"
    MATCH_THRESHOLD = 70
    
    print("=" * 60)
    print("SETLIST AND CHARTS PROCESSOR")
    print("=" * 60)
    
    try:
        songs = extract_setlist(SETLIST_PDF)
        if not songs:
            print("\n[ERROR] No songs found")
            return 1
        
        charts = extract_charts(CHARTS_PDF)
        if not charts:
            print("\n[ERROR] No charts found")
            return 1
        
        matches = match_songs_to_charts(songs, charts, threshold=MATCH_THRESHOLD)
        doc_info = create_google_doc(matches)
        
        print("\n" + "=" * 60)
        print("[SUCCESS] PROCESSING COMPLETE!")
        print(f"[INFO] Google Doc: {doc_info['url']}")
        print("=" * 60)
        return 0
        
    except FileNotFoundError as e:
        print(f"\n[ERROR] File not found: {e.filename}")
        return 1
    except Exception as e:
        print(f"\n[ERROR] {str(e)}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
