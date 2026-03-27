"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import Link from "next/link";
import AudioList from "@/components/AudioList";
import AudioPlayer from "@/components/AudioPlayer";

interface Audio {
  id: string;
  filename: string;
  filepath: string;
  date: string;
  startTime: string;
  endTime: string;
  personTag: string;
  lastPosition: number;
  subtitleId?: string;
  subtitleFile?: string;
  kind?: string;
  title?: string;
}

interface AudioDateItem {
  value: string;
  label: string;
  count: number;
}

export default function Home() {
  const [audios, setAudios] = useState<Audio[]>([]);
  const [selectedAudio, setSelectedAudio] = useState<Audio | null>(null);
  const [playHistory, setPlayHistory] = useState<Audio[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(true);
  const [showSearch, setShowSearch] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [playMode, setPlayMode] = useState<"sequence" | "shuffle">("sequence");
  const [availableDates, setAvailableDates] = useState<AudioDateItem[]>([]);
  const [selectedDate, setSelectedDate] = useState<string>("");
  const [dateMode, setDateMode] = useState(false);
  const [dateLoading, setDateLoading] = useState(false);

  const normalizedQuery = searchQuery.trim().toLowerCase();
  const filteredAudios = useMemo(
    () =>
      normalizedQuery
        ? audios.filter(
            (a) =>
              a.personTag.toLowerCase().includes(normalizedQuery) ||
              a.date.includes(searchQuery) ||
              (a.title || "").toLowerCase().includes(normalizedQuery) ||
              (a.kind || "").toLowerCase().includes(normalizedQuery)
          )
        : audios,
    [audios, normalizedQuery, searchQuery]
  );

  const fetchLegacyAudios = useCallback(async (cursor?: string | null, replace = false) => {
    const params = new URLSearchParams({ limit: "10" });
    if (cursor) params.set("cursor", cursor);
    const res = await fetch(`/api/audios?${params.toString()}`, { cache: "no-store" });
    const data = await res.json();
    const items = Array.isArray(data.items) ? data.items : [];
    const newCursor = data.nextCursor ?? null;
    setAudios((prev) => (replace ? items : [...prev, ...items]));
    setNextCursor(newCursor);
    setHasMore(Boolean(newCursor));
  }, []);

  const fetchAudiosByDate = useCallback(async (date: string) => {
    if (!date) return;
    setDateLoading(true);
    try {
      const res = await fetch(`/api/audios?date=${encodeURIComponent(date)}`, { cache: "no-store" });
      const data = await res.json();
      const items = Array.isArray(data.items) ? data.items : [];
      setAudios(items);
      setNextCursor(null);
      setHasMore(false);
    } finally {
      setDateLoading(false);
    }
  }, []);

  useEffect(() => {
    const initialize = async () => {
      setLoading(true);
      try {
        const datesRes = await fetch("/api/audio-dates", { cache: "no-store" });
        const datesData = datesRes.ok ? await datesRes.json() : { items: [] };
        const dates = Array.isArray(datesData.items) ? datesData.items : [];
        if (dates.length > 0) {
          setDateMode(true);
          setAvailableDates(dates);
          setSelectedDate(dates[0].value);
          return;
        }

        setDateMode(false);
        fetch("/api/sync", { method: "POST" }).catch(() => {});
        await fetchLegacyAudios(null, true);
      } finally {
        setLoading(false);
      }
    };
    initialize();
  }, [fetchLegacyAudios]);

  useEffect(() => {
    if (!dateMode || !selectedDate) return;
    setSelectedAudio(null);
    setPlayHistory([]);
    setSearchQuery("");
    void fetchAudiosByDate(selectedDate);
  }, [dateMode, selectedDate, fetchAudiosByDate]);

  const handleLoadMore = useCallback(async () => {
    if (dateMode || !hasMore || loadingMore) return;
    setLoadingMore(true);
    await fetchLegacyAudios(nextCursor, false);
    setLoadingMore(false);
  }, [dateMode, fetchLegacyAudios, hasMore, loadingMore, nextCursor]);

  const handlePositionChange = async (id: string, position: number) => {
    await fetch(`/api/audios/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lastPosition: position }),
    });
    setAudios((prev) => prev.map((audio) => (audio.id === id ? { ...audio, lastPosition: position } : audio)));
    setSelectedAudio((prev) => (prev && prev.id === id ? { ...prev, lastPosition: position } : prev));
  };

  const handleSelectAudio = (audio: Audio) => {
    if (selectedAudio && selectedAudio.id !== audio.id) {
      setPlayHistory((prev) => [...prev, selectedAudio]);
    }
    setSelectedAudio(audio);
  };

  const handlePrevious = () => {
    if (playHistory.length > 0) {
      const prev = playHistory[playHistory.length - 1];
      setPlayHistory((h) => h.slice(0, -1));
      setSelectedAudio(prev);
    }
  };

  const handleNext = () => {
    if (!selectedAudio) return;
    const listForPlayback = filteredAudios;
    const currentIndex = listForPlayback.findIndex((a) => a.id === selectedAudio.id);
    if (currentIndex === -1) return;
    if (playMode === "shuffle") {
      if (listForPlayback.length < 2) return;
      let nextIndex = currentIndex;
      while (nextIndex === currentIndex) {
        nextIndex = Math.floor(Math.random() * listForPlayback.length);
      }
      handleSelectAudio(listForPlayback[nextIndex]);
      return;
    }
    if (currentIndex < listForPlayback.length - 1) {
      handleSelectAudio(listForPlayback[currentIndex + 1]);
    }
  };

  const selectedDateIndex = availableDates.findIndex((item) => item.value === selectedDate);
  const currentDateMeta = availableDates.find((item) => item.value === selectedDate) ?? null;

  return (
    <div className="min-h-screen bg-gray-900 text-white">
      <div className="max-w-4xl mx-auto p-6">
        <header className="mb-8">
          <div className="flex items-center justify-between gap-4">
            <h1 className="text-2xl font-bold">音频播放器</h1>
            <Link
              href="/admin/feedback"
              className="rounded-lg bg-gray-800 px-4 py-2 text-sm text-gray-200 hover:bg-gray-700 transition"
            >
              反馈后台
            </Link>
          </div>
        </header>

        <div className="grid md:grid-cols-2 gap-6">
          <div>
            <h2 className="text-lg font-semibold mb-4">播放器</h2>
            {selectedAudio ? (
              <AudioPlayer
                key={selectedAudio.id}
                audio={selectedAudio}
                onPositionChange={handlePositionChange}
                onPrevious={handlePrevious}
                onNext={handleNext}
                hasPrevious={playHistory.length > 0}
                hasNext={
                  playMode === "shuffle"
                    ? filteredAudios.length > 1
                    : filteredAudios.findIndex((a) => a.id === selectedAudio.id) < filteredAudios.length - 1
                }
                playMode={playMode}
                onPlayModeChange={setPlayMode}
              />
            ) : (
              <div className="text-gray-400 bg-gray-800 rounded-lg p-8 text-center">
                请从列表中选择一个音频
              </div>
            )}
          </div>

          <div>
            <div className="flex items-center gap-2 mb-4">
              <h2 className="text-lg font-semibold">音频列表</h2>
              <button
                onClick={() => setShowSearch(!showSearch)}
                className="p-1.5 rounded-lg hover:bg-gray-800 transition"
              >
                <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
              </button>
            </div>

            {dateMode && (
              <div className="mb-4 rounded-lg bg-gray-800 p-3 space-y-3">
                <div className="text-sm font-medium text-gray-200">按日期选择</div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      if (selectedDateIndex >= 0 && selectedDateIndex < availableDates.length - 1) {
                        setSelectedDate(availableDates[selectedDateIndex + 1].value);
                      }
                    }}
                    disabled={selectedDateIndex < 0 || selectedDateIndex >= availableDates.length - 1}
                    className="rounded-lg bg-gray-700 px-3 py-2 text-sm text-gray-200 disabled:opacity-40"
                  >
                    上一天
                  </button>
                  <select
                    value={selectedDate}
                    onChange={(e) => setSelectedDate(e.target.value)}
                    className="flex-1 rounded-lg bg-gray-700 px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    {availableDates.map((item) => (
                      <option key={item.value} value={item.value}>
                        {item.label}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    onClick={() => {
                      if (selectedDateIndex > 0) {
                        setSelectedDate(availableDates[selectedDateIndex - 1].value);
                      }
                    }}
                    disabled={selectedDateIndex <= 0}
                    className="rounded-lg bg-gray-700 px-3 py-2 text-sm text-gray-200 disabled:opacity-40"
                  >
                    下一天
                  </button>
                </div>
                <div className="text-xs text-gray-400">
                  {currentDateMeta ? `${currentDateMeta.label} · ${currentDateMeta.count} 个 parts` : ""}
                </div>
              </div>
            )}

            {loading || dateLoading ? (
              <div className="text-gray-400">加载中...</div>
            ) : (
              <AudioList
                audios={filteredAudios}
                selectedId={selectedAudio?.id ?? null}
                onSelect={handleSelectAudio}
                showSearch={showSearch}
                searchQuery={searchQuery}
                onSearchChange={setSearchQuery}
                onLoadMore={handleLoadMore}
                hasMore={!searchQuery && !dateMode ? hasMore : false}
                loadingMore={loadingMore}
                showEndMessage={!dateMode}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
