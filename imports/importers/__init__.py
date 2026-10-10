from .inventory import InventoryImporter
from .orders import OrdersImporter
from .tracking import TrackingImporter

IMPORTERS = {
    importer.kind: importer
    for importer in (OrdersImporter, InventoryImporter, TrackingImporter)
}

__all__ = ['IMPORTERS', 'InventoryImporter', 'OrdersImporter', 'TrackingImporter']
