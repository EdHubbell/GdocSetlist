"""
Google Docs Creator Module - Line-by-Line Version
=================================================
Creates Google Docs with setlist data.
Inserts and formats content line by line to ensure accuracy.
"""

from google_auth import get_docs_service
from datetime import datetime
import time
from googleapiclient.errors import HttpError


def execute_with_retry(service, documentId, body, max_retries=5):
    """Execute batchUpdate with exponential backoff."""
    for attempt in range(max_retries):
        try:
            return service.documents().batchUpdate(
                documentId=documentId,
                body=body
            ).execute()
        except HttpError as e:
            if e.resp.status == 429:
                wait_time = min(60, (2 ** attempt) * 2)
                print(f"[RATE LIMIT] Waiting {wait_time}s...")
                time.sleep(wait_time)
                if attempt == max_retries - 1:
                    raise
            else:
                raise


def get_end_index(service, doc_id):
    """Get the end index of the document."""
    doc = service.documents().get(documentId=doc_id).execute()
    body = doc.get('body', {})
    content = body.get('content', [])
    if content:
        return content[-1].get('endIndex', 1)
    return 1


def create_setlist_document(matches, title="Yonder 7th Feb Setlist"):
    """Create a Google Doc with the setlist and matched charts."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    doc_title = f"{title}_{timestamp}"
    
    print(f"\n[GOOGLE DOCS] Creating document: {doc_title}")
    
    service = get_docs_service()
    
    # Create document
    document = {'title': doc_title}
    doc = service.documents().create(body=document).execute()
    doc_id = doc.get('documentId')
    doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
    
    print(f"[GOOGLE DOCS] Document created: {doc_id}")
    time.sleep(3.0)
    
    # Create tabs
    print(f"[GOOGLE DOCS] Creating {len(matches)} tabs...")
    song_list = list(matches.items())
    
    for i in range(0, len(song_list), 2):
        batch = song_list[i:i + 2]
        requests = []
        for song, data in batch:
            tab_title = song[:47] + "..." if len(song) > 50 else song
            requests.append({
                'addDocumentTab': {'tabProperties': {'title': tab_title}}
            })
        
        if requests:
            try:
                execute_with_retry(service, doc_id, {'requests': requests})
                print(f"[GOOGLE DOCS] Created tabs {i+1}-{min(i+2, len(song_list))}")
            except Exception as e:
                print(f"[ERROR] Failed to create tabs: {e}")
        time.sleep(3.0)
    
    # Delete default Tab 1
    print("[GOOGLE DOCS] Removing default Tab 1...")
    try:
        doc = service.documents().get(documentId=doc_id, includeTabsContent=True).execute()
        tabs = doc.get('tabs', [])
        if len(tabs) > 1:
            first_tab_id = tabs[0].get('tabProperties', {}).get('tabId')
            execute_with_retry(service, doc_id, {
                'requests': [{'deleteTab': {'tabId': first_tab_id}}]
            })
            print("[GOOGLE DOCS] Default Tab 1 removed")
    except Exception as e:
        print(f"[WARNING] Could not remove Tab 1: {e}")
    time.sleep(3.0)
    
    # Process each tab - insert and format line by line
    print(f"[GOOGLE DOCS] Adding content to tabs (line by line)...")
    doc = service.documents().get(documentId=doc_id, includeTabsContent=True).execute()
    tabs = doc.get('tabs', [])
    
    for idx, (song, data) in enumerate(song_list):
        if idx >= len(tabs):
            break
            
        tab_id = tabs[idx].get('tabProperties', {}).get('tabId')
        
        if not data['matched']:
            # Insert placeholder
            try:
                execute_with_retry(service, doc_id, {
                    'requests': [{
                        'insertText': {
                            'location': {'index': 1},
                            'text': "[No chart found for this song]"
                        }
                    }]
                })
                # Format placeholder
                execute_with_retry(service, doc_id, {
                    'requests': [
                        {
                            'updateTextStyle': {
                                'range': {'startIndex': 1, 'endIndex': 30},
                                'textStyle': {
                                    'weightedFontFamily': {'fontFamily': 'Consolas'},
                                    'fontSize': {'magnitude': 12, 'unit': 'PT'}
                                },
                                'fields': 'weightedFontFamily,fontSize'
                            }
                        }
                    ]
                })
                print(f"[GOOGLE DOCS] Added placeholder: {song}")
            except Exception as e:
                print(f"[ERROR] Failed: {e}")
            time.sleep(3.0)
            continue
        
        # Build lines to insert
        lines_to_insert = []
        
        # Title
        if data.get('title'):
            lines_to_insert.append({
                'text': data['title'] + '\n',
                'type': 'title'
            })
        
        # Notes
        if data.get('notes'):
            lines_to_insert.append({
                'text': data['notes'] + '\n',
                'type': 'notes'
            })
        
        # Blank line after header
        if data.get('title') or data.get('notes'):
            lines_to_insert.append({
                'text': '\n',
                'type': 'blank'
            })
        
        # Body content
        for segment in data.get('body', []):
            lines_to_insert.append({
                'text': segment['text'] + '\n',
                'type': segment.get('type', 'lyrics')
            })
        
        # Insert and format each line
        for line_info in lines_to_insert:
            text = line_info['text']
            line_type = line_info['type']
            
            # Get current end index
            end_idx = get_end_index(service, doc_id)
            insert_pos = max(1, end_idx - 1)
            
            # Insert text
            try:
                execute_with_retry(service, doc_id, {
                    'requests': [{
                        'insertText': {
                            'location': {'index': insert_pos},
                            'text': text
                        }
                    }]
                })
            except Exception as e:
                print(f"[ERROR] Failed to insert text: {e}")
                continue
            
            # Get new end index and calculate range
            new_end_idx = get_end_index(service, doc_id)
            start_idx = insert_pos
            end_range = new_end_idx - 1  # Exclude the section break
            
            # Build formatting requests
            format_requests = []
            
            # All text gets Consolas
            format_requests.append({
                'updateTextStyle': {
                    'range': {'startIndex': start_idx, 'endIndex': end_range},
                    'textStyle': {
                        'weightedFontFamily': {'fontFamily': 'Consolas'},
                        'fontSize': {'magnitude': 12, 'unit': 'PT'}
                    },
                    'fields': 'weightedFontFamily,fontSize'
                }
            })
            
            # Title and notes get centered
            if line_type in ('title', 'notes'):
                format_requests.append({
                    'updateParagraphStyle': {
                        'range': {'startIndex': start_idx, 'endIndex': end_range},
                        'paragraphStyle': {'alignment': 'CENTER'},
                        'fields': 'alignment'
                    }
                })
            
            # Chords get bold
            if line_type == 'chords':
                format_requests.append({
                    'updateTextStyle': {
                        'range': {'startIndex': start_idx, 'endIndex': end_range},
                        'textStyle': {'bold': True},
                        'fields': 'bold'
                    }
                })
            
            # Apply formatting
            for req in format_requests:
                try:
                    execute_with_retry(service, doc_id, {'requests': [req]})
                except Exception as e:
                    print(f"[WARNING] Formatting error: {e}")
                time.sleep(0.5)
            
            time.sleep(1.0)
        
        print(f"[GOOGLE DOCS] Completed tab: {song}")
        time.sleep(2.0)
    
    print(f"[GOOGLE DOCS] Document creation complete")
    print(f"[GOOGLE DOCS] Document URL: {doc_url}")
    
    return {'id': doc_id, 'url': doc_url, 'title': doc_title}
