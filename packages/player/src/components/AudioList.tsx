"use client";

import { useRef, useEffect } from "react";

interface Audio {
  id: string;
  filename: string;
  filepath: string;
  date: string;
  startTime: string;
  endTime: string;
  personTag: string;
  lastPosition: number;
  kind?: string;
  title?: string;
}

interface AudioListProps {
  audios: Audio[];
  selectedId: string | null;
  onSelect: (audio: Audio) => void;
  showSearch: boolean;
  searchQuery: string;
  onSearchChange: (query: string) => void;
  onLoadMore: () => void;
  hasMore: boolean;
  loadingMore: boolean;
  showEndMessage?: boolean;
}

function kindLabel(kind?: string) {
  switch (kind) {
    case "opening":
      return "开场";
    case "comment":
      return "评论";
    case "call":
      return "连麦";
    case "ending":
      return "结束";
    default:
      return kind || "";
  }
}

export default function AudioList({
  audios,
  selectedId,
  onSelect,
  showSearch,
  searchQuery,
  onSearchChange,
  onLoadMore,
  hasMore,
  loadingMore,
  showEndMessage = true,
}: AudioListProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (showSearch && inputRef.current) {
      inputRef.current.focus();
    }
  }, [showSearch]);

  useEffect(() => {
    const root = listRef.current;
    const target = sentinelRef.current;
    if (!root || !target || !hasMore || loadingMore) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          onLoadMore();
        }
      },
      { root, rootMargin: "200px 0px 200px 0px", threshold: 0 }
    );

    observer.observe(target);
    return () => observer.disconnect();
  }, [hasMore, loadingMore, onLoadMore]);

  useEffect(() => {
    const listEl = listRef.current;
    if (!listEl || !selectedId) return;
    const selectedEl = listEl.querySelector<HTMLButtonElement>(`[data-audio-id="${selectedId}"]`);
    if (selectedEl) {
      selectedEl.scrollIntoView({ block: "start", behavior: "smooth" });
    }
  }, [selectedId]);

  return (
    <div>
      {showSearch && (
        <input
          ref={inputRef}
          type="text"
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="搜索..."
          className="w-full px-3 py-2 mb-3 bg-gray-800 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      )}

      <div ref={listRef} className="max-h-[70vh] overflow-y-auto space-y-2 pr-2">
        {audios.length === 0 ? (
          <div className="text-gray-400 text-center py-4">{searchQuery.trim() ? "无匹配结果" : "没有音频文件。"}</div>
        ) : (
          audios.map((audio) => (
            <button
              key={audio.id}
              onClick={() => onSelect(audio)}
              data-audio-id={audio.id}
              className={`w-full text-left p-3 rounded-lg transition ${
                selectedId === audio.id
                  ? "bg-blue-600 text-white"
                  : "bg-gray-800 text-gray-200 hover:bg-gray-700"
              }`}
            >
              <div className="flex items-center justify-between gap-3">
                <div className="font-medium">{audio.personTag}</div>
                {kindLabel(audio.kind) && (
                  <span className="rounded-full bg-black/20 px-2 py-0.5 text-xs opacity-80">{kindLabel(audio.kind)}</span>
                )}
              </div>
              <div className="text-sm opacity-75 mt-1">{audio.startTime} - {audio.endTime}</div>
              {audio.lastPosition > 0 && (
                <div className="text-xs opacity-50 mt-1">
                  上次播放: {Math.floor(audio.lastPosition / 60)}:{Math.floor(audio.lastPosition % 60).toString().padStart(2, "0")}
                </div>
              )}
            </button>
          ))
        )}
        <div ref={sentinelRef} />
        {loadingMore && <div className="text-gray-500 text-center py-3">加载更多...</div>}
        {showEndMessage && !hasMore && audios.length > 0 && <div className="text-gray-600 text-center py-3">没有更多了</div>}
      </div>
    </div>
  );
}
