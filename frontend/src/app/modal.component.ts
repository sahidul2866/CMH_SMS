import { AfterViewInit, Component, ElementRef, EventEmitter, HostListener, Input, OnDestroy, Output, inject } from '@angular/core';

@Component({
  selector: 'app-modal', standalone: true,
  template: `<div class="shade" [class.fullscreen]="fullscreen" [class.clinical]="theme === 'clinical'" [class.compact]="compact" (click)="dismiss()"><section role="dialog" aria-modal="true" [attr.aria-label]="title" tabindex="-1" (click)="$event.stopPropagation()"><header><h2>{{ title }}</h2><button type="button" (click)="dismiss()" [disabled]="!dismissible" aria-label="Close dialog">×</button></header><div class="body"><div class="modal-content"><ng-content /></div></div><footer>Tab to move · Escape to close</footer></section></div>`,
  styles: [`:host{position:fixed;inset:0;z-index:1000}.shade{height:100%;display:grid;place-items:center;padding:20px;background:#10251c66;backdrop-filter:blur(3px)}section{width:min(760px,100%);max-height:calc(100dvh - 40px);display:flex;flex-direction:column;background:#fff;border:1px solid #dbe4df;border-radius:14px;box-shadow:0 24px 80px #10251c33;color:#20382d}header{display:flex;align-items:center;justify-content:space-between;padding:16px 22px;border-bottom:1px solid #e5ebe7}h2{margin:0;font-size:19px}button{width:34px;height:34px;border:1px solid #dbe4df;border-radius:7px;background:#fff;font-size:24px;color:inherit}.body{padding:18px 22px;overflow:auto}footer{padding:10px 22px;border-top:1px solid #e5ebe7;font-size:11px;color:#607568}button:focus-visible{outline:3px solid #4b8a6e;outline-offset:2px}@media(max-width:600px){.shade{padding:10px}section{max-height:calc(100dvh - 20px)}.body{padding:14px}header{padding:12px 14px}}.shade.fullscreen{padding:0;box-sizing:border-box;height:100dvh}.fullscreen section{width:100%;height:100%;max-height:100%;min-height:0;border:0;border-radius:0;box-sizing:border-box}.fullscreen .body{flex:1;min-height:0;overscroll-behavior:contain}.fullscreen header,.fullscreen footer{flex-shrink:0}.clinical{background:#102b4b80;box-sizing:border-box}.clinical section{box-sizing:border-box;min-height:0}.clinical header,.clinical footer{flex-shrink:0}.clinical header button{flex-shrink:0}.clinical section{width:min(1320px,100%);border:1px solid #9fbfe1;border-radius:16px;color:#102b50}.clinical header{padding:18px 24px;background:linear-gradient(110deg,#07376c,#0864bf 65%,#03418e);color:white;border-radius:15px 15px 0 0}.clinical h2{font-size:30px;font-weight:800}.clinical header button{width:44px;height:44px;background:#ffffff12;border:2px solid #8bb7ed;color:white;font-size:36px}.clinical .body{padding:18px 22px;background:#f7faff}.clinical footer{background:#e7f1fe;color:#254c78;font-size:14px}.clinical.fullscreen header{border-radius:0}.clinical.fullscreen section{width:100%}@media(max-width:600px){.clinical h2{font-size:23px}.clinical header{padding:12px 14px}.clinical .body{padding:12px}}.clinical.compact{padding:10px}.clinical.compact section{width:min(1000px,100%);max-height:calc(100dvh - 20px)}.clinical.compact header{padding:9px 16px}.clinical.compact h2{font-size:20px}.clinical.compact header button{width:30px;height:30px;font-size:26px}.clinical.compact .body{padding:12px 16px}.clinical.compact footer{display:none}@media(max-height:500px){.clinical.compact header{padding:5px 12px}.clinical.compact h2{font-size:17px}.clinical.compact .body{padding:6px 10px}}.compact .body{box-sizing:content-box;flex-shrink:0;overflow:hidden;min-height:0}.compact .modal-content{position:relative;transform-origin:top left;display:flow-root}`],
})
export class ModalComponent implements AfterViewInit, OnDestroy {
  @Input() title = '';
  @Input() theme = '';
  @Input() compact = false;
  @Input() dismissible = true;
  @Input() fullscreen = false;
  @Output() closed = new EventEmitter<void>();
  private host: ElementRef<HTMLElement> = inject(ElementRef);
  private previousFocus = document.activeElement as HTMLElement | null;
  private previousOverflow = document.body.style.overflow;
  private fitObserver?: ResizeObserver;
  private fitFrame = 0;
  private scheduleFit = (): void => {
    cancelAnimationFrame(this.fitFrame);
    this.fitFrame = requestAnimationFrame(() => this.fitToScreen());
  };
  private fitToScreen(): void {
    if (!this.compact) return;
    const root = this.host.nativeElement;
    const body = root.querySelector<HTMLElement>('.body')!;
    const content = root.querySelector<HTMLElement>('.modal-content')!;
    const header = root.querySelector<HTMLElement>('header')!;
    const dialog = root.querySelector<HTMLElement>('section')!;
    const viewportHeight = Math.min(window.innerHeight, window.visualViewport?.height ?? window.innerHeight);
    const style = getComputedStyle(body);
    const padding = parseFloat(style.paddingTop) + parseFloat(style.paddingBottom);
    const width = body.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
    const height = Math.max(1, viewportHeight - 20 - header.offsetHeight - padding - 8);
    const naturalHeight = content.scrollHeight;
    const naturalWidth = Math.max(content.scrollWidth, content.clientWidth);
    const scale = Math.min(1, height / Math.max(1, naturalHeight), width / Math.max(1, naturalWidth));
    content.style.transform = `scale(${scale})`;
    content.style.left = `${Math.max(0, (width - naturalWidth * scale) / 2)}px`;
    body.style.height = `${Math.ceil(naturalHeight * scale) + 4}px`;
    dialog.style.maxHeight = `${viewportHeight - 20}px`;
  }
  ngAfterViewInit(): void {
    document.body.style.overflow = 'hidden';
    if (this.compact) {
      this.fitObserver = new ResizeObserver(this.scheduleFit);
      this.fitObserver.observe(this.host.nativeElement.querySelector('.modal-content')!);
      this.fitObserver.observe(this.host.nativeElement.querySelector('header')!);
      window.addEventListener('resize', this.scheduleFit);
      window.visualViewport?.addEventListener('resize', this.scheduleFit);
      this.scheduleFit();
    }
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
  ngOnDestroy(): void {
    this.fitObserver?.disconnect();
    cancelAnimationFrame(this.fitFrame);
    window.removeEventListener('resize', this.scheduleFit);
    window.visualViewport?.removeEventListener('resize', this.scheduleFit);
    document.body.style.overflow = this.previousOverflow;
    this.previousFocus?.focus();
  }
}
