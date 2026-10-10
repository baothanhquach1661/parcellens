import csv
import io

from django.utils import timezone

from ..models import ImportLog, ImportStatus


class ImportFileError(Exception):
    """The whole file is unusable (wrong encoding, missing columns...)."""


class RowError(ValueError):
    """A problem on a specific line of the file."""

    def __init__(self, line, message):
        super().__init__(message)
        self.line = line


class BaseImporter:
    """Reads a CSV file and records the outcome in an ImportLog.

    Subclasses set `kind` and `required_columns` and implement `process(rows)`.
    Problems with a single record are logged and skipped; problems with the
    whole file mark the import as failed.
    """

    kind = None
    required_columns = ()

    def __init__(self, file, file_name, user=None):
        self.file = file
        self.file_name = file_name
        self.user = user
        self.log = None

    def run(self):
        self.log = ImportLog.objects.create(kind=self.kind, file_name=self.file_name, uploaded_by=self.user)
        try:
            rows = self.read_rows()
            self.process(rows)
            self.log.status = ImportStatus.SUCCEEDED
        except ImportFileError as error:
            self.log.status = ImportStatus.FAILED
            self.log.errors = [{'row': 0, 'record': '', 'message': str(error)}]
        except Exception as error:
            # A bug, not bad data: record it for the user, then let it raise for the developer.
            self.log.status = ImportStatus.FAILED
            self.log.errors = [{'row': 0, 'record': '', 'message': f'Unexpected error: {error}'}]
            raise
        finally:
            self.log.finished_at = timezone.now()
            self.log.save()
        return self.log

    def read_rows(self):
        """Return a list of (line_number, row_dict) with lower-case header names."""
        raw = self.file.read()
        if isinstance(raw, bytes):
            try:
                # utf-8-sig drops the byte-order mark Excel adds to "CSV UTF-8" files.
                raw = raw.decode('utf-8-sig')
            except UnicodeDecodeError:
                raise ImportFileError('The file is not UTF-8 encoded. Save it as "CSV UTF-8" and try again.') from None
        reader = csv.DictReader(io.StringIO(raw, newline=''))
        if not reader.fieldnames:
            raise ImportFileError('The file is empty.')
        # Header spelling varies between exports ("Lineitem sku" vs "Lineitem SKU").
        reader.fieldnames = [name.strip().lower() for name in reader.fieldnames]
        missing = [column for column in self.required_columns if column not in reader.fieldnames]
        if missing:
            raise ImportFileError(f'Missing required column(s): {", ".join(missing)}.')
        # Line 1 is the header, so the first data row is line 2 (same as in Excel).
        return [(line, row) for line, row in enumerate(reader, start=2)]

    def process(self, rows):
        raise NotImplementedError
