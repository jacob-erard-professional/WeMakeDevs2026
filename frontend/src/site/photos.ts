// The web landing uses the team photo. The native landing uses the credited conference photo.

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
    alt: 'The Conference Connections team working together in Salt Lake City',
    fallback: '#1E1B3A',
  },
  {
    id: 'stage',
    src: unsplash('1582192730841-2a682d7375f9'),
    alt: 'A panel discussion on a stage in a large auditorium with an audience',
    photographer: 'Product School',
    pageUrl: 'https://unsplash.com/photos/panel-discussion-in-large-auditorium-dJICd7b_LlE',
    fallback: '#141428',
  },
];
