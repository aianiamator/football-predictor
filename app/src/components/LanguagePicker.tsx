import { LANGS, type Lang } from "../i18n"

/**
 * A row of buttons, not a dropdown. Every option is visible at once, which is
 * the whole point for a reader who might not recognise the current setting.
 */
export default function LanguagePicker({
  lang,
  onChange,
}: {
  lang: Lang
  onChange: (l: Lang) => void
}) {
  return (
    <div className="-mx-4 overflow-x-auto px-4" style={{ scrollbarWidth: "none" }}>
      <div className="flex w-max gap-2">
        {LANGS.map((l) => {
          const on = l.code === lang
          return (
            <button
              key={l.code}
              type="button"
              onClick={() => onChange(l.code)}
              aria-pressed={on}
              lang={l.code}
              className={
                "tap shrink-0 whitespace-nowrap rounded-full border-2 px-4 font-semibold" +
                (on
                  ? " border-slate-900 bg-slate-900 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-900"
                  : " surface")
              }
              style={{ fontSize: 17 }}
            >
              {l.label}
            </button>
          )
        })}
      </div>
    </div>
  )
}
