from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display

from .models import Holiday, Issue, IssueNote, IssueStatus, RuleSetting, Severity

SEVERITY_COLORS = {Severity.HIGH: 'danger', Severity.MEDIUM: 'warning', Severity.LOW: 'info'}
STATUS_COLORS = {
    IssueStatus.OPEN: 'danger',
    IssueStatus.ACKNOWLEDGED: 'warning',
    IssueStatus.SNOOZED: 'info',
    IssueStatus.RESOLVED: 'success',
}


class IssueNoteInline(TabularInline):
    model = IssueNote
    extra = 0
    fields = ('created_at', 'author', 'body', 'is_system')
    readonly_fields = ('created_at', 'author', 'is_system')


@admin.register(Issue)
class IssueAdmin(ModelAdmin):
    list_display = (
        'severity_badge', 'rule_code', 'order', 'shipment', 'status_badge',
        'first_detected_at', 'last_seen_at',
    )
    list_filter = ('status', 'severity', 'rule_code')
    search_fields = ('order__name', 'shipment__tracking_number')
    list_select_related = ('order', 'shipment')
    readonly_fields = (
        'order', 'shipment', 'rule_code', 'severity', 'details', 'first_detected_at',
        'last_seen_at', 'acknowledged_at', 'resolved_at', 'resolved_by', 'resolution',
        'created_at', 'updated_at',
    )
    inlines = [IssueNoteInline]

    # Issues are created by the rules engine only.
    def has_add_permission(self, request):
        return False

    @display(description='Severity', ordering='severity', label=SEVERITY_COLORS)
    def severity_badge(self, obj):
        return obj.severity, obj.get_severity_display()

    @display(description='Status', ordering='status', label=STATUS_COLORS)
    def status_badge(self, obj):
        return obj.status, obj.get_status_display()


@admin.register(RuleSetting)
class RuleSettingAdmin(ModelAdmin):
    list_display = ('rule_code', 'enabled', 'severity', 'threshold', 'threshold_unit', 'cutoff_time')
    list_editable = ('enabled', 'severity', 'threshold', 'threshold_unit', 'cutoff_time')
    readonly_fields = ('rule_code',)

    # One row per rule, created by a data migration; rules are code, not data.
    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Holiday)
class HolidayAdmin(ModelAdmin):
    list_display = ('date', 'name')
    date_hierarchy = 'date'
