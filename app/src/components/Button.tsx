import { Pressable, StyleSheet, Text } from 'react-native';

import { BUTTON_HEIGHT, colors, radius, typo } from './theme';

type Props = {
  title: string;
  onPress: () => void;
  /** primary = 인디고 채움, secondary = 흰 바탕 테두리, danger = 흰 바탕 빨간 글자(삭제) */
  variant?: 'primary' | 'secondary' | 'danger';
  disabled?: boolean;
  accessibilityHint?: string;
};

export function Button({ title, onPress, variant = 'primary', disabled, accessibilityHint }: Props) {
  const primary = variant === 'primary';
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: !!disabled }}
      accessibilityHint={accessibilityHint}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.base,
        primary ? styles.primary : styles.outline,
        primary && pressed && { backgroundColor: colors.primaryPressed },
        !primary && pressed && { backgroundColor: colors.track },
        primary && disabled && { backgroundColor: colors.primaryDisabled },
      ]}>
      <Text
        style={[
          typo.button,
          { color: primary ? '#FFFFFF' : variant === 'danger' ? colors.error : colors.text },
        ]}>
        {title}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    minHeight: BUTTON_HEIGHT,
    borderRadius: radius.button,
    paddingHorizontal: 20,
    alignItems: 'center',
    justifyContent: 'center',
  },
  primary: { backgroundColor: colors.primary },
  outline: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
});
