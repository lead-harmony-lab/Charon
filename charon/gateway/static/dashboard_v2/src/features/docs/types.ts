/**
 * @file src/features/docs/types.ts
 * @description Type definitions for ADRs, System Specs, Manual pages, and unified mention items.
 */

export type DocCategory = 'adr' | 'spec' | 'manual';

/**
 * Normalized interface used for autocomplete lists and link resolution.
 */
export interface DocMentionItem {
  id: string;
  title: string;
  category: DocCategory;
  path?: string;
  description?: string;
}

/**
 * Manual page tree node structure.
 */
export interface ManualNode {
  id: string;
  title: string;
  content?: string;
  children?: ManualNode[];
}

/**
 * Architecture Decision Record (ADR) item representation.
 */
export interface ADRDoc {
  id: string;
  title: string;
  status: 'draft' | 'accepted' | 'rejected' | 'superseded';
  content?: string;
  date?: string;
}

/**
 * System Spec item representation.
 */
export interface SpecDoc {
  id: string;
  title: string;
  status?: string;
  content?: string;
}