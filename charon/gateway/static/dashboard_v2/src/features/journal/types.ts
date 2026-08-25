/**
 * @file src/features/journal/types.ts
 * @description Type definitions for DevLog journal entries and formatting helpers.
 */
import { DocMentionItem } from '../docs/types';

// ADDED 'runbook' to the EntryType union
export type EntryType = 'observation' | 'defect' | 'feature' | 'architecture' | 'session' | 'runbook';
export type TicketStatus = 'todo' | 'in_progress' | 'blocked' | 'done';
export type TicketPriority = 'low' | 'medium' | 'high' | 'critical';

export type { DocMentionItem };

export interface JournalEntry {
  id: string;
  title: string;
  content: string;
  timestamp: string;
  type: EntryType;
  status: TicketStatus | null;
  priority: TicketPriority;
  linkedArtifacts: string[];
  linkedTickets: string[]; // Array of referenced ticket IDs (e.g., ["LOG-001", "LOG-004"])
  linkedDocs?: string[];   // Array of referenced doc IDs (e.g., ["ADR-001", "getting-started"])
  updatedAt?: string;
}

export function formatTimestamp(timestamp: string): string {
  const date = new Date(timestamp);
  if (isNaN(date.getTime())) return timestamp;
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}