// Landing page: parallax photo bands with headline copy, plus How it works / What it does / Sign up.
import { useContext, useState } from 'react';
import type { PropsWithChildren } from 'react';
import { Animated, Image, Pressable, StyleSheet, Text, View, useWindowDimensions } from 'react-native';

import { useReduceMotion } from '../Flow';
import { parseJoinCode } from '../joinLink';
import { Action, Copy, Field, Label, Message, colors, styles } from '../ui';
import type { Photo } from './photos';
import { heroPhotos } from './photos';
import { paths } from './router';
import { Container, ScrollOffset, SectionTitle } from './SiteShell';

const PARALLAX = 0.28; // image moves at this fraction of scroll speed

function Band({ photo, tall, children }: PropsWithChildren<{ photo: Photo; tall?: boolean }>) {
  const scrollY = useContext(ScrollOffset);
  const reduceMotion = useReduceMotion();
  const { height: viewport } = useWindowDimensions();
  const [top, setTop] = useState(0);
  const [bandHeight, setBandHeight] = useState(tall ? 640 : 420);
  const [failed, setFailed] = useState(false);

  const parallax = !reduceMotion && scrollY;
  const bleed = parallax ? bandHeight * PARALLAX : 0;
  const translateY = parallax
    ? scrollY.interpolate({
        inputRange: [top - viewport, top + bandHeight],
        outputRange: [-bleed, bleed],
        extrapolate: 'clamp',
      })
    : 0;

  return (
    <View style={[band.wrap, tall && band.tall, { backgroundColor: photo.fallback }]}
      onLayout={(event) => { setTop(event.nativeEvent.layout.y); setBandHeight(event.nativeEvent.layout.height); }}>
      {!failed ? (
        <Animated.View style={[band.imageLayer, { top: -bleed, bottom: -bleed, transform: [{ translateY }] }]}>
          <Image source={{ uri: photo.src }} accessibilityLabel={photo.alt} alt={photo.alt}
            resizeMode="cover" style={band.image} onError={() => setFailed(true)} />
        </Animated.View>
      ) : null}
      <View style={band.scrim} />
      <Container style={band.content}>{children}</Container>
    </View>
  );
}

// Buttons for use over dark photo bands: the light primary/secondary pair keeps contrast on the scrim.
function BandAction({ title, onPress, secondary }: { title: string; onPress: () => void; secondary?: boolean }) {
  const [focused, setFocused] = useState(false);
  return (
    <Pressable accessibilityRole="button" onPress={onPress} onFocus={() => setFocused(true)} onBlur={() => setFocused(false)}
      style={({ pressed }) => [band.button, secondary && band.buttonSecondary, focused && band.focused, pressed && band.pressed]}>
      <Text style={[band.buttonText, secondary && band.buttonTextSecondary]}>{title}</Text>
    </Pressable>
  );
}

function Step({ number, title, children }: PropsWithChildren<{ number: number; title: string }>) {
  return (
    <View style={grid.card}>
      <Text style={grid.number}>{number}</Text>
      <Text accessibilityRole="header" style={grid.cardTitle}>{title}</Text>
      <Copy>{children}</Copy>
    </View>
  );
}

function Feature({ title, children }: PropsWithChildren<{ title: string }>) {
  return (
    <View style={grid.feature}>
      <Text accessibilityRole="header" style={grid.cardTitle}>{title}</Text>
      <Copy>{children}</Copy>
    </View>
  );
}

export function Landing({ navigate }: { navigate: (path: string) => void }) {
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [hero, whiteboard, stage, pizza, pairing] = heroPhotos;

  function openEvent() {
    const parsed = parseJoinCode(code);
    if (!parsed) { setError('Enter the event code from the event page, or paste the full join link.'); return; }
    navigate(`${paths.join}/${encodeURIComponent(parsed)}`);
  }

  return (
    <View>
      <Band photo={hero} tall>
        <Text style={band.label}>Conference Connections</Text>
        <Text accessibilityRole="header" style={band.headline}>Find your people at the conference.</Text>
        <Text style={band.lede}>
          Upload a résumé and a short bio, tell us what you want to see, and get a ranked talk plan and a list of
          people worth meeting, each with a reason.
        </Text>
        <View style={styles.row}>
          <BandAction title="Join an event" onPress={() => navigate(paths.join)} />
          <BandAction title="See past talks" onPress={() => navigate(paths.talks)} secondary />
        </View>
      </Band>

      <Container style={section.block}>
        <Label>How it works</Label>
        <SectionTitle>Four steps from schedule to plan.</SectionTitle>
        <View style={grid.row}>
          <Step number={1} title="Organizer loads the schedule">
            Paste or import the talk list once. Talks are embedded and indexed so recommendations are ready before doors open.
          </Step>
          <Step number={2} title="Attendees open the link or QR">
            The event page and printed QR codes point at the event's join link. No app install, no account.
          </Step>
          <Step number={3} title="Fill in name, résumé, bio and interests">
            Add the times you can't make it. Your résumé stays private by default.
          </Step>
          <Step number={4} title="Get a ranked plan and people to meet">
            Every talk and person comes with a short reason, so you can tell at a glance why it made the list.
          </Step>
        </View>
      </Container>

      <Band photo={whiteboard}>
        <Text accessibilityRole="header" style={band.quote}>The hallway track, with a map.</Text>
      </Band>

      <Container style={section.block}>
        <Label>What it does</Label>
        <SectionTitle>Recommendations that explain themselves.</SectionTitle>
        <View style={grid.row}>
          <Feature title="Talk recommendations around your day">
            Ranked by fit with your background and what you said you want to learn, skipping anything in your blockout times and avoiding overlaps.
          </Feature>
          <Feature title="People matching">
            Meet attendees with complementary interests or shared problems. Each suggestion says why, and you decide whether to reach out.
          </Feature>
          <Feature title="Related past talks">
            Vector search across 24,000 archived KubeCon and PyVideo talks surfaces recordings that go deeper on what you're here for.
          </Feature>
          <Feature title="Private by default">
            Your résumé is private unless you choose otherwise. Contact details and résumés are shared only after both people accept a connection.
          </Feature>
        </View>
      </Container>

      <Band photo={stage}>
        <Text accessibilityRole="header" style={band.quote}>Skip the talks you'd have slept through.</Text>
      </Band>

      <Container style={section.block}>
        <Label>How to sign up for an event</Label>
        <SectionTitle>Two ways in.</SectionTitle>
        <View style={grid.row}>
          <View style={grid.feature}>
            <Text accessibilityRole="header" style={grid.cardTitle}>Open the link or scan the QR</Text>
            <Copy>
              Every event page and printed QR code links to a join page for that event. Opening it drops you straight into check-in for the right event.
            </Copy>
          </View>
          <View style={grid.feature}>
            <Text accessibilityRole="header" style={grid.cardTitle}>Or enter the event code</Text>
            <Field label="Event code" autoCapitalize="none" autoCorrect={false} value={code} maxLength={100}
              placeholder="e.g. cnh-slc-2026" onChangeText={(value) => { setCode(value); setError(''); }} onSubmitEditing={openEvent} />
            {error ? <Message error>{error}</Message> : null}
            <Action title="Open event" onPress={openEvent} />
          </View>
        </View>
      </Container>

      <Band photo={pizza}>
        <Text accessibilityRole="header" style={band.quote}>Built at a hackathon. Runs at yours.</Text>
        <Text style={band.lede}>Organizers load a schedule and share one link. That's the whole setup.</Text>
        <View style={styles.row}>
          <BandAction title="For organizers" onPress={() => navigate(paths.organizers)} />
        </View>
      </Band>

      <Band photo={pairing}>
        <Text accessibilityRole="header" style={band.quote}>Make the most of the days you're here.</Text>
        <View style={styles.row}>
          <BandAction title="Join an event" onPress={() => navigate(paths.join)} />
        </View>
      </Band>
    </View>
  );
}

const band = StyleSheet.create({
  wrap: { width: '100%', minHeight: 420, overflow: 'hidden', justifyContent: 'center', paddingVertical: 72 },
  tall: { minHeight: 640, paddingVertical: 96 },
  imageLayer: { position: 'absolute', left: 0, right: 0 },
  image: { width: '100%', height: '100%' },
  scrim: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(15, 15, 26, 0.58)' },
  content: { gap: 22 },
  label: { color: colors.glow, fontSize: 14, fontWeight: '700', letterSpacing: 0.3 },
  button: { minHeight: 48, justifyContent: 'center', paddingHorizontal: 22, backgroundColor: colors.glow, borderRadius: 999 },
  buttonSecondary: { backgroundColor: 'transparent', borderWidth: 2, borderColor: colors.onNight },
  buttonText: { color: colors.night, fontWeight: '800', fontSize: 16 },
  buttonTextSecondary: { color: colors.onNight },
  focused: { outlineColor: colors.onNight, outlineWidth: 2, outlineOffset: 3, outlineStyle: 'solid' },
  pressed: { opacity: 0.8 },
  headline: { color: colors.onNight, fontSize: 56, lineHeight: 62, fontWeight: '800', letterSpacing: -2.5, maxWidth: 760, textShadowColor: 'rgba(0,0,0,0.5)', textShadowRadius: 12 },
  quote: { color: colors.onNight, fontSize: 38, lineHeight: 44, fontWeight: '800', letterSpacing: -1.5, maxWidth: 720, textShadowColor: 'rgba(0,0,0,0.5)', textShadowRadius: 12 },
  lede: { color: colors.onNight, fontSize: 19, lineHeight: 29, maxWidth: 640, textShadowColor: 'rgba(0,0,0,0.6)', textShadowRadius: 8 },
});

const section = StyleSheet.create({
  block: { paddingVertical: 72, gap: 26 },
});

const grid = StyleSheet.create({
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: 20, marginTop: 8 },
  card: { flexBasis: 240, flexGrow: 1, flexShrink: 1, gap: 10, padding: 22, backgroundColor: colors.white, borderRadius: 14, borderWidth: 1, borderColor: colors.pale },
  feature: { flexBasis: 300, flexGrow: 1, flexShrink: 1, gap: 12, padding: 22, backgroundColor: colors.pale, borderRadius: 14 },
  number: { color: colors.accent, fontSize: 34, fontWeight: '800', letterSpacing: -1 },
  cardTitle: { color: colors.ink, fontSize: 20, fontWeight: '700', letterSpacing: -0.3, lineHeight: 26 },
});
