export type WidgetLocale = "vi" | "en" | "ja" | "ko" | "zh" | "fr" | "de" | "es" | "th";

const widgetStrings: Record<string, Record<string, string>> = {
  vi: { placeholder: "Nhập tin nhắn...", send: "Gửi", powered: "Powered by Plugo", connecting: "Đang kết nối...", reconnecting: "Đang kết nối lại...", disconnected: "Mất kết nối", newMessages: "Tin nhắn mới", charLimit: "ký tự", suggestions: "Gợi ý:", error: "Đã xảy ra lỗi", chatTitle: "Chat hỗ trợ", typing: "Đang nhập..." },
  en: { placeholder: "Type a message...", send: "Send", powered: "Powered by Plugo", connecting: "Connecting...", reconnecting: "Reconnecting...", disconnected: "Disconnected", newMessages: "New messages", charLimit: "chars", suggestions: "Suggestions:", error: "An error occurred", chatTitle: "Chat Support", typing: "Typing..." },
  ja: { placeholder: "メッセージを入力...", send: "送信", powered: "Powered by Plugo", connecting: "接続中...", reconnecting: "再接続中...", disconnected: "切断されました", newMessages: "新着メッセージ", charLimit: "文字", suggestions: "提案:", error: "エラーが発生しました", chatTitle: "チャットサポート", typing: "入力中..." },
  ko: { placeholder: "메시지를 입력하세요...", send: "전송", powered: "Powered by Plugo", connecting: "연결 중...", reconnecting: "재연결 중...", disconnected: "연결 끊김", newMessages: "새 메시지", charLimit: "자", suggestions: "제안:", error: "오류가 발생했습니다", chatTitle: "채팅 지원", typing: "입력 중..." },
  zh: { placeholder: "输入消息...", send: "发送", powered: "Powered by Plugo", connecting: "连接中...", reconnecting: "重新连接...", disconnected: "已断开", newMessages: "新消息", charLimit: "字符", suggestions: "建议:", error: "发生错误", chatTitle: "在线客服", typing: "正在输入..." },
  fr: { placeholder: "Tapez un message...", send: "Envoyer", powered: "Powered by Plugo", connecting: "Connexion...", reconnecting: "Reconnexion...", disconnected: "Déconnecté", newMessages: "Nouveaux messages", charLimit: "car.", suggestions: "Suggestions:", error: "Une erreur est survenue", chatTitle: "Support Chat", typing: "En train d'écrire..." },
  de: { placeholder: "Nachricht eingeben...", send: "Senden", powered: "Powered by Plugo", connecting: "Verbindung...", reconnecting: "Erneut verbinden...", disconnected: "Getrennt", newMessages: "Neue Nachrichten", charLimit: "Zeichen", suggestions: "Vorschläge:", error: "Ein Fehler ist aufgetreten", chatTitle: "Chat-Support", typing: "Schreibt..." },
  es: { placeholder: "Escribe un mensaje...", send: "Enviar", powered: "Powered by Plugo", connecting: "Conectando...", reconnecting: "Reconectando...", disconnected: "Desconectado", newMessages: "Nuevos mensajes", charLimit: "car.", suggestions: "Sugerencias:", error: "Se produjo un error", chatTitle: "Soporte Chat", typing: "Escribiendo..." },
  th: { placeholder: "พิมพ์ข้อความ...", send: "ส่ง", powered: "Powered by Plugo", connecting: "กำลังเชื่อมต่อ...", reconnecting: "กำลังเชื่อมต่อใหม่...", disconnected: "ขาดการเชื่อมต่อ", newMessages: "ข้อความใหม่", charLimit: "ตัวอักษร", suggestions: "คำแนะนำ:", error: "เกิดข้อผิดพลาด", chatTitle: "แชทสนับสนุน", typing: "กำลังพิมพ์..." },
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
