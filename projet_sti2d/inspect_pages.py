import os, re, pdfplumber

# Pages 49-50 numerotation logicielle (0-indexed: 48, 49)
TARGET = [48, 49]

path = os.environ.get("PDF_PATH", "")
if not path:
    print("PDF_PATH non defini"); raise SystemExit(1)

with pdfplumber.open(path) as pdf:
    total = len(pdf.pages)
    print(f"Total pages: {total}")
    for pno in TARGET:
        if pno >= total:
            print(f"Page {pno+1} hors limites"); continue
        p = pdf.pages[pno]
        txt = p.extract_text() or ""
        print(f"\n=== PAGE {pno+1} ===")
        print(txt[:600])
        # Essai avec differentes strategies pour bien capturer la grille
        for strategy in [
            {"vertical_strategy":"lines","horizontal_strategy":"lines"},
            {"vertical_strategy":"text","horizontal_strategy":"text"},
        ]:
            tables = p.extract_tables(strategy) or []
            if tables:
                print(f"  -> {len(tables)} table(s) [strat={strategy['vertical_strategy']}]")
                for ti, t in enumerate(tables):
                    cols = max((len(r) for r in t if r), default=0)
                    print(f"  -- Table {ti}: {len(t)} rows x {cols} cols --")
                    for row in t:
                        print("   ", [str(c or "")[:25] for c in row])
                break
