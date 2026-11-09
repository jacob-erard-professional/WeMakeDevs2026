// Public site chrome: top nav, scrolling page body, footer with photo credits.
// The body is an Animated.ScrollView whose offset is shared via ScrollOffset for the landing parallax.
import { createContext, useRef, useState } from 'react';
import type { ComponentRef, PropsWithChildren, RefObject } from 'react';
import { Animated, Linking, Pressable, StyleSheet, Text, View, useWindowDimensions } from 'react-native';
import type { ScrollView } from 'react-native';

import { colors, styles } from '../ui';
import { heroPhotos } from './photos';
import { paths } from './router';
import type { Page } from './router';

export const ScrollOffset = createContext<Animated.Value | null>(null);

// Large page/section title with header semantics but without Heading's focus-on-mount, which is
// reserved for the one heading that announces a screen change.
export function SectionTitle({ children }: PropsWithChildren) {
  return <Text accessibilityRole="header" style={[styles.heading, styles.largeHeading]}>{children}</Text>;
}

// Shared page-width container for non-hero content.
export function Container({ children, style }: PropsWithChildren<{ style?: object }>) {
  return <View style={[shell.container, style]}>{children}</View>;
}

const navItems: { page: Page; title: string }[] = [
  { page: 'events', title: 'Past events' },
  { page: 'talks', title: 'Past talks' },
  { page: 'organizers', title: 'Organizers' },
];

function NavLink({ title, current, onPress, brand }: { title: string; current: boolean; onPress: () => void; brand?: boolean }) {
  const [focused, setFocused] = useState(false);
  return (
    <Pressable accessibilityRole="link" aria-current={current ? 'page' : undefined}
      onPress={onPress} onFocus={() => setFocused(true)} onBlur={() => setFocused(false)}
      style={[shell.navLink, focused && shell.focused]}>
      <Text style={[shell.navText, brand && shell.brand, current && !brand && shell.navCurrent]}>{title}</Text>
    </Pressable>
  );
}

export function SiteShell({ page, navigate, scrollRef, children }: PropsWithChildren<{
  page: Page;
  navigate: (path: string) => void;
  scrollRef: RefObject<ComponentRef<typeof ScrollView> | null>;
}>) {
  const scrollY = useRef(new Animated.Value(0)).current;
  const { width } = useWindowDimensions();
  const compact = width < 720;
  const [menuOpen, setMenuOpen] = useState(false);

  function go(target: Page) {
    setMenuOpen(false);
    navigate(paths[target]);
  }

  const links = navItems.map((item) => (
    <NavLink key={item.page} title={item.title} current={page === item.page} onPress={() => go(item.page)} />
  ));

  return (
    <View style={shell.screen}>
      <View role="navigation" style={shell.nav}>
        <View style={shell.navRow}>
          <NavLink title="Conference Connections" brand current={page === 'home'} onPress={() => go('home')} />
          {!compact ? <View style={shell.navLinks}>{links}</View> : null}
          <View style={shell.navActions}>
            <Pressable accessibilityRole="button" onPress={() => go('join')} style={({ pressed }) => [shell.joinButton, pressed && shell.dimmed]}>
              <Text style={shell.joinText}>Join an event</Text>
            </Pressable>
            {compact ? (
              <Pressable accessibilityRole="button" accessibilityLabel={menuOpen ? 'Close menu' : 'Open menu'}
                aria-expanded={menuOpen} onPress={() => setMenuOpen((open) => !open)} style={shell.menuButton}>
                <Text style={shell.menuText}>{menuOpen ? 'Close' : 'Menu'}</Text>
              </Pressable>
            ) : null}
          </View>
        </View>
        {compact && menuOpen ? <View style={shell.menu}>{links}</View> : null}
      </View>

      <Animated.ScrollView ref={scrollRef as never} keyboardShouldPersistTaps="handled" scrollEventThrottle={16}
        onScroll={Animated.event([{ nativeEvent: { contentOffset: { y: scrollY } } }], { useNativeDriver: false })}
        contentContainerStyle={shell.body}>
        <ScrollOffset.Provider value={scrollY}>
          <View style={shell.page}>{children}</View>
        </ScrollOffset.Provider>
        <Footer onNavigate={go} />
      </Animated.ScrollView>
    </View>
  );
}

function Footer({ onNavigate }: { onNavigate: (page: Page) => void }) {
  return (
    <View role="contentinfo" style={shell.footer}>
      <Container style={shell.footerInner}>
        <View style={shell.footerLinks}>
          <NavLink title="Home" current={false} onPress={() => onNavigate('home')} />
          {navItems.map((item) => (
            <NavLink key={item.page} title={item.title} current={false} onPress={() => onNavigate(item.page)} />
          ))}
          <NavLink title="Join an event" current={false} onPress={() => onNavigate('join')} />
        </View>
        <Text style={shell.credits}>
          Photos on Unsplash by{' '}
          {heroPhotos.map((photo, index) => (
            <Text key={photo.id}>
              <Text accessibilityRole="link" style={shell.creditLink} onPress={() => Linking.openURL(photo.pageUrl)}>
                {photo.photographer}
              </Text>
              {index < heroPhotos.length - 2 ? ', ' : index === heroPhotos.length - 2 ? ' and ' : ''}
            </Text>
          ))}
          . Demo session: nothing here is stored.
        </Text>
      </Container>
    </View>
  );
}

const shell = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.paper },
  nav: { backgroundColor: colors.night, paddingHorizontal: 16, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: colors.nightSoft },
  navRow: { width: '100%', maxWidth: 1180, alignSelf: 'center', flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', columnGap: 16, flexWrap: 'wrap', rowGap: 8 },
  navLinks: { flexDirection: 'row', alignItems: 'center', columnGap: 4, flexShrink: 1, flexWrap: 'wrap' },
  navActions: { flexDirection: 'row', alignItems: 'center', columnGap: 8 },
  navLink: { paddingHorizontal: 10, paddingVertical: 10, borderRadius: 8, minHeight: 44, justifyContent: 'center' },
  navText: { color: colors.onNightMuted, fontSize: 16, fontWeight: '600' },
  navCurrent: { color: colors.onNight, textDecorationLine: 'underline' },
  brand: { color: colors.onNight, fontSize: 18, fontWeight: '800', letterSpacing: -0.5 },
  focused: { outlineColor: colors.glow, outlineWidth: 2, outlineOffset: 2, outlineStyle: 'solid' },
  joinButton: { minHeight: 44, justifyContent: 'center', paddingHorizontal: 16, backgroundColor: colors.glow, borderRadius: 999 },
  joinText: { color: colors.night, fontWeight: '800', fontSize: 15 },
  menuButton: { minHeight: 44, justifyContent: 'center', paddingHorizontal: 12, borderRadius: 8, borderWidth: 1, borderColor: colors.onNightMuted },
  menuText: { color: colors.onNight, fontWeight: '700', fontSize: 15 },
  menu: { paddingTop: 8, gap: 2 },
  dimmed: { opacity: 0.8 },
  body: { flexGrow: 1 },
  page: { flexGrow: 1 },
  container: { width: '100%', maxWidth: 1180, alignSelf: 'center', paddingHorizontal: 24 },
  footer: { backgroundColor: colors.night, paddingVertical: 36, marginTop: 48 },
  footerInner: { gap: 20 },
  footerLinks: { flexDirection: 'row', flexWrap: 'wrap', columnGap: 8, rowGap: 4, marginLeft: -10 },
  credits: { color: colors.onNightMuted, fontSize: 14, lineHeight: 22 },
  creditLink: { color: colors.onNight, textDecorationLine: 'underline' },
});
