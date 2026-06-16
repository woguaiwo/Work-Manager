# Work Manager for VS Code

A companion extension for [Work Manager](https://github.com/woguaiwo/Work-Manager) that tracks the current working directory of your active VS Code integrated terminal. This lets Work Manager distinguish different tasks even when you work in multiple directories inside the same VS Code window — including remote SSH workspaces.

## Why?

Work Manager reads the foreground window title to know what you are working on. For local VS Code, the title shows the workspace folder. For remote SSH, the title only shows `[SSH: hostname]`, and the terminal directory is never visible.

This extension solves that by:

1. Writing the active terminal CWD to `~/.wm_vscode_cwd`.
2. Optionally injecting the CWD into the VS Code window title so Work Manager can read it directly.

## Features

- Tracks the active integrated terminal's current directory
- Works for local and remote (SSH) VS Code windows
- Updates the VS Code window title to include the terminal CWD
- Configurable output path and title format

## Requirements

- VS Code 1.93 or newer
- Shell integration enabled in VS Code terminal (enabled by default)

## Extension Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `workManager.outputPath` | `~/.wm_vscode_cwd` | File to write the active terminal CWD to |
| `workManager.updateWindowTitle` | `true` | Inject CWD into the VS Code window title |
| `workManager.titleFormat` | see `package.json` | Format for the injected window title |
| `workManager.updateIntervalMs` | `1000` | How often to refresh the CWD |

Available placeholders in `titleFormat`:

- `${cwd}` — full current working directory
- `${cwdBasename}` — last segment of the CWD (e.g. `backend` from `/project/backend`)

Standard VS Code placeholders such as `${dirty}`, `${activeEditorShort}`, `${separator}`, `${rootName}`, and `${appName}` are also supported because the final string is passed to VS Code's own `window.title` setting.

## Installation

### From a Local `.vsix` File

1. In the `vscode-extension` folder, run:
   ```bash
   npm install
   npm run compile
   npx @vscode/vsce package
   ```
2. You will get a `.vsix` file.
3. In VS Code, press `Ctrl+Shift+P` → `Extensions: Install from VSIX...` → pick the file.

### From the VS Code Marketplace

1. Search for **"Work Manager for VS Code"** in the Extensions view.
2. Click Install.

## Publish to Marketplace

1. Register a free account at [Azure DevOps](https://dev.azure.com).
2. Create a Personal Access Token with `Marketplace > Publish` scope.
3. Install the publishing tool:
   ```bash
   npm install -g @vscode/vsce
   ```
4. Login and publish:
   ```bash
   vsce login <publisher-name>
   vsce publish
   ```

Replace `<publisher-name>` with your Marketplace publisher ID.

## License

MIT
