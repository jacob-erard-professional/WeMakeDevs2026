import type { PropsWithChildren } from 'react';
import { StyleSheet } from 'react-native';

import { Copy, Label } from '../ui';
import { Container, SectionTitle } from './SiteShell';

export function OrganizersPage({ children }: PropsWithChildren) {
  return <Container style={page.block}>{children}</Container>;
}

// Shown while setting up; the published pass screen keeps the page quiet.
export function OrganizerIntro() {
  return (
    <>
      <Label>For organizers</Label>
      <SectionTitle>Set up your conference.</SectionTitle>
      <Copy>Add event details and sessions, then share one link or display a QR code for attendee check-in.</Copy>
    </>
  );
}

const page = StyleSheet.create({ block: { paddingVertical: 48, gap: 24 } });
