from io import BytesIO

import pymupdf
from docx import Document


class DocumentError(ValueError):
    pass


def extract_text(filename: str, content: bytes) -> str:
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    try:
        if ext == "pdf":
            doc = pymupdf.open(stream=content, filetype="pdf")
            pages = []
            for page in doc:
                page_text = page.get_text()
                words = page.get_text("words")
                for link in page.get_links():
                    uri = link.get("uri")
                    if not uri:
                        continue
                    rect = link.get("from")
                    hits = [word for word in words if pymupdf.Rect(word[:4]).intersects(rect)]
                    if hits:
                        block, line = hits[0][5:7]
                        label = " ".join(word[4] for word in sorted((w for w in words if w[5] == block and w[6] == line), key=lambda w: w[7]))
                        position = page_text.find(label)
                        while position >= 0 and page_text[position + len(label):].startswith(" [[URL:"):
                            position = page_text.find(label, position + len(label))
                        if position >= 0:
                            page_text = page_text[:position] + f"{label} [[URL:{uri}]]" + page_text[position + len(label):]
                        else:
                            page_text += f"\n[[URL:{uri}]]"
                    else:
                        page_text += f"\n[[URL:{uri}]]"
                pages.append(page_text)
            text = "\n".join(pages)
        elif ext == "docx":
            doc = Document(BytesIO(content))
            text = "\n".join(p.text for p in doc.paragraphs) + "\n" + "\n".join(
                " | ".join(cell.text for cell in row.cells) for table in doc.tables for row in table.rows
            )
        else:
            raise DocumentError("Only PDF and DOCX files are supported")
    except DocumentError:
        raise
    except Exception as exc:
        raise DocumentError("Could not read document; ensure it is a valid PDF or DOCX") from exc
    text = text.strip()
    if len(text) < 30:
        raise DocumentError("No readable text found. Scanned PDFs need OCR before upload")
    return text
