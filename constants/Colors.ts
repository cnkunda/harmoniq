/**
 * Expo template light/dark palette (used by `Themed.tsx`, `useThemeColor`, template screens).
 * Harmoniq’s **product** wood/cream palette for feature UI lives in `src/constants/colors.ts`.
 * Keep this export shape stable so existing `useThemeColor` call sites stay valid.
 */
const tintColorLight = '#2f95dc';
const tintColorDark = '#fff';

export default {
  light: {
    text: '#000',
    background: '#fff',
    tint: tintColorLight,
    tabIconDefault: '#ccc',
    tabIconSelected: tintColorLight,
  },
  dark: {
    text: '#fff',
    background: '#000',
    tint: tintColorDark,
    tabIconDefault: '#ccc',
    tabIconSelected: tintColorDark,
  },
};
