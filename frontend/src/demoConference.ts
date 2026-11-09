import type { ConferencePreview } from './conference';

export const demoConference: ConferencePreview = {
  name: 'Cloud Native Hackathon',
  talks: [
    {
      id: 'talk-platforms',
      title: 'Building accessible internal platforms',
      reason: 'Matches your interest in accessibility and developer tooling.',
    },
  ],
  people: [
    {
      id: 'attendee-demo',
      title: 'Alex Rivera',
      reason: 'You both work on developer tools and want to share accessibility practices.',
    },
  ],
};
