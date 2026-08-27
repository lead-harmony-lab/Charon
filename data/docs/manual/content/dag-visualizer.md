### DAG Visualizer

**Scope & Rendering**
Consumes the `steps` array to render the high-level Directed Acyclic Graph of execution. 

**Technical Details**
* Renders a vertical timeline UI using absolute positioning for connection lines (`2px` solid tracks) linking sequential node dots.
* Displays the active `agent_name`, timestamp, and primary step payload.