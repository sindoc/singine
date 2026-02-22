"""Logseq URL parsing and metadata extraction."""

import re
import urllib.parse
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
import pendulum
from pendulum import DateTime

from .config import Config


@dataclass
class LogseqURL:
    """Represents a parsed Logseq URL."""
    protocol: str
    graph_name: str
    page_name: str
    raw_url: str

    @property
    def page_file_name(self) -> str:
        """Convert page name to filename (replaces / with ___)."""
        filename = self.page_name.replace("/", "___")
        return f"{filename}.md"


class LogseqURLParser:
    """Parser for logseq:// protocol URLs."""

    URL_PATTERN = re.compile(r'^logseq://graph/(?P<graph>[^?]+)\?page=(?P<page>.+)$')

    @classmethod
    def parse(cls, url: str) -> Optional[LogseqURL]:
        """Parse a Logseq URL into components."""
        match = cls.URL_PATTERN.match(url.strip())
        if not match:
            return None

        graph_name = match.group('graph')
        page_name_encoded = match.group('page')
        page_name = urllib.parse.unquote(page_name_encoded)

        return LogseqURL(
            protocol="logseq",
            graph_name=graph_name,
            page_name=page_name,
            raw_url=url
        )


@dataclass
class PageMetadata:
    """Metadata extracted from a Logseq page."""
    page_name: str
    file_path: Path
    exists: bool
    content: Optional[str] = None
    line_count: Optional[int] = None
    word_count: Optional[int] = None
    created_date: Optional[DateTime] = None
    modified_date: Optional[DateTime] = None
    properties: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    outbound_links: List[str] = field(default_factory=list)
    namespace: Optional[str] = None
    page_title: Optional[str] = None
    parent_pages: List[str] = field(default_factory=list)


class LogseqMetadataExtractor:
    """Extracts metadata from Logseq pages."""

    PROPERTY_PATTERN = re.compile(r'^(?P<key>[^:]+)::\s*(?P<value>.+)$', re.MULTILINE)
    TAG_PATTERN = re.compile(r'#([A-Za-z0-9_-]+)')
    LINK_PATTERN = re.compile(r'\[\[([^\]]+)\]\]')

    def __init__(self, graph_path: Path):
        self.graph_path = graph_path
        self.pages_dir = graph_path / "pages"

    def extract_from_url(self, url: str) -> Optional[PageMetadata]:
        """Extract metadata from a Logseq URL."""
        parsed = LogseqURLParser.parse(url)
        if not parsed:
            raise ValueError(f"Invalid Logseq URL: {url}")
        return self.extract_from_page(parsed.page_name)

    def extract_from_page(self, page_name: str) -> PageMetadata:
        """Extract metadata from a page by name."""
        file_path = self._find_page_file(page_name)

        if not file_path or not file_path.exists():
            return PageMetadata(
                page_name=page_name,
                file_path=file_path or Path(""),
                exists=False
            )

        metadata = PageMetadata(
            page_name=page_name,
            file_path=file_path,
            exists=True
        )

        # Parse hierarchy
        if "/" in page_name:
            parts = page_name.split("/")
            metadata.namespace = "/".join(parts[:-1])
            metadata.page_title = parts[-1]
            metadata.parent_pages = ["/".join(parts[:i+1]) for i in range(len(parts)-1)]
        else:
            metadata.page_title = page_name

        # Read content
        try:
            content = file_path.read_text(encoding='utf-8')
            metadata.content = content
            metadata.line_count = len(content.splitlines())
            metadata.word_count = len(content.split())
            metadata.properties = self._extract_properties(content)
            metadata.tags = self._extract_tags(content)
            metadata.outbound_links = self._extract_links(content)

            import os
            stat = os.stat(file_path)
            metadata.created_date = pendulum.from_timestamp(stat.st_ctime)
            metadata.modified_date = pendulum.from_timestamp(stat.st_mtime)
        except Exception:
            pass

        return metadata

    def _find_page_file(self, page_name: str) -> Optional[Path]:
        """Find markdown file for page name."""
        filename = page_name.replace("/", "___") + ".md"
        page_path = self.pages_dir / filename
        return page_path if page_path.exists() else None

    def _extract_properties(self, content: str) -> Dict[str, Any]:
        """Extract Logseq properties (key:: value)."""
        properties = {}
        for match in self.PROPERTY_PATTERN.finditer(content):
            key = match.group('key').strip()
            value = match.group('value').strip()
            if value.startswith('[[') and value.endswith(']]'):
                value = value[2:-2]
            properties[key] = value
        return properties

    def _extract_tags(self, content: str) -> List[str]:
        """Extract hashtags."""
        tags = {match.group(1) for match in self.TAG_PATTERN.finditer(content)}
        return sorted(list(tags))

    def _extract_links(self, content: str) -> List[str]:
        """Extract page links ([[Page Name]])."""
        links = {match.group(1) for match in self.LINK_PATTERN.finditer(content)}
        return sorted(list(links))


def get_page_metadata(url_or_page: str) -> Optional[PageMetadata]:
    """Get metadata from URL or page name."""
    config = Config()
    graph_path = config.get_logseq_path()
    extractor = LogseqMetadataExtractor(graph_path)

    if url_or_page.startswith('logseq://'):
        return extractor.extract_from_url(url_or_page)
    else:
        return extractor.extract_from_page(url_or_page)
