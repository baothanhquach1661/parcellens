# CSV import formats

ShipRadar imports three kinds of CSV files. Run an import with:

```bash
docker compose exec web python manage.py import_csv <orders|inventory|tracking> <path> [--user <username>]
```

Every run creates an **Import log** (admin → Data → Import logs) with counts and one line per rejected record.

## Rules shared by all imports

- Files must be UTF-8. Excel's "CSV UTF-8" works; its byte-order mark is ignored.
- Header names are matched without regard to case or surrounding spaces.
- Line numbers in errors match the spreadsheet (the header is line 1).
- A missing required column fails the whole file and imports nothing.
- A bad record is skipped and logged; the rest of the file is still imported.
- Importing the same file twice creates nothing new: records are updated instead.
- Dates and times: `2026-10-08 09:15:40 -0700` or ISO 8601. A time without an offset is read in the store's time zone (America/Los_Angeles). Everything is stored in UTC.

## Orders (`orders`)

Shopify's order export ([Exporting orders](https://help.shopify.com/en/manual/fulfillment/managing-orders/exporting-orders)). An order with several line items spans several rows that share the same `Name`; order-level columns are read from the first of those rows.

| Column | Required | Notes |
|---|---|---|
| `Name` | Yes | Order key, e.g. `#1001` |
| `Financial Status` | Yes | `pending`, `authorized`, `partially_paid`, `paid`, `partially_refunded`, `refunded`, `voided` (any case) |
| `Created at` | Yes | Becomes `placed_at` |
| `Total` | Yes | |
| `Lineitem quantity`, `Lineitem name`, `Lineitem price`, `Lineitem SKU` | Yes | One line item per row |
| `Fulfillment Status` | No | `unfulfilled` (default), `partial`, `fulfilled` |
| `Paid at`, `Fulfilled at`, `Canceled at` | No | `Cancelled at` is accepted too |
| `Email`, `Currency`, `Shipping Method`, `Shipping Name`, `Shipping Address1`, `Shipping Address2`, `Shipping City`, `Shipping Province`, `Shipping Zip`, `Shipping Country` | No | Stored as they are, even when they look wrong |
| `Fulfillment Location` | No | ShipRadar column: a location code such as `LA`. Empty means the default location. Shopify's own `Location` column is the point-of-sale location and is ignored |

One bad line item rejects its whole order.

Sample: `samples/shopify_orders_sample.csv`.

## Inventory (`inventory`)

One row per SKU per location. Both a simple format and the column names of Shopify's inventory export ([Inventory CSV](https://help.shopify.com/en/manual/products/inventory/setup/inventory-csv)) are accepted.

| Column | Required | Also accepted | Notes |
|---|---|---|---|
| `sku` | Yes | | Creates the SKU if it is new |
| `location` | Yes | | Location code (`LA`) or name (`Los Angeles warehouse`) |
| `on hand` | Yes | `On hand (current)`, `on_hand`, `quantity` | Whole number, 0 or more |
| `name` | No | `Title`, `product` | Updates the SKU name when given |
| `counted at` | No | `counted_at`, `as of` | Defaults to the time of the import |

SKUs that are not in the file keep their current stock, so a partial file is safe. Shopify allows negative stock; ShipRadar rejects it because it usually means a counting error.

Sample: `samples/inventory_sample.csv`.

## Tracking (`tracking`)

One row per carrier event. The first event for a tracking number creates the shipment. Rows can be in any order: after the import each shipment takes its status from its newest event.

| Column | Required | Also accepted | Notes |
|---|---|---|---|
| `order` | Yes | `order name`, `order number`, `name` | Must match an imported order |
| `carrier` | Yes | | `ups`, `usps`, `fedex`, `dhl`, `other` (any case) |
| `tracking number` | Yes | `tracking_number`, `tracking` | Spaces are removed and letters upper-cased |
| `status` | Yes | | See below |
| `event time` | Yes | `occurred at`, `timestamp`, `date` | Rejected if more than 5 minutes in the future |
| `description` | No | | Carrier wording |
| `event location` | No | `location`, `city` | Where the event happened |
| `shipped at` | No | | Used when the shipment is created; defaults to the first event time |
| `expected delivery` | No | `expected delivery date`, `estimated delivery`, `eta` | A newer estimate replaces the old one |

Statuses: `label_created`, `in_transit`, `out_for_delivery`, `delivered`, `exception`, `returned_to_sender`. Common carrier words are mapped: `Pre-Transit`, `Info Received`, `Label Printed` → label created; `Picked Up` → in transit; `Failed Attempt`, `Delivery Attempted` → exception; `Return to Sender`, `Returned` → returned to sender.

A tracking number that already belongs to another order is rejected.

Sample: `samples/tracking_sample.csv`.
