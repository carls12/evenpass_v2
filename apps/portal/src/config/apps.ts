import type { IconName } from '../components/Icon';
import type { Key } from '../i18n/en';

export type AppStatus = 'available' | 'coming-soon' | 'planned';

export interface PlatformApp {
  id: string;
  name: string;
  description: Key;
  status: AppStatus;
  icon: IconName;
  /** Entry URL. Only set for apps that are actually deployed — others render without a link. */
  href?: string;
  /** For available apps: what exists today. For future apps: the planned scope (labelled as such). */
  highlights: Key[];
  /** Health URL: when it answers, the app is shown as available (for apps that are switched on per server). */
  probe?: { url: string; href: string };
}

/**
 * The application registry. To add an app to the platform, add an entry here and
 * a matching route in infrastructure/caddy/Caddyfile.
 */
export const APPS: PlatformApp[] = [
  {
    id: 'eventpass',
    name: 'EventPass Studio',
    description: 'app.eventpass.description',
    status: 'available',
    icon: 'ticket',
    href: '/eventpass/',
    highlights: ['app.eventpass.h1', 'app.eventpass.h2', 'app.eventpass.h3', 'app.eventpass.h4'],
  },
  {
    id: 'sermon-ai',
    name: 'Sermon Intelligence',
    description: 'app.sermon-ai.description',
    status: 'available',
    icon: 'waveform',
    href: '/sermon-ai/',
    highlights: ['app.sermon-ai.h1', 'app.sermon-ai.h2', 'app.sermon-ai.h3', 'app.sermon-ai.h4'],
  },
  {
    // Separate repository (carls12/bodyofchrist-django). Becomes "available" by itself as soon as it
    // runs on the server (COMPOSE_PROFILES=bodyofchrist): the portal asks its health URL.
    id: 'bodyofchrist',
    name: 'Body of Christ',
    description: 'app.bodyofchrist.description',
    status: 'coming-soon',
    icon: 'heart',
    probe: { url: '/bodyofchrist/healthz', href: '/bodyofchrist/' },
    highlights: ['app.bodyofchrist.h1', 'app.bodyofchrist.h2', 'app.bodyofchrist.h3', 'app.bodyofchrist.h4'],
  },
  {
    // Windows desktop program (separate repository carls12/churchprojectionapp), offered as a download.
    id: 'projection',
    name: 'ChurchProjection Studio',
    description: 'app.projection.description',
    status: 'coming-soon',
    icon: 'screen',
    highlights: ['app.projection.h1', 'app.projection.h2', 'app.projection.h3', 'app.projection.h4'],
  },
  {
    id: 'bible-study',
    name: 'Bible Study',
    description: 'app.bible-study.description',
    status: 'planned',
    icon: 'book',
    highlights: ['app.bible-study.h1', 'app.bible-study.h2'],
  },
];

export const STATUS_KEY: Record<AppStatus, Key> = {
  available: 'status.available',
  'coming-soon': 'status.coming-soon',
  planned: 'status.planned',
};
