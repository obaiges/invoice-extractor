import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { ExtractionResult } from '../models/invoice.model';

@Injectable({ providedIn: 'root' })
export class ExtractionService {
  private readonly endpoint = '/api/v1/documents/extract';

  constructor(private readonly http: HttpClient) {}

  extract(file: File): Observable<ExtractionResult> {
    const formData = new FormData();
    formData.append('file', file, file.name);
    return this.http.post<ExtractionResult>(this.endpoint, formData);
  }
}
