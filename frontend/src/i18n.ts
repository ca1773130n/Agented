import { createI18n } from 'vue-i18n'
import en from './locales/en.json'

const STORAGE_KEY = 'agented-locale'

const SUPPORTED_LOCALE_CODES = ['en', 'ko', 'ja', 'zh'] as const
type SupportedLocale = (typeof SUPPORTED_LOCALE_CODES)[number]

function isSupportedLocale(lang: string): lang is SupportedLocale {
  return (SUPPORTED_LOCALE_CODES as readonly string[]).includes(lang)
}

function getInitialLocale(): SupportedLocale {
  // Check localStorage first
  const stored = localStorage.getItem(STORAGE_KEY)
  if (stored && isSupportedLocale(stored)) return stored
  // Check browser language
  const browserLang = navigator.language.split('-')[0]
  if (isSupportedLocale(browserLang)) return browserLang
  return 'en'
}

export const i18n = createI18n({
  legacy: false,
  locale: getInitialLocale(),
  fallbackLocale: 'en',
  messages: { en } as Record<string, typeof en>,
})

export const SUPPORTED_LOCALES = [
  { code: 'en' as const, name: 'English', nativeName: 'English' },
  { code: 'ko' as const, name: 'Korean', nativeName: '한국어' },
  { code: 'ja' as const, name: 'Japanese', nativeName: '日本語' },
  { code: 'zh' as const, name: 'Chinese', nativeName: '中文' },
]

export async function setLocale(lang: SupportedLocale) {
  if (!i18n.global.availableLocales.includes(lang)) {
    const messages = await import(`./locales/${lang}.json`)
    i18n.global.setLocaleMessage(lang, messages.default)
  }
  ;(i18n.global.locale as unknown as { value: string }).value = lang
  localStorage.setItem(STORAGE_KEY, lang)
  document.documentElement.lang = lang
}
