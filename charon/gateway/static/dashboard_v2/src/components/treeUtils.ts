export interface ManualNode {
  id: string;
  title: string;
  content?: string;
  updatedAt?: string;
  lastChildUpdate?: {
    id: string;
    title: string;
    timestamp: string;
  };
  children?: ManualNode[];
}

// --- Tree Manipulation Helpers ---

export const findNodeById = (nodes: ManualNode[], id: string): ManualNode | null => {
  for (const node of nodes) {
    if (node.id === id) return node;
    if (node.children) {
      const found = findNodeById(node.children, id);
      if (found) return found;
    }
  }
  return null;
};

// Returns an array of ancestor IDs leading up to (but not including) the target node
export const findNodePath = (nodes: ManualNode[], targetId: string, currentPath: string[] = []): string[] | null => {
  for (const node of nodes) {
    if (node.id === targetId) return currentPath;
    if (node.children) {
      const path = findNodePath(node.children, targetId, [...currentPath, node.id]);
      if (path) return path;
    }
  }
  return null;
};

// Recursively filters nodes matching query in title or content, preserving parent structures
export const filterTree = (nodes: ManualNode[], query: string): ManualNode[] => {
  if (!query.trim()) return nodes;
  const q = query.toLowerCase();

  return nodes.reduce((acc: ManualNode[], node) => {
    const titleMatches = node.title.toLowerCase().includes(q);
    const contentMatches = node.content?.toLowerCase().includes(q) || false;
    const matchingChildren = node.children ? filterTree(node.children, query) : [];

    if (titleMatches || contentMatches || matchingChildren.length > 0) {
      acc.push({
        ...node,
        children: matchingChildren
      });
    }
    return acc;
  }, []);
};

export const updateTree = (nodes: ManualNode[], id: string, updates: Partial<ManualNode>): ManualNode[] => {
  return nodes.map(node => {
    if (node.id === id) return { ...node, ...updates };
    if (node.children) return { ...node, children: updateTree(node.children, id, updates) };
    return node;
  });
};

export const addNodeToTree = (nodes: ManualNode[], parentId: string | null, newNode: ManualNode): ManualNode[] => {
  if (!parentId) return [...nodes, newNode];
  return nodes.map(node => {
    if (node.id === parentId) return { ...node, children: [...(node.children || []), newNode] };
    if (node.children) return { ...node, children: addNodeToTree(node.children, parentId, newNode) };
    return node;
  });
};

// --- Drag & Drop Pure Functions ---

export const isDescendant = (nodes: ManualNode[], parentId: string, targetId: string): boolean => {
  const parentNode = findNodeById(nodes, parentId);
  if (!parentNode || !parentNode.children) return false;
  return !!findNodeById(parentNode.children, targetId);
};

// Deep clones the tree while extracting the target node
export const removeNode = (nodes: ManualNode[], idToRemove: string): { newTree: ManualNode[], removedNode: ManualNode | null } => {
  let removedNode: ManualNode | null = null;
  const filterNodes = (list: ManualNode[]): ManualNode[] => {
    return list.filter(node => {
      if (node.id === idToRemove) {
        removedNode = { ...node }; // Copy to detach
        return false;
      }
      if (node.children) {
        node.children = filterNodes(node.children);
      }
      return true;
    }).map(node => ({ ...node })); // Deep clone step
  };

  const newTree = filterNodes(JSON.parse(JSON.stringify(nodes))); // Ensure total decoupling
  return { newTree, removedNode };
};

export const insertNode = (nodes: ManualNode[], targetId: string, newNode: ManualNode, position: 'before' | 'after' | 'inside'): ManualNode[] => {
  return nodes.reduce((acc: ManualNode[], node) => {
    if (node.id === targetId) {
      if (position === 'before') {
        acc.push(newNode, node);
      } else if (position === 'after') {
        acc.push(node, newNode);
      } else if (position === 'inside') {
        acc.push({ ...node, children: [...(node.children || []), newNode] });
      }
    } else {
      if (node.children) {
        acc.push({ ...node, children: insertNode(node.children, targetId, newNode, position) });
      } else {
        acc.push(node);
      }
    }
    return acc;
  }, []);
};