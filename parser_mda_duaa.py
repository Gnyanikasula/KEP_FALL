import re
import json
import os
import pdfplumber


UK_MDR_PATH = r"consolidated_UKMDR.pdf"
EU_MDR_PATH = r"consolidated_EUMDR.pdf"
DUAA_PATH   = r"DUAA.pdf"
OUTPUT_PATH = r"regulatory_chunks.json"

APPEND_TO_EXISTING = True

UK_MDR_IN_SCOPE_REGS     = {2, 5, 7, 8, 9}
EU_MDR_IN_SCOPE_ARTICLES = {2, 10, 61, 83, 87}


def extract_text(path):
    pages = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                pages.append(t)
    return "\n".join(pages)


def clean_uk(text):
    text = re.sub(r"\r", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\[F\d+", "", text)  # strip [F123 tag marker, keep content
    text = re.sub(r"\]", "", text)
    text = re.sub(r"Document Generated:\s*\d{4}-\d{2}-\d{2}", "", text)
    text = re.sub(r"Changes to legislation:[^\n]*", "", text)
    text = re.sub(r"View outstanding changes", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_eu(text):
    text = re.sub(r"\r", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def word_count(text):
    return len(text.split())


def extract_refs(text):
    refs, seen = [], set()
    for pat in [r"[Rr]egulation\s+(\d+)", r"[Aa]rticle\s+(\d+)",
                r"[Ss]ection\s+(\d+)", r"[Pp]aragraph\s+(\d+)"]:
        for m in re.findall(pat, text):
            if m not in seen:
                seen.add(m)
                refs.append(m.strip())
    return refs


# splits "(a) text (b) text ..." — returns None if no points or if duplicate
# letters appear (which means they're list items, not parallel normative alternatives)
def split_lettered_points(text):
    POINT_RE = re.compile(r"(?:(?:^|\n)\s*)\(([a-z]{1,2})\)\s+", re.MULTILINE)
    parts = POINT_RE.split(text)
    if len(parts) < 3:
        return None
    lead = parts[0].strip()
    letters = [parts[i] for i in range(1, len(parts) - 1, 2)]
    texts   = [parts[i].strip() for i in range(2, len(parts), 2)]
    # duplicate letters indicate repeated list items, not parallel sub-points
    if len(set(letters)) < len(letters):
        return None
    points = [(l, t) for l, t in zip(letters, texts) if t]
    return {"lead": lead, "points": points} if points else None


# emits one chunk per lettered sub-point, or one paragraph chunk if no clean split
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


# splits a UK MDR regulation body on (1), (2), (3)... paragraph markers
# note: "X.—(1) text" format means (1) is NOT at line start, so the content
# of paragraph (1) ends up in parts[0] — we must include it as Para1
def split_uk_paragraphs(body):
    PARA_RE = re.compile(r"(?m)^\((\d+)\)\s+")
    parts = PARA_RE.split(body)
    if len(parts) < 3:
        return [("1", body.strip())] if body.strip() else []
    result = []
    lead = parts[0].strip()
    if lead and len(lead.split()) > 5:
        result.append(("1", lead))
    for i in range(1, len(parts) - 1, 2):
        pn, pt = parts[i].strip(), parts[i + 1].strip()
        if pt:
            result.append((pn, pt))
    return result


def parse_uk_mdr(text):
    print("[UK MDR 2002]")
    chunks = []

    REG_RE  = re.compile(r"(?m)^(\d+)\.—\((\d+)\)\s+")
    matches = list(REG_RE.finditer(text))
    if not matches:
        print("  [WARNING] no regulation headers found")
        return chunks

    seen_regs = set()
    for idx, m in enumerate(matches):
        reg_num = int(m.group(1))
        if reg_num not in UK_MDR_IN_SCOPE_REGS or reg_num in seen_regs:
            continue
        seen_regs.add(reg_num)

        # bound by the NEXT occurrence of the same regulation number (E+W+S only, not N.I.)
        # if no duplicate exists, fall back to the next different regulation number
        same_reg_next = next(
            (j for j in range(idx + 1, len(matches)) if matches[j].group(1) == str(reg_num)),
            None
        )
        diff_reg_next = next(
            (j for j in range(idx + 1, len(matches)) if int(matches[j].group(1)) != reg_num),
            None
        )
        end_pos = (matches[same_reg_next].start() if same_reg_next is not None
                   else (matches[diff_reg_next].start() if diff_reg_next is not None
                         else len(text)))
        body = text[m.start():end_pos].strip()

        before       = text[max(0, m.start() - 300):m.start()]
        title_search = re.findall(r"\n([A-Z][^\n]{5,60})\s*$", before)
        title        = title_search[-1].strip() if title_search else f"Regulation {reg_num}"

        # UK MDR uses (1)(2)(3) numbered paragraphs — split there, not at (a)(b)(c)
        # lettered sub-points inside UK MDR definitions are list items, not parallel norms
        for pn, pt in split_uk_paragraphs(body) or [("1", body)]:
            cid = f"UKMDR_Reg{reg_num}_Para{pn}"
            ctx = f"UK MDR 2002, Regulation {reg_num}({pn}) — {title}"
            c = {
                "chunk_id":       cid,
                "regulation":     "UK MDR 2002",
                "article":        str(reg_num),
                "article_title":  title,
                "paragraph":      pn,
                "sub_point":      "",
                "context_header": ctx,
                "text":           pt,
                "references":     extract_refs(pt),
                "word_count":     word_count(pt),
            }
            chunks.append(c)
            print(f"  {cid}  ({c['word_count']} words)")

    # Part 4A — regulations 44ZC through 44ZP
    m4a = re.search(r"PART 4A", text)
    if m4a:
        part4a    = text[m4a.start():]
        next_part = re.search(r"(?m)^PART \d", part4a[100:])
        if next_part:
            part4a = part4a[:100 + next_part.start()]

        PROV_RE = re.compile(r"(?m)^(44Z[A-P])\.(?:—\((\d+)\))?\s*")
        provs   = list(PROV_RE.finditer(part4a))

        # deduplicate provisions — consolidated PDF may have E+W+S and N.I. copies
        seen_provs = set()
        for i, pm in enumerate(provs):
            reg_id = pm.group(1)
            if reg_id in seen_provs:
                continue
            seen_provs.add(reg_id)

            # bound by next DIFFERENT provision ID
            next_diff_prov = next(
                (j for j in range(i + 1, len(provs)) if provs[j].group(1) != reg_id),
                None
            )
            end = provs[next_diff_prov].start() if next_diff_prov is not None else len(part4a)
            body = part4a[pm.start():end].strip()
            if not body:
                continue

            for pn, pt in split_uk_paragraphs(body) or [("1", body)]:
                cid = f"UKMDR_{reg_id}_Para{pn}"
                ctx = f"UK MDR 2002, Regulation {reg_id}({pn}) — Post-market surveillance"
                c = {
                    "chunk_id":       cid,
                    "regulation":     "UK MDR 2002",
                    "article":        "Part4A",
                    "article_title":  "Post-market surveillance requirements",
                    "paragraph":      pn,
                    "sub_point":      "",
                    "context_header": ctx,
                    "text":           pt,
                    "references":     extract_refs(pt),
                    "word_count":     word_count(pt),
                }
                chunks.append(c)
                print(f"  {cid}  ({c['word_count']} words)")
    else:
        print("  [WARNING] Part 4A not found")

    print(f"  UK MDR: {len(chunks)} chunks")
    return chunks


def parse_eu_mdr(text):
    print("[EU MDR 2017/745]")
    chunks = []

    ARTICLE_RE = re.compile(r"(?m)^Article\s+(\d+)\s*\n([^\n]+)")
    ANNEX_RE   = re.compile(r"(?m)^ANNEX\s+([IVXLCDM]+)\b")

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
            if num not in EU_MDR_IN_SCOPE_ARTICLES:
                continue
            title = m.group(2).strip()
            body  = text[m.end():next_pos].strip()

            PARA_RE    = re.compile(r"(?m)^(\d+)\.\s+")
            para_parts = PARA_RE.split(body)
            if len(para_parts) < 3:
                new = make_chunks("EU MDR 2017/745", str(num), title, "1", body,
                                  f"EUMDR_Art{num}_Para1",
                                  f"EU MDR 2017/745, Article {num} — {title}")
                for c in new:
                    print(f"  {c['chunk_id']}  ({c['word_count']} words)")
                chunks.extend(new)
            else:
                for j in range(1, len(para_parts) - 1, 2):
                    pn, pt = para_parts[j], para_parts[j + 1].strip()
                    if not pt:
                        continue
                    new = make_chunks("EU MDR 2017/745", str(num), title, pn, pt,
                                      f"EUMDR_Art{num}_Para{pn}",
                                      f"EU MDR 2017/745, Article {num}({pn}) — {title}")
                    for c in new:
                        print(f"  {c['chunk_id']}  ({c['word_count']} words)")
                    chunks.extend(new)

        elif stype == "annex":
            label = m.group(1).strip().upper()
            body  = text[m.end():next_pos]

            if label == "I":
                sec17 = re.search(r"(?m)^17\.\s+Electronic programmable systems", body)
                sec18 = re.search(r"(?m)^18\.\s+", body)
                if sec17:
                    end      = sec18.start() if sec18 else sec17.start() + 3000
                    s17_text = body[sec17.start():end].strip()
                    SUBSEC   = re.compile(r"(?m)^17\.(\d+)\.\s+")
                    subs     = list(SUBSEC.finditer(s17_text))
                    if not subs:
                        chunks.append({
                            "chunk_id": "EUMDR_AnnexI_S17",
                            "regulation": "EU MDR 2017/745",
                            "article": "Annex I",
                            "article_title": "General safety and performance requirements",
                            "paragraph": "17", "sub_point": "",
                            "context_header": "EU MDR 2017/745, Annex I §17 — Electronic programmable systems / software",
                            "text": s17_text, "references": extract_refs(s17_text),
                            "word_count": word_count(s17_text),
                        })
                        print(f"  EUMDR_AnnexI_S17  ({word_count(s17_text)} words)")
                    else:
                        for k, sm in enumerate(subs):
                            sub_n    = sm.group(1)
                            sub_end  = subs[k + 1].start() if k + 1 < len(subs) else len(s17_text)
                            sub_text = s17_text[sm.start():sub_end].strip()
                            cid = f"EUMDR_AnnexI_S17_{sub_n}"
                            chunks.append({
                                "chunk_id": cid, "regulation": "EU MDR 2017/745",
                                "article": "Annex I",
                                "article_title": "General safety and performance requirements",
                                "paragraph": f"17.{sub_n}", "sub_point": "",
                                "context_header": f"EU MDR 2017/745, Annex I §17.{sub_n} — Software requirements",
                                "text": sub_text, "references": extract_refs(sub_text),
                                "word_count": word_count(sub_text),
                            })
                            print(f"  {cid}  ({word_count(sub_text)} words)")

            elif label == "VIII":
                r11 = re.search(r"Rule\s+11\b", body)
                r12 = re.search(r"Rule\s+12\b", body)
                if r11:
                    end      = r12.start() if r12 else r11.start() + 2000
                    r11_text = body[r11.start():end].strip()
                    chunks.append({
                        "chunk_id": "EUMDR_AnnexVIII_Rule11",
                        "regulation": "EU MDR 2017/745",
                        "article": "Annex VIII", "article_title": "Classification rules",
                        "paragraph": "Rule 11", "sub_point": "",
                        "context_header": "EU MDR 2017/745, Annex VIII Rule 11 — Software classification",
                        "text": r11_text, "references": extract_refs(r11_text),
                        "word_count": word_count(r11_text),
                    })
                    print(f"  EUMDR_AnnexVIII_Rule11  ({word_count(r11_text)} words)")

    print(f"  EU MDR: {len(chunks)} chunks")
    return chunks


def parse_duaa(text):
    print("[DUAA 2025]")
    chunks = []

    # DUAA PDF has a table of contents — skip it and find the real substantive text
    # identified by "(1) For Article 22" in the 200 chars after the heading
    all_m80 = list(re.compile(r"(?m)^80\s+Automated decision-making").finditer(text))
    real_m80 = next(
        (m for m in all_m80 if re.search(r"For Article 22", text[m.end():m.end() + 200])),
        None
    )
    if real_m80 is None:
        print("  [WARNING] Section 80 substantive text not found")
        return chunks

    after_m80 = text[real_m80.end():]
    next_sec  = re.search(r"(?m)^81\s+", after_m80)
    body_end  = real_m80.end() + next_sec.start() if next_sec else real_m80.start() + 10000
    body      = text[real_m80.start():body_end]

    ART_RE      = re.compile(r"Article\s+(22[A-D])\s*\n([^\n]+)\n", re.IGNORECASE)
    art_matches = list(ART_RE.finditer(body))

    if not art_matches:
        chunks.append({
            "chunk_id": "DUAA_S80", "regulation": "DUAA 2025",
            "article": "80", "article_title": "Automated decision-making",
            "paragraph": "1", "sub_point": "",
            "context_header": "DUAA 2025, Section 80 — Automated decision-making",
            "text": body.strip(), "references": extract_refs(body),
            "word_count": word_count(body),
        })
        print(f"  DUAA_S80  ({word_count(body)} words)  [fallback]")
        return chunks

    seen_ids = set()
    for idx, am in enumerate(art_matches):
        art_label = am.group(1).upper()
        art_title = am.group(2).strip()
        art_end   = art_matches[idx + 1].start() if idx + 1 < len(art_matches) else len(body)
        art_body  = body[am.end():art_end].strip()

        PARA_RE    = re.compile(r"(?m)^(\d+)\.\s+")
        para_parts = PARA_RE.split(art_body)
        if len(para_parts) < 3:
            if art_body:
                new = make_chunks("DUAA 2025", f"S80-{art_label}", art_title, "1", art_body,
                                  f"DUAA_S80_Art{art_label}_1",
                                  f"DUAA 2025, Section 80, Article {art_label}(1) — {art_title}")
                for c in new:
                    if c["chunk_id"] not in seen_ids:
                        seen_ids.add(c["chunk_id"])
                        chunks.append(c)
                        print(f"  {c['chunk_id']}  ({c['word_count']} words)")
        else:
            for i in range(1, len(para_parts) - 1, 2):
                pn, pt = para_parts[i], para_parts[i + 1].strip()
                if not pt:
                    continue
                new = make_chunks("DUAA 2025", f"S80-{art_label}", art_title, pn, pt,
                                  f"DUAA_S80_Art{art_label}_{pn}",
                                  f"DUAA 2025, Section 80, Article {art_label}({pn}) — {art_title}")
                for c in new:
                    if c["chunk_id"] not in seen_ids:
                        seen_ids.add(c["chunk_id"])
                        chunks.append(c)
                        print(f"  {c['chunk_id']}  ({c['word_count']} words)")

    # Schedule 6 — the real heading is "SCHEDULE 6 Section 80" (uppercase)
    # multiple lowercase "Schedule 6" references exist in the PDF — skip them
    real_sch6 = re.search(r"SCHEDULE\s+6\s+Section 80", text)
    if real_sch6:
        sch6_body = text[real_sch6.start():]
        next_sched = re.search(r"(?m)^SCHEDULE\s+\d", sch6_body[100:])
        sch6_text  = sch6_body[:100 + next_sched.start()].strip() if next_sched else sch6_body[:4000].strip()
        chunks.append({
            "chunk_id": "DUAA_Sch6",
            "regulation": "DUAA 2025",
            "article": "Schedule 6",
            "article_title": "Automated decision-making: minor and consequential amendments",
            "paragraph": "1", "sub_point": "",
            "context_header": ("DUAA 2025, Schedule 6 — Automated decision-making: "
                               "amendments to GDPR Art 13(2)(f) and Art 14(2)(g) transparency obligations"),
            "text": sch6_text, "references": extract_refs(sch6_text),
            "word_count": word_count(sch6_text),
        })
        print(f"  DUAA_Sch6  ({word_count(sch6_text)} words)")
    else:
        print("  [WARNING] Schedule 6 not found")

    print(f"  DUAA: {len(chunks)} chunks")
    return chunks


def main():
    all_new = []

    if os.path.exists(UK_MDR_PATH):
        all_new.extend(parse_uk_mdr(clean_uk(extract_text(UK_MDR_PATH))))
    else:
        print(f"[SKIP] {UK_MDR_PATH} not found")

    if os.path.exists(EU_MDR_PATH):
        all_new.extend(parse_eu_mdr(clean_eu(extract_text(EU_MDR_PATH))))
    else:
        print(f"[SKIP] {EU_MDR_PATH} not found")

    if os.path.exists(DUAA_PATH):
        all_new.extend(parse_duaa(clean_uk(extract_text(DUAA_PATH))))
    else:
        print(f"[SKIP] {DUAA_PATH} not found")

    if not all_new:
        print("[ERROR] no chunks produced")
        return

    # global dedup by chunk_id — keep first occurrence
    seen = set()
    deduped = []
    for c in all_new:
        if c["chunk_id"] not in seen:
            seen.add(c["chunk_id"])
            deduped.append(c)
    if len(deduped) < len(all_new):
        print(f"  (deduped {len(all_new) - len(deduped)} duplicate chunk IDs)")
    all_new = deduped

    if APPEND_TO_EXISTING and os.path.exists(OUTPUT_PATH):
        with open(OUTPUT_PATH, encoding="utf-8") as f:
            existing = json.load(f)
        existing_ids = {c["chunk_id"] for c in existing}
        added    = [c for c in all_new if c["chunk_id"] not in existing_ids]
        combined = existing + added
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(combined, f, indent=2, ensure_ascii=False)
        print(f"\nappended {len(added)} chunks  (total: {len(combined)})")
    else:
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(all_new, f, indent=2, ensure_ascii=False)
        print(f"\n{len(all_new)} chunks written to {OUTPUT_PATH}")

    by_reg = {}
    for c in all_new:
        by_reg[c["regulation"]] = by_reg.get(c["regulation"], 0) + 1
    for reg, count in sorted(by_reg.items()):
        print(f"  {reg}: {count}")


if __name__ == "__main__":
    main()