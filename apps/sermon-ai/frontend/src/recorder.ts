/**
 * Records a long sermon as a series of self-contained audio files ("segments").
 *
 * Each segment is at most SEGMENT_MS long, stays well below the 25 MB transcription limit
 * and can be decoded on its own. The next segment starts a moment before the previous one
 * stops, so no words are lost at the boundary. Every few seconds a chunk is handed to
 * `onChunk` (which persists and uploads it).
 */
const SEGMENT_MS = 10 * 60 * 1000;
const OVERLAP_MS = 1500;
const CHUNK_MS = 5000;

export function pickMimeType(): string {
  const options = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus'];
  return options.find((t) => typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(t)) || '';
}

export class SegmentedRecorder {
  private active: MediaRecorder | null = null;
  private stopping: Promise<void>[] = [];
  private rotateTimer = 0;
  private segment = 0;

  constructor(
    private stream: MediaStream,
    private mime: string,
    private onChunk: (segment: number, seq: number, blob: Blob) => void,
    private onSegmentDone: (segment: number) => void,
    private onError: (message: string) => void,
    private segmentMs = SEGMENT_MS,
  ) {}

  start(firstSegment: number) {
    this.active = this.open(firstSegment);
    this.stream.getAudioTracks().forEach((t) => t.addEventListener('ended', () =>
      this.onError('The microphone was disconnected. Already recorded audio is kept — press Stop, then record more.')));
  }

  private open(segment: number): MediaRecorder {
    const rec = new MediaRecorder(this.stream, { mimeType: this.mime, audioBitsPerSecond: 32000 });
    let seq = 0;
    this.segment = segment;
    rec.ondataavailable = (e) => { if (e.data.size > 0) this.onChunk(segment, seq++, e.data); };
    rec.onerror = () => this.onError('The recorder stopped unexpectedly. Already recorded audio is kept.');
    rec.start(CHUNK_MS);
    this.rotateTimer = window.setTimeout(() => this.rotate(segment), this.segmentMs);
    return rec;
  }

  private rotate(segment: number) {
    const old = this.active!;
    this.active = this.open(segment + 1);
    this.stopping.push(this.finish(old, segment, OVERLAP_MS));
  }

  private finish(rec: MediaRecorder, segment: number, after = 0): Promise<void> {
    return new Promise((resolve) => {
      window.setTimeout(() => {
        if (rec.state === 'inactive') { resolve(); return; }
        rec.addEventListener('stop', () => { this.onSegmentDone(segment); resolve(); }, { once: true });
        rec.stop(); // emits a final dataavailable before 'stop'
      }, after);
    });
  }

  /** Stops recording; resolves once every chunk has been handed to onChunk. */
  async stop() {
    window.clearTimeout(this.rotateTimer);
    if (this.active) await this.finish(this.active, this.segment);
    await Promise.all(this.stopping);
    this.active = null;
    this.stream.getTracks().forEach((t) => t.stop());
  }
}
