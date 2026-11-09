import type { PropsWithChildren } from 'react';
import { useState } from 'react';
import { Platform, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import type { TextInputProps } from 'react-native';

export const colors = {
  ink: '#112C2A',
  muted: '#455E59',
  paper: '#F3F7F1',
  white: '#FFFFFF',
  green: '#195848',
  pale: '#DCEFE4',
  line: '#B0C4B8',
  error: '#922D24',
};

export function Label({ children }: PropsWithChildren) {
  return <Text style={styles.label}>{children}</Text>;
}

export function Copy({ children }: PropsWithChildren) {
  return <Text style={styles.copy}>{children}</Text>;
}

export function Heading({ children }: PropsWithChildren) {
  return <Text accessibilityRole="header" style={styles.heading}>{children}</Text>;
}

export function Card({ children }: PropsWithChildren) {
  return <View style={styles.card}>{children}</View>;
}

export function Field({ label, multiline, ...props }: TextInputProps & { label: string }) {
  return (
    <View style={styles.field}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <TextInput
        accessibilityLabel={label}
        multiline={multiline}
        placeholderTextColor={colors.muted}
        style={[styles.input, multiline && styles.multiline]}
        {...props}
      />
    </View>
  );
}

export function Action({ title, onPress, secondary, selected, disabled }: {
  title: string;
  onPress: () => void;
  secondary?: boolean;
  selected?: boolean;
  disabled?: boolean;
}) {
  const [focused, setFocused] = useState(false);
  const toggleState = Platform.OS === 'web'
    ? { 'aria-pressed': selected, accessibilityState: { disabled } }
    : { accessibilityState: { selected, disabled } };

  return (
    <Pressable
      accessibilityRole="button"
      {...toggleState}
      disabled={disabled}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        secondary && styles.secondary,
        selected && styles.selected,
        focused && styles.focused,
        (pressed || disabled) && styles.dimmed,
      ]}
    >
      <Text style={[styles.buttonText, (secondary || selected) && styles.secondaryText, selected && styles.selectedText]}>
        {title}
      </Text>
    </Pressable>
  );
}

export function Message({ children, error }: PropsWithChildren<{ error?: boolean }>) {
  return (
    <Text accessibilityLiveRegion={error ? 'assertive' : 'polite'} accessibilityRole={error ? 'alert' : undefined}
      style={[styles.message, error && styles.error]}>
      {children}
    </Text>
  );
}

export const styles = StyleSheet.create({
  stack: { gap: 14 },
  row: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 10 },
  label: { color: colors.green, fontSize: 14, fontWeight: '700', letterSpacing: 0.7 },
  copy: { color: colors.muted, fontSize: 16, lineHeight: 24 },
  heading: { color: colors.ink, fontSize: 24, fontWeight: '700' },
  card: { borderWidth: 1, borderColor: colors.line, borderRadius: 18, backgroundColor: colors.white, padding: 18, gap: 12 },
  field: { gap: 6 },
  fieldLabel: { color: colors.ink, fontWeight: '600', fontSize: 16 },
  input: { minHeight: 48, borderWidth: 1, borderColor: colors.line, borderRadius: 10, padding: 12, color: colors.ink, backgroundColor: colors.white, fontSize: 16 },
  multiline: { minHeight: 96, textAlignVertical: 'top' },
  button: { minHeight: 46, justifyContent: 'center', paddingHorizontal: 16, paddingVertical: 10, borderRadius: 10, backgroundColor: colors.green, borderWidth: 1, borderColor: colors.green, alignSelf: 'flex-start', maxWidth: '100%' },
  buttonText: { color: colors.white, fontWeight: '700', fontSize: 16 },
  secondary: { backgroundColor: colors.white },
  secondaryText: { color: colors.green },
  selected: { backgroundColor: colors.pale },
  selectedText: { textDecorationLine: 'underline' },
  focused: { outlineColor: colors.ink, outlineWidth: 2, outlineOffset: 2, outlineStyle: 'solid' },
  dimmed: { opacity: 0.72 },
  message: { fontSize: 16, lineHeight: 22, color: colors.green },
  error: { color: colors.error },
});
