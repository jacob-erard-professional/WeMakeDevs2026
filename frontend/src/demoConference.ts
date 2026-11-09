import { parseSchedule } from './conference';
import type { Conference } from './conference';

export const sampleSchedule = [
  '10:00 | 10:45 | Building accessible internal platforms | Accessibility | Summit Room',
  '10:15 | 11:00 | Practical eBPF for platform teams | Kubernetes | Wasatch Room',
  '11:15 | 12:00 | Tracing requests across Kubernetes | Observability | Summit Room',
  '13:00 | 13:45 | Make your first open source contribution | Open source | Wasatch Room',
  '14:00 | 14:45 | Incident response with better signals | Observability | Summit Room',
].join('\n');

export const demoConference: Conference = {
  name: 'Cloud Native Conference',
  code: 'cloud-native',
  talks: parseSchedule(sampleSchedule).talks,
};

export const demoPeople = [
  { id: 'alex', name: 'Alex Rivera', role: 'Developer experience engineer', topics: ['Accessibility', 'Open source'], opener: 'Ask Alex about making developer tools easier to use.' },
  { id: 'sam', name: 'Sam Okafor', role: 'Platform engineer', topics: ['Kubernetes', 'Observability'], opener: 'Ask Sam what made their Kubernetes debugging workflow faster.' },
  { id: 'jules', name: 'Jules Park', role: 'Site reliability engineer', topics: ['Observability', 'Open source'], opener: 'Ask Jules how their team chooses which signals to alert on.' },
];
