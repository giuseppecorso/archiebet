import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

export interface User {
  id: number;
  username: string;
  is_admin: boolean;
}

/** Login con cookie di sessione: il cookie lo gestisce il browser, qui teniamo solo l'utente. */
@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  readonly user = signal<User | null>(null);

  /** Chiede al backend chi è collegato (null se nessuno). */
  async loadSession(): Promise<User | null> {
    try {
      this.user.set(await firstValueFrom(this.http.get<User>('/api/auth/me')));
    } catch {
      this.user.set(null);
    }
    return this.user();
  }

  async login(username: string, password: string): Promise<void> {
    this.user.set(await firstValueFrom(this.http.post<User>('/api/auth/login', { username, password })));
  }

  async logout(): Promise<void> {
    await firstValueFrom(this.http.post('/api/auth/logout', {}));
    this.user.set(null);
  }
}
