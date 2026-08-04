import { Component, Input } from '@angular/core';

@Component({
  selector: 'app-field',
  imports: [],
  templateUrl: './field.component.html',
  styleUrl: './field.component.css',
})
export class FieldComponent {
  @Input() label = '';
  @Input() value: string | number | null | undefined = null;

  get display(): string {
    if (this.value === null || this.value === undefined || this.value === '') {
      return 'No detectado';
    }
    return String(this.value);
  }

  get missing(): boolean {
    return this.value === null || this.value === undefined || this.value === '';
  }
}
