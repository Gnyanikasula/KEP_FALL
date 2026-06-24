import re
import json
import os
import pdfplumber


GDPR_PATH   = r"GDPR.pdf"
EUAI_PATH   = r"EU_AI_ACT.pdf"
OUTPUT_PATH = r"regulatory_chunks.json"

# GDPR - 14 articles
# Art 5-9: principles, lawfulness, consent, special categories
# Art 13-18: transparency and data subject rights
# Art 22: automated decision-making
# Art 25: privacy by design
# Art 32: security of processing
# Art 35: DPIA
GDPR_IN_SCOPE = {5, 6, 7, 9, 13, 14, 15, 16, 17, 18, 22, 25, 32, 35}


EUAI_IN_SCOPE_ARTICLES = {
    5,
    6, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 26, 29,
    50,
    51, 52, 53,
}
EUAI_IN_SCOPE_ANNEXES = {"III", "IV"}

ARTICLE_RE = re.compile(r"^Article\s+(\d+)\s*\n([^\n]+)", re.MULTILINE)
ANNEX_RE   = re.compile(r"^(?:ANNEX|Annex)\s+([IVXLCDM]+)\b", re.MULTILINE)


def extract_text(path):
    pages = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                pages.append(t)
    return "\n".join(pages)


def clean(text):
    text = re.sub(r"\r", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"L \d+/\d+\s+EN\s+Official Journal[^\n]*", "", text)
    text = re.sub(r"ELI:\s*http\S+", "", text)
    text = re.sub(r"\d+/\d+\s+ELI[^\n]*", "", text)
    text = re.sub(r"4\.5\.2016\s+EN\s+Official Journal[^\n]*", "", text)
    text = re.sub(r"OJ L,\s*\d+\.\d+\.\d+[^\n]*", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def word_count(text):
    return len(text.split())


def extract_refs(text):
    refs, seen = [], set()
    for pat in [r"Article\s+(\d+)", r"Art\.\s*(\d+)",
                r"Annex\s+([IVXLCDM]+)", r"paragraph\s+(\d+)"]:
        for m in re.findall(pat, text, re.IGNORECASE):
            if m not in seen:
                seen.add(m)
                refs.append(m.strip())
    return refs


def split_paragraphs(body):
    parts = re.split(r"(?m)^(\d+)\.\s+", body)
    if len(parts) < 3:
        return [("1", body.strip())] if body.strip() else []
    result = []
    for i in range(1, len(parts) - 1, 2):
        num, text = parts[i].strip(), parts[i + 1].strip()
        if text:
            result.append((num, text))
    return result


# returns {"lead": str, "points": [(letter, text), ...]} or None
def split_lettered_points(text):
    POINT_RE = re.compile(r"(?:(?:^|\n)\s*)\(([a-z]{1,2})\)\s+", re.MULTILINE)
    parts = POINT_RE.split(text)
    if len(parts) < 3:
        return None
    lead = parts[0].strip()
    points = [(parts[i], parts[i + 1].strip())
              for i in range(1, len(parts) - 1, 2) if parts[i + 1].strip()]
    return {"lead": lead, "points": points} if points else None


# emits one chunk per lettered sub-point, or one chunk if no sub-points
def make_chunks(regulation, article, title, para_num, para_text, id_prefix, ctx_prefix):
    split = split_lettered_points(para_text)
    if split is None:
        return [{
            "chunk_id":       id_prefix,
            "regulation":     regulation,
            "article":        article,
            "article_title":  title,
            "paragraph":      para_num,
            "sub_point":      "",
            "context_header": ctx_prefix,
            "text":           para_text,
            "references":     extract_refs(para_text),
            "word_count":     word_count(para_text),
        }]
    chunks = []
    for letter, pt in split["points"]:
        full = f"{split['lead']} ({letter}) {pt}" if split["lead"] else f"({letter}) {pt}"
        chunks.append({
            "chunk_id":       f"{id_prefix}_{letter}",
            "regulation":     regulation,
            "article":        article,
            "article_title":  title,
            "paragraph":      para_num,
            "sub_point":      letter,
            "context_header": f"{ctx_prefix}({letter})",
            "text":           full,
            "references":     extract_refs(full),
            "word_count":     word_count(full),
        })
    return chunks


def parse_gdpr():
    print(f"[GDPR] {GDPR_PATH}")
    text    = clean(extract_text(GDPR_PATH))
    chunks  = []
    matches = list(ARTICLE_RE.finditer(text))
    if not matches:
        print("  [WARNING] no article headers found")
        return chunks

    for idx, m in enumerate(matches):
        num = int(m.group(1))
        if num not in GDPR_IN_SCOPE:
            continue
        title    = m.group(2).strip()
        body_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body     = text[m.end():body_end].strip()
        for pn, pt in split_paragraphs(body) or [("1", body)]:
            if not pt.strip():
                continue
            new = make_chunks("GDPR", str(num), title, pn, pt,
                              f"GDPR_Art{num}_Para{pn}",
                              f"GDPR, Article {num}({pn}) — {title}")
            for c in new:
                print(f"  {c['chunk_id']}  ({c['word_count']} words)")
            chunks.extend(new)
    return chunks


def parse_euai():
    print(f"[EU AI Act] {EUAI_PATH}")
    text  = clean(extract_text(EUAI_PATH))
    chunks = []

    art_matches   = list(ARTICLE_RE.finditer(text))
    annex_matches = list(ANNEX_RE.finditer(text))
    if not art_matches:
        print("  [WARNING] no article headers found")
        return chunks

    boundaries = (
        [(m.start(), "article", m) for m in art_matches] +
        [(m.start(), "annex",   m) for m in annex_matches]
    )
    boundaries.sort(key=lambda x: x[0])

    for i, (pos, stype, m) in enumerate(boundaries):
        next_pos = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(text)

        if stype == "article":
            num = int(m.group(1))
            if num not in EUAI_IN_SCOPE_ARTICLES:
                continue
            title = m.group(2).strip()
            body  = text[m.end():next_pos].strip()
            for pn, pt in split_paragraphs(body) or [("1", body)]:
                if not pt.strip():
                    continue
                new = make_chunks("EU AI Act", str(num), title, pn, pt,
                                  f"EUAI_Art{num}_Para{pn}",
                                  f"EU AI Act, Article {num}({pn}) — {title}")
                for c in new:
                    print(f"  {c['chunk_id']}  ({c['word_count']} words)")
                chunks.extend(new)

        elif stype == "annex":
            label = m.group(1).strip().upper()
            if label not in EUAI_IN_SCOPE_ANNEXES:
                continue
            body  = text[m.end():next_pos].strip()
            parts = re.split(r"(?m)^(\d+)\.\s+", body)
            if len(parts) < 3:
                if body.strip():
                    cid = f"EUAI_Annex{label}_Point1"
                    chunks.append({
                        "chunk_id":       cid,
                        "regulation":     "EU AI Act",
                        "article":        f"Annex {label}",
                        "article_title":  f"Annex {label}",
                        "paragraph":      "1",
                        "sub_point":      "",
                        "context_header": f"EU AI Act, Annex {label}",
                        "text":           body.strip(),
                        "references":     extract_refs(body),
                        "word_count":     word_count(body),
                    })
                    print(f"  {cid}  ({word_count(body)} words)")
            else:
                for j in range(1, len(parts) - 1, 2):
                    pn, pt = parts[j].strip(), parts[j + 1].strip()
                    if not pt:
                        continue
                    new = make_chunks("EU AI Act", f"Annex {label}", f"Annex {label}",
                                      pn, pt,
                                      f"EUAI_Annex{label}_Point{pn}",
                                      f"EU AI Act, Annex {label}, Point {pn}")
                    for c in new:
                        print(f"  {c['chunk_id']}  ({c['word_count']} words)")
                    chunks.extend(new)

    return chunks


def main():
    all_chunks = []

    if os.path.exists(GDPR_PATH):
        all_chunks.extend(parse_gdpr())
    else:
        print(f"[ERROR] not found: {GDPR_PATH}")

    if os.path.exists(EUAI_PATH):
        all_chunks.extend(parse_euai())
    else:
        print(f"[ERROR] not found: {EUAI_PATH}")

    if not all_chunks:
        print("[ERROR] no chunks extracted")
        return

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, indent=2, ensure_ascii=False)

    gdpr_n  = sum(1 for c in all_chunks if c["regulation"] == "GDPR")
    euai_n  = sum(1 for c in all_chunks if c["regulation"] == "EU AI Act")
    point_n = sum(1 for c in all_chunks if c.get("sub_point"))
    print(f"\n{len(all_chunks)} total  (GDPR: {gdpr_n}, EU AI Act: {euai_n}, "
          f"point-level: {point_n})")
    print(f"output: {OUTPUT_PATH}")

    found_gdpr = {int(c["article"]) for c in all_chunks
                  if c["regulation"] == "GDPR" and c["article"].isdigit()}
    found_euai = {int(c["article"]) for c in all_chunks
                  if c["regulation"] == "EU AI Act" and c["article"].isdigit()}
    for missing, label in [(GDPR_IN_SCOPE - found_gdpr, "GDPR"),
                           (EUAI_IN_SCOPE_ARTICLES - found_euai, "EU AI Act")]:
        if missing:
            print(f"[WARNING] no chunks for {label} articles: {sorted(missing)}")


if __name__ == "__main__":
    main()