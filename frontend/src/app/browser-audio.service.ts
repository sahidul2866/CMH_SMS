import { Injectable } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class BrowserAudioService {
  enabled = false;
  status = '';
  private context?: AudioContext;
  private socket?: WebSocket;
  private retry?: number;
  private heartbeat?: number;
  private queue: {clip: string; volume: number; testId?: string; last: boolean}[] = [];
  private playing = false;
  private generation = 0;
  private currentTestId?: string;
  private source?: AudioBufferSourceNode;

  async enable(): Promise<void> {
    try {
      this.context ??= new AudioContext();
      await this.context.resume();
      if (this.context.state !== 'running') throw new Error('Audio suspended');
      const tone = this.context.createOscillator();
      const gain = this.context.createGain();
      gain.gain.value = 0.05;
      tone.connect(gain).connect(this.context.destination);
      tone.start(); tone.stop(this.context.currentTime + 0.15);
      this.enabled = true;
      this.connect();
    } catch (error) {
      const detail = error instanceof Error ? `${error.name}: ${error.message}` : String(error);
      this.status = `Cannot enable browser sound: ${detail}`;
    }
  }

  disable(): void {
    this.enabled = false;
    window.clearTimeout(this.retry);
    window.clearInterval(this.heartbeat);
    this.clear();
    this.socket?.close();
    this.status = '';
  }

  private report(testId: string | undefined, phase: string, detail = ''): void {
    if (testId && this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify({type: 'audio.diagnostic', test_id: testId, phase, detail}));
    }
  }

  private clear(): void {
    for (const testId of new Set([this.currentTestId, ...this.queue.map(item => item.testId)])) {
      this.report(testId, 'failed', 'Browser sound was muted, disconnected, or announcements were turned off before playback completed.');
    }
    this.currentTestId = undefined;
    this.generation++;
    this.queue = [];
    this.source?.stop();
  }

  private connect(): void {
    if (!this.enabled || this.socket?.readyState === WebSocket.OPEN || this.socket?.readyState === WebSocket.CONNECTING) return;
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const socket = new WebSocket(`${protocol}//${location.host}/api/v1/realtime/audio`);
    this.socket = socket;
    let lastMessage = Date.now();
    this.status = 'Connecting sound…';
    socket.onopen = () => {
      this.status = 'Browser sound enabled';
      this.heartbeat = window.setInterval(() => {
        if (Date.now() - lastMessage > 45000) { socket.close(); return; }
        if (socket.readyState === WebSocket.OPEN) socket.send('ping');
      }, 15000);
    };
    socket.onmessage = event => {
      if (!this.enabled || this.socket !== socket) return;
      lastMessage = Date.now();
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'audio.stop') this.clear();
        if (data.type === 'audio.ready' && Array.isArray(data.clips)) {
          const volume = Math.max(0, Math.min(1, data.volume ?? 1));
          const repeats = Math.min(3, data.repeat_count || 1);
          for (let i = 0; i < repeats; i++) {
            this.queue.push(...data.clips.map((clip: string, index: number) => ({clip, volume, testId: data.diagnostic_id, last: i === repeats - 1 && index === data.clips.length - 1})));
          }
          void this.play();
        }
      } catch { this.status = 'Unable to read announcement audio'; }
    };
    socket.onerror = () => socket.close();
    socket.onclose = event => {
      if (this.socket !== socket) return;
      window.clearInterval(this.heartbeat);
      if (!this.enabled) return;
      this.clear();
      if (event.code === 4401 || event.code === 4403) {
        this.enabled = false;
        this.status = 'Sign in with waiting-display permission to enable sound.';
        return;
      }
      this.status = 'Sound disconnected; reconnecting…';
      this.retry = window.setTimeout(() => this.connect(), 2000);
    };
  }

  private async play(): Promise<void> {
    if (this.playing || !this.context) return;
    this.playing = true;
    try {
      while (this.enabled && this.queue.length) {
        const generation = this.generation;
        const item = this.queue.shift()!;
        this.currentTestId = item.testId;
        const bytes = Uint8Array.from(atob(item.clip), c => c.charCodeAt(0));
        const buffer = await this.context.decodeAudioData(bytes.buffer);
        if (generation !== this.generation || !this.enabled) continue;
        await this.context.resume();
        if (this.context.state !== 'running') throw new Error('Audio suspended');
        if (generation !== this.generation || !this.enabled) continue;
        const source = this.context.createBufferSource();
        this.source = source;
        source.buffer = buffer;
        const gain = this.context.createGain();
        gain.gain.value = item.volume;
        source.connect(gain).connect(this.context.destination);
        this.report(item.testId, "playing");
        await new Promise<void>(resolve => { source.onended = () => resolve(); source.start(); });
        if (item.last && generation === this.generation) this.report(item.testId, "completed");
        this.currentTestId = undefined;
        this.source = undefined;
      }
    } catch (error) {
      const detail = error instanceof Error ? `${error.name}: ${error.message}` : String(error);
      this.report(this.currentTestId, "failed", detail);
      this.disable();
      this.status = `Playback failed: ${detail}. Enable browser sound to retry.`;
    } finally { this.playing = false; }
  }
}
