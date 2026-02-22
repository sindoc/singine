"""Temporal algebra for intuitive date/time operations.

This module provides a human-friendly temporal expression language for singine,
enabling natural date specifications like:
    - day#"3 months ago"
    - day#"yesterday"
    - day#"start of last week"
    - day#"middle of last week"
    - day#"end of this month"
"""

import re
from datetime import datetime
from typing import Optional, Tuple
import pendulum
from pendulum import DateTime


class TemporalParser:
    """Parser for temporal expressions in singine's query language."""

    # Temporal operator patterns
    DAY_OPERATOR = re.compile(r'day#"([^"]+)"')
    PAST_DAY_OPERATOR = re.compile(r'pastDay#"([^"]+)"')
    FUTURE_DAY_OPERATOR = re.compile(r'futureDay#"([^"]+)"')

    def __init__(self, reference_date: Optional[DateTime] = None):
        """Initialize parser with optional reference date (defaults to now)."""
        self.reference_date = reference_date or pendulum.now()

    def parse_temporal_expression(self, expression: str) -> DateTime:
        """Parse a temporal expression and return a DateTime object.

        Args:
            expression: Temporal expression like:
                - day#"3 months ago"
                - pastDay#"3 months"
                - futureDay#"2 weeks"

        Returns:
            DateTime object representing the parsed date

        Raises:
            ValueError: If expression cannot be parsed
        """
        # Check for pastDay# operator
        match = self.PAST_DAY_OPERATOR.match(expression)
        if match:
            duration_expr = match.group(1)
            return self._parse_past_duration(duration_expr)

        # Check for futureDay# operator
        match = self.FUTURE_DAY_OPERATOR.match(expression)
        if match:
            duration_expr = match.group(1)
            return self._parse_future_duration(duration_expr)

        # Check for day# operator
        match = self.DAY_OPERATOR.match(expression)
        if match:
            natural_expr = match.group(1)
            return self._parse_natural_date(natural_expr)

        raise ValueError(f"Invalid temporal expression: {expression}")

    def _parse_natural_date(self, expression: str) -> DateTime:
        """Parse natural language date expression.

        Supports expressions like:
        - "today", "yesterday", "tomorrow"
        - "N days/weeks/months/years ago"
        - "start/middle/end of this/last/next week/month/year"
        - "last Monday", "next Friday"

        Args:
            expression: Natural language date expression

        Returns:
            DateTime object

        Raises:
            ValueError: If expression cannot be parsed
        """
        expr = expression.lower().strip()

        # Simple day references
        if expr == "today":
            return self.reference_date.start_of('day')
        elif expr == "yesterday":
            return self.reference_date.subtract(days=1).start_of('day')
        elif expr == "tomorrow":
            return self.reference_date.add(days=1).start_of('day')

        # Relative time ago: "3 months ago", "2 weeks ago"
        ago_match = re.match(r'(\d+)\s+(day|week|month|year)s?\s+ago', expr)
        if ago_match:
            amount = int(ago_match.group(1))
            unit = ago_match.group(2)
            return self._subtract_time(amount, unit)

        # Relative time from now: "in 3 months", "in 2 weeks"
        in_match = re.match(r'in\s+(\d+)\s+(day|week|month|year)s?', expr)
        if in_match:
            amount = int(in_match.group(1))
            unit = in_match.group(2)
            return self._add_time(amount, unit)

        # Start/middle/end of period
        period_match = re.match(
            r'(start|beginning|middle|center|end)\s+of\s+(this|last|next)\s+(week|month|year)',
            expr
        )
        if period_match:
            position = period_match.group(1)
            relative = period_match.group(2)
            period = period_match.group(3)
            return self._parse_period_position(position, relative, period)

        # Weekday references: "last Monday", "next Friday"
        weekday_match = re.match(r'(last|next)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)', expr)
        if weekday_match:
            relative = weekday_match.group(1)
            weekday = weekday_match.group(2)
            return self._parse_weekday(relative, weekday)

        raise ValueError(f"Cannot parse date expression: {expression}")

    def _subtract_time(self, amount: int, unit: str) -> DateTime:
        """Subtract time from reference date."""
        if unit == 'day':
            return self.reference_date.subtract(days=amount).start_of('day')
        elif unit == 'week':
            return self.reference_date.subtract(weeks=amount).start_of('day')
        elif unit == 'month':
            return self.reference_date.subtract(months=amount).start_of('day')
        elif unit == 'year':
            return self.reference_date.subtract(years=amount).start_of('day')
        raise ValueError(f"Unknown time unit: {unit}")

    def _add_time(self, amount: int, unit: str) -> DateTime:
        """Add time to reference date."""
        if unit == 'day':
            return self.reference_date.add(days=amount).start_of('day')
        elif unit == 'week':
            return self.reference_date.add(weeks=amount).start_of('day')
        elif unit == 'month':
            return self.reference_date.add(months=amount).start_of('day')
        elif unit == 'year':
            return self.reference_date.add(years=amount).start_of('day')
        raise ValueError(f"Unknown time unit: {unit}")

    def _parse_period_position(self, position: str, relative: str, period: str) -> DateTime:
        """Parse period position like 'start of last month'."""
        # Get the target period
        if relative == 'this':
            date = self.reference_date
        elif relative == 'last':
            if period == 'week':
                date = self.reference_date.subtract(weeks=1)
            elif period == 'month':
                date = self.reference_date.subtract(months=1)
            elif period == 'year':
                date = self.reference_date.subtract(years=1)
        elif relative == 'next':
            if period == 'week':
                date = self.reference_date.add(weeks=1)
            elif period == 'month':
                date = self.reference_date.add(months=1)
            elif period == 'year':
                date = self.reference_date.add(years=1)

        # Apply position
        if position in ['start', 'beginning']:
            return date.start_of(period)
        elif position in ['middle', 'center']:
            start = date.start_of(period)
            end = date.end_of(period)
            middle_day = start.day + (end.day - start.day) // 2
            return start.set(day=middle_day)
        elif position == 'end':
            return date.end_of(period).start_of('day')

        raise ValueError(f"Unknown position: {position}")

    def _parse_weekday(self, relative: str, weekday: str) -> DateTime:
        """Parse weekday reference like 'last Monday' or 'next Friday'."""
        weekday_map = {
            'monday': 1, 'tuesday': 2, 'wednesday': 3, 'thursday': 4,
            'friday': 5, 'saturday': 6, 'sunday': 7
        }

        target_weekday = weekday_map[weekday]
        current_weekday = self.reference_date.day_of_week

        if relative == 'last':
            # Find last occurrence
            days_back = current_weekday - target_weekday
            if days_back <= 0:
                days_back += 7
            return self.reference_date.subtract(days=days_back).start_of('day')
        elif relative == 'next':
            # Find next occurrence
            days_forward = target_weekday - current_weekday
            if days_forward <= 0:
                days_forward += 7
            return self.reference_date.add(days=days_forward).start_of('day')

        raise ValueError(f"Unknown relative: {relative}")

    def _parse_past_duration(self, expression: str) -> DateTime:
        """Parse past duration expression like '3 months' or '2 weeks'.

        pastDay# operator provides a cleaner way to express past dates
        without needing the 'ago' suffix.

        Args:
            expression: Duration expression like '3 months', '2 weeks', '1 year'

        Returns:
            DateTime object in the past

        Raises:
            ValueError: If expression cannot be parsed
        """
        expr = expression.lower().strip()

        # Match pattern: "N day(s)/week(s)/month(s)/year(s)"
        match = re.match(r'(\d+)\s+(day|week|month|year)s?', expr)
        if match:
            amount = int(match.group(1))
            unit = match.group(2)
            return self._subtract_time(amount, unit)

        raise ValueError(f"Invalid past duration expression: {expression}")

    def _parse_future_duration(self, expression: str) -> DateTime:
        """Parse future duration expression like '3 months' or '2 weeks'.

        futureDay# operator provides a cleaner way to express future dates
        without needing the 'in N units' format.

        Args:
            expression: Duration expression like '3 months', '2 weeks', '1 year'

        Returns:
            DateTime object in the future

        Raises:
            ValueError: If expression cannot be parsed
        """
        expr = expression.lower().strip()

        # Match pattern: "N day(s)/week(s)/month(s)/year(s)"
        match = re.match(r'(\d+)\s+(day|week|month|year)s?', expr)
        if match:
            amount = int(match.group(1))
            unit = match.group(2)
            return self._add_time(amount, unit)

        raise ValueError(f"Invalid future duration expression: {expression}")


# Convenience functions for common operations
def parse_date(expression: str, reference_date: Optional[DateTime] = None) -> DateTime:
    """Parse a date expression and return a DateTime object.

    Args:
        expression: Temporal expression like 'day#"3 months ago"'
        reference_date: Optional reference date (defaults to now)

    Returns:
        DateTime object
    """
    parser = TemporalParser(reference_date)
    return parser.parse_temporal_expression(expression)
