import { Component, EventEmitter, Output } from '@angular/core';

const ACCEPTED_EXTENSIONS = ['pdf', 'png', 'jpg', 'jpeg', 'webp'];
const MAX_SIZE_MB = 15;

@Component({
  selector: 'app-upload',
  imports: [],
  templateUrl: './upload.component.html',
  styleUrl: './upload.component.css',
})
export class UploadComponent {
  @Output() fileSelected = new EventEmitter<File>();
  @Output() errorMessage = new EventEmitter<string>();

  isDragging = false;
  readonly inputId = 'invoice-file-input';
  readonly acceptValue = ACCEPTED_EXTENSIONS.map((extension) => `.${extension}`).join(',');

  onDragOver(event: DragEvent): void {
    event.preventDefault();
    this.isDragging = true;
  }

  onDragLeave(): void {
    this.isDragging = false;
  }

  onDrop(event: DragEvent): void {
    event.preventDefault();
    this.isDragging = false;
    const file = event.dataTransfer?.files?.[0];
    if (file) {
      this.handleFile(file);
    }
  }

  onFileInput(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (file) {
      this.handleFile(file);
    }
    input.value = '';
  }

  private handleFile(file: File): void {
    const extension = file.name.split('.').pop()?.toLowerCase() ?? '';
    if (!ACCEPTED_EXTENSIONS.includes(extension)) {
      this.errorMessage.emit(
        `Formato no soportado: ".${extension || 'desconocido'}". Usa PDF, PNG, JPG o WEBP.`,
      );
      return;
    }
    if (file.size > MAX_SIZE_MB * 1024 * 1024) {
      this.errorMessage.emit(`El archivo supera el tamaño máximo de ${MAX_SIZE_MB} MB.`);
      return;
    }
    this.fileSelected.emit(file);
  }
}
