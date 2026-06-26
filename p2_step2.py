import json
import logging
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

CHUNKS_PATH = Path("regulatory_chunks.json")
VOCAB_PATH  = Path("data/vocab_index.json")
EMBED_PATH  = Path("data/class_embeddings.npy")
OUTPUT_PATH = Path("data/articles_with_classes.json")

TOP_K = 20


def load_inputs():
    with open(CHUNKS_PATH, encoding="utf-8") as f:
        chunks = json.load(f)
    with open(VOCAB_PATH, encoding="utf-8") as f:
        vocab = json.load(f)
    embeddings = np.load(str(EMBED_PATH))
    log.info(f"Chunks: {len(chunks)}  |  Classes: {len(vocab['classes'])}  |  Embeddings: {embeddings.shape}")
    return chunks, vocab, embeddings


def group_by_article(chunks: list[dict]) -> dict[str, dict]:
    articles: dict[str, dict] = {}

    for chunk in chunks:
        regulation    = chunk.get("regulation", "UNKNOWN")
        article_num   = chunk.get("article", "UNKNOWN")
        article_title = chunk.get("article_title", "")
        group_key     = f"{regulation}__Art{article_num}"

        if group_key not in articles:
            articles[group_key] = {
                "article_id"   : group_key,
                "regulation"   : regulation,
                "article_num"  : article_num,
                "article_title": article_title,
                "chunks"       : [],
                "merged_text"  : "",
            }
        articles[group_key]["chunks"].append(chunk.get("chunk_id", ""))
        articles[group_key]["merged_text"] += " " + chunk.get("text", "")

    for art in articles.values():
        art["merged_text"] = art["merged_text"].strip()

    log.info(f"Articles after grouping: {len(articles)}")
    return articles


def retrieve_top_classes(
    articles: dict[str, dict],
    class_embeddings: np.ndarray,
    classes: list[dict],
    model: SentenceTransformer,
    top_k: int,
) -> list[dict]:
    article_list = list(articles.values())
    texts = [a["merged_text"] for a in article_list]

    log.info(f"Embedding {len(texts)} articles ...")
    article_embeddings = model.encode(
        texts,
        batch_size=16,
        show_progress_bar=True,
        normalize_embeddings=True,
        convert_to_numpy=True,
    ).astype(np.float32)

    similarity = article_embeddings @ class_embeddings.T

    results = []
    for i, article in enumerate(tqdm(article_list, desc="Selecting top classes")):
        top_indices = np.argsort(similarity[i])[::-1][:top_k]
        top_classes = [
            {
                "uri"  : classes[idx]["uri"],
                "name" : classes[idx].get("name", classes[idx]["uri"].split("#")[-1]),
                "label": classes[idx]["label"],
                "score": float(round(similarity[i][idx], 4)),
            }
            for idx in top_indices
        ]
        results.append({
            "article_id"   : article["article_id"],
            "regulation"   : article["regulation"],
            "article_num"  : article["article_num"],
            "article_title": article["article_title"],
            "chunk_ids"    : article["chunks"],
            "merged_text"  : article["merged_text"],
            "top_classes"  : top_classes,
        })

    return results


def main():
    chunks, vocab, class_embeddings = load_inputs()
    articles = group_by_article(chunks)

    model   = SentenceTransformer("all-MiniLM-L6-v2")
    results = retrieve_top_classes(articles, class_embeddings, vocab["classes"], model, TOP_K)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    log.info(f"Saved {len(results)} articles → {OUTPUT_PATH}")
    print(f"\nArticles: {len(results)}  |  Top-K: {TOP_K}  |  Output: {OUTPUT_PATH}")
    print("Next → step3_extraction.py")


if __name__ == "__main__":
    main()