"use client";

import { EditorContent, useEditor, type Editor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { Bold, Heading2, Italic, List, ListOrdered, Quote } from "lucide-react";
import { Markdown as MarkdownExtension } from "tiptap-markdown";

import { Icon } from "@/components/console";
import { cn } from "@/lib/cn";

/**
 * WYSIWYG rich-text editor (0.8.1) that reads and writes **Markdown** (Decision: TipTap →
 * Markdown). `value` seeds the editor once; `onChange` emits Markdown on every edit (the parent
 * holds the Markdown string in form state). Deliberately *not* re-synced from `value` on every
 * render — that would fight the cursor; the seed-once + emit pattern is the standard controlled-ish
 * shape for a contenteditable.
 *
 * Heavy (TipTap + ProseMirror), so it is lazy-loaded (`next/dynamic`, `ssr:false`) by the edit
 * form — public viewers render Markdown with the light `Markdown` component instead.
 * `immediatelyRender: false` avoids a Next.js SSR hydration mismatch (TipTap ≥2.5 guidance).
 */

type RichTextEditorProps = {
  value: string;
  onChange: (markdown: string) => void;
  placeholder?: string;
  /** Accessible name for the ProseMirror contenteditable (it has no associated <label>). */
  ariaLabel?: string;
};

// tiptap-markdown stores its serializer on editor.storage.markdown; type it narrowly.
type MarkdownStorage = { markdown: { getMarkdown: () => string } };

function ToolbarButton({
  editor,
  active,
  onClick,
  label,
  children,
}: {
  editor: Editor;
  active: boolean;
  onClick: () => void;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      aria-pressed={active}
      // Toggling a mark blurs nothing — keep the selection by preventing the mousedown default.
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
      disabled={!editor.isEditable}
      className={cn(
        "grid h-7 w-7 place-items-center rounded-inset border transition-colors",
        active
          ? "border-[color:var(--hairline-strong)] bg-panel-2 text-signal"
          : "border-transparent text-text-mute hover:text-text",
      )}
    >
      {children}
    </button>
  );
}

export function RichTextEditor({ value, onChange, placeholder, ariaLabel }: RichTextEditorProps) {
  const editor = useEditor({
    immediatelyRender: false,
    extensions: [
      StarterKit,
      // Parses the `content` string as Markdown and exposes getMarkdown() for serialization.
      MarkdownExtension.configure({ html: false, linkify: true }),
    ],
    content: value,
    onUpdate: ({ editor }) => {
      onChange((editor.storage as unknown as MarkdownStorage).markdown.getMarkdown());
    },
    editorProps: {
      attributes: {
        // Console field skin + element styles for the ProseMirror content (no typography plugin).
        class: cn(
          "field-input min-h-32 w-full px-2.5 py-2 font-sans text-[13px] leading-[1.6]",
          "focus:outline-none",
          "[&_h1]:text-base [&_h1]:font-medium [&_h1]:text-text",
          "[&_h2]:text-[14px] [&_h2]:font-medium [&_h2]:text-text",
          "[&_p]:text-text-soft",
          "[&_ul]:ml-4 [&_ul]:list-disc [&_ol]:ml-4 [&_ol]:list-decimal [&_li]:my-0.5",
          "[&_blockquote]:border-l-2 [&_blockquote]:border-[color:var(--hairline-strong)] [&_blockquote]:pl-3 [&_blockquote]:text-text-mute",
          "[&_code]:rounded-inset [&_code]:bg-panel-2 [&_code]:px-1 [&_code]:font-mono [&_code]:text-[12px]",
        ),
        ...(placeholder ? { "data-placeholder": placeholder } : {}),
        ...(ariaLabel ? { "aria-label": ariaLabel } : {}),
      },
    },
  });

  if (!editor) {
    return <div className="field-input min-h-32 w-full px-2.5 py-2 text-[13px] text-text-faint" />;
  }

  return (
    <div className="grid gap-1.5">
      <div className="flex items-center gap-0.5">
        <ToolbarButton
          editor={editor}
          active={editor.isActive("bold")}
          onClick={() => editor.chain().focus().toggleBold().run()}
          label="Bold"
        >
          <Icon icon={Bold} size={14} />
        </ToolbarButton>
        <ToolbarButton
          editor={editor}
          active={editor.isActive("italic")}
          onClick={() => editor.chain().focus().toggleItalic().run()}
          label="Italic"
        >
          <Icon icon={Italic} size={14} />
        </ToolbarButton>
        <ToolbarButton
          editor={editor}
          active={editor.isActive("heading", { level: 2 })}
          onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
          label="Heading"
        >
          <Icon icon={Heading2} size={14} />
        </ToolbarButton>
        <ToolbarButton
          editor={editor}
          active={editor.isActive("bulletList")}
          onClick={() => editor.chain().focus().toggleBulletList().run()}
          label="Bullet list"
        >
          <Icon icon={List} size={14} />
        </ToolbarButton>
        <ToolbarButton
          editor={editor}
          active={editor.isActive("orderedList")}
          onClick={() => editor.chain().focus().toggleOrderedList().run()}
          label="Numbered list"
        >
          <Icon icon={ListOrdered} size={14} />
        </ToolbarButton>
        <ToolbarButton
          editor={editor}
          active={editor.isActive("blockquote")}
          onClick={() => editor.chain().focus().toggleBlockquote().run()}
          label="Quote"
        >
          <Icon icon={Quote} size={14} />
        </ToolbarButton>
      </div>
      <EditorContent editor={editor} />
    </div>
  );
}
