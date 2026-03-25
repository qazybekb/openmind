#!/usr/bin/env python3
"""Download and extract text from a PDF URL. Usage: python3 read_pdf.py <url>"""
import sys, tempfile, urllib.request, fitz

if len(sys.argv) < 2:
    print("Usage: python3 read_pdf.py <url>")
    sys.exit(1)

url = sys.argv[1]

with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
    urllib.request.urlretrieve(url, tmp.name)
    doc = fitz.open(tmp.name)
    for i, page in enumerate(doc):
        text = page.get_text().strip()
        if text:
            print(f"--- Page {i+1} ---")
            print(text)
    doc.close()
