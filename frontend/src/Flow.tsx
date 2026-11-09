import { createContext, useContext, useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { PropsWithChildren } from 'react';
import { AccessibilityInfo, Animated, Easing, Platform } from 'react-native';
import type { StyleProp, ViewStyle } from 'react-native';

const ReduceMotion = createContext(true);

export function MotionPreferences({ children }: PropsWithChildren) {
  const [reduceMotion, setReduceMotion] = useState(true);
  useEffect(() => {
    let active = true;
    const subscription = AccessibilityInfo.addEventListener('reduceMotionChanged', setReduceMotion);
    AccessibilityInfo.isReduceMotionEnabled().then((enabled) => {
      if (active) setReduceMotion(enabled);
    }).catch(() => {});
    return () => {
      active = false;
      subscription?.remove();
    };
  }, []);

  return <ReduceMotion.Provider value={reduceMotion}>{children}</ReduceMotion.Provider>;
}

// True when the device or browser asks for reduced motion (and before the preference is known).
export function useReduceMotion(): boolean {
  return useContext(ReduceMotion);
}

export function Flow({ step, style, fadeOnly, children }: PropsWithChildren<{
  step: string;
  style?: StyleProp<ViewStyle>;
  fadeOnly?: boolean;
}>) {
  const reduceMotion = useContext(ReduceMotion);
  const previousStep = useRef(step);
  const progress = useRef(new Animated.Value(1)).current;

  useLayoutEffect(() => {
    const changed = previousStep.current !== step;
    previousStep.current = step;
    if (reduceMotion || !changed) {
      progress.setValue(1);
      return;
    }

    progress.setValue(0);
    const animation = Animated.timing(progress, {
      toValue: 1,
      duration: 200,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: Platform.OS !== 'web',
    });
    animation.start();
    return () => animation.stop();
  }, [progress, reduceMotion, step]);

  return (
    <Animated.View style={[
      style,
      {
        opacity: progress.interpolate({ inputRange: [0, 1], outputRange: [fadeOnly ? 0.82 : 0.35, 1] }),
        transform: [{ translateY: progress.interpolate({ inputRange: [0, 1], outputRange: [fadeOnly ? 0 : 8, 0] }) }],
      },
    ]}>
      {children}
    </Animated.View>
  );
}
