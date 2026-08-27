### Blackboard Trace

**Scope & Rendering**
Consumes the `thoughts` array to render a live, terminal-like feed of the system's inner monologue.

**Technical Details**
* **Auto-scrolling**: Implements a `useRef` attached to an empty bottom `<div>`. A `useEffect` hook triggers `scrollIntoView({ behavior: 'smooth' })` whenever the `thoughts` array mutates, keeping the user locked to the latest telemetry.
* **Color-Coded Taxonomy**: Dynamically styles thought badges based on `thought_type` (`ANALYSIS` → Purple, `PLANNING` → Blue, `EXECUTION` → Green, `ERROR` → Red).