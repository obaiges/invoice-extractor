import { Component, computed, input } from '@angular/core';

import { FieldComponent } from '../field/field.component';
import { ExtractionResult, Invoice } from '../../models/invoice.model';
import { formatDate, formatMoney, formatQuantity } from '../../utils/format';

@Component({
  selector: 'app-result',
  imports: [FieldComponent],
  templateUrl: './result.component.html',
  styleUrl: './result.component.css',
})
export class ResultComponent {
  result = input.required<ExtractionResult>();

  private missingSet = computed(() => new Set(this.result().missing_fields ?? []));

  get invoice(): Invoice {
    return this.result().invoice;
  }

  get warnings(): string[] {
    return this.result().warnings ?? [];
  }

  get partial(): boolean {
    return this.result().status === 'partial';
  }

  isMissing(key: string): boolean {
    return this.missingSet().has(key);
  }

  money(value: number | null): string | null {
    return formatMoney(value, this.invoice.currency);
  }

  date(value: string | null): string | null {
    return formatDate(value);
  }

  quantity(value: number | null): string | null {
    return formatQuantity(value);
  }
}
