import { useState } from 'react';
import { Modal, Platform, Pressable, ScrollView, Share, StyleSheet, Text, View, useWindowDimensions } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import QRCode from 'react-native-qrcode-svg';

import { Action, colors, Copy, Heading, Label, Message, styles } from './ui';

export function EntryPass({ name, code, link, details, onReset }: {
  name: string;
  code: string;
  link: string;
  details?: string;
  onReset: () => void;
}) {
  const [presenting, setPresenting] = useState(false);
  const [focused, setFocused] = useState(false);
  const [message, setMessage] = useState('');
  const { width, height } = useWindowDimensions();
  const qrSize = Math.max(150, Math.min(width - 64, height * 0.52, 540));
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

  function passInfo(centered = false) {
    return (
      <View style={[pass.info, centered && pass.centered]}>
        <Label>Join code</Label>
        <Text selectable style={pass.code}>{code}</Text>
        <Text selectable style={[pass.link, centered && pass.title]}>{link}</Text>
      </View>
    );
  }

  const shareActions = (
    <>
      {canShare ? <Action title="Share join link" onPress={() => void share()} secondary /> : null}
      {web ? <Action title="Copy join link" onPress={() => void copyLink()} secondary /> : null}
    </>
  );

  return (
    <View style={styles.stack}>
      <Label>Ready to share</Label>
      <Heading large>{name}</Heading>
      {details ? <Copy>{details}</Copy> : null}
      <Copy>Scan the QR with your phone camera, or share the link with attendees.</Copy>
      <View style={pass.row}>
        <Pressable accessibilityRole="button" accessibilityLabel="Open presentation QR"
          onFocus={() => setFocused(true)} onBlur={() => setFocused(false)}
          onPress={() => { setMessage(''); setPresenting(true); }}
          style={[pass.qr, focused && pass.focused]}>
          <QRCode value={link} size={Math.min(width - 56, 260)} quietZone={36} />
        </Pressable>
        {passInfo()}
      </View>
      <View style={styles.row}>
        <Action title="Present QR" onPress={() => { setMessage(''); setPresenting(true); }} />
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
            <Label>Scan to join</Label>
            <Heading large style={pass.title}>{name}</Heading>
            <View accessible accessibilityRole="image" accessibilityLabel={`Join QR code for ${name}`} style={pass.qr}>
              <QRCode value={link} size={qrSize} quietZone={Math.round(qrSize * 0.13)} />
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
  screen: { flex: 1, backgroundColor: colors.paper },
  row: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', columnGap: 24, rowGap: 18 },
  qr: { alignSelf: 'center', backgroundColor: colors.white },
  focused: { outlineWidth: 2, outlineOffset: 4, outlineStyle: 'solid', outlineColor: colors.accent },
  info: { gap: 5, flexShrink: 1 },
  centered: { alignItems: 'center' },
  title: { textAlign: 'center' },
  code: { color: colors.ink, fontSize: 24, fontWeight: '700', fontVariant: ['tabular-nums'] },
  link: { color: colors.muted, fontSize: 15 },
  presentation: { flexGrow: 1, padding: 24, alignItems: 'center', justifyContent: 'center', gap: 14 },
  toolbar: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'center', columnGap: 24, rowGap: 4 },
});
