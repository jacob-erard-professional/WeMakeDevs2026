import type { ComponentRef, PropsWithChildren } from 'react';
import { useEffect, useRef, useState } from 'react';
import { Platform, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import type { StyleProp, TextInputProps, TextStyle } from 'react-native';

export const colors = {
  ink: '#1D1D22',
  muted: '#65656E',
  paper: '#F7F7FA',
  chrome: '#ECECF1',
  white: '#FFFFFF',
  accent: '#0B70E0',
  pale: '#E9F2FF',
  line: '#C9C9D1',
  error: '#C12B21',
  desktop: '#D6D7DE',
  shadow: '#1B1C26',
};

export function Label({ children }: PropsWithChildren) {
  return <Text style={styles.label}>{children}</Text>;
}

export function Copy({ children }: PropsWithChildren) {
  return <Text style={styles.copy}>{children}</Text>;
}

export function Heading({ children, large, style }: PropsWithChildren<{ large?: boolean; style?: StyleProp<TextStyle> }>) {
  const ref = useRef<ComponentRef<typeof Text>>(null);
  const focusOnWeb = large && Platform.OS === 'web';
  const focusProps = focusOnWeb ? { tabIndex: -1 } : {};
  useEffect(() => {
    if (focusOnWeb) ref.current?.focus();
  }, [children, focusOnWeb]);

  return (
    <Text ref={ref} accessibilityRole="header" {...focusProps}
      style={[styles.heading, large && styles.largeHeading, style]}>
      {children}
    </Text>
  );
}

export function Section({ children }: PropsWithChildren) {
  return <View style={styles.section}>{children}</View>;
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

export function Action({ title, onPress, secondary, selected, disabled, expanded, accessibilityLabel }: {
  title: string;
  onPress: () => void;
  secondary?: boolean;
  selected?: boolean;
  disabled?: boolean;
  expanded?: boolean;
  accessibilityLabel?: string;
}) {
  const [focused, setFocused] = useState(false);
  const toggleState = Platform.OS === 'web'
    ? { 'aria-pressed': selected, 'aria-expanded': expanded, accessibilityState: { disabled } }
    : { accessibilityState: { selected, disabled, expanded } };

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel}
      {...toggleState}
      disabled={disabled}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        secondary && styles.secondary,
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

export function TalkDetails({ title, abstract, extra }: { title: string; abstract: string; extra?: string }) {
  const [expanded, setExpanded] = useState(false);
  const summary = abstract.length > 150 ? `${abstract.slice(0, 150).replace(/\s+\S*$/, '')}…` : extra ? abstract : '';
  return (
    <View>
      {expanded || summary ? <Copy>{expanded ? abstract : summary}</Copy> : null}
      {expanded && extra ? <Copy>{extra}</Copy> : null}
      <Action title={expanded ? 'Hide details' : 'Show details'} expanded={expanded}
        accessibilityLabel={`${expanded ? 'Hide' : 'Show'} details for ${title}`}
        onPress={() => setExpanded((open) => !open)} secondary />
    </View>
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
  stack: { gap: 18 },
  row: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', columnGap: 14, rowGap: 8 },
  label: { color: colors.accent, fontSize: 13, fontWeight: '700', letterSpacing: 0.45, textTransform: 'uppercase' },
  copy: { color: colors.muted, fontSize: 16, lineHeight: 24 },
  heading: { color: colors.ink, fontSize: 23, fontWeight: '700', letterSpacing: -0.5 },
  largeHeading: { fontSize: 40, fontWeight: '700', letterSpacing: -1.6 },
  section: { width: '100%', maxWidth: 650, gap: 18 },
  field: { gap: 7 },
  fieldLabel: { color: colors.ink, fontWeight: '600', fontSize: 16 },
  input: { minHeight: 48, borderWidth: 1, borderColor: colors.line, padding: 12, color: colors.ink, backgroundColor: colors.white, fontSize: 16, borderRadius: 10 },
  multiline: { minHeight: 96, textAlignVertical: 'top' },
  button: { minHeight: 42, justifyContent: 'center', paddingHorizontal: 16, paddingVertical: 9, backgroundColor: colors.accent, borderRadius: 10, alignSelf: 'flex-start', maxWidth: '100%', shadowColor: colors.shadow, shadowOpacity: 0.12, shadowRadius: 4, shadowOffset: { width: 0, height: 2 }, elevation: 2 },
  buttonText: { color: colors.white, fontWeight: '700', fontSize: 16 },
  secondary: { backgroundColor: colors.white, paddingHorizontal: 14, borderWidth: 1, borderColor: colors.line, shadowOpacity: 0 },
  secondaryText: { color: colors.accent },
  selectedText: { color: colors.accent },
  focused: { outlineColor: colors.ink, outlineWidth: 2, outlineOffset: 2, outlineStyle: 'solid' },
  dimmed: { opacity: 0.72 },
  message: { fontSize: 16, lineHeight: 22, color: colors.ink },
  error: { color: colors.error },
});
