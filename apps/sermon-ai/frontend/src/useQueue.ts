import { useEffect, useState } from 'react';
import { subscribe, type QueueState } from './uploadQueue';

export function useQueue() {
  const [state, setState] = useState<QueueState | null>(null);
  useEffect(() => subscribe(setState), []);
  return state;
}
