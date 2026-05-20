import sys
import os
import argparse
import uuid
import hashlib
import logging

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from hub.memory.chroma_client import get_or_create_collection, DOCS_COLLECTION
from hub.memory.embedder import embed_text, embed_batch
import asyncio

logger = logging.getLogger(__name__)


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    if chunk_size <= 0:
        raise ValueError(f"chunk_size must be > 0, got {chunk_size}")
    if overlap < 0:
        raise ValueError(f"overlap must be >= 0, got {overlap}")
    if overlap >= chunk_size:
        raise ValueError(f"overlap ({overlap}) must be < chunk_size ({chunk_size})")
    if not text or not text.strip():
        return []

    words = text.split()
    if len(words) == 0:
        return []

    chunks = []
    i = 0
    while i < len(words):
        chunk = " ".join(words[i:i + chunk_size])
        if len(chunk.strip()) > 50:
            chunks.append(chunk)
        i += chunk_size - overlap
    return chunks


def make_chunk_id(chunk: str, index: int, source: str) -> str:
    raw = f"{source}::{index}::{chunk[:100]}"
    return hashlib.sha256(raw.encode()).hexdigest()


async def index_text(
    content: str,
    tag: str,
    title: str = "",
    url: str = "",
    source: str = "manual"
):
    collection = get_or_create_collection(DOCS_COLLECTION)
    chunks = chunk_text(content)
    if not chunks:
        print(f"No chunks generated from '{title or source}' — skipping")
        return

    print(f"Indexing {len(chunks)} chunks from '{title or source}'...")

    embeddings = await embed_batch(chunks)
    ids = [make_chunk_id(chunk, i, source) for i, chunk in enumerate(chunks)]
    metadatas = [
        {
            "source": source,
            "source_tag": tag,
            "title": title,
            "url": url,
            "chunk_index": i,
        }
        for i in range(len(chunks))
    ]

    collection.upsert(
        ids=ids,
        embeddings=embeddings,
        documents=chunks,
        metadatas=metadatas
    )
    print(f"✓ Indexed {len(chunks)} chunks with tag '{tag}'")
    print(f"  Total docs in collection: {collection.count()}")


async def index_file(path: str, tag: str, title: str = ""):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except FileNotFoundError:
        logger.error(f"File not found: {path}")
        return
    except PermissionError:
        logger.error(f"Permission denied reading: {path}")
        return
    except UnicodeError as e:
        logger.error(f"Encoding error reading {path}: {e}")
        return
    except Exception as e:
        logger.error(f"Unexpected error reading {path}: {e}")
        return

    filename = os.path.basename(path)
    await index_text(content, tag=tag, title=title or filename, source=path)


async def index_directory(dir_path: str, tag: str, extensions: list[str] = None):
    extensions = extensions or [".md", ".txt", ".py", ".rst"]
    files = []
    for root, _, filenames in os.walk(dir_path):
        for filename in filenames:
            if any(filename.endswith(ext) for ext in extensions):
                files.append(os.path.join(root, filename))

    print(f"Found {len(files)} files to index in '{dir_path}'")
    for filepath in files:
        await index_file(filepath, tag=tag)


async def main():
    parser = argparse.ArgumentParser(description="Index documents into NEXUS ChromaDB")
    parser.add_argument("--path", help="File or directory path to index")
    parser.add_argument("--text", help="Raw text content to index")
    parser.add_argument("--tag", required=False, help="Source tag e.g. python, civil-engineering")
    parser.add_argument("--title", default="", help="Document title")
    parser.add_argument("--url", default="", help="Source URL")
    parser.add_argument("--list", action="store_true", help="List all indexed sources")
    args = parser.parse_args()

    if args.list:
        collection = get_or_create_collection(DOCS_COLLECTION)
        print(f"Total indexed documents: {collection.count()}")
        return

    if not args.tag:
        print("Error: --tag is required when indexing documents")
        parser.print_help()
        return

    if args.text:
        await index_text(args.text, tag=args.tag, title=args.title, url=args.url)
    elif args.path:
        if os.path.isdir(args.path):
            await index_directory(args.path, tag=args.tag)
        elif os.path.isfile(args.path):
            await index_file(args.path, tag=args.tag, title=args.title)
        else:
            print(f"Path not found: {args.path}")
    else:
        parser.print_help()


if __name__ == "__main__":
    asyncio.run(main())