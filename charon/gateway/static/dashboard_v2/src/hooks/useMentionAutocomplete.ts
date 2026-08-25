/**
 * @file src/hooks/useMentionAutocomplete.ts
 * @description Hook managing dual-trigger (# tickets, @ docs) inline mention autocompletion with 2-stage @ parsing.
 */
import { useState, useRef, ChangeEvent, KeyboardEvent } from 'react';
import { JournalEntry } from '../features/journal/types';
import { DocMentionItem } from '../features/docs/types';

export type MentionTrigger = '#' | '@' | null;
export type MentionCandidate = JournalEntry | DocMentionItem | { _isCategory: true; name: string };

export function useMentionAutocomplete(
  content: string,
  onChangeContent: (val: string) => void,
  onLinkTicket?: (ticketId: string) => void,
  onLinkDoc?: (docId: string) => void
) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [mentionQuery, setMentionQuery] = useState<string | null>(null);
  const [mentionCategory, setMentionCategory] = useState<string | null>(null);
  const [mentionTrigger, setMentionTrigger] = useState<MentionTrigger>(null);
  const [mentionStartIndex, setMentionStartIndex] = useState<number>(-1);
  const [mentionSelectedIndex, setMentionSelectedIndex] = useState<number>(0);

  const handleContentChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    const cursorPos = e.target.selectionStart;
    onChangeContent(value);

    const textBeforeCursor = value.slice(0, cursorPos);
    const hashIndex = textBeforeCursor.lastIndexOf('#');
    const atIndex = textBeforeCursor.lastIndexOf('@');

    // Pick whichever trigger symbol is closest to the current cursor position
    const triggerIndex = Math.max(hashIndex, atIndex);

    if (
      triggerIndex !== -1 &&
      (triggerIndex === 0 || /\s/.test(textBeforeCursor[triggerIndex - 1]))
    ) {
      const triggerChar = textBeforeCursor[triggerIndex] as '#' | '@';
      const query = textBeforeCursor.slice(triggerIndex + 1);

      if (!/\s/.test(query)) {
        if (triggerChar === '@') {
          // Check for 2-stage format: @Manual:searchQuery
          const catMatch = query.match(/^(adr|spec|manual):(.*)$/i);
          if (catMatch) {
            setMentionCategory(catMatch[1].toLowerCase());
            setMentionQuery(catMatch[2]);
          } else {
            setMentionCategory(null);
            setMentionQuery(query);
          }
        } else {
          setMentionCategory(null);
          setMentionQuery(query);
        }

        setMentionTrigger(triggerChar);
        setMentionStartIndex(triggerIndex);
        setMentionSelectedIndex(0);
        return;
      }
    }

    setMentionQuery(null);
    setMentionCategory(null);
    setMentionTrigger(null);
    setMentionStartIndex(-1);
  };

  const insertMention = (candidate: MentionCandidate) => {
    if (!textareaRef.current || mentionStartIndex === -1 || !mentionTrigger) return;
    const cursorPos = textareaRef.current.selectionStart;

    // Stage 1 Completion: Insert Category, keep menu open for Stage 2
    if ('_isCategory' in candidate) {
      const catName = candidate.name;
      const updatedContent =
        content.slice(0, mentionStartIndex) +
        `@${catName}:` +
        content.slice(cursorPos);

      onChangeContent(updatedContent);
      setMentionCategory(catName.toLowerCase());
      setMentionQuery('');

      setTimeout(() => {
        if (textareaRef.current) {
          textareaRef.current.focus();
          // Move cursor directly after the colon
          const nextPos = mentionStartIndex + catName.length + 2;
          textareaRef.current.setSelectionRange(nextPos, nextPos);
        }
      }, 0);
      return; // Do not close the mention state
    }

    // Stage 2 Completion: Insert full Link
    let mentionText = '';

    if (mentionTrigger === '#') {
      const entry = candidate as JournalEntry;
      // Absolute path to the journal entry
      mentionText = `[${entry.id}](/journal/${entry.id})`;
      if (onLinkTicket) {
        onLinkTicket(entry.id);
      }
    } else if (mentionTrigger === '@') {
      const doc = candidate as DocMentionItem;
      const title = doc.title || doc.id;
      // Absolute path to the manual node
      mentionText = `[@${title}](/docs/manual/${doc.id})`;
      if (onLinkDoc) {
        onLinkDoc(doc.id);
      }
    }

    const updatedContent =
      content.slice(0, mentionStartIndex) +
      mentionText +
      ' ' +
      content.slice(cursorPos);

    onChangeContent(updatedContent);

    // Reset Mention State
    setMentionQuery(null);
    setMentionCategory(null);
    setMentionTrigger(null);
    setMentionStartIndex(-1);

    setTimeout(() => {
      if (textareaRef.current) {
        textareaRef.current.focus();
        const nextPos = mentionStartIndex + mentionText.length + 1;
        textareaRef.current.setSelectionRange(nextPos, nextPos);
      }
    }, 0);
  };

  const handleKeyDown = (
    e: KeyboardEvent<HTMLTextAreaElement>,
    candidates: MentionCandidate[]
  ) => {
    if (mentionQuery === null || candidates.length === 0) return;

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setMentionSelectedIndex((prev) => (prev + 1) % candidates.length);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setMentionSelectedIndex((prev) => (prev - 1 + candidates.length) % candidates.length);
    } else if (e.key === 'Enter' || e.key === 'Tab') {
      e.preventDefault();
      insertMention(candidates[mentionSelectedIndex]);
    } else if (e.key === 'Escape') {
      setMentionQuery(null);
      setMentionCategory(null);
      setMentionTrigger(null);
      setMentionStartIndex(-1);
    }
  };

  return {
    textareaRef,
    mentionQuery,
    mentionCategory,
    setMentionQuery,
    mentionTrigger,
    setMentionTrigger,
    mentionSelectedIndex,
    setMentionSelectedIndex,
    handleContentChange,
    handleKeyDown,
    insertMention,
  };
}