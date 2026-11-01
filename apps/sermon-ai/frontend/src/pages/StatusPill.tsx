import type { Status } from '../api';

const LABEL: Record<Status, [string, string]> = {
  recording: ['Recording', 'pill-rec'],
  recorded: ['Recorded', 'pill-info'],
  transcribing: ['Transcribing…', 'pill-busy'],
  transcribed: ['Transcribed', 'pill-info'],
  analyzing: ['Writing reports…', 'pill-busy'],
  done: ['Reports ready', 'pill-ok'],
};

export function StatusPill({ status }: { status: Status }) {
  const [label, cls] = LABEL[status] ?? [status, 'pill-info'];
  return <span className={`pill ${cls}`}>{label}</span>;
}
