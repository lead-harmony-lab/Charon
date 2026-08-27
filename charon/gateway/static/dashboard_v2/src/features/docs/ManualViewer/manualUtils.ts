/**
 * @file src/features/docs/ManualViewer/manualUtils.ts
 * @description
 */
import { ManualNode } from '../../../components/treeUtils';

export function triggerManualViewer(id: string) {
  window.dispatchEvent(new CustomEvent('open-manual-topic', { detail: { id } }));
  window.location.hash = id;
}

export const INITIAL_TREE: ManualNode[] = [];

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