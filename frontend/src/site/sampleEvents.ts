// Synthetic sample data for the public Past events / Past talks pages. There is no list endpoint
// yet; the pages read through loadPastEvents() so the API can replace this module later.
// Everything here is invented: no real people, contact details, or résumés.

export type PastTalk = {
  id: string;
  eventId: string;
  title: string;
  speakers: string[];
  track: string;
  time: string;
  abstract: string;
};

export type PastEvent = {
  id: string;
  name: string;
  location: string;
  dates: string;
  attendees: number;
  summary: string;
  talks: PastTalk[];
};

const events: PastEvent[] = [
  {
    id: 'cloud-native-summit-2025',
    name: 'Cloud Native Summit 2025',
    location: 'Denver, CO',
    dates: 'Oct 14–15, 2025',
    attendees: 1840,
    summary: 'Two days of platform engineering, observability, and Kubernetes operations talks across four tracks.',
    talks: [
      { id: 'cns-1', eventId: 'cloud-native-summit-2025', title: 'Debugging eBPF Programs in Production Without Losing Your Mind', speakers: ['Priya Raman'], track: 'Observability', time: 'Tue 10:00 MT', abstract: 'A field guide to tracing kernel-side failures when the only signal you have is a dropped packet counter.' },
      { id: 'cns-2', eventId: 'cloud-native-summit-2025', title: 'Platform Teams Are Product Teams', speakers: ['Marcus Oyelaran', 'Lena Fischer'], track: 'Platform Engineering', time: 'Tue 11:15 MT', abstract: 'How two platform teams rebuilt their roadmap around internal customer interviews and shipped fewer, better golden paths.' },
      { id: 'cns-3', eventId: 'cloud-native-summit-2025', title: 'Vector Search for Operators: Finding the Runbook You Forgot You Wrote', speakers: ['Dmitri Volkov'], track: 'Data', time: 'Tue 14:00 MT', abstract: 'Embedding incident timelines and runbooks so on-call engineers get the right doc in the first thirty seconds.' },
      { id: 'cns-4', eventId: 'cloud-native-summit-2025', title: 'Scaling GitOps Past 500 Clusters', speakers: ['Aisha Bello'], track: 'Platform Engineering', time: 'Wed 09:30 MT', abstract: 'Fleet management patterns, drift detection, and the policy guardrails that kept a multi-region rollout boring.' },
      { id: 'cns-5', eventId: 'cloud-native-summit-2025', title: 'OpenTelemetry Sampling Strategies That Pay for Themselves', speakers: ['Tomás Herrera'], track: 'Observability', time: 'Wed 13:00 MT', abstract: 'Tail-based sampling, cost attribution by service, and what to keep when the bill arrives.' },
    ],
  },
  {
    id: 'pyconf-mountain-2025',
    name: 'PyConf Mountain 2025',
    location: 'Salt Lake City, UT',
    dates: 'Jun 6–8, 2025',
    attendees: 920,
    summary: 'A community Python conference with a heavy data and tooling slant, plus a student hack day.',
    talks: [
      { id: 'pcm-1', eventId: 'pyconf-mountain-2025', title: 'Async Python Without the Footguns', speakers: ['Hannah Oduya'], track: 'Language', time: 'Fri 10:30 MT', abstract: 'Structured concurrency, cancellation, and the five patterns that cover ninety percent of real services.' },
      { id: 'pcm-2', eventId: 'pyconf-mountain-2025', title: 'Type Hints at Scale: Migrating a 400k-Line Monolith', speakers: ['Jun Park', 'Olivia Grant'], track: 'Tooling', time: 'Fri 13:30 MT', abstract: 'Incremental typing, CI gates, and the surprising bugs the checker found along the way.' },
      { id: 'pcm-3', eventId: 'pyconf-mountain-2025', title: 'Building Recommendation Pipelines with Embeddings and a Small Budget', speakers: ['Sofia Mendes'], track: 'Data', time: 'Sat 11:00 MT', abstract: 'From résumé text to ranked suggestions with open models, batch inference, and honest evaluation.' },
      { id: 'pcm-4', eventId: 'pyconf-mountain-2025', title: 'FastAPI in Production: What We Wish We Knew', speakers: ['Ravi Chandran'], track: 'Web', time: 'Sat 14:30 MT', abstract: 'Dependency injection, background tasks, and the observability wiring that made incidents short.' },
    ],
  },
  {
    id: 'devfest-northwest-2025',
    name: 'DevFest Northwest 2025',
    location: 'Portland, OR',
    dates: 'Mar 22, 2025',
    attendees: 610,
    summary: 'A one-day developer festival mixing frontend, infrastructure, and career talks with a lightning-talk evening.',
    talks: [
      { id: 'dfn-1', eventId: 'devfest-northwest-2025', title: 'Accessible by Default: Designing Forms People Can Finish', speakers: ['Imani Walker'], track: 'Frontend', time: 'Sat 09:45 PT', abstract: 'Label everything, respect text scaling, and test with a screen reader before the design review.' },
      { id: 'dfn-2', eventId: 'devfest-northwest-2025', title: 'React Native on the Web: One Codebase, Honest Trade-offs', speakers: ['Noah Lindqvist'], track: 'Frontend', time: 'Sat 11:00 PT', abstract: 'Where shared components shine, where they leak, and how to keep navigation sane without a heavy router.' },
      { id: 'dfn-3', eventId: 'devfest-northwest-2025', title: 'Your First Kubernetes Operator in an Afternoon', speakers: ['Grace Nakamura'], track: 'Infrastructure', time: 'Sat 13:15 PT', abstract: 'Reconcile loops, status conditions, and the testing harness that keeps a hobby operator trustworthy.' },
      { id: 'dfn-4', eventId: 'devfest-northwest-2025', title: 'Talking to Strangers: Getting Value Out of Conferences', speakers: ['Elena Petrova'], track: 'Career', time: 'Sat 16:00 PT', abstract: 'A practical playbook for picking talks, meeting the right people, and following up without being weird.' },
    ],
  },
];

export const sampleDataNotice = 'Sample data: these events and talks are synthetic placeholders until the public listing API is available.';

export async function loadPastEvents(): Promise<PastEvent[]> {
  return events;
}

export async function loadPastTalks(): Promise<PastTalk[]> {
  return events.flatMap((event) => event.talks);
}

export function eventName(eventId: string): string {
  return events.find((event) => event.id === eventId)?.name ?? eventId;
}
