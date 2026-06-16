/**
 * Work Manager for VS Code
 *
 * Tracks the current working directory (CWD) of the active integrated terminal
 * and exposes it to the local Work Manager app in two ways:
 *  1. Writes the CWD to a local file.
 *  2. Optionally injects the CWD into the VS Code window title.
 */
import * as vscode from 'vscode';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';

const DEFAULT_OUTPUT_FILENAME = '.wm_vscode_cwd';

let updateTimer: NodeJS.Timeout | undefined;
let lastCwd: string | undefined;
let originalTitleSetting: string | undefined;
let disposables: vscode.Disposable[] = [];

export function activate(context: vscode.ExtensionContext) {
    // Register command to force a refresh
    context.subscriptions.push(
        vscode.commands.registerCommand('workManager.updateNow', updateNow)
    );

    // Listen for terminal activation and CWD changes
    context.subscriptions.push(
        vscode.window.onDidChangeActiveTerminal(() => scheduleUpdate())
    );

    // Some terminals fire shellIntegration events; listen on the active terminal if available
    context.subscriptions.push(
        vscode.window.onDidOpenTerminal(trackTerminal)
    );

    vscode.window.terminals.forEach(trackTerminal);

    // Listen for configuration changes
    context.subscriptions.push(
        vscode.workspace.onDidChangeConfiguration((e) => {
            if (e.affectsConfiguration('workManager')) {
                scheduleUpdate();
            }
        })
    );

    scheduleUpdate();
}

export function deactivate() {
    if (updateTimer) {
        clearTimeout(updateTimer);
        updateTimer = undefined;
    }
    disposables.forEach(d => d.dispose());
    disposables = [];
    restoreWindowTitle();
}

function trackTerminal(terminal: vscode.Terminal) {
    const si = (terminal as any).shellIntegration;
    if (si && typeof si.onDidChangeCurrentDirectory === 'function') {
        disposables.push(
            si.onDidChangeCurrentDirectory(() => scheduleUpdate())
        );
    }
}

function scheduleUpdate() {
    if (updateTimer) {
        clearTimeout(updateTimer);
    }
    const config = vscode.workspace.getConfiguration('workManager');
    const interval = config.get<number>('updateIntervalMs', 1000);
    updateTimer = setTimeout(updateNow, Math.max(100, interval));
}

async function updateNow() {
    const cwd = await getActiveTerminalCwd();
    if (cwd) {
        lastCwd = cwd;
        await writeCwdToFile(cwd);
        await updateWindowTitle(cwd);
    }
}

async function getActiveTerminalCwd(): Promise<string | undefined> {
    const terminal = vscode.window.activeTerminal;
    if (!terminal) {
        return undefined;
    }

    // Method 1: shellIntegration.cwd (VS Code 1.93+, requires shell integration enabled)
    const si = (terminal as any).shellIntegration;
    if (si && si.cwd) {
        return si.cwd.fsPath;
    }

    // Method 2: send a POSIX shell command and read the result
    // This only works if the terminal is in a shell that supports `pwd` and
    // the shell integration stream is enabled. It is a best-effort fallback.
    try {
        const result = await new Promise<string | undefined>((resolve) => {
            const disposable = vscode.window.onDidChangeTerminalShellIntegration((event) => {
                if (event.terminal === terminal && event.shellIntegration.cwd) {
                    disposable.dispose();
                    resolve(event.shellIntegration.cwd.fsPath);
                }
            });
            setTimeout(() => {
                disposable.dispose();
                resolve(undefined);
            }, 500);
        });
        if (result) { return result; }
    } catch {
        // ignore
    }

    return lastCwd;
}

async function writeCwdToFile(cwd: string) {
    const config = vscode.workspace.getConfiguration('workManager');
    let outputPath = config.get<string>('outputPath', '');

    if (!outputPath) {
        outputPath = path.join(os.homedir(), DEFAULT_OUTPUT_FILENAME);
    }

    try {
        fs.writeFileSync(outputPath, cwd, { encoding: 'utf8' });
    } catch (err) {
        console.error('[Work Manager] Failed to write CWD file:', err);
    }
}

async function updateWindowTitle(cwd: string) {
    const config = vscode.workspace.getConfiguration('workManager');
    if (!config.get<boolean>('updateWindowTitle', true)) {
        restoreWindowTitle();
        return;
    }

    const format = config.get<string>(
        'titleFormat',
        '${dirty}${activeEditorShort}${separator}${rootName}${separator}[${cwdBasename}]${separator}${appName}'
    );

    const cwdBasename = path.basename(cwd) || cwd;

    // Expand the supported variables manually
    let newTitle = format
        .replace(/\${cwd}/g, cwd)
        .replace(/\${cwdBasename}/g, cwdBasename);

    // Update only the workspace-scoped setting; remember original value first time
    const titleConfig = vscode.workspace.getConfiguration('window');
    if (originalTitleSetting === undefined) {
        originalTitleSetting = titleConfig.get<string>('title', '');
    }

    try {
        await titleConfig.update('title', newTitle, vscode.ConfigurationTarget.Workspace);
    } catch (err) {
        console.error('[Work Manager] Failed to update window title:', err);
    }
}

function restoreWindowTitle() {
    if (originalTitleSetting === undefined) {
        return;
    }
    const titleConfig = vscode.workspace.getConfiguration('window');
    titleConfig.update('title', originalTitleSetting, vscode.ConfigurationTarget.Workspace)
        .then(undefined, (err) => console.error('[Work Manager] Failed to restore window title:', err));
    originalTitleSetting = undefined;
}
