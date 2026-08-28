import { dict, type Lang } from "../i18n"

/**
 * Permanent on every screen. Not dismissible, not collapsible, not conditional.
 * This is a product constraint, not a design choice.
 */
export default function Footer({ lang }: { lang: Lang }) {
  return (
    <footer
      className="muted mx-auto max-w-lg px-4 pb-8 pt-6 text-center"
      style={{ fontSize: 15, lineHeight: 1.55 }}
    >
      {dict(lang).footer}
    </footer>
  )
}
