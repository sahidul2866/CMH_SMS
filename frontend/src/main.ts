import 'zone.js';

import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { ErrorHandler, inject, provideAppInitializer, provideZoneChangeDetection } from '@angular/core';
import { bootstrapApplication } from '@angular/platform-browser';

import { ApplicationErrorHandler, ClientLogService, clientLogInterceptor } from './app/client-log.service';

import { AppComponent } from './app/app.component';
import { authInterceptor } from './app/auth.interceptor';
import { demoInterceptor } from './app/demo.interceptor';

bootstrapApplication(AppComponent, {
  providers: [
    { provide: ErrorHandler, useClass: ApplicationErrorHandler },
    provideAppInitializer(() => inject(ClientLogService).start()),
    provideZoneChangeDetection({ eventCoalescing: true }),
    provideHttpClient(withInterceptors([demoInterceptor, clientLogInterceptor, authInterceptor])),
  ],
}).catch(console.error);
