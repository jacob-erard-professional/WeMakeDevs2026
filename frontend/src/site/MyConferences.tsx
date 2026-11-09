import { useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { joinPath } from '../joinLink';
import type { RememberedConference } from '../session';
import { Action, colors, Copy, Heading, Label, Message, styles } from '../ui';
import { paths } from './router';
import { Container } from './SiteShell';

export function MyConferences({ conferences, navigate, onForget }: {
  conferences: RememberedConference[];
  navigate: (path: string) => void;
  onForget: (code: string) => boolean;
}) {
  const [confirm, setConfirm] = useState<string>();
  const [error, setError] = useState('');

  return (
    <Container style={list.page}>
      <Heading large>My conferences</Heading>
      <Copy>Open a conference you’ve joined or pick up where you left off at check-in.</Copy>
      <Action title="Join another conference" onPress={() => navigate(paths.join)} />
      {!conferences.length ? <Message>No conferences here yet. Join with an event code or an organizer’s link.</Message> : null}
      {conferences.map((conference) => (
        <View key={conference.code} style={list.event}>
          <Label>{conference.checkedIn ? 'Checked in' : 'Check-in started'}</Label>
          <Heading>{conference.name}</Heading>
          <View style={styles.row}>
            <Action title={conference.checkedIn ? 'Open my plan' : 'Continue check-in'}
              accessibilityLabel={`${conference.checkedIn ? 'Open my plan for' : 'Continue check-in for'} ${conference.name}`}
              onPress={() => navigate(joinPath(conference.code, conference.checkedIn ? 'plan' : conference.draftStep))} secondary />
            {conference.checkedIn && conference.hasDraft ? (
              <Action title="Resume profile draft" accessibilityLabel={`Resume profile draft for ${conference.name}`}
                onPress={() => navigate(joinPath(conference.code, conference.draftStep))} secondary />
            ) : null}
            {confirm !== conference.code ? (
              <Action title="Forget on this device" accessibilityLabel={`Forget ${conference.name} on this device`}
                onPress={() => { setConfirm(conference.code); setError(''); }} secondary />
            ) : null}
          </View>
          {confirm === conference.code ? (
            <>
              <Copy>This clears the saved check-in and any draft from this device. Your conference profile stays on the server.</Copy>
              <View style={styles.row}>
                <Action title="Forget conference" onPress={() => {
                  if (onForget(conference.code)) setConfirm(undefined);
                  else setError('Wait for your profile to finish saving, then try again.');
                }} secondary />
                <Action title="Keep conference" onPress={() => { setConfirm(undefined); setError(''); }} secondary />
              </View>
              {error ? <Message error>{error}</Message> : null}
            </>
          ) : null}
        </View>
      ))}
    </Container>
  );
}

const list = StyleSheet.create({
  page: { maxWidth: 920, paddingVertical: 48, gap: 22 },
  event: { borderTopWidth: 1, borderColor: colors.chrome, paddingVertical: 16, gap: 6 },
});
