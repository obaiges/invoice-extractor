export interface Party {
  name: string | null;
  tax_id: string | null;
  address: string | null;
}

export interface InvoiceLine {
  description: string | null;
  quantity: number | null;
  unit_price: number | null;
  total: number | null;
  tax_rate: number | null;
}

export interface TaxEntry {
  rate: number | null;
  amount: number | null;
}

export interface Invoice {
  invoice_number: string | null;
  issue_date: string | null;
  due_date: string | null;
  currency: string | null;
  seller: Party;
  buyer: Party;
  lines: InvoiceLine[];
  subtotal: number | null;
  shipping_handling: number | null;
  taxes: TaxEntry[];
  total: number | null;
}

export interface ExtractionResult {
  status: 'success' | 'partial';
  invoice: Invoice;
  missing_fields: string[];
  warnings: string[];
}

export interface ApiError {
  status: 'error';
  code: string;
  message: string;
}
