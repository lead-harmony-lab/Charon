### Avatar Stream Visualizer

**Data Flow & Real-Time Sync**
This standalone component provides real-time visualization of the daemon's "Concierge" layer. It establishes two WebSocket subscriptions via `wsClient`:
* **`proactive_interjection`**: Updates the avatar's emotional state, current speech text, and optional target coordinates.
* **`cursor_motion`**: High-frequency updates overriding the current `pointerTarget` coordinates.

**Canvas Rendering Loop**
Instead of standard DOM elements, it utilizes an HTML5 `<canvas>` element and a `requestAnimationFrame` loop to render a dynamic HUD. 
* **Viseme Orb**: Draws a radial gradient orb that pulses smoothly using a sine wave (`Math.sin(phase)`). The color maps dynamically to the WebSocket emotion data (Blue for 'speaking', Green for others).
* **Pointer Target**: If coordinate data is present, it draws a red, translucent stroke rectangle (`ctx.strokeRect`) to indicate where the system is "looking" or pointing on the screen.