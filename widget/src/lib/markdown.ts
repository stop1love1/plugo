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
    link(token) {
      return `<a href="${token.href}" target="_blank" rel="noopener noreferrer">${token.text}</a>`;
    },
  },
});

export function parseMarkdown(text: string): string {
  return marked.parse(text) as string;
}
