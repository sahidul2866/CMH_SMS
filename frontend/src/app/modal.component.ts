import { AfterViewInit, Component, ElementRef, EventEmitter, HostListener, Input, OnDestroy, Output, inject } from '@angular/core';

@Component({
  selector: 'app-modal', standalone: true,
  template: `<div class="shade" (click)="dismiss()"><section role="dialog" aria-modal="true" [attr.aria-label]="title" tabindex="-1" (click)="$event.stopPropagation()"><header><h2>{{ title }}</h2><button type="button" (click)="dismiss()" [disabled]="!dismissible" aria-label="Close dialog">×</button></header><div class="body"><ng-content /></div><footer>Tab to move · Escape to close</footer></section></div>`,
  styles: [`:host{position:fixed;inset:0;z-index:1000}.shade{height:100%;display:grid;place-items:center;padding:20px;background:#10251c66;backdrop-filter:blur(3px)}section{width:min(760px,100%);max-height:calc(100dvh - 40px);display:flex;flex-direction:column;background:#fff;border:1px solid #dbe4df;border-radius:14px;box-shadow:0 24px 80px #10251c33;color:#20382d}header{display:flex;align-items:center;justify-content:space-between;padding:16px 22px;border-bottom:1px solid #e5ebe7}h2{margin:0;font-size:19px}button{width:34px;height:34px;border:1px solid #dbe4df;border-radius:7px;background:#fff;font-size:24px;color:inherit}.body{padding:18px 22px;overflow:auto}footer{padding:10px 22px;border-top:1px solid #e5ebe7;font-size:11px;color:#607568}button:focus-visible{outline:3px solid #4b8a6e;outline-offset:2px}@media(max-width:600px){.shade{padding:10px}section{max-height:calc(100dvh - 20px)}.body{padding:14px}header{padding:12px 14px}}`],
})
export class ModalComponent implements AfterViewInit, OnDestroy {
  @Input() title = '';
  @Input() dismissible = true;
  @Output() closed = new EventEmitter<void>();
  private host: ElementRef<HTMLElement> = inject(ElementRef);
  private previousFocus = document.activeElement as HTMLElement | null;
  private previousOverflow = document.body.style.overflow;
  ngAfterViewInit(): void {
    document.body.style.overflow = 'hidden';
    setTimeout(() => (this.host.nativeElement.querySelector('[autofocus], input:not([readonly]), select, textarea') as HTMLElement | null)?.focus());
  }
  dismiss(): void { if (this.dismissible) this.closed.emit(); }
  @HostListener('document:keydown', ['$event']) onKey(event: KeyboardEvent): void {
    if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); this.dismiss(); }
    if (event.key !== 'Tab') return;
    const focusable = Array.from(this.host.nativeElement.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex="0"]')).filter(el => el.getClientRects().length);
    const first = focusable[0], last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
  }
  ngOnDestroy(): void { document.body.style.overflow = this.previousOverflow; this.previousFocus?.focus(); }
}
