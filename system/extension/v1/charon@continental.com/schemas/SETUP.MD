`charond` is officially back online and responding on port 8000!

The reason the GNOME Shell Extension is still failing to authenticate is right in your `gschema.xml`: **the `api-key`, `api-url`, and `api-key-header` keys are missing from the schema definition**.

When `extension.js` calls `this._settings.get_string('api-key')`, GLib throws a "Key not found" error, causing the code to hit the `catch` block and fall back to `DEFAULT_CHARON_API_KEY` (`'charon-secret-key-change-me'`).

---

### Step 1: Update `org.gnome.shell.extensions.charon.gschema.xml`

Add the missing settings keys to your schema file:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<schemalist>
  <schema id="org.gnome.shell.extensions.charon" path="/org/gnome/shell/extensions/charon/">
    <key name="toggle-shortcut" type="as">
      <default>['&lt;Super&gt;&lt;Alt&gt;c']</default>
      <summary>Toggle Charon prompt overlay</summary>
      <description>Shortcut key combination to open the Charon concierge menu and focus input.</description>
    </key>
    <key name="api-url" type="s">
      <default>'http://127.0.0.1:8000'</default>
      <summary>Charon Daemon API Endpoint</summary>
      <description>Base URL for the Charon REST and WebSocket daemon.</description>
    </key>
    <key name="api-key" type="s">
      <default>'charon-secret-key-change-me'</default>
      <summary>Charon API Key</summary>
      <description>Secret token for API authentication.</description>
    </key>
    <key name="api-key-header" type="s">
      <default>'X-API-Key'</default>
      <summary>API Key Header Name</summary>
      <description>HTTP header name used for transmitting the API key.</description>
    </key>
  </schema>
</schemalist>

```

---

### Step 2: Compile Schemas & Store the Real API Key

Run the following in your extension's directory (replace `~/.local/share/gnome-shell/extensions/<your-extension-uuid>/schemas/` with your actual schema path if different):

```bash
# 1. Compile the updated schema
glib-compile-intent ~/.local/share/gnome-shell/extensions/<your-extension-uuid>/intent/

# 2. Write your real API key to GSettings
gsettings set org.gnome.shell.extensions.charon api-key "f026286a1cd2556b7bfd1e5af643e6e4b4b095aa8d9c02c4e1ee918cc827647c"

```

---

### Step 3: Reload the Extension

Toggle the extension in GNOME Shell to trigger `enable()` with the newly compiled schema:

```bash
gnome-extensions disable <your-extension-uuid>
gnome-extensions enable <your-extension-uuid>

```

Your panel indicator should now transition from `⚠️ Charon: Offline` to **`👔 Charon: Online`** with live Overseer telemetry updates streaming through the WebSocket connection!