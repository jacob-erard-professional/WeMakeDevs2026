export type Recommendation = {
  id: string;
  title: string;
  reason: string;
};

export type ConferencePreview = {
  name: string;
  talks: Recommendation[];
  people: Recommendation[];
};
