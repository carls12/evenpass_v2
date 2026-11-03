import type { IconName } from '../components/Icon';

export type AppStatus = 'available' | 'coming-soon' | 'planned';

export interface PlatformApp {
  id: string;
  name: string;
  description: string;
  status: AppStatus;
  icon: IconName;
  /** Entry URL. Only set for apps that are actually deployed — others render without a link. */
  href?: string;
  /** For available apps: what exists today. For future apps: the planned scope (labelled as such). */
  highlights: string[];
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
    description: 'Event registration, badge generation and QR check-in management.',
    status: 'available',
    icon: 'ticket',
    href: '/eventpass/',
    highlights: ['Online registration with custom fields', 'Printable PDF badges & A4 sheets', 'QR check-in with any phone camera', 'Temporary access for gate staff'],
  },
  {
    id: 'sermon-ai',
    name: 'Sermon Intelligence',
    description: 'AI-powered sermon transcription, translation and structured reporting.',
    status: 'available',
    icon: 'waveform',
    href: '/sermon-ai/',
    highlights: ['Record sermons right in the browser', 'Transcription in English, French and German', 'Structured reports & full translations', 'Export as PDF or Markdown'],
  },
  {
    // Separate repository (carls12/bodyofchrist-django). Becomes "available" by itself as soon as it
    // runs on the server (COMPOSE_PROFILES=bodyofchrist): the portal asks its health URL.
    id: 'bodyofchrist',
    name: 'Body of Christ',
    description: 'Spiritual growth tracking for assemblies: goals, prayer, Bible reading and reports.',
    status: 'coming-soon',
    icon: 'heart',
    probe: { url: '/bodyofchrist/healthz', href: '/bodyofchrist/' },
    highlights: ['Weekly goals, prayer timer and Bible reading log', 'Assemblies with leaders and group chat', 'Prayer chain, quizzes and calendar', 'PDF reports for leaders'],
  },
  {
    id: 'bible-study',
    name: 'Bible Study',
    description: 'Digital Bible study and learning resources.',
    status: 'planned',
    icon: 'book',
    highlights: ['Study plans and resources', 'Group learning'],
  },
];

export const STATUS_LABEL: Record<AppStatus, string> = {
  available: 'Available',
  'coming-soon': 'Coming Soon',
  planned: 'Planned',
};
