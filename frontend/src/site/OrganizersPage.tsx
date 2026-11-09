// Organizer pitch followed by the existing Organizer tool (passed in unchanged as children).
import type { PropsWithChildren } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { Copy, Label, colors } from '../ui';
import { Container, SectionTitle } from './SiteShell';

function Point({ title, children }: PropsWithChildren<{ title: string }>) {
  return (
    <View style={pitch.point}>
      <Text accessibilityRole="header" style={pitch.pointTitle}>{title}</Text>
      <Copy>{children}</Copy>
    </View>
  );
}

export function OrganizersPage({ children }: PropsWithChildren) {
  return (
    <Container style={pitch.block}>
      <Label>Organizers</Label>
      <SectionTitle>Load your schedule. Share one link.</SectionTitle>
      <View style={pitch.row}>
        <Point title="Load your schedule">Paste the talk list and review the parsed preview before publishing. Fix titles, speakers, and times in place.</Point>
        <Point title="Share one link or QR">Put it on the event page and the badge table. Attendees land on your event's check-in without an app or account.</Point>
        <Point title="See who'd enjoy each talk">Recommendations are built from the schedule you load, so you can see which talks draw which interests as people join.</Point>
      </View>
      <View style={pitch.tool}>{children}</View>
    </Container>
  );
}

const pitch = StyleSheet.create({
  block: { paddingVertical: 56, gap: 22 },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: 20 },
  point: { flexBasis: 260, flexGrow: 1, flexShrink: 1, gap: 10, padding: 22, backgroundColor: colors.pale, borderRadius: 14 },
  pointTitle: { color: colors.ink, fontSize: 20, fontWeight: '700', letterSpacing: -0.3, lineHeight: 26 },
  tool: { marginTop: 24, paddingTop: 36, borderTopWidth: 1, borderTopColor: colors.pale },
});
