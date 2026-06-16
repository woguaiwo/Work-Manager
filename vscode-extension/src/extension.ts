/**
 * Work Manager for VS Code
 *
 * Tracks the current working directory (CWD) of the active integrated terminal
 * and exposes it to the local Work Manager app.
 */
import * as vscode from 'vscode';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';

const DEFAULT_OUTPUT_FILENAME = '.wm_vscode_cwd';

let updateTimer: NodeJS.Timeout | undefined;
let originalTitleSetting: string | undefined;
let disposables: vscode.Disposable[] = [];

// Cache the latest known CWD for each terminal
const terminalCwdMap = new WeakMap<vscode.Terminal, string>();

export function activate(context: vscode.ExtensionContext) {
    context.subscriptions.push(
        vscode.commands.registerCommand('workManager.updateNow', updateNow)
    );

    // When a terminal's shell integration becomes ready, register its CWD listener
    context.subscriptions.push(
        vscode.window.onDidChangeTerminalShellIntegration((event) => {
            const cwd = event.shellIntegration.cwd?.fsPath;
            if (cwd) {
                terminalCwdMap.set(event.terminal, cwd);
                registerCwdListener(event.terminal, event.shellIntegration);
                scheduleUpdate();
            }
        })
    );

    // Track already-open terminals
    vscode.window.terminals.forEach((terminal) => {
        const si = (terminal as any).shellIntegration;
        if (si?.cwd) {
            terminalCwdMap.set(terminal, si.cwd.fsPath);
            registerCwdListener(terminal, si);
        }
    });

    context.subscriptions.push(
        vscode.window.onDidChangeActiveTerminal(() => scheduleUpdate())
    );

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

function registerCwdListener(terminal: vscode.Terminal, si: any) {
    if (typeof si.onDidChangeCurrentDirectory !== 'function') {
        return;
    }
    const existing = (terminal as any)._wmCwdDisposable;
    if (existing) {
        existing.dispose();
    }
    const disposable = si.onDidChangeCurrentDirectory((uri: vscode.Uri) => {
        terminalCwdMap.set(terminal, uri.fsPath);
        scheduleUpdate();
    });
    (terminal as any)._wmCwdDisposable = disposable;
    disposables.push(disposable);
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
    const cwd = getActiveTerminalCwd();
    if (cwd) {
        await writeCwdToFile(cwd);
        await updateWindowTitle(cwd);
    }
}

function getActiveTerminalCwd(): string | undefined {
    const terminal = vscode.window.activeTerminal;
    if (!terminal) {
        return undefined;
    }

    // 1. Use cached CWD from shell integration events
    if (terminalCwdMap.has(terminal)) {
        return terminalCwdMap.get(terminal);
    }

    // 2. Try reading current shellIntegration state
    const si = (terminal as any).shellIntegration;
    if (si?.cwd) {
        const cwd = si.cwd.fsPath;
        terminalCwdMap.set(terminal, cwd);
        registerCwdListener(terminal, si);
        return cwd;
    }

    return undefined;
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

    const newTitle = format
        .replace(/\${cwd}/g, cwd)
        .replace(/\${cwdBasename}/g, cwdBasename);

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
