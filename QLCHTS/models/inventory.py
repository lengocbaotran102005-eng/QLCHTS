"""Model giao dịch kho (nhập kho, xuất bán, điều chỉnh, hoàn kho)."""
from dataclasses import dataclass

import config
from models.base import row_to_kwargs


@dataclass
class InventoryTransaction:
    transaction_id: int | None = None
    product_id: int | None = None
    sku: str = ""
    product_name: str = ""
    transaction_type: str = "IMPORT"
    quantity_change: int = 0
    stock_after: int = 0
    reference_code: str = ""
    note: str = ""
    created_by: str = ""
    created_at: str = ""

    @classmethod
    def from_row(cls, row) -> "InventoryTransaction":
        tx = cls(**row_to_kwargs(cls, row))
        tx.reference_code = tx.reference_code or ""
        tx.note = tx.note or ""
        tx.created_by = tx.created_by or ""
        return tx

    @property
    def type_label(self) -> str:
        return config.INVENTORY_TYPE_LABELS.get(self.transaction_type, self.transaction_type)
