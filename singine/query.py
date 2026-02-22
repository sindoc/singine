"""Query language parser and filter engine for singine.

Provides SQL-like WHERE clause filtering for Logseq blocks/tasks with support
for temporal expressions and human-readable attribute names.
"""

import re
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass
from enum import Enum
import pendulum
from pendulum import DateTime

from .temporal import TemporalParser
from .logseq import Todo


class Operator(Enum):
    """Comparison operators for WHERE clauses."""
    EQ = "="
    NE = "!="
    GT = ">"
    GTE = ">="
    LT = "<"
    LTE = "<="
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"


@dataclass
class Condition:
    """Represents a single condition in a WHERE clause."""
    attribute: str
    operator: Operator
    value: Any


class WhereParser:
    """Parser for WHERE clause expressions.

    Supports expressions like:
        Last Updated Date >= pastDay#"3 months"
        Status = TODO
        Priority = A
        Content contains urgent
    """

    # Pattern for WHERE conditions - flexible attribute matching
    # Attributes can be unquoted words/phrases, operators, then values
    CONDITION_PATTERN = re.compile(
        r'^([A-Za-z][A-Za-z0-9\s]*?)\s+(>=|<=|!=|>|<|=|contains|starts_with|ends_with)\s+(.+)$',
        re.IGNORECASE
    )

    # Operator mapping
    OPERATOR_MAP = {
        '=': Operator.EQ,
        '!=': Operator.NE,
        '>': Operator.GT,
        '>=': Operator.GTE,
        '<': Operator.LT,
        '<=': Operator.LTE,
        'contains': Operator.CONTAINS,
        'starts_with': Operator.STARTS_WITH,
        'ends_with': Operator.ENDS_WITH,
    }

    def __init__(self):
        """Initialize WHERE parser."""
        self.temporal_parser = TemporalParser()

    def parse(self, where_clause: str) -> List[Condition]:
        """Parse WHERE clause into list of conditions.

        Supports flexible attribute names without requiring quotes.

        Examples:
            Last Updated Date >= pastDay#"3 months"
            Status = TODO
            Priority = A
            Content contains meeting

        Currently supports single conditions. Future: AND/OR logic.

        Args:
            where_clause: WHERE clause string

        Returns:
            List of Condition objects
        """
        where_clause = where_clause.strip()

        match = self.CONDITION_PATTERN.match(where_clause)
        if not match:
            raise ValueError(f"Invalid WHERE clause: {where_clause}")

        attribute = match.group(1).strip()
        operator_str = match.group(2).lower()
        value_str = match.group(3).strip()

        operator = self.OPERATOR_MAP.get(operator_str)
        if not operator:
            raise ValueError(f"Unknown operator: {operator_str}")

        # Parse value (could be temporal expression, string, number)
        value = self._parse_value(value_str)

        return [Condition(attribute=attribute, operator=operator, value=value)]

    def _parse_value(self, value_str: str) -> Any:
        """Parse value from string, handling temporal expressions, strings, numbers.

        Supports:
        - Temporal operators: day#"...", pastDay#"...", futureDay#"..."
        - Quoted strings: "value"
        - Numbers: 123, 45.6
        - Unquoted strings: TODO, DOING, urgent
        """
        value_str = value_str.strip()

        # Check for temporal expressions (all operators)
        if value_str.startswith('day#') or value_str.startswith('pastDay#') or value_str.startswith('futureDay#'):
            return self.temporal_parser.parse_temporal_expression(value_str)

        # Check for quoted string
        if value_str.startswith('"') and value_str.endswith('"'):
            return value_str[1:-1]

        # Check for number
        try:
            if '.' in value_str:
                return float(value_str)
            return int(value_str)
        except ValueError:
            pass

        # Return as-is (unquoted string)
        return value_str


class TodoFilter:
    """Filters todos based on WHERE conditions.

    Maps human-readable attribute names to Todo object properties.
    """

    # Attribute name mappings (human-readable -> internal)
    ATTRIBUTE_MAP = {
        # Status attributes
        "status": "status",
        "task status": "status",

        # Content attributes
        "content": "content",
        "text": "content",
        "description": "content",

        # Priority attributes
        "priority": "priority",
        "priority level": "priority",

        # File attributes
        "file": "file_path",
        "file name": "file_name",
        "file path": "file_path",

        # Date attributes
        "last updated": "last_updated",
        "last updated date": "last_updated",
        "modified date": "last_updated",
        "created date": "created_date",
        "creation date": "created_date",
    }

    def __init__(self, conditions: List[Condition]):
        """Initialize filter with conditions."""
        self.conditions = conditions

    def matches(self, todo: Todo) -> bool:
        """Check if todo matches all conditions."""
        for condition in self.conditions:
            if not self._evaluate_condition(todo, condition):
                return False
        return True

    def _evaluate_condition(self, todo: Todo, condition: Condition) -> bool:
        """Evaluate a single condition against a todo."""
        # Map attribute name
        attr_key = condition.attribute.lower()
        internal_attr = self.ATTRIBUTE_MAP.get(attr_key)

        if not internal_attr:
            raise ValueError(f"Unknown attribute: {condition.attribute}")

        # Get attribute value from todo
        todo_value = self._get_attribute_value(todo, internal_attr)

        # Handle None values
        if todo_value is None:
            return False

        # Evaluate based on operator
        return self._compare_values(todo_value, condition.operator, condition.value)

    def _get_attribute_value(self, todo: Todo, attribute: str) -> Any:
        """Get attribute value from todo object."""
        if attribute == "status":
            return todo.status.value
        elif attribute == "content":
            return todo.content
        elif attribute == "priority":
            return todo.priority
        elif attribute == "file_path":
            return str(todo.file_path)
        elif attribute == "file_name":
            return todo.file_path.name
        elif attribute == "last_updated":
            return todo.last_updated
        elif attribute == "created_date":
            return todo.created_date

        return None

    def _compare_values(self, left: Any, operator: Operator, right: Any) -> bool:
        """Compare two values based on operator."""
        # Handle DateTime comparisons
        if isinstance(left, DateTime) or isinstance(right, DateTime):
            return self._compare_dates(left, operator, right)

        # Handle string comparisons
        if isinstance(left, str) and isinstance(right, str):
            return self._compare_strings(left, operator, right)

        # Handle numeric comparisons
        try:
            left_num = float(left) if not isinstance(left, (int, float)) else left
            right_num = float(right) if not isinstance(right, (int, float)) else right

            if operator == Operator.EQ:
                return left_num == right_num
            elif operator == Operator.NE:
                return left_num != right_num
            elif operator == Operator.GT:
                return left_num > right_num
            elif operator == Operator.GTE:
                return left_num >= right_num
            elif operator == Operator.LT:
                return left_num < right_num
            elif operator == Operator.LTE:
                return left_num <= right_num
        except (ValueError, TypeError):
            pass

        # Fallback to string comparison
        return self._compare_strings(str(left), operator, str(right))

    def _compare_dates(self, left: Any, operator: Operator, right: Any) -> bool:
        """Compare dates."""
        # Convert to DateTime if needed
        if not isinstance(left, DateTime):
            if hasattr(left, 'timestamp'):
                left = pendulum.instance(left)
            else:
                return False

        if not isinstance(right, DateTime):
            if hasattr(right, 'timestamp'):
                right = pendulum.instance(right)
            else:
                return False

        if operator == Operator.EQ:
            return left.date() == right.date()
        elif operator == Operator.NE:
            return left.date() != right.date()
        elif operator == Operator.GT:
            return left > right
        elif operator == Operator.GTE:
            return left >= right
        elif operator == Operator.LT:
            return left < right
        elif operator == Operator.LTE:
            return left <= right

        return False

    def _compare_strings(self, left: str, operator: Operator, right: str) -> bool:
        """Compare strings."""
        if operator == Operator.EQ:
            return left == right
        elif operator == Operator.NE:
            return left != right
        elif operator == Operator.CONTAINS:
            return right.lower() in left.lower()
        elif operator == Operator.STARTS_WITH:
            return left.lower().startswith(right.lower())
        elif operator == Operator.ENDS_WITH:
            return left.lower().endswith(right.lower())
        elif operator == Operator.GT:
            return left > right
        elif operator == Operator.GTE:
            return left >= right
        elif operator == Operator.LT:
            return left < right
        elif operator == Operator.LTE:
            return left <= right

        return False


def filter_todos(todos: List[Todo], where_clause: str) -> List[Todo]:
    """Filter todos based on WHERE clause.

    Args:
        todos: List of Todo objects
        where_clause: WHERE clause string

    Returns:
        Filtered list of todos
    """
    parser = WhereParser()
    conditions = parser.parse(where_clause)
    filter_engine = TodoFilter(conditions)

    return [todo for todo in todos if filter_engine.matches(todo)]
