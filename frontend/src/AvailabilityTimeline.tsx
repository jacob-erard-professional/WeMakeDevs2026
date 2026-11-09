import { useMemo, useRef, useState } from 'react';
import { PanResponder, StyleSheet, Text, View } from 'react-native';

import { formatTime } from './conference';
import type { TimeRange } from './conference';
import { colors, Copy } from './ui';

const chunk = 15;

export function AvailabilityTimeline({ start, end, blocked, disabled, mode, onSelect }: {
  start: number;
  end: number;
  blocked: TimeRange[];
  disabled: boolean;
  mode: 'available' | 'unavailable';
  onSelect: (range: TimeRange) => void;
}) {
  const [width, setWidth] = useState(0);
  const [preview, setPreview] = useState<TimeRange>();
  const drag = useRef<{ origin: number; anchor: number; range: TimeRange } | undefined>(undefined);
  const span = end - start;
  const percent = (time: number): `${number}%` => `${100 * (time - start) / span}%`;
  const responder = useMemo(() => {
    const slotAt = (x: number) => Math.max(start, Math.min(end - chunk, start + Math.floor(x / width * span / chunk) * chunk));
    return PanResponder.create({
      onStartShouldSetPanResponder: () => width > 0 && !disabled,
      onPanResponderGrant: ({ nativeEvent }) => {
        const anchor = slotAt(nativeEvent.locationX);
        const range = { start: anchor, end: anchor + chunk };
        drag.current = { origin: nativeEvent.pageX - nativeEvent.locationX, anchor, range };
        setPreview(range);
      },
      onPanResponderMove: ({ nativeEvent }) => {
        const current = drag.current;
        if (!current) return;
        const slot = slotAt(nativeEvent.pageX - current.origin);
        current.range = { start: Math.min(current.anchor, slot), end: Math.max(current.anchor, slot) + chunk };
        setPreview(current.range);
      },
      onPanResponderRelease: () => {
        if (drag.current && !disabled) onSelect(drag.current.range);
        drag.current = undefined;
        setPreview(undefined);
      },
      onPanResponderTerminate: () => {
        drag.current = undefined;
        setPreview(undefined);
      },
    });
  }, [width, disabled, start, end, span, onSelect]);

  return (
    <View style={timeline.layout}>
      <Copy>{mode === 'available'
        ? 'Drag across a blocked time to make it available again. You can also enter exact times below.'
        : 'Drag across the timeline to mark 15-minute blocks as unavailable, or enter exact times below.'}</Copy>
      <View style={timeline.ticks}>
        {[start, start + Math.round(span / (2 * chunk)) * chunk, end].map((time) => (
          <Text key={time} style={timeline.tick}>{formatTime(time)}</Text>
        ))}
      </View>
      <View testID="availability-timeline" accessibilityLabel="Availability timeline. Use the time fields to enter a range without dragging."
        onLayout={(event) => setWidth(event.nativeEvent.layout.width)}
        style={timeline.track} {...responder.panHandlers}>
        <View pointerEvents="none" style={StyleSheet.absoluteFill}>
          {Array.from({ length: Math.floor(span / 60) }, (_, index) => start + (index + 1) * 60)
            .filter((time) => time < end)
            .map((time) => <View key={time} style={[timeline.mark, { left: percent(time) }]} />)}
          {[...blocked, ...(preview ? [preview] : [])].map((range, index) => {
            const from = Math.max(start, range.start);
            const to = Math.min(end, range.end);
            return to > from ? (
              <View key={index} style={[
                timeline.block,
                index === blocked.length && mode === 'available' && timeline.available,
                { left: percent(from), right: `${100 - 100 * (to - start) / span}%` },
              ]} />
            ) : null;
          })}
        </View>
      </View>
      {preview ? <Copy>{formatTime(preview.start)} to {formatTime(preview.end)}</Copy> : null}
    </View>
  );
}

const timeline = StyleSheet.create({
  layout: { gap: 8 },
  ticks: { flexDirection: 'row', justifyContent: 'space-between', flexWrap: 'wrap' },
  tick: { color: colors.muted, fontSize: 13 },
  track: { minHeight: 48, backgroundColor: colors.chrome, borderRadius: 6, overflow: 'hidden' },
  mark: { position: 'absolute', top: 0, bottom: 0, width: 1, backgroundColor: colors.line },
  block: { position: 'absolute', top: 5, bottom: 5, backgroundColor: colors.accent, borderRadius: 4 },
  available: { backgroundColor: '#D9EEE7', borderWidth: 1, borderColor: '#43806D' },
});
