import { HttpErrorResponse } from '@angular/common/http';
import { Component, inject } from '@angular/core';

import { ResultComponent } from './components/result/result.component';
import { UploadComponent } from './components/upload/upload.component';
import { ApiError, ExtractionResult } from './models/invoice.model';
import { ExtractionService } from './services/extraction.service';

@Component({
  selector: 'app-root',
  imports: [UploadComponent, ResultComponent],
  templateUrl: './app.component.html',
  styleUrl: './app.component.css',
})
export class AppComponent {
  private readonly extractionService = inject(ExtractionService);

  result: ExtractionResult | null = null;
  loading = false;
  errorMessage: string | null = null;
  fileName = '';

  onFileSelected(file: File): void {
    this.result = null;
    this.errorMessage = null;
    this.fileName = file.name;
    this.loading = true;

    this.extractionService.extract(file).subscribe({
      next: (result) => {
        this.result = result;
        this.loading = false;
      },
      error: (error: HttpErrorResponse) => {
        this.loading = false;
        this.errorMessage = this.readErrorMessage(error);
      },
    });
  }

  onValidationError(message: string): void {
    this.errorMessage = message;
    this.result = null;
  }

  reset(): void {
    this.result = null;
    this.errorMessage = null;
    this.loading = false;
    this.fileName = '';
  }

  private readErrorMessage(error: HttpErrorResponse): string {
    const body = error.error as ApiError | undefined;
    if (body && typeof body === 'object' && body.status === 'error' && body.message) {
      return body.message;
    }
    if (error.status === 0) {
      return 'No se pudo conectar con el backend. Asegúrate de que está arrancado en http://localhost:8000.';
    }
    return `Ocurrió un error inesperado (HTTP ${error.status}).`;
  }
}
