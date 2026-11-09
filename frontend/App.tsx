import { StatusBar } from 'expo-status-bar';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';

import type { Recommendation } from './src/conference';
import { demoConference } from './src/demoConference';

function RecommendationSection({
  heading,
  recommendations,
}: {
  heading: string;
  recommendations: Recommendation[];
}) {
  return (
    <View style={styles.section}>
      <Text accessibilityRole="header" style={styles.heading}>{heading}</Text>
      {recommendations.map(({ id, title, reason }) => (
        <View key={id} style={styles.card}>
          <Text style={styles.title}>{title}</Text>
          <Text style={styles.body}>{reason}</Text>
        </View>
      ))}
    </View>
  );
}

export default function App() {
  return (
    <SafeAreaProvider>
      <SafeAreaView style={styles.screen}>
        <StatusBar style="dark" />
        <ScrollView contentContainerStyle={styles.content}>
          <Text style={styles.body}>Demo preview · Sample data</Text>
          <Text accessibilityRole="header" style={styles.hero}>{demoConference.name}</Text>
          <Text style={styles.body}>Find talks to attend and people to meet.</Text>
          <RecommendationSection heading="Talks to attend" recommendations={demoConference.talks} />
          <RecommendationSection heading="People to meet" recommendations={demoConference.people} />
        </ScrollView>
      </SafeAreaView>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: '#F1F5F9' },
  content: { width: '100%', maxWidth: 720, alignSelf: 'center', padding: 24, gap: 12 },
  hero: { fontSize: 36, fontWeight: '700', color: '#0F172A' },
  section: { marginTop: 16, gap: 8 },
  heading: { fontSize: 24, fontWeight: '700', color: '#0F172A' },
  card: { padding: 16, borderRadius: 12, backgroundColor: '#FFFFFF', gap: 6 },
  title: { fontSize: 18, fontWeight: '600', color: '#0F172A' },
  body: { fontSize: 16, color: '#334155' },
});
