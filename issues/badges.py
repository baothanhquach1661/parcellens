"""Sidebar badge (see UNFOLD['SIDEBAR'] in settings)."""

from .models import Issue, IssueStatus


def open_issues(request):
    """Exceptions nobody has picked up yet."""
    return Issue.objects.filter(status=IssueStatus.OPEN).count() or None
