/** Coalesce bursts and allow at most one refresh batch, plus one trailing refresh. */
export class RefreshScheduler {
  private timer?: ReturnType<typeof setTimeout>;
  private running = false;
  private pending = false;
  private showIndicator = false;
  private generation = 0;
  private cancelRun?: () => void;
  private readonly run: (showIndicator: boolean, done: () => void) => () => void;
  private readonly delay: number;

  constructor(run: (showIndicator: boolean, done: () => void) => () => void, delay = 150) {
    this.run = run;
    this.delay = delay;
  }

  request(showIndicator = false): void {
    this.pending = true;
    this.showIndicator ||= showIndicator;
    if (this.running || this.timer !== undefined) return;
    this.timer = setTimeout(() => this.flush(), this.delay);
  }

  cancel(): void {
    this.generation++;
    if (this.timer !== undefined) clearTimeout(this.timer);
    this.timer = undefined;
    this.pending = false;
    this.showIndicator = false;
    this.running = false;
    const cancelRun = this.cancelRun;
    this.cancelRun = undefined;
    cancelRun?.();
  }

  private flush(): void {
    this.timer = undefined;
    if (!this.pending || this.running) return;
    this.pending = false;
    const showIndicator = this.showIndicator;
    this.showIndicator = false;
    const generation = ++this.generation;
    this.running = true;
    const cancelRun = this.run(showIndicator, () => {
      if (generation !== this.generation) return;
      this.running = false;
      this.cancelRun = undefined;
      if (this.pending) this.request();
    });
    if (this.running && generation === this.generation) this.cancelRun = cancelRun;
  }
}
