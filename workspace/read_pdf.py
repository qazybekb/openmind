#!/usr/bin/env python3
"""Download and extract text from a PDF URL. Usage: python3 read_pdf.py <url>"""
import sys, urllib.request, fitz

if len(sys.argv) < 2:
    print("Usage: python3 read_pdf.py <url>")
    sys.exit(1)

url = sys.argv[1]
urllib.request.urlretrieve(url, "/tmp/reading.pdf")
doc = fitz.open("/tmp/reading.pdf")

for i, page in enumerate(doc):
    text = page.get_text().strip()
    if text:
        print(f"--- Page {i+1} ---")
        print(text)
