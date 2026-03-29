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
      return `<div class="plugo-image"><img src="${url}" alt="${alt}" loading="lazy" /></div>`;
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

/** Post-process: wrap consecutive images into a slideshow */
function wrapImageSlideshow(html: string): string {
  return html.replace(
    /(<div class="plugo-image">.*?<\/div>\s*){2,}/g,
    (match) => {
      const images = match.match(/<div class="plugo-image">.*?<\/div>/gs) || [];
      const slides = images.map((img, i) =>
        `<div class="plugo-slide${i === 0 ? " active" : ""}">${img}</div>`
      ).join("");
      return `<div class="plugo-slideshow" data-total="${images.length}"><div class="plugo-slides">${slides}</div><div class="plugo-slide-nav"><button class="plugo-slide-prev" data-dir="prev">\u2039</button><span class="plugo-slide-count">1/${images.length}</span><button class="plugo-slide-next" data-dir="next">\u203A</button></div></div>`;
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
  let html = marked.parse(text) as string;
  html = wrapImageSlideshow(html);
  html = wrapButtonGroups(html);
  return html;
}

/** Parse markdown with incomplete syntax handling — for streaming */
export function parseStreamingMarkdown(text: string): string {
  const closed = closeIncompleteMarkdown(text);
  return marked.parse(closed) as string;
}
