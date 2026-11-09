import type { ComponentRef, PropsWithChildren } from 'react';
import { useEffect, useRef, useState } from 'react';
import { Platform, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import type { StyleProp, TextInputProps, TextStyle } from 'react-native';

export const colors = {
  ink: '#191924',
  muted: '#565666',
  paper: '#FAF9FD',
  chrome: '#EAF0FA',
  white: '#FFFFFF',
  accent: '#5040AF',
  pale: '#EEEBF9',
  line: '#8B849E',
  error: '#922D24',
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
  row: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', columnGap: 18, rowGap: 4 },
  label: { color: colors.accent, fontSize: 14, fontWeight: '700', letterSpacing: 0.3 },
  copy: { color: colors.muted, fontSize: 16, lineHeight: 24 },
  heading: { color: colors.ink, fontSize: 23, fontWeight: '600', letterSpacing: -0.35 },
  largeHeading: { fontSize: 40, fontWeight: '700', letterSpacing: -1.5 },
  section: { width: '100%', maxWidth: 650, gap: 18 },
  field: { gap: 7 },
  fieldLabel: { color: colors.ink, fontWeight: '600', fontSize: 16 },
  input: { minHeight: 48, borderBottomWidth: 1, borderColor: colors.line, padding: 12, color: colors.ink, backgroundColor: colors.pale, fontSize: 16, borderTopLeftRadius: 6, borderTopRightRadius: 6 },
  multiline: { minHeight: 96, textAlignVertical: 'top' },
  button: { minHeight: 46, justifyContent: 'center', paddingHorizontal: 18, paddingVertical: 10, backgroundColor: colors.accent, borderRadius: 8, alignSelf: 'flex-start', maxWidth: '100%' },
  buttonText: { color: colors.white, fontWeight: '700', fontSize: 16 },
  secondary: { backgroundColor: 'transparent', paddingHorizontal: 0, borderRadius: 0 },
  secondaryText: { color: colors.accent },
  selectedText: { textDecorationLine: 'underline' },
  focused: { outlineColor: colors.ink, outlineWidth: 2, outlineOffset: 2, outlineStyle: 'solid' },
  dimmed: { opacity: 0.72 },
  message: { fontSize: 16, lineHeight: 22, color: colors.ink },
  error: { color: colors.error },
});
