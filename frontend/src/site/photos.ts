// Landing-page photography. All photos are from Unsplash under the Unsplash License, which
// allows free use and hotlinking from images.unsplash.com. Verified to return HTTP 200 on 2026-11-09.
// Each photo carries a fallback colour so headline text stays readable if the image fails.

export type Photo = {
  id: string;
  src: string;
  alt: string;
  // Unsplash photos are credited in the footer; our own team photo has no credit line.
  photographer?: string;
  pageUrl?: string;
  fallback: string;
};

function unsplash(id: string, width = 1800): string {
  return `https://images.unsplash.com/photo-${id}?w=${width}&q=70&auto=format&fit=crop`;
}

export const heroPhotos: Photo[] = [
  {
    id: 'team',
    src: '/hackathon-team.jpg',
    alt: 'Our team hacking on laptops around a coffee table in Salt Lake City',
    fallback: '#1E1B3A',
  },
  {
    id: 'whiteboard',
    src: unsplash('1758873269117-d5845126928a'),
    alt: 'A team collaborating around a whiteboard in an office',
    photographer: 'Vitaly Gariev',
    pageUrl: 'https://unsplash.com/photos/team-collaborating-around-a-whiteboard-in-an-office-CdTQI-Nh7J4',
    fallback: '#2A1F4A',
  },
  {
    id: 'stage',
    src: unsplash('1582192730841-2a682d7375f9'),
    alt: 'A panel discussion on a stage in a large auditorium with an audience',
    photographer: 'Product School',
    pageUrl: 'https://unsplash.com/photos/panel-discussion-in-large-auditorium-dJICd7b_LlE',
    fallback: '#141428',
  },
  {
    id: 'pizza',
    src: unsplash('1632657604272-bc2295c56389'),
    alt: 'A stack of pizza boxes on a table, late-night hackathon fuel',
    photographer: 'Mathias Reding',
    pageUrl: 'https://unsplash.com/photos/a-stack-of-pizza-boxes-sitting-on-top-of-a-table-0R8IhuzfsOk',
    fallback: '#3A1E2E',
  },
  {
    id: 'pairing',
    src: unsplash('1759884247144-53d52c31f859'),
    alt: 'Two people working side by side on laptops at a table',
    photographer: 'Compagnons',
    pageUrl: 'https://unsplash.com/photos/two-people-working-on-laptops-at-a-table-ak4hmkNSU8g',
    fallback: '#1B2A3A',
  },
];
