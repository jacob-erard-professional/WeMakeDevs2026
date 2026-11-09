import { useState } from 'react';
import type { ComponentRef, PropsWithChildren, RefObject } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View, useWindowDimensions } from 'react-native';

import { colors, styles } from '../ui';
import { paths } from './router';
import type { Page } from './router';

export function SectionTitle({ children }: PropsWithChildren) {
  return <Text accessibilityRole="header" style={[styles.heading, styles.largeHeading]}>{children}</Text>;
}

export function Container({ children, style }: PropsWithChildren<{ style?: object }>) {
  const { width } = useWindowDimensions();
  return <View style={[shell.container, width < 640 && shell.mobileContainer, style]}>{children}</View>;
}

function NavLink({ title, current, onPress, icon, compact }: {
  title: string; current: boolean; onPress: () => void; icon?: string; compact?: boolean;
}) {
  const [focused, setFocused] = useState(false);
  return (
    <Pressable accessibilityRole="link" aria-current={current ? 'page' : undefined}
      onPress={onPress} onFocus={() => setFocused(true)} onBlur={() => setFocused(false)}
      style={[shell.navLink, compact && shell.compactNavLink, current && shell.navCurrent, focused && shell.focused]}>
      {icon ? <Text accessible={false} aria-hidden style={shell.navIcon}>{icon}</Text> : null}
      <Text style={[shell.navText, compact && shell.compactNavText]}>{title}</Text>
    </Pressable>
  );
}

function TrafficLights() {
  return (
    <View accessible accessibilityLabel="Click Talk window" style={shell.trafficLights}>
      <View style={[shell.light, shell.close]} />
      <View style={[shell.light, shell.minimize]} />
      <View style={[shell.light, shell.maximize]} />
    </View>
  );
}

export function SiteShell({ page, navigate, scrollRef, children }: PropsWithChildren<{
  page: Page;
  navigate: (path: string) => void;
  scrollRef: RefObject<ComponentRef<typeof ScrollView> | null>;
}>) {
  const { width } = useWindowDimensions();
  const mobile = width < 640;
  const [viewportHeight, setViewportHeight] = useState(0);

  function go(target: Page) {
    navigate(paths[target]);
  }

  const navigation = (
    <>
      <NavLink title="Home" icon="⌂" current={page === 'home'} onPress={() => go('home')} compact={mobile} />
      <NavLink title="Talks" icon="⌕" current={page === 'talks'} onPress={() => go('talks')} compact={mobile} />
      <NavLink title="My conferences" icon="☰" current={page === 'myConferences'} onPress={() => go('myConferences')} compact={mobile} />
      <NavLink title="Organizers" icon="◫" current={page === 'organizers'} onPress={() => go('organizers')} compact={mobile} />
      <NavLink title="Join" icon="✦" current={page === 'join'} onPress={() => go('join')} compact={mobile} />
    </>
  );

  return (
    <View style={[shell.desktop, mobile && shell.mobileDesktop]}>
      <View style={[shell.window, mobile && shell.phone]}>
        <View style={[shell.titlebar, mobile && shell.phoneTitlebar]}>
          {mobile ? <View accessible={false} style={shell.dynamicIsland} /> : <TrafficLights />}
          <Text style={shell.windowTitle}>Click Talk</Text>
          {!mobile ? <Text style={shell.titlebarHint}>Your conference companion</Text> : <Text style={shell.phoneTime}>9:41</Text>}
        </View>
        <View style={shell.appBody}>
          {!mobile ? (
            <View role="navigation" style={shell.sidebar}>
              <Text style={shell.sidebarBrand}>Conference
Connections</Text>
              <Text style={shell.sidebarLabel}>Navigate</Text>
              <View style={shell.navList}>{navigation}</View>
              <View style={shell.sidebarFooter}>
                <Text style={shell.sidebarFooterText}>Made for the people in the room.</Text>
              </View>
            </View>
          ) : null}
          <ScrollView ref={scrollRef} keyboardShouldPersistTaps="handled"
            onLayout={(event) => setViewportHeight(event.nativeEvent.layout.height)}
            contentContainerStyle={[shell.body, mobile && shell.mobileBody]}>
            <View style={[{ minHeight: viewportHeight }, page === 'home' && shell.home]}>{children}</View>
            {!mobile ? <Footer onNavigate={go} /> : null}
          </ScrollView>
        </View>
        {mobile ? <View role="navigation" style={shell.tabBar}>{navigation}</View> : null}
      </View>
    </View>
  );
}

function Footer({ onNavigate }: { onNavigate: (page: Page) => void }) {
  return (
    <View role="contentinfo" style={shell.footer}>
      <Text style={shell.footerText}>Designed for a better conference day.</Text>
      <Pressable accessibilityRole="link" onPress={() => onNavigate('events')} style={shell.footerLink}>
        <Text style={shell.footerLinkText}>Event archive →</Text>
      </Pressable>
    </View>
  );
}

const shell = StyleSheet.create({
  desktop: { flex: 1, backgroundColor: colors.desktop, padding: 28 },
  mobileDesktop: { backgroundColor: colors.paper, padding: 0 },
  window: { flex: 1, maxWidth: 1440, width: '100%', alignSelf: 'center', overflow: 'hidden', backgroundColor: colors.paper, borderRadius: 16, borderWidth: 1, borderColor: '#BEC0C9', shadowColor: colors.shadow, shadowOpacity: 0.25, shadowRadius: 30, shadowOffset: { width: 0, height: 14 }, elevation: 12 },
  phone: { maxWidth: 560, borderRadius: 0, borderWidth: 0, shadowOpacity: 0 },
  titlebar: { height: 48, flexDirection: 'row', alignItems: 'center', paddingHorizontal: 18, backgroundColor: '#F4F4F6', borderBottomWidth: 1, borderBottomColor: '#D3D3DA' },
  phoneTitlebar: { height: 56, justifyContent: 'center', backgroundColor: colors.white, borderBottomColor: '#E7E7EC' },
  trafficLights: { flexDirection: 'row', gap: 8, width: 136 },
  light: { width: 12, height: 12, borderRadius: 6, borderWidth: 1, borderColor: 'rgba(0,0,0,0.12)' },
  close: { backgroundColor: '#FF5F57' },
  minimize: { backgroundColor: '#FEBC2E' },
  maximize: { backgroundColor: '#28C840' },
  windowTitle: { flex: 1, color: colors.ink, fontWeight: '700', fontSize: 14, textAlign: 'center', letterSpacing: -0.2 },
  titlebarHint: { width: 136, color: colors.muted, fontSize: 12, textAlign: 'right' },
  dynamicIsland: { position: 'absolute', top: 8, width: 92, height: 24, borderRadius: 14, backgroundColor: '#17171B' },
  phoneTime: { position: 'absolute', left: 22, color: colors.ink, fontSize: 13, fontWeight: '700' },
  appBody: { flex: 1, flexDirection: 'row' },
  sidebar: { width: 218, padding: 22, backgroundColor: '#F0F0F4', borderRightWidth: 1, borderRightColor: '#D9D9E0' },
  sidebarBrand: { color: colors.ink, fontSize: 18, fontWeight: '800', letterSpacing: -0.7, lineHeight: 21, marginBottom: 42 },
  sidebarLabel: { color: colors.muted, fontSize: 11, fontWeight: '700', letterSpacing: 0.5, textTransform: 'uppercase', marginBottom: 8 },
  navList: { gap: 4 },
  navLink: { minHeight: 42, flexDirection: 'row', alignItems: 'center', columnGap: 10, paddingHorizontal: 10, borderRadius: 9 },
  navCurrent: { backgroundColor: colors.white },
  navIcon: { width: 18, color: colors.muted, fontSize: 18, textAlign: 'center' },
  navText: { color: colors.ink, fontSize: 15, fontWeight: '600' },
  sidebarFooter: { marginTop: 'auto', paddingTop: 18, borderTopWidth: 1, borderTopColor: '#D9D9E0' },
  sidebarFooterText: { color: colors.muted, fontSize: 12, lineHeight: 17 },
  focused: { outlineColor: colors.accent, outlineWidth: 2, outlineOffset: 2, outlineStyle: 'solid' },
  body: { flexGrow: 1 },
  mobileBody: { paddingBottom: 0 },
  home: { justifyContent: 'center' },
  container: { width: '100%', maxWidth: 1180, alignSelf: 'center', paddingHorizontal: 40 },
  mobileContainer: { paddingHorizontal: 20 },
  footer: { marginTop: 48, paddingVertical: 22, paddingHorizontal: 40, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', borderTopWidth: 1, borderTopColor: '#DEDEE5' },
  footerText: { color: colors.muted, fontSize: 13 },
  footerLink: { paddingVertical: 8 },
  footerLinkText: { color: colors.accent, fontSize: 14, fontWeight: '700' },
  tabBar: { height: 72, flexDirection: 'row', justifyContent: 'space-around', alignItems: 'center', paddingHorizontal: 10, backgroundColor: 'rgba(255,255,255,0.97)', borderTopWidth: 1, borderTopColor: '#DDDEE5' },
  compactNavLink: { minWidth: 68, minHeight: 54, justifyContent: 'center', alignItems: 'center', flexDirection: 'column', rowGap: 1, paddingHorizontal: 8 },
  compactNavText: { fontSize: 11 },
});
