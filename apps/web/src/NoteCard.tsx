import type { NodeProps } from "@xyflow/react";

type NoteData = { content: string; color: string };

export function NoteCard({ data, selected }: NodeProps) {
  const note = data as NoteData;
  return <div className={`note-card ${selected ? "selected" : ""}`} style={{ borderColor: note.color, backgroundColor: `${note.color}ee` }}>
    {renderMarkdown(note.content)}
  </div>;
}

function renderMarkdown(source: string) {
  return source.split("\n").slice(0, 40).map((line, index) => {
    if (line.startsWith("### ")) return <h4 key={index}>{line.slice(4)}</h4>;
    if (line.startsWith("## ")) return <h3 key={index}>{line.slice(3)}</h3>;
    if (line.startsWith("# ")) return <h2 key={index}>{line.slice(2)}</h2>;
    if (line.startsWith("- ")) return <div className="note-list" key={index}>• {line.slice(2)}</div>;
    if (line.startsWith("> ")) return <blockquote key={index}>{line.slice(2)}</blockquote>;
    if (line.startsWith("```")) return <code key={index}>{line.slice(3)}</code>;
    return <p key={index}>{line || "\u00a0"}</p>;
  });
}
