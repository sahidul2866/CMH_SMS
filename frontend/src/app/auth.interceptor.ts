import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { catchError, throwError } from 'rxjs';

export const authInterceptor: HttpInterceptorFn = (request, next) =>
  next(request).pipe(
    catchError((error: unknown) => {
      const isLoginRequest = request.url.endsWith('/auth/login');
      const isSessionCheck = request.url.endsWith('/auth/session');
      if (error instanceof HttpErrorResponse && error.status === 401 && !isLoginRequest && !isSessionCheck) {
        window.location.assign('/');
      }
      return throwError(() => error);
    }),
  );
