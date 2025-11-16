import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import requests
import xml.etree.ElementTree as ET

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from database import db, create_document, get_documents

app = FastAPI(title="Top News Aggregator", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Curated, reputable sources (use RSS feeds to respect TOS)
SOURCES: List[Dict[str, str]] = [
    {
        "name": "BBC World",
        "slug": "bbc",
        "url": "https://www.bbc.com/news",
        "rss_url": "http://feeds.bbci.co.uk/news/world/rss.xml",
        "category": "world",
    },
    {
        "name": "Reuters World",
        "slug": "reuters",
        "url": "https://www.reuters.com",
        "rss_url": "https://feeds.reuters.com/reuters/worldNews",
        "category": "world",
    },
    {
        "name": "AP News Top",
        "slug": "ap",
        "url": "https://apnews.com",
        "rss_url": "https://feeds.apnews.com/apf-topnews",
        "category": "top",
    },
    {
        "name": "CNN Top",
        "slug": "cnn",
        "url": "https://www.cnn.com",
        "rss_url": "http://rss.cnn.com/rss/edition.rss",
        "category": "top",
    },
]


class SourceModel(BaseModel):
    name: str
    slug: str
    url: str
    rss_url: str
    category: Optional[str] = None


class ArticleModel(BaseModel):
    source_slug: str
    source_name: str
    title: str
    summary: Optional[str] = None
    link: str
    image_url: Optional[str] = None
    published_at: Optional[datetime] = None
    categories: Optional[List[str]] = []


@app.get("/")
def read_root():
    return {"message": "News API is running"}


@app.get("/api/sources", response_model=List[SourceModel])
def list_sources():
    return [SourceModel(**s) for s in SOURCES]


def _parse_rss_datetime(text: Optional[str]) -> Optional[datetime]:
    if not text:
        return None
    # Try common formats
    fmts = [
        "%a, %d %b %Y %H:%M:%S %Z",
        "%a, %d %b %Y %H:%M:%S %z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
    ]
    for f in fmts:
        try:
            return datetime.strptime(text, f)
        except Exception:
            continue
    return None


def fetch_rss(url: str) -> List[Dict[str, Any]]:
    # Fetch and parse RSS/Atom feeds without external deps
    headers = {"User-Agent": "Mozilla/5.0 (compatible; FlamesNewsBot/1.0)"}
    r = requests.get(url, headers=headers, timeout=15)
    r.raise_for_status()
    content = r.content
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return []

    # RSS 2.0: channel/item
    items: List[ET.Element] = []
    channel = root.find("channel")
    if channel is not None:
        items = channel.findall("item")
    else:
        # Atom: entry
        items = root.findall("{http://www.w3.org/2005/Atom}entry")

    parsed: List[Dict[str, Any]] = []

    for it in items:
        title = None
        link = None
        summary = None
        pub = None
        image = None
        categories: List[str] = []

        # RSS
        t = it.findtext("title")
        if t:
            title = t.strip()
        l = it.findtext("link")
        if l and l.strip().startswith("http"):
            link = l.strip()
        # Some feeds use <link href="..."/> (Atom)
        if link is None:
            link_el = it.find("{http://www.w3.org/2005/Atom}link")
            if link_el is not None and link_el.attrib.get("href"):
                link = link_el.attrib.get("href")
        summary = (it.findtext("description") or it.findtext("{http://www.w3.org/2005/Atom}summary") or "")
        pub = it.findtext("pubDate") or it.findtext("{http://www.w3.org/2005/Atom}updated") or it.findtext("{http://purl.org/dc/elements/1.1/}date")
        published_at = _parse_rss_datetime(pub)

        # media content
        media_content = it.find("{http://search.yahoo.com/mrss/}content")
        if media_content is not None and media_content.attrib.get("url"):
            image = media_content.attrib.get("url")
        if image is None:
            enclosure = it.find("enclosure")
            if enclosure is not None and enclosure.attrib.get("url") and enclosure.attrib.get("type", "").startswith("image"):
                image = enclosure.attrib.get("url")
        # category tags
        for cat in it.findall("category"):
            if cat.text:
                categories.append(cat.text.strip())

        if title and link:
            parsed.append({
                "title": title,
                "link": link,
                "summary": summary,
                "published_at": published_at,
                "image_url": image,
                "categories": categories,
            })

    return parsed


def upsert_articles_for_source(source: Dict[str, str]) -> int:
    inserted = 0
    feed_items = fetch_rss(source["rss_url"])
    for item in feed_items:
        try:
            # Check if exists by link
            existing = get_documents("article", {"link": item["link"]}, limit=1)
            if existing:
                continue
            doc = {
                **item,
                "source_slug": source["slug"],
                "source_name": source["name"],
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }
            create_document("article", doc)
            inserted += 1
        except Exception:
            continue
    return inserted


@app.get("/api/refresh")
def refresh_articles() -> Dict[str, Any]:
    results: Dict[str, int] = {}
    total = 0
    for src in SOURCES:
        count = upsert_articles_for_source(src)
        results[src["slug"]] = count
        total += count
    return {"inserted": total, "by_source": results}


@app.get("/api/articles")
def get_articles(
    source: Optional[str] = Query(None, description="Filter by source slug"),
    limit: int = Query(40, ge=1, le=200, description="Max items to return"),
    refresh: bool = Query(False, description="Fetch latest from sources before returning"),
):
    if refresh:
        try:
            refresh_articles()
        except Exception:
            pass

    filt: Dict[str, Any] = {}
    if source:
        filt["source_slug"] = source

    # Latest first by published_at or created_at
    try:
        items = list(db["article"].find(filt).sort([
            ("published_at", -1), ("created_at", -1)
        ]).limit(limit))
    except Exception:
        # Fallback to helper
        items = get_documents("article", filt, limit)

    # Transform ObjectId, datetimes
    def transform(doc: Dict[str, Any]) -> Dict[str, Any]:
        d = dict(doc)
        if "_id" in d:
            d["id"] = str(d.pop("_id"))
        for k in ["created_at", "updated_at", "published_at"]:
            v = d.get(k)
            if isinstance(v, datetime):
                d[k] = v.isoformat()
        return d

    return [transform(x) for x in items]


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"

    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    import os as _os
    response["database_url"] = "✅ Set" if _os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if _os.getenv("DATABASE_NAME") else "❌ Not Set"

    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
