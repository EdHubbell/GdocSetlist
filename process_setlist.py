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

# Every mapping is one character to one character, so normalising a chart
# body can't shift chords out of alignment with the lyrics beneath them.
SMART_CHARS = str.maketrans({
    '‘': "'", '’': "'", '′': "'", '´': "'", '`': "'",
    '“': '"', '”': '"', '″': '"',
    '–': '-', '—': '-', '−': '-',
    ' ': ' ',
})

def normalize_text(text):
    """Replace smart quotes, primes and dashes with ASCII equivalents."""
    return text.translate(SMART_CHARS) if text else text


KEY_TOKEN_RE = re.compile(r'^[A-G][b#]?m?(/[A-G][b#]?m?)?$')

def _pick_key_column(song_rows, bounds):
    """Return the index of the column holding musical keys, or None.

    The key column isn't always the rightmost one - some setlists print
    key before the cue/tags column - so identify it by content instead.
    """
    for i, (lo, hi) in enumerate(bounds):
        values = [' '.join(w['text'] for w in r if lo <= w['x0'] < hi).strip()
                  for r in song_rows]
        values = [v for v in values if v]
        if not values:
            continue
        keys = sum(1 for v in values if KEY_TOKEN_RE.match(v))
        if keys / len(values) >= 0.7:
            return i
    return None


def _extract_setlist_columns(pdf_path):
    """Extract song titles and keys from a column-formatted setlist PDF.

    Song rows share one font size and start at the left margin; header and
    section rows use different sizes. Titles occupy the leftmost column, with
    cue/key columns to the right. Returns a list of {'title', 'key'} dicts,
    or [] if the PDF isn't this shape so the caller can fall back to
    line-based extraction.
    """
    songs = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            words = page.extract_words(extra_attrs=['size'])
            if not words:
                continue

            rows = {}
            for w in words:
                key = round(w['top'] / 3.0)
                rows.setdefault(key, []).append(w)
            rows = [sorted(r, key=lambda w: w['x0']) for _, r in sorted(rows.items())]

            # Song rows use the most common leading font size on the page
            lead_sizes = [round(r[0]['size'], 1) for r in rows]
            body_size = max(set(lead_sizes), key=lead_sizes.count)

            # Margin comes from body rows only; stray footer text (e.g. the
            # TCPDF credit) can sit further left and would skew it.
            body_rows = [r for r in rows if round(r[0]['size'], 1) == body_size]
            left_margin = min(r[0]['x0'] for r in body_rows)

            song_rows = [r for r in body_rows
                         if abs(r[0]['x0'] - left_margin) < 5]
            # Fewer than 3 aligned rows means there's no song table here (e.g.
            # an empty Spares/Encores page) and the "mode" is just a header.
            if len(song_rows) < 3:
                continue

            # Columns to the right of the title are the x-positions, well
            # right of the margin, that appear in most song rows.
            candidates = {}
            for r in song_rows:
                for x in {round(w['x0']) for w in r if w['x0'] > left_margin + 50}:
                    candidates[x] = candidates.get(x, 0) + 1
            common = sorted(x for x, n in candidates.items()
                            if n >= len(song_rows) * 0.5)
            cutoff = common[0] - 5 if common else float('inf')

            # Each right-hand column runs from its own x to the next one.
            bounds = [(common[i] - 5,
                       common[i + 1] - 5 if i + 1 < len(common) else float('inf'))
                      for i in range(len(common))]
            key_col = _pick_key_column(song_rows, bounds)

            for r in song_rows:
                title = ' '.join(w['text'] for w in r if w['x0'] < cutoff).strip()
                key = ''
                if key_col is not None:
                    lo, hi = bounds[key_col]
                    key = ' '.join(w['text'] for w in r
                                   if lo <= w['x0'] < hi).strip()
                if len(title) >= 2:
                    songs.append({'title': normalize_text(title),
                                  'key': normalize_text(key)})
    return songs


def extract_setlist(pdf_path):
    print(f"Reading setlist from: {pdf_path}")
    columnar = _extract_setlist_columns(pdf_path)
    if columnar:
        with_keys = sum(1 for s in columnar if s['key'])
        print(f"   [OK] Extracted {len(columnar)} songs (column layout), "
              f"{with_keys} with keys")
        return columnar

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
                # Line-based extraction can't isolate a key column.
                all_songs.append({'title': normalize_text(cleaned), 'key': ''})
    print(f"   [OK] Extracted {len(all_songs)} songs")
    return all_songs

def _group_chars_by_line(chars, y_tolerance=2.0):
    """Group PDF characters into lines by y-coordinate proximity."""
    if not chars:
        return []
    sorted_chars = sorted(chars, key=lambda c: (c['top'], c['x0']))
    groups = []
    current = [sorted_chars[0]]
    ref_y = sorted_chars[0]['top']
    for c in sorted_chars[1:]:
        if abs(c['top'] - ref_y) < y_tolerance:
            current.append(c)
        else:
            groups.append(current)
            current = [c]
            ref_y = c['top']
    groups.append(current)
    return groups

def _detect_body_char_width(line_groups):
    """Detect monospace character width from adjacent character x-spacing."""
    spacings = []
    for lc in line_groups:
        sc = sorted(lc, key=lambda c: c['x0'])
        for i in range(1, len(sc)):
            dx = sc[i]['x0'] - sc[i-1]['x0']
            if 3 < dx < 10:
                spacings.append(dx)
    if not spacings:
        return 6.17
    spacings.sort()
    return spacings[len(spacings) // 2]

def _reconstruct_spaced_line(line_chars, min_x, char_width):
    """Reconstruct a text line preserving horizontal spacing via column positions."""
    sc = sorted(line_chars, key=lambda c: c['x0'])
    result = []
    for c in sc:
        col = int((c['x0'] - min_x) / char_width + 0.5)
        while len(result) < col:
            result.append(' ')
        result.append(c['text'])
    return ''.join(result).rstrip()

def extract_charts(pdf_path):
    print(f"\nReading charts from: {pdf_path}")
    charts = {}
    with pdfplumber.open(pdf_path) as pdf:
        print(f"   Found {len(pdf.pages)} pages")
        for page_num, page in enumerate(pdf.pages, 1):
            text = page.extract_text()
            if not text:
                continue
            lines = [l for l in text.split('\n') if l.strip() and not re.match(r'^\s*\d+\s*$', l.strip())]
            if len(lines) < 2:
                continue
            title = lines[0]
            notes = lines[1] if len(lines) > 1 else ''

            # Use character-level extraction for body to preserve chord spacing
            chars = page.chars
            if chars and len(lines) > 2:
                all_lines = _group_chars_by_line(chars)
                all_lines = [lg for lg in all_lines
                             if not re.match(r'^\s*\d+\s*$',
                                 ''.join(c['text'] for c in lg).strip())]
                if len(all_lines) > 2:
                    body_groups = all_lines[2:]
                    char_width = _detect_body_char_width(body_groups)
                    min_x = min(c['x0'] for lg in body_groups for c in lg)

                    # Detect normal line spacing for blank line insertion
                    line_ys = [min(c['top'] for c in lg) for lg in body_groups]
                    normal_spacing = None
                    if len(line_ys) >= 2:
                        y_diffs = sorted(line_ys[i+1] - line_ys[i]
                                         for i in range(len(line_ys) - 1))
                        normal_spacing = y_diffs[len(y_diffs) // 2]

                    body_lines = []
                    for i, lg in enumerate(body_groups):
                        if i > 0 and normal_spacing and normal_spacing > 1:
                            gap = line_ys[i] - line_ys[i - 1]
                            blanks = max(0, round(gap / normal_spacing) - 1)
                            body_lines.extend([''] * blanks)
                        body_lines.append(
                            _reconstruct_spaced_line(lg, min_x, char_width))

                    while body_lines and not body_lines[-1]:
                        body_lines.pop()
                    body = '\n'.join(body_lines)
                else:
                    body = ''
            else:
                body = '\n'.join(lines[2:]) if len(lines) > 2 else ''

            charts[page_num] = {
                'title': normalize_text(title),
                'notes': normalize_text(notes),
                'body': normalize_text(body),
                'raw_title': normalize_text(title)
            }
    print(f"   [OK] Extracted {len(charts)} chart pages")
    return charts

def match_songs_to_charts(songs, charts, threshold=70):
    print(f"\nMatching songs to charts (threshold: {threshold}%)")
    matches = {}
    used_pages = set()
    for entry in songs:
        song = entry['title']
        setlist_key = entry.get('key', '')
        best_match = None
        best_score = 0
        best_rank = (0, 0)
        for page_num, chart_data in charts.items():
            if page_num in used_pages:
                continue
            chart_title = chart_data.get('raw_title', '') or chart_data.get('title', '')
            ratio = fuzz.ratio(song.lower(), chart_title.lower())
            partial = fuzz.partial_ratio(song.lower(), chart_title.lower())
            token = fuzz.token_sort_ratio(song.lower(), chart_title.lower())
            # partial_ratio scores any substring at 100 ("Crazy" inside "Crazy
            # Arms"), so discount it and break ties on whole-title similarity.
            score = max(ratio, token, partial * 0.9)
            rank = (score, ratio)
            if rank > best_rank and score >= threshold:
                best_rank = rank
                best_score = int(round(score))
                best_match = page_num
        if best_match:
            chart = charts[best_match]
            chart_key = extract_key(chart.get('notes', ''))
            if setlist_key and chart_key and setlist_key != chart_key:
                print(f"   [WARNING] Key mismatch for '{song}': "
                      f"setlist says {setlist_key}, chart says {chart_key}")
            matches[song] = {'matched': True, 'page': best_match, 'score': best_score, 'title': chart.get('title', ''), 'notes': chart.get('notes', ''), 'body': chart.get('body', ''), 'setlist_key': setlist_key, 'chart_key': chart_key}
            used_pages.add(best_match)
        else:
            matches[song] = {'matched': False, 'page': None, 'score': 0, 'title': '', 'notes': '', 'body': '', 'setlist_key': setlist_key, 'chart_key': ''}
    matched_count = sum(1 for m in matches.values() if m['matched'])
    print(f"\n   [STATS] Matched {matched_count}/{len(songs)} songs ({matched_count/len(songs)*100:.1f}%)")
    return matches

CHORD_RE = re.compile(
    r'^[A-G][b#]?'
    r'(m|min|maj|dim|aug|sus|add)?'
    r'[0-9]?'
    r'(sus[24]|add[0-9]+|maj[0-9]+)?'
    r'(/[A-G][b#]?)?$'
)

def is_chord_line(line):
    """Return True if 80%+ of whitespace-separated tokens are chord symbols or TACET."""
    tokens = line.split()
    if not tokens:
        return False
    chord_count = 0
    for token in tokens:
        clean = token.strip('(),|[]')
        if clean.upper() == 'TACET':
            chord_count += 1
        elif CHORD_RE.match(clean):
            chord_count += 1
    return (chord_count / len(tokens)) >= 0.8

def extract_key(notes):
    """Pull the key out of a chart's 'Key: A Tags: ...' line."""
    if not notes:
        return ''
    match = re.search(r'Key:\s*(.+?)(?:\s+Tags:|$)', notes)
    return match.group(1).strip() if match else ''

def make_tab_title(song, data):
    """Tab label: song name with the key appended, truncated to fit.

    The setlist's own key column wins - it's what the band is playing
    tonight - with the chart's key as a fallback for songs whose setlist
    row had no key.
    """
    key = data.get('setlist_key') or data.get('chart_key') or ''
    label = f"{song} - {key}" if key else song
    return label[:47] + "..." if len(label) > 50 else label

def build_tab_requests(tab_id, title, notes, body_text):
    """Build insert + formatting requests for a single tab in ONE batchUpdate."""
    full_text = title + '\n' + notes + '\n\n' + body_text + '\n'
    requests = []

    # 1) Insert all text at once
    requests.append({
        'insertText': {
            'location': {'tabId': tab_id, 'index': 1},
            'text': full_text,
        }
    })

    # 2) Consolas 12pt on entire text
    text_end = 1 + len(full_text)
    requests.append({
        'updateTextStyle': {
            'range': {'tabId': tab_id, 'startIndex': 1, 'endIndex': text_end},
            'textStyle': {
                'weightedFontFamily': {'fontFamily': 'Consolas'},
                'fontSize': {'magnitude': 12, 'unit': 'PT'},
            },
            'fields': 'weightedFontFamily,fontSize',
        }
    })

    # Pre-calculate line positions (cursor starts at 1)
    cursor = 1

    # 3) Center the title
    title_start = cursor
    cursor += len(title) + 1
    requests.append({
        'updateParagraphStyle': {
            'range': {'tabId': tab_id, 'startIndex': title_start, 'endIndex': cursor},
            'paragraphStyle': {'alignment': 'CENTER'},
            'fields': 'alignment',
        }
    })

    # 4) Center the notes
    notes_start = cursor
    cursor += len(notes) + 1
    requests.append({
        'updateParagraphStyle': {
            'range': {'tabId': tab_id, 'startIndex': notes_start, 'endIndex': cursor},
            'paragraphStyle': {'alignment': 'CENTER'},
            'fields': 'alignment',
        }
    })

    # Skip blank line
    cursor += 1

    # 5) Bold chord lines in body
    for line in body_text.split('\n'):
        line_start = cursor
        cursor += len(line) + 1
        if is_chord_line(line):
            requests.append({
                'updateTextStyle': {
                    'range': {'tabId': tab_id, 'startIndex': line_start, 'endIndex': cursor},
                    'textStyle': {'bold': True},
                    'fields': 'bold',
                }
            })

    return requests

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
        requests = [{'addDocumentTab': {'tabProperties': {'title': make_tab_title(song, data)}}} for song, data in batch]
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
    
    # Add content + formatting to each tab (single batchUpdate per tab)
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

        try:
            reqs = build_tab_requests(
                tab_id,
                data.get('title', ''),
                data.get('notes', ''),
                data.get('body', ''),
            )
            execute_with_retry(service, doc_id, {'requests': reqs})
            print(f"[GOOGLE DOCS] Formatted: {song}")
        except Exception as e:
            print(f"[ERROR] Failed: {e}")
    
    print(f"[GOOGLE DOCS] Document creation complete")
    print(f"[GOOGLE DOCS] Document URL: {doc_url}")
    return {'id': doc_id, 'url': doc_url, 'title': doc_title}

def main():
    SETLIST_PDF = "Lapin Bleu Aug 19th 2026.pdf"
    CHARTS_PDF = "Lapin Bleu Jan 28th charts.pdf"
    DOC_TITLE = "Lapin Bleu Aug 19th 2026 Setlist"
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
        doc_info = create_google_doc(matches, title=DOC_TITLE)
        
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
