import { CommonModule } from '@angular/common';
import { Component, ElementRef, Input, forwardRef, inject } from '@angular/core';
import { ControlValueAccessor, NG_VALUE_ACCESSOR } from '@angular/forms';

/** A single editable combobox; only a selected option's value is saved. */
@Component({
  selector: 'app-searchable-select',
  standalone: true,
  imports: [CommonModule],
  providers: [{provide: NG_VALUE_ACCESSOR, useExisting: forwardRef(() => SearchableSelectComponent), multi: true}],
  template: `
    <div class="control">
      <input type="text" role="combobox" autocomplete="off" [value]="text" [disabled]="disabled"
        [placeholder]="placeholder" [attr.aria-label]="label" [attr.aria-required]="required"
        [attr.aria-expanded]="open" [attr.aria-controls]="listId" aria-autocomplete="list"
        [attr.aria-activedescendant]="open && filtered.length ? listId + '-' + active : null"
        (focus)="show()" (click)="show()" (input)="search($any($event.target).value)"
        (keydown)="onKey($event)" (blur)="close()">
      <span class="chevron" aria-hidden="true">⌄</span>
    </div>
    <ul *ngIf="open" role="listbox" [id]="listId" [attr.aria-label]="label + ' options'" class="options">
      <li *ngFor="let option of filtered; let index = index" role="option" [id]="listId + '-' + index"
        [attr.aria-selected]="value === option.value" [class.active]="active === index"
        (mousedown)="$event.preventDefault()" (click)="choose(option)" (mouseenter)="active = index">{{ option.label }}</li>
      <li *ngIf="!filtered.length" class="empty" role="presentation">No matching options</li>
    </ul>`,
  styles: [`:host{display:block;position:relative;min-width:0;font-weight:400}.control{position:relative}input{width:100%;height:38px;min-width:0;box-sizing:border-box;border:1px solid #ccd9d0;border-radius:6px;background:#fff;padding:8px 30px 8px 10px;color:#233e2e;font:13px Arial,sans-serif}input:focus-visible{outline:3px solid #4b8a6e;outline-offset:2px}.chevron{position:absolute;right:11px;top:9px;pointer-events:none;color:#607568}.options{position:absolute;z-index:1200;top:100%;left:0;right:0;max-height:200px;overflow-y:auto;padding:4px;margin:5px 0 0;list-style:none;border:1px solid #a6beb0;border-radius:7px;background:white;box-shadow:0 7px 22px #123c3126;color:#233e2e;font:13px Arial,sans-serif}.options li{padding:10px;border-radius:4px;cursor:pointer}.options li.active{background:#e1efe7}.options li[aria-selected=true]{font-weight:700}.options .empty{color:#607568;cursor:default}`],
})
export class SearchableSelectComponent implements ControlValueAccessor {
  private static sequence = 0;
  readonly listId = `searchable-options-${++SearchableSelectComponent.sequence}`;
  private readonly element = inject(ElementRef<HTMLElement>);
  @Input() label = 'Select option';
  @Input() placeholder = 'Search or select…';
  @Input() required = false;
  private choices: {value: string; label: string}[] = [];
  @Input() set options(options: {value: string; label: string}[]) {
    this.choices = options || [];
    if (!this.open) this.restoreLabel();
    this.active = Math.min(this.active, Math.max(0, this.filtered.length - 1));
  }
  value = '';
  text = '';
  query = '';
  open = false;
  active = 0;
  disabled = false;
  private onChange: (value: string) => void = () => {};
  private onTouched: () => void = () => {};
  get filtered() {
    const query = this.query.trim().toLowerCase();
    return this.choices.filter(option => `${option.label} ${option.value}`.toLowerCase().includes(query));
  }
  writeValue(value: string | null | undefined): void { this.value = value || ''; this.restoreLabel(); }
  registerOnChange(fn: (value: string) => void): void { this.onChange = fn; }
  registerOnTouched(fn: () => void): void { this.onTouched = fn; }
  setDisabledState(disabled: boolean): void { this.disabled = disabled; if (disabled) this.close(); }
  private restoreLabel(): void { this.text = this.choices.find(option => option.value === this.value)?.label || this.value; }
  show(): void { if (!this.open && !this.disabled) { this.open = true; this.query = ''; this.active = Math.max(0, this.filtered.findIndex(option => option.value === this.value)); } }
  search(text: string): void {
    this.text = this.query = text;
    this.open = true;
    this.active = 0;
    if (this.value) { this.value = ''; this.onChange(''); }
  }
  choose(option: {value: string; label: string}): void {
    this.value = option.value;
    this.text = option.label;
    this.query = '';
    this.open = false;
    this.onChange(option.value);
    this.onTouched();
  }
  close(): void { this.open = false; this.query = ''; this.restoreLabel(); this.onTouched(); }
  onKey(event: KeyboardEvent): void {
    if (event.key === 'Escape' && this.open) { event.preventDefault(); event.stopPropagation(); this.close(); return; }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      if (!this.open) this.show();
      else this.active = Math.max(0, Math.min(this.filtered.length - 1, this.active + (event.key === 'ArrowDown' ? 1 : -1)));
      requestAnimationFrame(() => this.element.nativeElement.querySelector(`#${this.listId}-${this.active}`)?.scrollIntoView({block: 'nearest'}));
    } else if (event.key === 'Enter' && this.open) {
      event.preventDefault();
      if (this.filtered[this.active]) this.choose(this.filtered[this.active]);
    }
  }
}
