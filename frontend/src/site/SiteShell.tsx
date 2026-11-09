import { useState } from 'react';
import type { ComponentRef, PropsWithChildren, RefObject } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View, useWindowDimensions } from 'react-native';

import { colors, styles } from '../ui';
import { paths } from './router';
import type { Page } from './router';

// Large page/section title with header semantics but without Heading's focus-on-mount, which is
// reserved for the one heading that announces a screen change.
export function SectionTitle({ children }: PropsWithChildren) {
  return <Text accessibilityRole="header" style={[styles.heading, styles.largeHeading]}>{children}</Text>;
}

// Shared page-width container.
export function Container({ children, style }: PropsWithChildren<{ style?: object }>) {
  return <View style={[shell.container, style]}>{children}</View>;
}

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
  const { width } = useWindowDimensions();
  const compact = width < 540;
  const [viewportHeight, setViewportHeight] = useState(0);

  function go(target: Page) {
    navigate(paths[target]);
  }

  return (
    <View style={shell.screen}>
      <View role="navigation" style={shell.nav}>
        <View style={shell.navRow}>
          <NavLink title="Click Talk" brand current={page === 'home'} onPress={() => go('home')} />
          <View style={shell.navActions}>
            <NavLink title="Search Talks" current={page === 'talks'} onPress={() => go('talks')} />
            <NavLink title="My conferences" current={page === 'myConferences'} onPress={() => go('myConferences')} />
            {!compact ? <NavLink title="Join event" current={page === 'join'} onPress={() => go('join')} /> : null}
          </View>
        </View>
      </View>

      <ScrollView ref={scrollRef} keyboardShouldPersistTaps="handled"
        onLayout={(event) => setViewportHeight(event.nativeEvent.layout.height)}
        contentContainerStyle={shell.body}>
        <View style={[{ minHeight: viewportHeight }, page === 'home' && shell.home]}>{children}</View>
        <Footer onNavigate={go} />
      </ScrollView>
    </View>
  );
}

function Footer({ onNavigate }: { onNavigate: (page: Page) => void }) {
  return (
    <View role="contentinfo" style={shell.footer}>
      <Container>
        <View style={shell.footerLinks}>
          <NavLink title="Home" current={false} onPress={() => onNavigate('home')} />
          <NavLink title="Event archive" current={false} onPress={() => onNavigate('events')} />
        </View>
      </Container>
    </View>
  );
}

const shell = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.paper },
  nav: { backgroundColor: colors.chrome, paddingHorizontal: 16, paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: colors.pale },
  navRow: { width: '100%', maxWidth: 1180, alignSelf: 'center', flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', columnGap: 16, flexWrap: 'wrap', rowGap: 8 },
  navActions: { flexDirection: 'row', alignItems: 'center', columnGap: 8 },
  navLink: { paddingHorizontal: 10, paddingVertical: 10, borderRadius: 8, minHeight: 44, justifyContent: 'center' },
  navText: { color: colors.accent, fontSize: 15, fontWeight: '600' },
  navCurrent: { textDecorationLine: 'underline' },
  brand: { color: colors.ink, fontSize: 17, fontWeight: '700', letterSpacing: -0.4 },
  focused: { outlineColor: colors.accent, outlineWidth: 2, outlineOffset: 2, outlineStyle: 'solid' },
  body: { flexGrow: 1 },
  home: { justifyContent: 'center' },
  container: { width: '100%', maxWidth: 1180, alignSelf: 'center', paddingHorizontal: 24 },
  footer: { backgroundColor: colors.chrome, paddingVertical: 16, borderTopWidth: 1, borderTopColor: colors.pale },
  footerLinks: { flexDirection: 'row', flexWrap: 'wrap', columnGap: 8, rowGap: 4, marginLeft: -10 },
});
