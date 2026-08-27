### MarkdownRenderer

**Scope & Rendering**
A robust wrapper around `react-markdown` and `react-syntax-highlighter`. It applies custom styles to headers, blockquotes, and lists to match the application's dark theme.

**Key Features**
* **Code Blocks:** Automatically detects block vs. inline code. Block code utilizes the `oneDark` Prism theme and renders a stylized language header if a language tag (e.g., `bash`, `json`) is provided.
* **Link Interception:** Overrides default anchor tag behavior. If a link URL begins with `#` (an internal reference), it intercepts the click event, prevents default routing, and fires the `onInternalLinkClick(id)` callback, enabling seamless navigation between internal documents.