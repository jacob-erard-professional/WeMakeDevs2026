// A conference landing page with separate attendee and organizer entry points.
import { useContext, useState } from 'react';
import type { PropsWithChildren } from 'react';
import { Animated, Image, Platform, Pressable, StyleSheet, Text, View, useWindowDimensions } from 'react-native';

import { useReduceMotion } from '../Flow';
import { Action, Copy, Label, colors, styles } from '../ui';
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

function BandAction({ title, onPress }: { title: string; onPress: () => void }) {
  const [focused, setFocused] = useState(false);
  return (
    <Pressable accessibilityRole="button" onPress={onPress} onFocus={() => setFocused(true)} onBlur={() => setFocused(false)}
      style={({ pressed }) => [band.button, focused && band.focused, pressed && band.pressed]}>
      <Text style={band.buttonText}>{title}</Text>
    </Pressable>
  );
}

export function Landing({ navigate }: { navigate: (path: string) => void }) {
  const hero = Platform.OS === 'web' ? heroPhotos[0] : heroPhotos[1];

  return (
    <View>
      <Band photo={hero} tall>
        <Text style={band.label}>Conference Connections</Text>
        <Text accessibilityRole="header" style={band.headline}>Make more of your conference.</Text>
        <Text style={band.lede}>
          Give attendees a way to find the right sessions and people. Give organizers one link to bring everyone in.
        </Text>
        <View style={styles.row}>
          <BandAction title="I am an attendee" onPress={() => navigate(paths.join)} />
          <BandAction title="I am an organizer" onPress={() => navigate(paths.organizers)} />
        </View>
      </Band>

      <Container style={section.block}>
        <Label>Choose your path</Label>
        <View style={section.paths}>
          <View style={section.path}>
            <SectionTitle>Attending?</SectionTitle>
            <Copy>Open your organizer’s link or enter your event code. Explore the schedule, find relevant past talks, and meet people who share your interests.</Copy>
            <Action title="Join a conference" onPress={() => navigate(paths.join)} secondary />
          </View>
          <View style={section.path}>
            <SectionTitle>Organizing?</SectionTitle>
            <Copy>Bring your schedule, review the sessions, and share a join link or a QR code attendees can scan from the room.</Copy>
            <Action title="Set up a conference" onPress={() => navigate(paths.organizers)} secondary />
          </View>
        </View>
      </Container>
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
  buttonText: { color: colors.night, fontWeight: '800', fontSize: 16 },
  focused: { outlineColor: colors.onNight, outlineWidth: 2, outlineOffset: 3, outlineStyle: 'solid' },
  pressed: { opacity: 0.8 },
  headline: { color: colors.onNight, fontSize: 56, lineHeight: 62, fontWeight: '800', letterSpacing: -2.5, maxWidth: 760, textShadowColor: 'rgba(0,0,0,0.5)', textShadowRadius: 12 },
  lede: { color: colors.onNight, fontSize: 19, lineHeight: 29, maxWidth: 640, textShadowColor: 'rgba(0,0,0,0.6)', textShadowRadius: 8 },
});

const section = StyleSheet.create({
  block: { paddingVertical: 64, gap: 26 },
  paths: { flexDirection: 'row', flexWrap: 'wrap', columnGap: 64, rowGap: 30 },
  path: { flexBasis: 290, flexGrow: 1, flexShrink: 1, gap: 12 },
});
