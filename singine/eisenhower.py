"""Eisenhower Matrix classifier and pretty printer for tasks.

The Eisenhower Matrix categorizes tasks into four quadrants:
- Q1: Urgent & Important (Do First)
- Q2: Important, Not Urgent (Schedule)
- Q3: Urgent, Not Important (Delegate)
- Q4: Neither Urgent nor Important (Eliminate)

This helps prioritize tasks effectively, especially useful for ADHD-friendly task management.
"""

from typing import List, Dict
from enum import Enum
from datetime import datetime
import pendulum
from pendulum import DateTime

from .logseq import Todo, TodoStatus


class Quadrant(Enum):
    """Eisenhower Matrix quadrants."""
    Q1_DO_FIRST = "Q1: Urgent & Important"
    Q2_SCHEDULE = "Q2: Important, Not Urgent"
    Q3_DELEGATE = "Q3: Urgent, Not Important"
    Q4_ELIMINATE = "Q4: Neither Urgent nor Important"


class EisenhowerClassifier:
    """Classifies tasks into Eisenhower Matrix quadrants.

    Uses Logseq constructs to determine urgency and importance:

    **Importance Indicators:**
    - Priority [#A] = High importance
    - Priority [#B] = Medium importance
    - Priority [#C] or none = Low importance
    - DOING status = Important (actively working on it)

    **Urgency Indicators:**
    - NOW status = Urgent
    - Recent activity (updated in last 7 days) = Urgent
    - TODO with no recent activity = Not urgent
    - LATER, WAITING = Not urgent
    """

    # Urgency threshold: tasks updated in last N days are considered urgent
    URGENCY_THRESHOLD_DAYS = 7

    def __init__(self, reference_date: DateTime = None):
        """Initialize classifier with optional reference date."""
        self.reference_date = reference_date or pendulum.now()

    def classify(self, todo: Todo) -> Quadrant:
        """Classify a todo into an Eisenhower quadrant.

        Args:
            todo: Todo object to classify

        Returns:
            Quadrant enum
        """
        is_important = self._is_important(todo)
        is_urgent = self._is_urgent(todo)

        if is_important and is_urgent:
            return Quadrant.Q1_DO_FIRST
        elif is_important and not is_urgent:
            return Quadrant.Q2_SCHEDULE
        elif not is_important and is_urgent:
            return Quadrant.Q3_DELEGATE
        else:
            return Quadrant.Q4_ELIMINATE

    def _is_important(self, todo: Todo) -> bool:
        """Determine if a task is important.

        Importance criteria:
        - Priority A or B
        - DOING status (actively working = important)
        - NOW status
        """
        # High priority tags
        if todo.priority in ['A', 'B']:
            return True

        # Active work indicates importance
        if todo.status in [TodoStatus.DOING, TodoStatus.NOW]:
            return True

        return False

    def _is_urgent(self, todo: Todo) -> bool:
        """Determine if a task is urgent.

        Urgency criteria:
        - NOW status
        - Recent activity (updated in last 7 days)
        - Priority A with TODO status
        """
        # NOW status is always urgent
        if todo.status == TodoStatus.NOW:
            return True

        # Recent activity indicates urgency
        if todo.last_updated:
            days_since_update = (self.reference_date - todo.last_updated).days
            if days_since_update <= self.URGENCY_THRESHOLD_DAYS:
                return True

        # High priority TODOs are urgent
        if todo.priority == 'A' and todo.status == TodoStatus.TODO:
            return True

        return False


def group_by_quadrant(todos: List[Todo]) -> Dict[Quadrant, List[Todo]]:
    """Group todos by Eisenhower quadrant.

    Args:
        todos: List of Todo objects

    Returns:
        Dictionary mapping Quadrant to list of todos
    """
    classifier = EisenhowerClassifier()
    quadrants = {q: [] for q in Quadrant}

    for todo in todos:
        quadrant = classifier.classify(todo)
        quadrants[quadrant].append(todo)

    return quadrants


def format_eisenhower_matrix(todos: List[Todo], use_color: bool = True) -> str:
    """Format todos as an Eisenhower Matrix.

    Args:
        todos: List of Todo objects
        use_color: Whether to use ANSI colors (default True)

    Returns:
        Formatted string with tasks organized by quadrant
    """
    if not todos:
        return "No tasks found."

    quadrants = group_by_quadrant(todos)

    # ANSI color codes
    if use_color:
        RED = '\033[91m'
        YELLOW = '\033[93m'
        GREEN = '\033[92m'
        BLUE = '\033[94m'
        BOLD = '\033[1m'
        RESET = '\033[0m'
        DIM = '\033[2m'
    else:
        RED = YELLOW = GREEN = BLUE = BOLD = RESET = DIM = ''

    output = []

    # Q1: Urgent & Important (RED - Do First!)
    q1_tasks = quadrants[Quadrant.Q1_DO_FIRST]
    if q1_tasks:
        output.append(f"\n{RED}{BOLD}━━━ {Quadrant.Q1_DO_FIRST.value} ━━━{RESET}")
        output.append(f"{RED}🔥 DO FIRST - Critical tasks requiring immediate attention{RESET}")
        output.append("")
        for i, todo in enumerate(q1_tasks, 1):
            output.append(_format_task(todo, f"{RED}{i}{RESET}", use_color))
        output.append("")

    # Q2: Important, Not Urgent (BLUE - Schedule)
    q2_tasks = quadrants[Quadrant.Q2_SCHEDULE]
    if q2_tasks:
        output.append(f"\n{BLUE}{BOLD}━━━ {Quadrant.Q2_SCHEDULE.value} ━━━{RESET}")
        output.append(f"{BLUE}📅 SCHEDULE - Plan time for these important tasks{RESET}")
        output.append("")
        for i, todo in enumerate(q2_tasks, 1):
            output.append(_format_task(todo, f"{BLUE}{i}{RESET}", use_color))
        output.append("")

    # Q3: Urgent, Not Important (YELLOW - Delegate)
    q3_tasks = quadrants[Quadrant.Q3_DELEGATE]
    if q3_tasks:
        output.append(f"\n{YELLOW}{BOLD}━━━ {Quadrant.Q3_DELEGATE.value} ━━━{RESET}")
        output.append(f"{YELLOW}👥 DELEGATE - Consider delegating or batching these{RESET}")
        output.append("")
        for i, todo in enumerate(q3_tasks, 1):
            output.append(_format_task(todo, f"{YELLOW}{i}{RESET}", use_color))
        output.append("")

    # Q4: Neither Urgent nor Important (DIM - Eliminate)
    q4_tasks = quadrants[Quadrant.Q4_ELIMINATE]
    if q4_tasks:
        output.append(f"\n{DIM}{BOLD}━━━ {Quadrant.Q4_ELIMINATE.value} ━━━{RESET}")
        output.append(f"{DIM}🗑️  ELIMINATE - Question if these are necessary{RESET}")
        output.append("")
        for i, todo in enumerate(q4_tasks, 1):
            output.append(_format_task(todo, f"{DIM}{i}{RESET}", use_color))
        output.append("")

    # Summary
    output.append(f"\n{BOLD}Summary:{RESET}")
    output.append(f"  Q1 (Do First):  {RED}{len(q1_tasks)}{RESET} tasks")
    output.append(f"  Q2 (Schedule):  {BLUE}{len(q2_tasks)}{RESET} tasks")
    output.append(f"  Q3 (Delegate):  {YELLOW}{len(q3_tasks)}{RESET} tasks")
    output.append(f"  Q4 (Eliminate): {DIM}{len(q4_tasks)}{RESET} tasks")

    return "\n".join(output)


def _format_task(todo: Todo, index: str, use_color: bool) -> str:
    """Format a single task with details.

    Args:
        todo: Todo object
        index: Task index/number
        use_color: Whether to use ANSI colors

    Returns:
        Formatted task string
    """
    if use_color:
        BOLD = '\033[1m'
        RESET = '\033[0m'
        DIM = '\033[2m'
        CYAN = '\033[96m'
    else:
        BOLD = RESET = DIM = CYAN = ''

    # Format priority
    priority_str = f"[{BOLD}#{todo.priority}{RESET}] " if todo.priority else ""

    # Format status with emoji
    status_emoji = {
        TodoStatus.NOW: "⚡",
        TodoStatus.DOING: "🔄",
        TodoStatus.TODO: "📋",
        TodoStatus.LATER: "🕐",
        TodoStatus.WAITING: "⏸️",
    }.get(todo.status, "")

    # Format last updated
    if todo.last_updated:
        days_ago = (pendulum.now() - todo.last_updated).days
        if days_ago == 0:
            time_str = "today"
        elif days_ago == 1:
            time_str = "yesterday"
        elif days_ago < 7:
            time_str = f"{days_ago}d ago"
        elif days_ago < 30:
            weeks = days_ago // 7
            time_str = f"{weeks}w ago"
        else:
            months = days_ago // 30
            time_str = f"{months}mo ago"
        last_updated = f"{DIM}Updated: {time_str}{RESET}"
    else:
        last_updated = ""

    # Format location
    location = f"{DIM}{todo.file_path.name}:{todo.line_number}{RESET}"

    # Check if content contains H1 markdown (starts with "# ")
    content_lines = todo.content.strip().split('\n')
    formatted_content_parts = []

    for line in content_lines:
        if line.strip().startswith('# '):
            # Extract H1 heading text (remove the "# " prefix)
            heading_text = line.strip()[2:].strip()
            # Make H1 headings prominent with box and uppercase
            h1_formatted = f"\n{'═' * (len(heading_text) + 6)}\n║  {heading_text.upper()}  ║\n{'═' * (len(heading_text) + 6)}\n"
            formatted_content_parts.append(h1_formatted)
        else:
            formatted_content_parts.append(line)

    formatted_content = '\n'.join(formatted_content_parts)

    # Build output
    parts = [
        f"  {index}. {status_emoji} {BOLD}{formatted_content}{RESET}",
        f"     {priority_str}{todo.status.value}  •  {last_updated}  •  {location}"
    ]

    return "\n".join(parts)
