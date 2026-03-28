export type WidgetLocale = "vi" | "en" | "ja" | "ko" | "zh" | "fr" | "de" | "es" | "th";

const widgetStrings: Record<string, Record<string, string>> = {
  vi: { placeholder: "Nhập tin nhắn...", send: "Gửi", powered: "Powered by Plugo" },
  en: { placeholder: "Type a message...", send: "Send", powered: "Powered by Plugo" },
  ja: { placeholder: "メッセージを入力...", send: "送信", powered: "Powered by Plugo" },
  ko: { placeholder: "메시지를 입력하세요...", send: "전송", powered: "Powered by Plugo" },
  zh: { placeholder: "输入消息...", send: "发送", powered: "Powered by Plugo" },
  fr: { placeholder: "Tapez un message...", send: "Envoyer", powered: "Powered by Plugo" },
  de: { placeholder: "Nachricht eingeben...", send: "Senden", powered: "Powered by Plugo" },
  es: { placeholder: "Escribe un mensaje...", send: "Enviar", powered: "Powered by Plugo" },
  th: { placeholder: "พิมพ์ข้อความ...", send: "ส่ง", powered: "Powered by Plugo" },
};

/** Map a raw language code to a supported locale key */
function normalizeLocale(lang: string): string {
  const code = lang.toLowerCase().split("-")[0];
  if (code in widgetStrings) return code;
  return "en"; // fallback
}

export function getWidgetString(key: string, lang: string = "en"): string {
  const locale = normalizeLocale(lang);
  return widgetStrings[locale]?.[key] || widgetStrings["en"][key] || key;
}

/**
 * Auto-detect the primary language of the host page.
 * Priority:
 *   1. <html lang="..."> attribute (most reliable — set by the project)
 *   2. <meta http-equiv="content-language"> tag
 *   3. <meta property="og:locale"> tag
 *   4. Sample page text and detect Vietnamese/CJK/Thai by character frequency
 *   5. navigator.language (browser default — least specific to the project)
 */
export function detectLanguage(): string {
  // 1. html lang attribute — the standard way to declare page language
  const htmlLang = document.documentElement.lang;
  if (htmlLang) return htmlLang;

  // 2. meta content-language
  const metaLang = document.querySelector('meta[http-equiv="content-language"]');
  if (metaLang) {
    const val = metaLang.getAttribute("content");
    if (val) return val;
  }

  // 3. og:locale
  const ogLocale = document.querySelector('meta[property="og:locale"]');
  if (ogLocale) {
    const val = ogLocale.getAttribute("content");
    if (val) return val.replace("_", "-");
  }

  // 4. Detect from page text content (sample first 3000 chars)
  const textSample = (document.body?.innerText || "").substring(0, 3000);
  if (textSample.length > 100) {
    const detected = detectFromText(textSample);
    if (detected) return detected;
  }

  // 5. Browser language (fallback)
  return navigator.language || "en";
}

/**
 * Simple character-frequency based language detection.
 * Works well for distinguishing Vietnamese, CJK, Thai, etc. from Latin scripts.
 */
function detectFromText(text: string): string | null {
  // Vietnamese diacritical characters — highly specific
  const viChars = /[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]/gi;
  const viMatches = text.match(viChars);
  if (viMatches && viMatches.length > text.length * 0.02) return "vi";

  // CJK Unified Ideographs
  const cjk = /[\u4e00-\u9fff]/g;
  const cjkMatches = text.match(cjk);
  if (cjkMatches && cjkMatches.length > text.length * 0.1) {
    // Distinguish Chinese vs Japanese
    const hiragana = /[\u3040-\u309f]/g;
    const hiraMatches = text.match(hiragana);
    if (hiraMatches && hiraMatches.length > 5) return "ja";
    return "zh";
  }

  // Korean Hangul
  const hangul = /[\uac00-\ud7af\u1100-\u11ff]/g;
  const hangulMatches = text.match(hangul);
  if (hangulMatches && hangulMatches.length > text.length * 0.1) return "ko";

  // Thai
  const thai = /[\u0e00-\u0e7f]/g;
  const thaiMatches = text.match(thai);
  if (thaiMatches && thaiMatches.length > text.length * 0.1) return "th";

  return null; // Can't determine — let the caller use browser default
}
