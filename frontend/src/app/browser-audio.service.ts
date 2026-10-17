import { Injectable } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class BrowserAudioService {
  enabled = false;
  status = '';
  private context?: AudioContext;
  private socket?: WebSocket;
  private retry?: number;
  private heartbeat?: number;
  private queue: {clip: string; volume: number}[] = [];
  private playing = false;
  private generation = 0;
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
    } catch { this.status = 'Sound blocked. Click Enable browser sound again.'; }
  }

  disable(): void {
    this.enabled = false;
    window.clearTimeout(this.retry);
    window.clearInterval(this.heartbeat);
    this.socket?.close();
    this.clear();
    this.status = '';
  }

  private clear(): void {
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
          for (let i = 0; i < Math.min(3, data.repeat_count || 1); i++) {
            this.queue.push(...data.clips.map((clip: string) => ({clip, volume})));
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
        await new Promise<void>(resolve => { source.onended = () => resolve(); source.start(); });
        this.source = undefined;
      }
    } catch {
      this.disable();
      this.status = 'Playback failed. Check speaker output, then enable browser sound again.';
    } finally { this.playing = false; }
  }
}
