from django.contrib import admin
from django.utils.html import format_html, format_html_join
from unfold.admin import ModelAdmin
from unfold.decorators import display

from .models import ImportLog, ImportStatus

STATUS_COLORS = {
    'running': 'info',
    'succeeded': 'success',
    'succeeded_with_errors': 'warning',
    'failed': 'danger',
}


@admin.register(ImportLog)
class ImportLogAdmin(ModelAdmin):
    list_display = (
        'started_at', 'kind', 'file_name', 'status_badge',
        'rows_total', 'rows_created', 'rows_updated', 'rows_failed', 'uploaded_by',
    )
    list_filter = ('kind', 'status')
    search_fields = ('file_name',)
    list_select_related = ('uploaded_by',)
    fields = (
        'kind', 'file_name', 'status', 'uploaded_by', 'started_at', 'finished_at',
        'rows_total', 'rows_created', 'rows_updated', 'rows_failed', 'errors_table',
    )
    readonly_fields = fields

    # Imports are created by the importer, never typed in by hand.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @display(description='Status', ordering='status', label=STATUS_COLORS)
    def status_badge(self, obj):
        if obj.status == ImportStatus.SUCCEEDED and obj.rows_failed:
            return 'succeeded_with_errors', 'Succeeded with errors'
        return obj.status, obj.get_status_display()

    @admin.display(description='Errors')
    def errors_table(self, obj):
        if not obj.errors:
            return '-'
        # format_html escapes every value: CSV content is untrusted input.
        rows = format_html_join(
            '',
            '<tr><td>{}</td><td>{}</td><td>{}</td></tr>',
            ((error.get('row'), error.get('record'), error.get('message')) for error in obj.errors),
        )
        return format_html(
            '<table><thead><tr><th>Line</th><th>Record</th><th>Message</th></tr></thead>'
            '<tbody>{}</tbody></table>',
            rows,
        )
