import { useState, useEffect } from "react";
import { getLocale, setLocale, onLocaleChange, t, type Locale } from "./i18n";

export function useLocale() {
  const [locale, _setLocale] = useState<Locale>(getLocale());

  useEffect(() => {
    return onLocaleChange(() => _setLocale(getLocale()));
  }, []);

  return {
    locale,
    setLocale,
    t,
  };
}
