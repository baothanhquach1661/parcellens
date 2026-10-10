from django import forms
from unfold.widgets import UnfoldAdminFileFieldWidget, UnfoldAdminSelectWidget

from .models import ImportKind

# Imports run inside the web request, so keep files small enough to finish quickly.
MAX_UPLOAD_MB = 10


class ImportUploadForm(forms.Form):
    kind = forms.ChoiceField(
        label='File type',
        choices=ImportKind.choices,
        widget=UnfoldAdminSelectWidget,
    )
    file = forms.FileField(
        label='CSV file',
        widget=UnfoldAdminFileFieldWidget,
        help_text=f'UTF-8 CSV, up to {MAX_UPLOAD_MB} MB. Importing the same file again is safe.',
    )

    def clean_file(self):
        upload = self.cleaned_data['file']
        if not upload.name.lower().endswith('.csv'):
            raise forms.ValidationError('Choose a .csv file. In Excel or Numbers: File > Export > CSV.')
        if upload.size > MAX_UPLOAD_MB * 1024 * 1024:
            raise forms.ValidationError(f'The file is larger than {MAX_UPLOAD_MB} MB. Split it and import each part.')
        return upload
