import { HttpErrorResponse } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { AuthService } from '../../core/auth.service';

@Component({
  selector: 'ab-login',
  imports: [ReactiveFormsModule],
  templateUrl: './login.html',
  styleUrl: './login.scss',
})
export class Login {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  protected readonly form = inject(NonNullableFormBuilder).group({
    username: ['', Validators.required],
    password: ['', Validators.required],
  });
  protected readonly error = signal<string | null>(null);
  protected readonly busy = signal(false);

  protected async submit(): Promise<void> {
    if (this.form.invalid) {
      this.error.set('Scrivi nome utente e password.');
      return;
    }
    this.busy.set(true);
    this.error.set(null);
    try {
      const { username, password } = this.form.getRawValue();
      await this.auth.login(username, password);
      await this.router.navigate(['/partite']);
    } catch (e) {
      this.error.set(
        e instanceof HttpErrorResponse && e.status === 401
          ? 'Nome utente o password errati.'
          : 'Il server non risponde. Il backend è acceso?',
      );
    } finally {
      this.busy.set(false);
    }
  }
}
