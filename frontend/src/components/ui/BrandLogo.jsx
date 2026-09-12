/**
 * The logo, on whatever it is sitting on.
 *
 * Two files already exist: the normal mark (navy "PG", gold "uru") and a white
 * one. The whole problem is that the navy disappears on a dark surface - which
 * is exactly what a dark-mode phone did to the sign-in screen.
 *
 * Why this takes a `tone` prop instead of reading the OS
 * -----------------------------------------------------
 * The obvious version is `<picture>` with `media="(prefers-color-scheme: dark)"`.
 * It is wrong here, and quietly so.
 *
 * `prefers-color-scheme` reports what the *phone* is set to. It has nothing to
 * do with what this app renders, and this app declares `color-scheme: light`
 * (see index.html) - so on a dark-mode handset the page is still light. The
 * media query would match, swap in the white logo, and paint white-on-white.
 * The bug would appear only for people with dark mode on, which is the hardest
 * kind to be told about.
 *
 * So the caller says what it is putting the logo on, because the caller is the
 * only one who knows:
 *
 *   tone="light"  (default)  dark mark, for white and off-white surfaces
 *   tone="dark"              white mark, for brand-900/950 panels and footers
 *
 * When a real dark theme lands this reads the theme instead of the prop, and it
 * is one file rather than the seven that used to hard-code a filename.
 */
const SRC = {
  light: '/pgguru-logo.png',
  dark: '/pgguru-logo-white.png',
}

export function BrandLogo({ tone = 'light', className = 'h-10 w-auto', alt = 'PGuru', ...rest }) {
  return <img src={SRC[tone] || SRC.light} alt={alt} className={className} {...rest} />
}

export default BrandLogo
