import os
import sys
import asyncio
import logging

logger = logging.getLogger(__name__)

INDEXABLE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx",
    ".md", ".txt", ".rst", ".json",
    ".html", ".css", ".sql", ".yaml", ".yml",
    ".env.example", ".toml", ".cfg", ".ini"
}

EXCLUDED_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv",
    "venv", ".env", "dist", "build", ".next",
    "migrations", ".mypy_cache", ".pytest_cache"
}


async def index_codebase(
    path: str,
    tag: str,
    hub_url: str = "http://localhost:8000",
    api_key: str = "",
):
    import httpx

    files_found = []
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
        for filename in files:
            ext = os.path.splitext(filename)[1].lower()
            if ext in INDEXABLE_EXTENSIONS:
                files_found.append(os.path.join(root, filename))

    logger.info(f"Found {len(files_found)} indexable files in {path}")

    indexed = 0
    errors = 0

    async with httpx.AsyncClient(timeout=30) as client:
        for filepath in files_found:
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()

                if len(content.strip()) < 50:
                    continue

                response = await client.post(
                    f"{hub_url}/api/docs/index",
                    json={
                        "content": content,
                        "tag": tag,
                        "title": os.path.basename(filepath),
                        "source": filepath,
                    },
                    headers={"Authorization": f"Bearer {api_key}"}
                )

                if response.status_code == 200:
                    indexed += 1
                else:
                    errors += 1
                    logger.warning(f"Failed to index {filepath}: {response.status_code}")

            except Exception as e:
                errors += 1
                logger.exception(f"Error indexing {filepath}: {e}")

    return {
        "total_files": len(files_found),
        "indexed": indexed,
        "errors": errors,
        "path": path,
        "tag": tag,
    }