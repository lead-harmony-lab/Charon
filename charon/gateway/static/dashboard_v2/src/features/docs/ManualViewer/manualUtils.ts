/**
 * @file src/features/docs/ManualViewer/manualUtils.ts
 * @description
 */
import { ManualNode } from '../../../components/treeUtils';

export function triggerManualViewer(id: string) {
  window.dispatchEvent(new CustomEvent('open-manual-topic', { detail: { id } }));
  window.location.hash = id;
}

export const INITIAL_TREE: ManualNode[] = [
  {
    id: 'getting-started',
    title: 'Getting Started',
    content: `## Charon Control: Getting Started\n\nWelcome to Charon Control. This system orchestrates agents, diagnostics, and integrations via a unified daemon connection. See [Backend Orchestrator](#backend-orchestrator) for more info.`
  },
  {
    id: 'backend-orchestrator',
    title: 'Backend Orchestrator',
    content: `## Backend Orchestrator\n\nThe central rust/node daemon that manages state.`,
    children: [
      {
        id: 'websocket-protocol',
        title: 'WebSocket Protocol',
        content: `### WebSocket Protocol\n\nAll real-time communication flows through the centralized WS router.`,
      }
    ]
  },
  {
    id: 'desktop-avatar',
    title: 'Desktop Avatar',
    content: `## Desktop Avatar\n\nThe primary user-facing frontend.`,
    children: []
  }
];

export function parseMarkdownToNodeTree(rawMarkdown: string): ManualNode[] {
  const lines = rawMarkdown.split('\n');
  const rootNodes: ManualNode[] = [];
  let currentParent: ManualNode | null = null;
  let currentChunk: string[] = [];
  let currentTitle = '';
  let currentId = '';

  const finalizeNode = () => {
    if (!currentTitle) return;
    const newNode: ManualNode = {
      id: currentId || currentTitle.toLowerCase().replace(/[^a-z0-9]+/g, '-'),
      title: currentTitle,
      content: currentChunk.join('\n').trim(),
      children: []
    };

    if (currentParent) {
      currentParent.children = currentParent.children || [];
      currentParent.children.push(newNode);
    } else {
      rootNodes.push(newNode);
    }
  };

  for (const line of lines) {
    if (line.startsWith('## ')) {
      finalizeNode();
      currentTitle = line.replace('## ', '').trim();
      currentId = currentTitle.toLowerCase().replace(/[^a-z0-9]+/g, '-');
      currentChunk = [line];
      currentParent = null;
    } else if (line.startsWith('### ') && rootNodes.length > 0) {
      finalizeNode();
      currentTitle = line.replace('### ', '').trim();
      currentId = currentTitle.toLowerCase().replace(/[^a-z0-9]+/g, '-');
      currentChunk = [line];
      currentParent = rootNodes[rootNodes.length - 1];
    } else {
      currentChunk.push(line);
    }
  }

  finalizeNode();
  return rootNodes.length > 0 ? rootNodes : INITIAL_TREE;
}