import { CameraView, useCameraPermissions } from 'expo-camera';
import { useRef, useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { Action, Copy, Heading, Message, Section, styles } from './ui';

export function JoinScanner({ onScan, onClose }: { onScan: (code: string) => void; onClose: () => void }) {
  const [permission, requestPermission] = useCameraPermissions();
  const [cameraError, setCameraError] = useState(false);
  const handled = useRef(false);
  const requesting = useRef(false);
  const canAsk = permission?.canAskAgain === true;

  async function allowCamera() {
    if (requesting.current) return;
    requesting.current = true;
    setCameraError(false);
    try {
      await requestPermission();
    } catch {
      setCameraError(true);
    } finally {
      requesting.current = false;
    }
  }

  return (
    <Section>
      <Heading>Scan a conference QR</Heading>
      <Copy>Point your camera at the organizer’s QR code. You can also type the code printed beside it.</Copy>
      {permission?.granted && !cameraError ? (
        <View style={scannerStyles.preview}>
          <CameraView
            style={StyleSheet.absoluteFill}
            facing="back"
            barcodeScannerSettings={{ barcodeTypes: ['qr'] }}
            onMountError={() => setCameraError(true)}
            onBarcodeScanned={({ data }) => {
              if (handled.current) return;
              handled.current = true;
              onScan(data);
            }}
          />
        </View>
      ) : null}
      {cameraError ? <Message error>The camera could not start. Close the scanner and type the conference code.</Message> : null}
      {permission && !permission.granted && !canAsk ? (
        <Message error>Camera access is off. Enable it in device settings or type the conference code.</Message>
      ) : null}
      <View style={styles.row}>
        {canAsk && !permission?.granted ? <Action title="Allow camera" onPress={allowCamera} /> : null}
        <Action title="Close scanner" onPress={onClose} secondary />
      </View>
    </Section>
  );
}

const scannerStyles = StyleSheet.create({
  preview: { width: '100%', maxWidth: 480, aspectRatio: 1.35, overflow: 'hidden', backgroundColor: '#191B20' },
});
