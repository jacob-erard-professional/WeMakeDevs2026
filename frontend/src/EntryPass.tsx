import { useMemo, useState } from 'react';
import { create } from 'qrcode';
import { Modal, Platform, Pressable, ScrollView, Share, StyleSheet, Text, View, useWindowDimensions } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import Svg, { Path, Rect } from 'react-native-svg';

import { Action, colors, Copy, Heading, Label, Message, styles } from './ui';

function roundedCode(link: string) {
  const { modules } = create(link, { errorCorrectionLevel: 'M' });
  const { size } = modules;
  const dark = (y: number, x: number) => y >= 0 && x >= 0 && y < size && x < size && modules.get(y, x);
  const paths: string[] = [];
  const radius = 0.3;

  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      if (!dark(y, x)) continue;
      // Round exposed corners while keeping adjacent black modules joined.
      const top = !dark(y - 1, x);
      const bottom = !dark(y + 1, x);
      const left = !dark(y, x - 1);
      const right = !dark(y, x + 1);
      const tl = top && left ? radius : 0;
      const tr = top && right ? radius : 0;
      const br = bottom && right ? radius : 0;
      const bl = bottom && left ? radius : 0;
      paths.push(
        `M${x + tl},${y}H${x + 1 - tr}Q${x + 1},${y} ${x + 1},${y + tr}`
        + `V${y + 1 - br}Q${x + 1},${y + 1} ${x + 1 - br},${y + 1}`
        + `H${x + bl}Q${x},${y + 1} ${x},${y + 1 - bl}`
        + `V${y + tl}Q${x},${y} ${x + tl},${y}Z`,
      );
    }
  }

  return { path: paths.join(''), extent: size + 8 };
}

function PassCode({ link, size }: { link: string; size: number }) {
  const { path, extent } = useMemo(() => roundedCode(link), [link]);

  return (
    <View style={pass.frame}>
      <Svg width={size} height={size} viewBox={`-4 -4 ${extent} ${extent}`}>
        <Rect x={-4} y={-4} width={extent} height={extent} fill={colors.white} />
        <Path d={path} fill="#000000" />
      </Svg>
    </View>
  );
}

export function EntryPass({ name, code, link, details, onReset, onTrySample }: {
  name: string;
  code: string;
  link: string;
  details?: string;
  onReset: () => void;
  onTrySample?: () => void;
}) {
  const [presenting, setPresenting] = useState(false);
  const [focused, setFocused] = useState(false);
  const [message, setMessage] = useState('');
  const { width, height } = useWindowDimensions();
  const qrSize = Math.max(120, Math.min(width - 80, height * 0.5, 520));
  const web = Platform.OS === 'web';
  const canShare = !web || typeof navigator.share === 'function';

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(link);
      setMessage('Join link copied.');
    } catch {
      setMessage('Select the join link to copy it manually.');
    }
  }

  async function share() {
    setMessage('');
    try {
      if (web) await navigator.share({ title: name, url: link });
      else await Share.share({ title: name, message: link });
    } catch (reason) {
      if (reason instanceof Error && reason.name === 'AbortError') return;
      if (web) await copyLink();
      else setMessage('Select the join link to copy it manually.');
    }
  }

  async function fullscreen() {
    try { await document.documentElement.requestFullscreen(); }
    catch { setMessage('Browser full screen is unavailable. The QR still fills this page.'); }
  }

  function close() {
    setPresenting(false);
    setMessage('');
    if (web && document.fullscreenElement) {
      void document.exitFullscreen().catch(() => {});
    }
  }

  function openPresentation() {
    setMessage('');
    setPresenting(true);
  }

  function passInfo(centered = false) {
    return (
      <View style={[pass.info, centered && pass.centered]}>
        <Label>Join code</Label>
        <Text selectable style={pass.code}>{code}</Text>
        <Text selectable style={[pass.link, centered && pass.title]}>{link}</Text>
      </View>
    );
  }

  const shareActions = !onTrySample && (
    <>
      {canShare ? <Action title="Share join link" onPress={() => void share()} secondary /> : null}
      {web ? <Action title="Copy join link" onPress={() => void copyLink()} secondary /> : null}
    </>
  );

  return (
    <View style={styles.stack}>
      <Label>{onTrySample ? 'Sample conference published' : 'Ready to share'}</Label>
      <Heading large>{name}</Heading>
      {details ? <Copy>{details}</Copy> : null}
      <Copy>{onTrySample
        ? 'Preview the QR here, then try check-in in this app session.'
        : 'Scan the QR with your phone camera, or share the link with attendees.'}</Copy>
      <View style={pass.row}>
        <Pressable accessibilityRole="button" accessibilityLabel="Open full-screen QR"
          onFocus={() => setFocused(true)} onBlur={() => setFocused(false)}
          onPress={openPresentation}
          style={({ pressed }) => [pass.preview, focused && pass.focused, pressed && pass.pressed]}>
          <PassCode link={link} size={Math.max(120, Math.min(width - 96, 230))} />
          <Text style={pass.previewLabel}>Open full-screen QR ↗</Text>
        </Pressable>
        {passInfo()}
      </View>
      <View style={styles.row}>
        {onTrySample ? <Action title="Try attendee check-in" onPress={onTrySample} /> : null}
        {shareActions}
        <Action title="Create another conference" onPress={onReset} secondary />
      </View>
      {!presenting && message ? <Message>{message}</Message> : null}
      <Modal visible={presenting} animationType="none" presentationStyle="fullScreen" onRequestClose={close}>
        <SafeAreaView style={pass.screen}>
          <ScrollView contentContainerStyle={pass.presentation}>
            <View style={pass.toolbar}>
              <Action title="Close presentation" onPress={close} secondary />
              {shareActions}
              {web && typeof document.documentElement.requestFullscreen === 'function' ? (
                <Action title="Browser full screen" onPress={() => void fullscreen()} secondary />
              ) : null}
            </View>
            <Label>{onTrySample ? 'Sample QR · preview only' : 'Scan to join'}</Label>
            <Text accessibilityRole="header" style={[styles.heading, styles.largeHeading, pass.title]}>{name}</Text>
            <View accessible accessibilityRole="image" accessibilityLabel={`Join QR code for ${name}`}>
              <PassCode link={link} size={qrSize} />
            </View>
            {passInfo(true)}
            {message ? <Message>{message}</Message> : null}
          </ScrollView>
        </SafeAreaView>
      </Modal>
    </View>
  );
}

const pass = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.chrome },
  row: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', columnGap: 24, rowGap: 18 },
  frame: { alignSelf: 'center', backgroundColor: colors.white, borderWidth: 1, borderColor: '#A8B8D7', borderRadius: 12, padding: 12 },
  preview: { alignItems: 'center', gap: 10, padding: 8, borderRadius: 12 },
  previewLabel: { color: colors.accent, fontSize: 15, fontWeight: '700', textDecorationLine: 'underline' },
  pressed: { backgroundColor: colors.chrome },
  focused: { outlineWidth: 2, outlineOffset: 4, outlineStyle: 'solid', outlineColor: colors.accent },
  info: { gap: 5, flexShrink: 1 },
  centered: { alignItems: 'center' },
  title: { textAlign: 'center' },
  code: { color: colors.ink, fontSize: 24, fontWeight: '700', fontVariant: ['tabular-nums'] },
  link: { color: colors.muted, fontSize: 15 },
  presentation: { flexGrow: 1, padding: 24, alignItems: 'center', justifyContent: 'center', gap: 14 },
  toolbar: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'center', columnGap: 24, rowGap: 4 },
});
