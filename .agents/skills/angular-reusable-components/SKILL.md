---
name: angular-reusable-components
description: Best practices and standards for building Angular reusable components, standalone architecture, signals, Less styling, and typed API services.
---

# Angular Reusable Components Best Practices

This skill outlines guidelines and architectural patterns for developing scalable, reusable Angular applications.

## 1. Component Architecture & Structure
Each component must follow a clean separation of concerns with 4 dedicated files:
* `<name>.component.ts` — Logic, signals, inputs, outputs, lifecycle.
* `<name>.component.html` — Semantic markup, template bindings, accessible markup.
* `<name>.component.less` — Scoped Less styling with nested rules, variables, and mixins.
* `<name>.component.spec.ts` — Comprehensive unit test specifications.

### Modern Angular Standards:
* **Standalone Architecture**: All components, directives, and pipes must be `standalone: true`. Avoid legacy `NgModule`.
* **Change Detection**: Always specify `changeDetection: ChangeDetectionStrategy.OnPush`.
* **Reactivity with Signals**:
  * Use `input<T>()` and `input.required<T>()` for inputs instead of `@Input()`.
  * Use `output<T>()` for event emissions instead of `@Output()`.
  * Use `signal<T>()` for writable local UI state.
  * Use `computed(() => ...)` for derived, side-effect-free state.
  * Expose service state as read-only signals using `.asReadonly()`.

### Example Reusable Component (`.ts`):
```typescript
import { ChangeDetectionStrategy, Component, computed, input, output, signal } from '@angular/core';
import { CommonModule } from '@angular/common';

export type StatusVariant = 'pending' | 'in-progress' | 'resolved' | 'critical';

@Component({
  selector: 'app-status-badge',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './status-badge.component.html',
  styleUrl: './status-badge.component.less',
  changeDetection: ChangeDetectionStrategy.OnPush
})
export class StatusBadgeComponent {
  status = input.required<StatusVariant>();
  label = input<string>();
  statusChange = output<StatusVariant>();

  badgeClass = computed(() => `badge badge-${this.status()}`);
  displayLabel = computed(() => this.label() || this.status().toUpperCase());

  onClick(): void {
    this.statusChange.emit(this.status());
  }
}
```

## 2. Styling with LESS (`.less`)
* Use modular Less styling:
  * Maintain shared variables in `src/styles/variables.less` (colors, spacing, typography).
  * Scope classes using BEM or semantic naming.
  * Use CSS custom properties where dynamic theming is required.
  * Ensure responsive layouts with media query mixins.

## 3. Service Layer & API Integration
* Services must be injectable at the root (`@Injectable({ providedIn: 'root' })`).
* Encapsulate API communication using Angular's `HttpClient`.
* All API requests and responses must have strictly typed TypeScript interfaces.
* Catch errors gracefully with RxJS `catchError` and surface user-friendly states or signals.

```typescript
@Injectable({
  providedIn: 'root'
})
export class ReliefRequestService {
  private http = inject(HttpClient);
  private apiUrl = '/api/v1/relief-requests';

  private requestsState = signal<ReliefRequest[]>([]);
  readonly requests = this.requestsState.asReadonly();

  getAll(): Observable<ReliefRequest[]> {
    return this.http.get<ReliefRequest[]>(this.apiUrl).pipe(
      tap(data => this.requestsState.set(data)),
      catchError(err => {
        console.error('Error fetching requests', err);
        return throwError(() => err);
      })
    );
  }
}
```

## 4. Folder Structure Convention
```text
src/app/
├── core/                  # Core singletons (interceptors, auth, guards, base services)
├── shared/                # Reusable UI components, pipes, directives
│   ├── components/
│   │   ├── badge/
│   │   │   ├── badge.component.ts
│   │   │   ├── badge.component.html
│   │   │   ├── badge.component.less
│   │   │   └── badge.component.spec.ts
│   │   └── index.ts       # Barrel file for easy imports
├── features/              # Feature modules (pages and business domains)
│   ├── relief-requests/
│   │   ├── components/
│   │   ├── services/
│   │   └── relief-requests.component.ts
├── styles/
│   ├── variables.less
│   ├── mixins.less
│   └── styles.less
```
