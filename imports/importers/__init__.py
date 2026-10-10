from .orders import OrdersImporter

IMPORTERS = {
    OrdersImporter.kind: OrdersImporter,
}

__all__ = ['IMPORTERS', 'OrdersImporter']
