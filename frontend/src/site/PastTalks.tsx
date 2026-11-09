import { useState } from 'react';
import { StyleSheet, View } from 'react-native';

import type { CatalogSource } from '../api';
import { Action, Field, Heading, styles } from '../ui';
import { CatalogTalks } from './CatalogTalks';
import { Container } from './SiteShell';

export function PastTalks({ onBrowseSchedule, onConference }: {
  onBrowseSchedule: () => void;
  onConference: (id: string) => void;
}) {
  const [text, setText] = useState('');
  const [query, setQuery] = useState('');
  const [source, setSource] = useState<CatalogSource>('published');

  function search() {
    setQuery(text.trim());
  }

  return (
    <Container style={page.block}>
      <Heading large>Search Talks</Heading>
      <Field label="Search talks, speakers, or topics" value={text} onChangeText={setText} maxLength={160}
        autoCorrect={false} returnKeyType="search" onSubmitEditing={search} />
      <View style={styles.row}>
        <Action title="Search" onPress={search} />
        <Action title="Browse my event schedule" onPress={onBrowseSchedule} secondary />
      </View>
      <View style={styles.row}>
        <Action title="Conference schedules" selected={source === 'published'} onPress={() => setSource('published')} secondary />
        <Action title="Historical talks" selected={source === 'archive'} onPress={() => setSource('archive')} secondary />
      </View>
      <CatalogTalks key={`${source}:${query}`} source={source} query={query} onConference={onConference} />
    </Container>
  );
}

const page = StyleSheet.create({
  block: { paddingVertical: 48, maxWidth: 920, gap: 20 },
});
