from django.contrib import admin, messages
from django.shortcuts import redirect
from django.template.loader import render_to_string
from django.template.response import TemplateResponse
from unfold.admin import ModelAdmin
from unfold.decorators import action, display
from unfold.enums import ActionVariant

from .forms import ImportUploadForm
from .importers import IMPORTERS
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
        'kind', 'file_name', 'status_label', 'uploaded_by', 'started_at', 'finished_at',
        'rows_total', 'rows_created', 'rows_updated', 'rows_failed', 'errors_table',
    )
    readonly_fields = fields
    # "Import CSV" button above the list.
    actions_list = ['upload_csv']

    # Logs are written by the importer, never typed in or edited by hand.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_upload_permission(self, request):
        # Admin and staff roles may both import (see the permission plan).
        return request.user.has_perm('imports.view_importlog')

    @action(
        description='Import CSV',
        url_path='upload',
        icon='upload_file',
        variant=ActionVariant.PRIMARY,
        permissions=['upload'],
    )
    def upload_csv(self, request):
        form = ImportUploadForm(request.POST or None, request.FILES or None)
        if request.method == 'POST' and form.is_valid():
            upload = form.cleaned_data['file']
            importer_class = IMPORTERS[form.cleaned_data['kind']]
            log = importer_class(upload, file_name=upload.name, user=request.user).run()
            self._report(request, log)
            # The log page lists every rejected line.
            return redirect('admin:imports_importlog_change', log.pk)

        context = {
            **self.admin_site.each_context(request),
            'title': 'Import a CSV file',
            'opts': self.model._meta,
            'form': form,
            'formats': [
                (importer.kind.label, ', '.join(importer.required_columns))
                for importer in IMPORTERS.values()
            ],
        }
        return TemplateResponse(request, 'admin/imports/importlog/upload.html', context)

    def _report(self, request, log):
        if log.status == ImportStatus.FAILED:
            reason = log.errors[0]['message'] if log.errors else 'unknown error'
            messages.error(request, f'Import failed, nothing was saved: {reason}')
        elif log.rows_failed:
            messages.warning(
                request,
                f'{log.rows_created} created, {log.rows_updated} updated, '
                f'{log.rows_failed} rejected. The rejected lines are listed below.',
            )
        else:
            messages.success(
                request,
                f'Import finished: {log.rows_created} created, {log.rows_updated} updated.',
            )

    @staticmethod
    def _status(obj):
        if obj.status == ImportStatus.SUCCEEDED and obj.rows_failed:
            return 'succeeded_with_errors', 'Succeeded with errors'
        return obj.status, obj.get_status_display()

    @display(description='Status', ordering='status', label=STATUS_COLORS)
    def status_badge(self, obj):
        return self._status(obj)

    @admin.display(description='Status')
    def status_label(self, obj):
        # Same badge on the detail page (label=... only applies to list columns).
        key, text = self._status(obj)
        return render_to_string('unfold/helpers/label.html', {'text': text, 'variant': STATUS_COLORS[key]})

    @admin.display(description='Errors')
    def errors_table(self, obj):
        if not obj.errors:
            return '-'
        # Rendered by a Django template, so every value is HTML-escaped:
        # CSV content is untrusted input.
        table = {
            'headers': ['Line', 'Record', 'Message'],
            'rows': [
                [error.get('row'), error.get('record') or '-', error.get('message')]
                for error in obj.errors
            ],
        }
        return render_to_string('unfold/components/table.html', {'table': table, 'striped': 1})
