import { Marked } from "marked";
import hljs from "highlight.js/lib/core";
import javascript from "highlight.js/lib/languages/javascript";
import python from "highlight.js/lib/languages/python";
import xml from "highlight.js/lib/languages/xml";
import css from "highlight.js/lib/languages/css";
import json from "highlight.js/lib/languages/json";
import bash from "highlight.js/lib/languages/bash";

hljs.registerLanguage("javascript", javascript);
hljs.registerLanguage("js", javascript);
hljs.registerLanguage("python", python);
hljs.registerLanguage("html", xml);
hljs.registerLanguage("xml", xml);
hljs.registerLanguage("css", css);
hljs.registerLanguage("json", json);
hljs.registerLanguage("bash", bash);
hljs.registerLanguage("sh", bash);

/** Extract YouTube video ID from various URL formats */
function getYouTubeId(url: string): string | null {
  const m = url.match(/(?:youtube\.com\/(?:watch\?v=|embed\/|shorts\/)|youtu\.be\/)([\w-]{11})/);
  return m ? m[1] : null;
}

/** Escape a string for safe use inside an HTML attribute */
function escapeAttr(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/** Sanitize URL — only allow http(s) and relative paths */
function sanitizeUrl(url: string): string {
  if (/^https?:\/\//i.test(url) || url.startsWith("/")) return url;
  return "#";
}

const marked = new Marked({
  renderer: {
    // Escape raw HTML to prevent XSS
    html(token) {
      return token.text
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
    },
    code(token) {
      const lang = token.lang || "";
      let highlighted: string;
      if (lang && hljs.getLanguage(lang)) {
        highlighted = hljs.highlight(token.text, { language: lang }).value;
      } else {
        highlighted = hljs.highlightAuto(token.text).value;
      }
      return `<pre class="plugo-code"><code class="hljs">${highlighted}</code></pre>`;
    },
    // Images — detect videos by URL, otherwise render as image
    image(token) {
      const url = sanitizeUrl(token.href);
      const alt = token.text || "";
      // YouTube embed
      const ytId = getYouTubeId(url);
      if (ytId || alt.toLowerCase() === "video") {
        if (ytId) {
          return `<div class="plugo-video"><iframe src="https://www.youtube.com/embed/${ytId}" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe></div>`;
        }
        // Generic video
        return `<div class="plugo-video"><video src="${url}" controls preload="metadata"></video></div>`;
      }
      // Regular image
      return `<div class="plugo-image"><img src="${url}" alt="${escapeAttr(alt)}" loading="lazy" /></div>`;
    },
    // Links — detect "button" title to render as button
    link(token) {
      const href = sanitizeUrl(token.href);
      if (token.title === "button") {
        return `<a href="${href}" target="_blank" rel="noopener noreferrer" class="plugo-btn">${token.text}</a>`;
      }
      return `<a href="${href}" target="_blank" rel="noopener noreferrer">${token.text}</a>`;
    },
  },
});

/** Post-process: wrap consecutive buttons into a button group */
function wrapButtonGroups(html: string): string {
  return html.replace(
    /(<a [^>]*class="plugo-btn"[^>]*>.*?<\/a>\s*)+/g,
    (match) => `<div class="plugo-btn-group">${match.trim()}</div>`
  );
}

/**
 * Pre-process: extract :::gallery blocks from markdown source and replace
 * with placeholder tokens. After marked parses the rest, we swap the
 * placeholders with rendered slideshow HTML.
 *
 * This is more reliable than post-processing HTML because:
 * 1. Explicit intent — the LLM declares a gallery, no guessing
 * 2. Works during streaming — partial :::gallery block is left as-is
 * 3. No fragile HTML regex that breaks when <p> tags appear between images
 */
const GALLERY_RE = /:::gallery\n([\s\S]*?):::/g;
const GALLERY_PLACEHOLDER = "PLUGOGALLERY";

function extractGalleries(text: string): { text: string; galleries: string[] } {
  const galleries: string[] = [];
  GALLERY_RE.lastIndex = 0;
  const replaced = text.replace(GALLERY_RE, (_match, content: string) => {
    const idx = galleries.length;
    galleries.push(content.trim());
    // Use a plain-text placeholder that survives marked parsing (HTML comments get escaped)
    return `${GALLERY_PLACEHOLDER}${idx}END`;
  });
  return { text: replaced, galleries };
}

/** Build slideshow HTML from an array of image HTML strings */
function renderSlideshow(imageHtmlArr: string[]): string {
  const total = imageHtmlArr.length;
  const slides = imageHtmlArr
    .map((imgHtml, i) => `<div class="plugo-slide${i === 0 ? " active" : ""}">${imgHtml}</div>`)
    .join("");
  const dots = imageHtmlArr
    .map((_, i) => `<button class="plugo-slide-dot${i === 0 ? " active" : ""}" data-slide="${i}"></button>`)
    .join("");
  return (
    `<div class="plugo-slideshow" data-total="${total}">` +
      `<div class="plugo-slides">${slides}` +
        `<button class="plugo-slide-prev" data-dir="prev">\u2039</button>` +
        `<button class="plugo-slide-next" data-dir="next">\u203A</button>` +
      `</div>` +
      `<div class="plugo-slide-nav">${dots}<span class="plugo-slide-count">1/${total}</span></div>` +
    `</div>`
  );
}

function buildSlideshowHtml(markdownImages: string): string {
  const imgRe = /!\[([^\]]*)\]\(([^)]+)\)/g;
  const images: { alt: string; url: string }[] = [];
  let m: RegExpExecArray | null;
  while ((m = imgRe.exec(markdownImages)) !== null) {
    images.push({ alt: m[1], url: sanitizeUrl(m[2]) });
  }
  if (images.length === 0) return "";
  if (images.length === 1) {
    return `<div class="plugo-image"><img src="${images[0].url}" alt="${escapeAttr(images[0].alt)}" loading="lazy" /></div>`;
  }
  const htmlArr = images.map(
    (img) => `<div class="plugo-image"><img src="${img.url}" alt="${escapeAttr(img.alt)}" loading="lazy" /></div>`,
  );
  return renderSlideshow(htmlArr);
}

function restoreGalleries(html: string, galleries: string[]): string {
  // Match the placeholder in any context (may be wrapped in <p> tags by marked)
  return html.replace(new RegExp(`(?:<p>)?${GALLERY_PLACEHOLDER}(\\d+)END(?:<\\/p>)?`, "g"), (_m, idx) => {
    const content = galleries[Number(idx)];
    return content ? buildSlideshowHtml(content) : "";
  });
}

/** Fallback: wrap consecutive images into a slideshow (for old responses without :::gallery) */
function wrapImageSlideshow(html: string): string {
  return html.replace(
    /(<div class="plugo-image">.*?<\/div>\s*){2,}/g,
    (match) => {
      const images = match.match(/<div class="plugo-image">.*?<\/div>/gs) || [];
      if (images.length < 2) return match;
      return renderSlideshow(images);
    }
  );
}

/**
 * Close any unclosed markdown syntax so partial streaming text renders cleanly.
 * Handles: bold, italic, strikethrough, code, code blocks, links, images.
 */
function closeIncompleteMarkdown(text: string): string {
  let s = text;

  // Close unclosed fenced code blocks (``` or ~~~)
  const fenceMatches = s.match(/^(`{3,}|~{3,})/gm);
  if (fenceMatches && fenceMatches.length % 2 !== 0) {
    s += "\n" + fenceMatches[fenceMatches.length - 1];
  }

  // Close unclosed inline code (odd number of `)
  const inlineCode = s.match(/(?<!`)`(?!`)/g);
  if (inlineCode && inlineCode.length % 2 !== 0) {
    s += "`";
  }

  // Close unclosed :::gallery block — append ::: so it renders as slideshow during streaming
  if (/:::gallery\n/.test(s) && !(GALLERY_RE.test(s))) {
    // Reset regex lastIndex since we use /g flag
    GALLERY_RE.lastIndex = 0;
    s += "\n:::";
  }
  GALLERY_RE.lastIndex = 0;

  // Close unclosed bold/italic markers
  const closePairs = (src: string, marker: string): string => {
    const escaped = marker.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const re = new RegExp(escaped, "g");
    const matches = src.match(re);
    if (matches && matches.length % 2 !== 0) {
      return src + marker;
    }
    return src;
  };
  s = closePairs(s, "***");
  s = closePairs(s, "**");
  s = closePairs(s, "*");
  s = closePairs(s, "~~");

  // Close unclosed link/image: detect trailing `[text` or `[text](url` without closing
  if (/\[[^\]]*$/.test(s) && !/\]\([^)]*\)/.test(s.slice(s.lastIndexOf("[")))) {
    // Incomplete link — just strip the opening bracket to show as plain text
    s = s.replace(/\[([^\]]*)$/, "$1");
  }

  return s;
}

export function parseMarkdown(text: string): string {
  const { text: cleaned, galleries } = extractGalleries(text);
  let html = marked.parse(cleaned) as string;
  html = restoreGalleries(html, galleries);
  html = wrapImageSlideshow(html); // fallback for old responses without :::gallery
  html = wrapButtonGroups(html);
  return html;
}

/** Parse markdown with incomplete syntax handling — for streaming */
export function parseStreamingMarkdown(text: string): string {
  const closed = closeIncompleteMarkdown(text);
  const { text: cleaned, galleries } = extractGalleries(closed);
  let html = marked.parse(cleaned) as string;
  html = restoreGalleries(html, galleries);
  html = wrapImageSlideshow(html); // fallback
  html = wrapButtonGroups(html);
  return html;
}
