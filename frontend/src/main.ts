import 'zone.js';

import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideZoneChangeDetection } from '@angular/core';
import { bootstrapApplication } from '@angular/platform-browser';

import { AppComponent } from './app/app.component';
import { authInterceptor } from './app/auth.interceptor';
import { demoInterceptor } from './app/demo.interceptor';

bootstrapApplication(AppComponent, {
  providers: [
    provideZoneChangeDetection({ eventCoalescing: true }),
    provideHttpClient(withInterceptors([demoInterceptor, authInterceptor])),
  ],
}).catch(console.error);
