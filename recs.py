from typing import List
from sqlmodel import Session, select
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from .models import Product

def recommend_for_product(session: Session, product_id: int, n: int = 4) -> List[Product]:
    products = session.exec(select(Product)).all()
    if not products:
        return []
    docs = [p.description or "" for p in products]
    vec = TfidfVectorizer(stop_words='english')
    X = vec.fit_transform(docs)
    idx_map = {p.id: i for i, p in enumerate(products)}
    if product_id not in idx_map:
        return products[:n]
    idx = idx_map[product_id]
    sims = cosine_similarity(X[idx], X).flatten()
    order = sims.argsort()[::-1]
    out = []
    for j in order:
        if products[j].id != product_id:
            out.append(products[j])
        if len(out) >= n:
            break
    return out
