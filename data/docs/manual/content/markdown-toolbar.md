### MarkdownToolbar

**Scope & Rendering**
A controlled component that attaches to a standard HTML textarea to provide WYSIWYG-like Markdown authoring.

**Technical Details**
* Requires a `textareaRef` to interact directly with the DOM node's selection state.
* Exposes quick-insert buttons for common Markdown syntax (bold, italic, headers, lists, code blocks, and internal links).
* **Cursor Management:** Intelligently wraps selected text with the chosen formatting tokens and automatically resets the cursor position inside the newly injected syntax, ensuring a smooth typing experience.