// Landing-page photography. All photos are from Unsplash under the Unsplash License, which
// allows free use and hotlinking from images.unsplash.com. Verified to return HTTP 200 on 2026-11-09.
// Each photo carries a fallback colour so headline text stays readable if the image fails.

export type Photo = {
  id: string;
  src: string;
  alt: string;
  photographer: string;
  pageUrl: string;
  fallback: string;
};

function unsplash(id: string, width = 1800): string {
  return `https://images.unsplash.com/photo-${id}?w=${width}&q=70&auto=format&fit=crop`;
}

export const heroPhotos: Photo[] = [
  {
    id: 'stage',
    src: unsplash('1582192730841-2a682d7375f9'),
    alt: 'A panel discussion on a stage in a large auditorium with an audience',
    photographer: 'Product School',
    pageUrl: 'https://unsplash.com/photos/panel-discussion-in-large-auditorium-dJICd7b_LlE',
    fallback: '#141428',
  },
];
