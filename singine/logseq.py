"""Logseq file parsing and todo extraction."""

import re
import os
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import pendulum
from pendulum import DateTime


class TodoStatus(Enum):
    """Logseq todo statuses."""
    TODO = "TODO"
    DOING = "DOING"
    DONE = "DONE"
    LATER = "LATER"
    NOW = "NOW"
    WAITING = "WAITING"
    CANCELED = "CANCELED"


@dataclass
class Todo:
    """Represents a todo item from Logseq."""
    status: TodoStatus
    content: str
    file_path: Path
    line_number: int
    priority: Optional[str] = None
    last_updated: Optional[DateTime] = None
    created_date: Optional[DateTime] = None

    def __str__(self) -> str:
        """Format todo for display."""
        priority_str = f"[{self.priority}] " if self.priority else ""
        location = f"{self.file_path.name}:{self.line_number}"

        # Format H1 markdown headings (lines starting with "# ")
        content_lines = self.content.strip().split('\n')
        formatted_parts = []

        for line in content_lines:
            if line.strip().startswith('# '):
                # Extract H1 heading text (remove the "# " prefix)
                heading_text = line.strip()[2:].strip()
                # Make H1 headings prominent
                h1_box = f"\n{'═' * (len(heading_text) + 6)}\n║  {heading_text.upper()}  ║\n{'═' * (len(heading_text) + 6)}"
                formatted_parts.append(h1_box)
            else:
                formatted_parts.append(line)

        formatted_content = '\n'.join(formatted_parts)

        return f"{self.status.value:8} {priority_str}{formatted_content:50} ({location})"


class LogseqParser:
    """Parser for Logseq markdown files."""

    # Regex pattern for Logseq todos
    # Matches: - TODO Some task, - DONE [#A] Another task, etc.
    TODO_PATTERN = re.compile(
        r'^[\s-]*(?P<status>TODO|DOING|DONE|LATER|NOW|WAITING|CANCELED)\s+'
        r'(?:\[#(?P<priority>[ABC])\]\s+)?'
        r'(?P<content>.+)$',
        re.MULTILINE
    )

    # Pattern for CLOCK entries: CLOCK: [2025-04-12 Sat 19:30:46]
    CLOCK_PATTERN = re.compile(
        r'CLOCK:\s*\[(\d{4}-\d{2}-\d{2})\s+\w+\s+(\d{2}:\d{2}:\d{2})\]'
    )

    def __init__(self, graph_path: Path):
        """Initialize parser with Logseq graph path."""
        self.graph_path = graph_path
        self.pages_dir = graph_path / "pages"
        self.journals_dir = graph_path / "journals"

    def find_all_todos(self) -> List[Todo]:
        """Find all todos in the Logseq graph."""
        todos = []

        # Parse both pages and journals
        for directory in [self.pages_dir, self.journals_dir]:
            if directory.exists():
                todos.extend(self._parse_directory(directory))

        return todos

    def _parse_directory(self, directory: Path) -> List[Todo]:
        """Parse all markdown files in a directory."""
        todos = []

        for md_file in directory.glob("*.md"):
            todos.extend(self._parse_file(md_file))

        return todos

    def _parse_file(self, file_path: Path) -> List[Todo]:
        """Parse a single markdown file for todos."""
        todos = []

        try:
            content = file_path.read_text(encoding='utf-8')
            lines = content.splitlines()

            # Get file metadata for fallback dates
            file_stat = os.stat(file_path)
            file_modified = pendulum.from_timestamp(file_stat.st_mtime)
            file_created = pendulum.from_timestamp(file_stat.st_ctime)

            # Parse journal date from filename if applicable
            journal_date = self._parse_journal_date(file_path)

            for line_num, line in enumerate(lines, start=1):
                match = self.TODO_PATTERN.search(line)
                if match:
                    status_str = match.group('status')
                    priority = match.group('priority')
                    task_content = match.group('content').strip()

                    # Capture child blocks (indented content after the TODO)
                    child_content = self._extract_child_blocks(lines, line_num)
                    if child_content:
                        task_content = task_content + "\n" + child_content

                    # Look for LOGBOOK entries after this todo
                    last_clock_time = self._find_last_clock_time(lines, line_num)

                    # Determine dates
                    # Priority: CLOCK time > journal date > file modified time
                    last_updated = last_clock_time or journal_date or file_modified
                    created = journal_date or file_created

                    todo = Todo(
                        status=TodoStatus[status_str],
                        content=task_content,
                        file_path=file_path,
                        line_number=line_num,
                        priority=priority,
                        last_updated=last_updated,
                        created_date=created
                    )
                    todos.append(todo)

        except Exception as e:
            # Skip files that can't be read
            pass

        return todos

    def _parse_journal_date(self, file_path: Path) -> Optional[DateTime]:
        """Parse date from journal filename (e.g., 2025_11_21.md)."""
        if file_path.parent.name != 'journals':
            return None

        try:
            # Journal format: YYYY_MM_DD.md
            name = file_path.stem
            parts = name.split('_')
            if len(parts) == 3:
                year, month, day = map(int, parts)
                return pendulum.datetime(year, month, day)
        except (ValueError, IndexError):
            pass

        return None

    def _find_last_clock_time(self, lines: List[str], todo_line: int) -> Optional[DateTime]:
        """Find the last CLOCK entry associated with a todo.

        Looks at lines immediately following the todo (typically in a :LOGBOOK: block).
        """
        last_clock = None

        # Look ahead up to 20 lines for LOGBOOK entries
        for i in range(todo_line, min(todo_line + 20, len(lines))):
            line = lines[i]

            # Stop if we hit another todo or a new top-level item
            if i > todo_line and (
                self.TODO_PATTERN.search(line) or
                (line.startswith('-') and not line.strip().startswith(':'))
            ):
                break

            # Look for CLOCK entries
            clock_match = self.CLOCK_PATTERN.search(line)
            if clock_match:
                date_str = clock_match.group(1)
                time_str = clock_match.group(2)
                try:
                    dt = pendulum.parse(f"{date_str} {time_str}")
                    if last_clock is None or dt > last_clock:
                        last_clock = dt
                except Exception:
                    pass

        return last_clock

    def _extract_child_blocks(self, lines: List[str], todo_line: int) -> Optional[str]:
        """Extract child block content (indented lines) after a todo.

        In Logseq, child blocks are indented and belong to the parent TODO.
        This captures content like:
        - TODO Main task
          # Heading in child block
          Additional details
          :logbook: ... :END: (skipped)

        Args:
            lines: All lines from the file
            todo_line: Line number of the TODO (1-indexed)

        Returns:
            String with child content, or None if no children
        """
        child_lines = []
        i = todo_line  # Start from line after TODO (0-indexed in list)

        while i < len(lines):
            line = lines[i]

            # Stop if we hit another todo at the same or higher level
            if i > todo_line - 1 and self.TODO_PATTERN.search(line):
                # Check if it's at the same indentation level
                if not line.startswith(' ') and not line.startswith('\t'):
                    break

            # Stop if we hit a new top-level bullet point
            if i > todo_line - 1 and line.startswith('-') and not line.startswith('  '):
                break

            # Skip :logbook: blocks and properties
            if i > todo_line - 1:
                stripped = line.strip()
                if stripped.startswith(':') and not stripped.startswith('::'):
                    # Skip metadata blocks like :logbook:, :PROPERTIES:, etc.
                    # Continue until we find :END:
                    if stripped.lower() in [':logbook:', ':properties:', ':clock:']:
                        while i < len(lines) and ':END:' not in lines[i].upper():
                            i += 1
                        i += 1  # Skip the :END: line
                        continue

                # Skip Logseq properties (background-color::, id::, etc.)
                if '::' in stripped and not stripped.startswith('#'):
                    i += 1
                    continue

                # Capture content that looks like child blocks
                if line.startswith('  ') or line.startswith('\t') or stripped.startswith('#'):
                    # Remove leading indentation and bullet points for cleaner output
                    clean_line = line.strip()
                    # Remove leading bullet points (-, *, +)
                    if clean_line.startswith('- '):
                        clean_line = clean_line[2:]
                    elif clean_line.startswith('* '):
                        clean_line = clean_line[2:]
                    elif clean_line.startswith('+ '):
                        clean_line = clean_line[2:]
                    if clean_line:  # Skip empty lines
                        child_lines.append(clean_line)

            i += 1

            # Safety limit: don't look more than 50 lines ahead
            if i > todo_line + 49:
                break

        return '\n'.join(child_lines) if child_lines else None
