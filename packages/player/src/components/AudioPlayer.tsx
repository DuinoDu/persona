"use client";

import { useState, useRef, useEffect, useCallback, useMemo } from "react";
import Link from "next/link";

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

interface Segment {
  start: number;
  end: number;
  text: string;
  role: string;
  sourceKind?: "sentences" | "segments";
  sourcePath?: string;
  sourceIndex?: number;
  absStart?: number;
  absEnd?: number;
  repair?: {
    isRepaired: boolean;
    processedAt?: string | null;
    feedbackId?: string;
    operation?: string | null;
  } | null;
}

interface FeedbackTarget extends Segment {
  index: number;
}

interface AudioPlayerProps {
  audio: Audio;
  onPositionChange: (id: string, position: number) => void;
  onPrevious: () => void;
  onNext: () => void;
  hasPrevious: boolean;
  hasNext: boolean;
  playMode: "sequence" | "shuffle";
  onPlayModeChange: (mode: "sequence" | "shuffle") => void;
}

const SPEEDS = [1, 1.5, 2];
const START_BUFFER_AHEAD_SECONDS = 8;
const RESUME_BUFFER_AHEAD_SECONDS = 6;
const MIN_CONTINUE_BUFFER_AHEAD_SECONDS = 2.5;

export default function AudioPlayer({
  audio,
  onPositionChange,
  onPrevious,
  onNext,
  hasPrevious,
  hasNext,
  playMode,
  onPlayModeChange,
}: AudioPlayerProps) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const subtitleRef = useRef<HTMLDivElement>(null);
  const feedbackTextareaRef = useRef<HTMLTextAreaElement>(null);
  const longPressTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastBufferSampleRef = useRef<{ timeMs: number; bufferedEnd: number } | null>(null);
  const initialStartPositionRef = useRef(audio.lastPosition);
  const initialSeekAppliedRef = useRef(false);
  const autoplayStartedRef = useRef(false);
  const suppressSubtitleClickRef = useRef(false);
  const shouldAutoplayRef = useRef(true);
  const waitingForBufferRef = useRef(false);
  const pendingPlayAfterBufferRef = useRef(false);
  const bufferPauseInFlightRef = useRef(false);

  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(audio.lastPosition);
  const [duration, setDuration] = useState(0);
  const [volume, setVolume] = useState(1);
  const [speed, setSpeed] = useState(1);
  const [isDragging, setIsDragging] = useState(false);
  const [segments, setSegments] = useState<Segment[]>([]);
  const [feedbackTarget, setFeedbackTarget] = useState<FeedbackTarget | null>(null);
  const [feedbackMessage, setFeedbackMessage] = useState("");
  const [feedbackSending, setFeedbackSending] = useState(false);
  const [feedbackError, setFeedbackError] = useState("");
  const [pendingRevertFeedbackId, setPendingRevertFeedbackId] = useState<string | null>(null);
  const [revertingFeedbackId, setRevertingFeedbackId] = useState<string | null>(null);
  const [revertError, setRevertError] = useState("");
  const [showVolume, setShowVolume] = useState(false);
  const [showSubtitleHint, setShowSubtitleHint] = useState(true);
  const [isAudioPreparing, setIsAudioPreparing] = useState(false);
  const [isAudioReady, setIsAudioReady] = useState(false);
  const [subtitlePhase, setSubtitlePhase] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [audioPhase, setAudioPhase] = useState<"idle" | "connecting" | "buffering" | "ready" | "error">("idle");
  const [bufferedEnd, setBufferedEnd] = useState(0);
  const [bufferedAhead, setBufferedAhead] = useState(0);
  const [bufferRateSecondsPerSecond, setBufferRateSecondsPerSecond] = useState<number | null>(null);
  const [audioError, setAudioError] = useState("");

  const currentSegmentIndex = segments.findIndex(
    (s) => currentTime >= s.start && currentTime < s.end
  );

  const loadSubtitles = useCallback(async (options?: { showLoading?: boolean }) => {
    const showLoading = options?.showLoading ?? false;
    if (showLoading) {
      setSubtitlePhase("loading");
    }
    try {
      const subtitleUrl = audio.subtitleId
        ? `/api/subtitles/by-part/${encodeURIComponent(audio.subtitleId)}`
        : `/api/subtitles/${encodeURIComponent(audio.filename)}`;
      const res = await fetch(subtitleUrl, {
        cache: "no-store",
      });
      if (res.ok) {
        const data = await res.json();
        setSegments(data.segments);
        setSubtitlePhase("ready");
      } else {
        if (showLoading) {
          setSegments([]);
          setSubtitlePhase("error");
        }
      }
    } catch {
      if (showLoading) {
        setSegments([]);
        setSubtitlePhase("error");
      }
    }
  }, [audio.filename, audio.subtitleId]);

  useEffect(() => {
    loadSubtitles({ showLoading: true });
  }, [loadSubtitles]);

  useEffect(() => {
    const interval = window.setInterval(() => {
      loadSubtitles({ showLoading: false });
    }, 15000);
    const handleFocus = () => {
      loadSubtitles({ showLoading: false });
    };
    window.addEventListener("focus", handleFocus);
    document.addEventListener("visibilitychange", handleFocus);
    return () => {
      window.clearInterval(interval);
      window.removeEventListener("focus", handleFocus);
      document.removeEventListener("visibilitychange", handleFocus);
    };
  }, [loadSubtitles]);

  const clearLongPressTimer = useCallback(() => {
    if (longPressTimerRef.current) {
      clearTimeout(longPressTimerRef.current);
      longPressTimerRef.current = null;
    }
  }, []);

  const closeFeedbackModal = useCallback(() => {
    setFeedbackTarget(null);
    setFeedbackMessage("");
    setFeedbackError("");
  }, []);

  useEffect(() => {
    setPendingRevertFeedbackId(null);
    setRevertingFeedbackId(null);
    setRevertError("");
  }, [audio.id]);

  useEffect(() => {
    if (currentSegmentIndex >= 0 && subtitleRef.current) {
      const activeEl = subtitleRef.current.querySelector(`[data-index="${currentSegmentIndex}"]`);
      if (activeEl) {
        activeEl.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }
  }, [currentSegmentIndex]);

  useEffect(() => {
    let cancelled = false;
    shouldAutoplayRef.current = true;
    lastBufferSampleRef.current = null;
    initialStartPositionRef.current = audio.lastPosition;
    initialSeekAppliedRef.current = false;
    autoplayStartedRef.current = false;
    waitingForBufferRef.current = false;
    pendingPlayAfterBufferRef.current = true;
    bufferPauseInFlightRef.current = false;

    const cleanupCurrentAudio = () => {
      const el = audioRef.current;
      if (el) {
        el.pause();
        el.removeAttribute("src");
        el.load();
      }
    };

    cleanupCurrentAudio();
    setIsPlaying(false);
    setDuration(0);
    setCurrentTime(initialStartPositionRef.current);
    setAudioError("");
    setIsAudioReady(false);
    setIsAudioPreparing(true);
    setAudioPhase("connecting");
    setBufferedEnd(0);
    setBufferedAhead(0);
    setBufferRateSecondsPerSecond(null);

    const el = audioRef.current;
      if (el) {
        el.src = audio.filepath;
        el.load();
      }

    return () => {
      cancelled = true;
      shouldAutoplayRef.current = false;
      cleanupCurrentAudio();
    };
  }, [audio.id, audio.filepath]);

  const formatBytes = useCallback((bytes: number | null) => {
    if (!bytes || bytes <= 0) return "0 B";
    if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${bytes} B`;
  }, []);

  const bufferedPercent = useMemo(() => {
    if (!duration || duration <= 0) return 0;
    return Math.min(100, Math.round((bufferedEnd / duration) * 100));
  }, [duration, bufferedEnd]);

  const bufferRateText = useMemo(() => {
    if (!bufferRateSecondsPerSecond || bufferRateSecondsPerSecond <= 0) return "";
    return `${bufferRateSecondsPerSecond.toFixed(1)} 秒/秒`;
  }, [bufferRateSecondsPerSecond]);

  const getThresholdSeconds = useCallback(
    (baseSeconds: number, el: HTMLAudioElement) => {
      const scaled = baseSeconds * speed;
      if (!Number.isFinite(el.duration) || el.duration <= 0) {
        return scaled;
      }
      const remaining = Math.max(el.duration - el.currentTime, 0);
      return Math.max(0.75, Math.min(scaled, Math.max(remaining - 0.2, 0.75)));
    },
    [speed]
  );

  const audioStatusText = useMemo(() => {
    if (audioPhase === "connecting") {
      return "MP3 准备中：等待服务端返回音频流";
    }
    if (audioPhase === "buffering") {
      return `MP3 流式缓冲中：已缓冲 ${formatTime(bufferedAhead)}，总进度 ${bufferedPercent}%（${formatTime(bufferedEnd)} / ${formatTime(duration)}${bufferRateText ? ` · ${bufferRateText}` : ""}）`;
    }
    if (audioPhase === "ready") return "MP3 已可播放";
    if (audioPhase === "error") return audioError || "音频加载失败";
    return "";
  }, [audioPhase, bufferedAhead, bufferedPercent, bufferedEnd, duration, bufferRateText, audioError]);

  const playedPercent = useMemo(() => {
    if (!duration || duration <= 0) return 0;
    return Math.min(100, Math.round((currentTime / duration) * 100));
  }, [currentTime, duration]);

  useEffect(() => {
    const timer = setTimeout(() => setShowSubtitleHint(false), 3000);
    return () => clearTimeout(timer);
  }, []);

  const savePosition = useCallback(() => {
    if (audioRef.current) {
      onPositionChange(audio.id, audioRef.current.currentTime);
    }
  }, [audio.id, onPositionChange]);

  useEffect(() => {
    const interval = setInterval(savePosition, 5000);
    return () => clearInterval(interval);
  }, [savePosition]);

  useEffect(() => {
    return () => savePosition();
  }, [savePosition]);

  useEffect(() => clearLongPressTimer, [clearLongPressTimer]);

  useEffect(() => {
    if (!feedbackTarget) return;
    const timer = window.setTimeout(() => {
      feedbackTextareaRef.current?.focus();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [feedbackTarget]);

  function formatTime(t: number) {
    const mins = Math.floor(t / 60);
    const secs = Math.floor(t % 60);
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  }

  const getBufferedAheadSeconds = useCallback((el: HTMLAudioElement) => {
    for (let i = 0; i < el.buffered.length; i += 1) {
      const start = el.buffered.start(i);
      const end = el.buffered.end(i);
      if (el.currentTime >= start && el.currentTime <= end) {
        return Math.max(0, end - el.currentTime);
      }
    }
    return 0;
  }, []);

  const syncBufferedState = useCallback(() => {
    const el = audioRef.current;
    if (!el) return null;
    let nextBufferedEnd = 0;
    for (let i = 0; i < el.buffered.length; i += 1) {
      const start = el.buffered.start(i);
      const end = el.buffered.end(i);
      if (el.currentTime >= start && el.currentTime <= end) {
        nextBufferedEnd = end;
        break;
      }
      nextBufferedEnd = Math.max(nextBufferedEnd, end);
    }
    const nextBufferedAhead = getBufferedAheadSeconds(el);

    setBufferedEnd(nextBufferedEnd);
    setBufferedAhead(nextBufferedAhead);
    const now = performance.now();
    const lastSample = lastBufferSampleRef.current;
    if (lastSample && nextBufferedEnd > lastSample.bufferedEnd) {
      const elapsedSeconds = Math.max((now - lastSample.timeMs) / 1000, 0.001);
      setBufferRateSecondsPerSecond((nextBufferedEnd - lastSample.bufferedEnd) / elapsedSeconds);
    }
    lastBufferSampleRef.current = { timeMs: now, bufferedEnd: nextBufferedEnd };
    return { bufferedEnd: nextBufferedEnd, bufferedAhead: nextBufferedAhead };
  }, [getBufferedAheadSeconds]);

  const startPlaybackWhenSafe = useCallback(async () => {
    const el = audioRef.current;
    if (!el || !shouldAutoplayRef.current) return;
    if (el.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) return;

    const snapshot = syncBufferedState();
    const bufferedAheadSeconds = snapshot?.bufferedAhead ?? getBufferedAheadSeconds(el);
    const threshold = waitingForBufferRef.current
      ? getThresholdSeconds(RESUME_BUFFER_AHEAD_SECONDS, el)
      : getThresholdSeconds(START_BUFFER_AHEAD_SECONDS, el);

    if (bufferedAheadSeconds < threshold) {
      waitingForBufferRef.current = true;
      pendingPlayAfterBufferRef.current = true;
      setIsPlaying(false);
      setIsAudioPreparing(true);
      setAudioPhase("buffering");
      return;
    }

    pendingPlayAfterBufferRef.current = false;
    waitingForBufferRef.current = false;
    bufferPauseInFlightRef.current = false;
    setIsAudioPreparing(false);
    setAudioPhase("ready");
    try {
      await el.play();
      autoplayStartedRef.current = true;
      setIsPlaying(true);
    } catch {
      pendingPlayAfterBufferRef.current = true;
      waitingForBufferRef.current = true;
      setIsPlaying(false);
      setAudioPhase("buffering");
    }
  }, [getBufferedAheadSeconds, getThresholdSeconds, syncBufferedState]);

  const pauseForBuffer = useCallback(() => {
    const el = audioRef.current;
    if (!el) return;
    waitingForBufferRef.current = true;
    pendingPlayAfterBufferRef.current = shouldAutoplayRef.current;
    bufferPauseInFlightRef.current = true;
    setIsPlaying(false);
    setIsAudioPreparing(true);
    setAudioPhase("buffering");
    el.pause();
  }, []);

  const togglePlay = () => {
    const el = audioRef.current;
    if (!el || !isAudioReady) return;
    if (isPlaying) {
      shouldAutoplayRef.current = false;
      pendingPlayAfterBufferRef.current = false;
      waitingForBufferRef.current = false;
      bufferPauseInFlightRef.current = false;
      el.pause();
      setIsPlaying(false);
    } else {
      shouldAutoplayRef.current = true;
      pendingPlayAfterBufferRef.current = true;
      void startPlaybackWhenSafe();
    }
  };

  const handleTimeUpdate = () => {
    const el = audioRef.current;
    if (!el) return;
    if (!isDragging) {
      setCurrentTime(el.currentTime);
    }
    const bufferedAheadSeconds = getBufferedAheadSeconds(el);
    setBufferedAhead(bufferedAheadSeconds);
    if (
      !el.paused &&
      shouldAutoplayRef.current &&
      bufferedAheadSeconds < getThresholdSeconds(MIN_CONTINUE_BUFFER_AHEAD_SECONDS, el)
    ) {
      pauseForBuffer();
    }
  };

  const handleLoadedMetadata = () => {
    if (audioRef.current) {
      setDuration(audioRef.current.duration);
      setAudioError("");
    }
  };

  const handleProgressChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const time = parseFloat(e.target.value);
    setCurrentTime(time);
    if (audioRef.current) {
      lastBufferSampleRef.current = null;
      audioRef.current.currentTime = time;
      if (shouldAutoplayRef.current) {
        waitingForBufferRef.current = true;
        pendingPlayAfterBufferRef.current = true;
        setIsAudioPreparing(true);
        setAudioPhase("buffering");
      } else {
        syncBufferedState();
      }
    }
  };

  const handleVolumeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const vol = parseFloat(e.target.value);
    setVolume(vol);
    if (audioRef.current) {
      audioRef.current.volume = vol;
    }
  };

  const handleSpeedChange = (newSpeed: number) => {
    setSpeed(newSpeed);
    if (audioRef.current) {
      audioRef.current.playbackRate = newSpeed;
      if (shouldAutoplayRef.current) {
        void startPlaybackWhenSafe();
      }
    }
  };

  const handleEnded = () => {
    setIsPlaying(false);
    savePosition();
  };

  const handleSubtitleClick = (startTime: number) => {
    if (suppressSubtitleClickRef.current) {
      suppressSubtitleClickRef.current = false;
      return;
    }
    setPendingRevertFeedbackId(null);
    if (audioRef.current) {
      lastBufferSampleRef.current = null;
      audioRef.current.currentTime = startTime;
      setCurrentTime(startTime);
      if (shouldAutoplayRef.current) {
        waitingForBufferRef.current = true;
        pendingPlayAfterBufferRef.current = true;
        setIsAudioPreparing(true);
        setAudioPhase("buffering");
      } else {
        syncBufferedState();
      }
    }
  };

  const openFeedbackForSegment = (segment: Segment, index: number) => {
    suppressSubtitleClickRef.current = true;
    setFeedbackMessage("");
    setFeedbackError("");
    setFeedbackTarget({
      ...segment,
      index,
    });
  };

  const handleSubtitlePointerDown = (segment: Segment, index: number) => (
    e: React.PointerEvent<HTMLDivElement>
  ) => {
    if (e.pointerType === "mouse" && e.button !== 0) {
      return;
    }
    clearLongPressTimer();
    longPressTimerRef.current = setTimeout(() => {
      openFeedbackForSegment(segment, index);
      clearLongPressTimer();
    }, 500);
  };

  const handleSubtitlePointerEnd = () => {
    clearLongPressTimer();
  };

  const getSubtitleFilename = () => {
    return audio.subtitleFile || audio.filename.replace(/\.mp3$/, ".json");
  };

  const handleSendFeedback = async () => {
    if (!feedbackMessage.trim() || !feedbackTarget) return;
    setFeedbackSending(true);
    setFeedbackError("");
    try {
      const res = await fetch("/api/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          audioId: audio.id,
          audioFilename: audio.filename,
          subtitleId: audio.subtitleId,
          audioDate: audio.date,
          audioPersonTag: audio.personTag,
          audioStartTime: audio.startTime,
          audioEndTime: audio.endTime,
          subtitleFile: getSubtitleFilename(),
          subtitleIndex: feedbackTarget.index,
          subtitleStart: feedbackTarget.start,
          subtitleEnd: feedbackTarget.end,
          subtitleText: feedbackTarget.text,
          subtitleSourceKind: feedbackTarget.sourceKind,
          subtitleSourcePath: feedbackTarget.sourcePath,
          subtitleSourceIndex: feedbackTarget.sourceIndex,
          subtitleAbsStart: feedbackTarget.absStart,
          subtitleAbsEnd: feedbackTarget.absEnd,
          message: feedbackMessage.trim(),
        }),
      });
      if (!res.ok) {
        const data = (await res.json().catch(() => null)) as { error?: string } | null;
        setFeedbackError(data?.error || "反馈提交失败，请稍后重试");
        return;
      }
      closeFeedbackModal();
      window.setTimeout(() => {
        loadSubtitles({ showLoading: false });
      }, 1000);
    } catch {
      setFeedbackError("网络异常，反馈未提交成功");
    } finally {
      setFeedbackSending(false);
    }
  };

  const handleRepairBadgeClick = async (
    e: React.MouseEvent<HTMLButtonElement>,
    segment: Segment
  ) => {
    e.preventDefault();
    e.stopPropagation();
    clearLongPressTimer();
    suppressSubtitleClickRef.current = true;
    const feedbackId = segment.repair?.feedbackId;
    if (!feedbackId) return;

    if (pendingRevertFeedbackId !== feedbackId) {
      setPendingRevertFeedbackId(feedbackId);
      setRevertError("");
      return;
    }

    setRevertingFeedbackId(feedbackId);
    setRevertError("");
    try {
      const res = await fetch(`/api/feedback/${encodeURIComponent(feedbackId)}/revert`, {
        method: "POST",
      });
      const data = (await res.json().catch(() => null)) as { error?: string } | null;
      if (!res.ok) {
        setRevertError(data?.error || "撤销修复失败，请稍后重试");
        return;
      }
      setPendingRevertFeedbackId(null);
      await loadSubtitles({ showLoading: false });
    } catch {
      setRevertError("网络异常，撤销修复失败");
    } finally {
      setRevertingFeedbackId(null);
    }
  };

  const formatSubtitleTime = (t: number) => {
    const totalSeconds = Math.max(0, Math.floor(t));
    const hours = Math.floor(totalSeconds / 3600);
    const mins = Math.floor((totalSeconds % 3600) / 60);
    const secs = totalSeconds % 60;
    if (hours > 0) {
      return `${hours}:${mins.toString().padStart(2, "0")}:${secs
        .toString()
        .padStart(2, "0")}`;
    }
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

  const formatProcessedAt = (value?: string | null) => {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    return date.toLocaleString("zh-CN", {
      hour12: false,
      timeZone: "Asia/Shanghai",
    });
  };

  return (
    <div className="bg-gray-800 rounded-lg p-4 space-y-4">
      <audio
        ref={audioRef}
        preload="auto"
        onTimeUpdate={handleTimeUpdate}
        onLoadedMetadata={handleLoadedMetadata}
        onEnded={handleEnded}
        onLoadStart={() => {
          setIsAudioPreparing(true);
          setIsAudioReady(false);
          setAudioPhase("connecting");
          setBufferedEnd(0);
          setBufferedAhead(0);
          setBufferRateSecondsPerSecond(null);
          initialSeekAppliedRef.current = false;
          autoplayStartedRef.current = false;
          waitingForBufferRef.current = false;
          pendingPlayAfterBufferRef.current = true;
          bufferPauseInFlightRef.current = false;
        }}
        onProgress={() => {
          syncBufferedState();
          if (pendingPlayAfterBufferRef.current && shouldAutoplayRef.current) {
            void startPlaybackWhenSafe();
          }
        }}
        onCanPlay={() => {
          const el = audioRef.current;
          syncBufferedState();
          if (el && !initialSeekAppliedRef.current) {
            el.currentTime = initialStartPositionRef.current;
            initialSeekAppliedRef.current = true;
            lastBufferSampleRef.current = null;
          }
          setIsAudioReady(true);
          if (shouldAutoplayRef.current && (!autoplayStartedRef.current || pendingPlayAfterBufferRef.current)) {
            pendingPlayAfterBufferRef.current = true;
            void startPlaybackWhenSafe();
          } else if (!waitingForBufferRef.current) {
            setIsAudioPreparing(false);
            setAudioPhase("ready");
          }
        }}
        onPlaying={() => {
          autoplayStartedRef.current = true;
          waitingForBufferRef.current = false;
          pendingPlayAfterBufferRef.current = false;
          bufferPauseInFlightRef.current = false;
          setIsPlaying(true);
          setIsAudioPreparing(false);
          setAudioError("");
          setAudioPhase("ready");
        }}
        onPause={() => {
          setIsPlaying(false);
          if (bufferPauseInFlightRef.current || waitingForBufferRef.current) {
            setIsAudioPreparing(true);
            setAudioPhase("buffering");
            bufferPauseInFlightRef.current = false;
            return;
          }
          if (audioPhase !== "error") {
            setIsAudioPreparing(false);
            setAudioPhase("ready");
          }
        }}
        onWaiting={() => {
          syncBufferedState();
          if (shouldAutoplayRef.current) {
            waitingForBufferRef.current = true;
            pendingPlayAfterBufferRef.current = true;
            setIsAudioPreparing(true);
            setAudioPhase("buffering");
          }
        }}
        onError={() => {
          setAudioError("音频播放失败，请重试");
          setIsPlaying(false);
          setIsAudioPreparing(false);
          setIsAudioReady(false);
          setAudioPhase("error");
        }}
      />

      <div className="text-white">
        <div className="font-medium">{audio.personTag}</div>
        <div className="text-sm text-gray-400">{audio.date} · {audio.startTime} - {audio.endTime}</div>
      </div>

      {(subtitlePhase === "loading" || isAudioPreparing || audioPhase === "connecting" || audioPhase === "buffering" || audioPhase === "error") && (
        <div className="rounded-lg bg-amber-500/10 px-3 py-2 text-sm text-amber-200 space-y-2">
          {subtitlePhase === "loading" && (
            <div>
              <div>字幕加载中…</div>
              <div className="mt-2 h-2 overflow-hidden rounded bg-black/20">
                <div className="h-full w-1/3 animate-pulse rounded bg-sky-300/70" />
              </div>
            </div>
          )}
          {(isAudioPreparing || audioPhase === "connecting" || audioPhase === "buffering") && (
            <div>
              <div>{audioStatusText}</div>
            </div>
          )}
          {audioPhase === "error" && (
            <div className="text-red-200">{audioStatusText}</div>
          )}
        </div>
      )}

      {audioError && (
        <div className="rounded-lg bg-red-950/60 px-3 py-2 text-sm text-red-200">
          {audioError}
        </div>
      )}

      {revertError && (
        <div className="rounded-lg bg-red-950/60 px-3 py-2 text-sm text-red-200">
          {revertError}
        </div>
      )}

      {/* Feedback Modal */}
      {feedbackTarget && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-800 rounded-lg p-4 w-full max-w-md space-y-4">
            <div className="flex justify-between items-center">
              <h3 className="text-white font-medium">反馈</h3>
              <button
                onClick={closeFeedbackModal}
                className="text-gray-400 hover:text-white"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="space-y-2 text-xs text-gray-400 bg-gray-900 rounded-lg p-3">
              <div>音频：{audio.filename}</div>
              <div>
                片段：{audio.personTag} / {audio.date} / {audio.startTime} - {audio.endTime}
              </div>
              <div>字幕文件：{getSubtitleFilename()}</div>
              <div>
                字幕位置：第 {feedbackTarget.index + 1} 句 / {formatSubtitleTime(feedbackTarget.start)} -{" "}
                {formatSubtitleTime(feedbackTarget.end)}
              </div>
              <div className="text-white">“{feedbackTarget.text}”</div>
            </div>
            <textarea
              ref={feedbackTextareaRef}
              value={feedbackMessage}
              onChange={(e) => setFeedbackMessage(e.target.value)}
              placeholder="请输入反馈内容..."
              className="w-full h-32 px-3 py-2 bg-gray-900 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
            />
            {feedbackError && (
              <div className="rounded-lg bg-red-950/60 px-3 py-2 text-sm text-red-200">
                {feedbackError}
              </div>
            )}
            <button
              onClick={handleSendFeedback}
              disabled={feedbackSending || !feedbackMessage.trim()}
              className="w-full py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 rounded-lg text-white transition"
            >
              {feedbackSending ? "发送中..." : "发送"}
            </button>
          </div>
        </div>
      )}

      <div
        ref={subtitleRef}
        className="relative h-48 overflow-y-auto bg-gray-900 rounded-lg p-3 space-y-2"
      >
        {showSubtitleHint && (
          <div className="absolute left-3 right-3 top-3 z-10 rounded-lg bg-black/70 px-3 py-2 text-xs text-gray-200 shadow-lg">
            点击字幕可跳转，长按字幕可反馈
          </div>
        )}
        {segments.length === 0 && (
          <div className="h-full flex items-center justify-center text-sm text-gray-500">
            无字幕
          </div>
        )}
        {segments.map((segment, index) => (
          <div
            key={index}
            data-index={index}
            onClick={() => handleSubtitleClick(segment.start)}
            onPointerDown={handleSubtitlePointerDown(segment, index)}
            onPointerUp={handleSubtitlePointerEnd}
            onPointerLeave={handleSubtitlePointerEnd}
            onPointerCancel={handleSubtitlePointerEnd}
            onContextMenu={(e) => e.preventDefault()}
            title={
              segment.repair?.isRepaired
                ? `已修复${segment.repair.processedAt ? ` · ${formatProcessedAt(segment.repair.processedAt)}` : ""}`
                : undefined
            }
            className={`cursor-pointer transition-all px-3 py-2 rounded ${
              segment.role === "host" ? "text-right" : "text-left"
            } ${
              segment.repair?.isRepaired
                ? index === currentSegmentIndex
                  ? "bg-green-600/30 text-white scale-105 ring-1 ring-green-400/60"
                  : "bg-green-900/20 text-green-200 hover:bg-green-900/35"
                : index === currentSegmentIndex
                  ? "bg-blue-600/30 text-white scale-105"
                  : "text-gray-400 hover:bg-gray-800"
            }`}
          >
            <div className={`flex items-center gap-2 ${segment.role === "host" ? "justify-end" : "justify-start"}`}>
              {segment.repair?.isRepaired && (
                <button
                  type="button"
                  onClick={(e) => void handleRepairBadgeClick(e, segment)}
                  onPointerDown={(e) => e.stopPropagation()}
                  className={`inline-flex rounded-full px-2 py-0.5 text-[10px] transition ${
                    pendingRevertFeedbackId === segment.repair.feedbackId
                      ? "bg-red-500/20 text-red-200 hover:bg-red-500/30"
                      : "bg-green-500/20 text-green-200 hover:bg-green-500/30"
                  }`}
                  title={
                    pendingRevertFeedbackId === segment.repair.feedbackId
                      ? "再次点击会撤销这次修复"
                      : "点击可撤销这次修复"
                  }
                >
                  {revertingFeedbackId === segment.repair.feedbackId
                    ? "撤销中..."
                    : pendingRevertFeedbackId === segment.repair.feedbackId
                      ? "撤销修复?"
                      : "已修复"}
                </button>
              )}
              <span className={`text-xs ${segment.role === "host" ? "text-blue-400" : "text-green-400"}`}>
                {segment.role === "host" ? "主持人" : "观众"}
              </span>
            </div>
            <p className={`text-sm ${index === currentSegmentIndex ? "text-white" : ""}`}>
              {segment.text}
            </p>
          </div>
        ))}
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={onPrevious}
          disabled={!hasPrevious || isAudioPreparing}
          className="w-10 h-10 rounded-full flex items-center justify-center text-white disabled:text-gray-600 hover:bg-gray-700 disabled:hover:bg-transparent transition"
        >
          <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
            <polygon points="19,20 9,12 19,4" />
            <rect x="5" y="4" width="3" height="16" />
          </svg>
        </button>

        <button
          onClick={togglePlay}
          disabled={!isAudioReady || Boolean(audioError)}
          className="w-12 h-12 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 rounded-full flex items-center justify-center text-white flex-shrink-0"
        >
          {isPlaying ? (
            <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
              <rect x="6" y="4" width="4" height="16" />
              <rect x="14" y="4" width="4" height="16" />
            </svg>
          ) : (
            <svg className="w-5 h-5 ml-1" fill="currentColor" viewBox="0 0 24 24">
              <polygon points="5,3 19,12 5,21" />
            </svg>
          )}
        </button>

        <button
          onClick={onNext}
          disabled={!hasNext || isAudioPreparing}
          className="w-10 h-10 rounded-full flex items-center justify-center text-white disabled:text-gray-600 hover:bg-gray-700 disabled:hover:bg-transparent transition"
        >
          <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
            <polygon points="5,4 15,12 5,20" />
            <rect x="16" y="4" width="3" height="16" />
          </svg>
        </button>

        <div className="flex-1 space-y-1 ml-2">
          <div className="relative h-3">
            <div className="absolute inset-x-0 top-1/2 h-2 -translate-y-1/2 overflow-hidden rounded-full bg-gray-600">
              <div
                className="absolute inset-y-0 left-0 rounded-full bg-cyan-400/30 shadow-[0_0_10px_rgba(34,211,238,0.45)] transition-all"
                style={{ width: `${bufferedPercent}%` }}
              />
              <div
                className="absolute inset-y-0 left-0 rounded-full bg-blue-500/90 transition-all"
                style={{ width: `${playedPercent}%` }}
              />
            </div>
            <input
              type="range"
              min={0}
              max={duration || 100}
              value={currentTime}
              onChange={handleProgressChange}
              onMouseDown={() => setIsDragging(true)}
              onMouseUp={() => setIsDragging(false)}
              disabled={!isAudioReady}
              className="absolute inset-0 z-10 w-full cursor-pointer appearance-none bg-transparent disabled:opacity-50"
            />
          </div>
          <div className="flex justify-between text-xs text-gray-400">
            <span>{formatTime(currentTime)}</span>
            <span>{formatTime(duration)}</span>
          </div>
        </div>
      </div>

      <div className="flex items-center justify-end">
        <div className="flex items-center gap-2">
          <Link
            href="/admin/feedback"
            className="px-3 py-2 rounded-lg text-sm text-gray-300 hover:bg-gray-700 transition"
          >
            反馈后台
          </Link>

          <button
            type="button"
            onClick={() => onPlayModeChange("sequence")}
            className={`p-2 rounded-lg transition ${
              playMode === "sequence"
                ? "bg-blue-600 text-white"
                : "text-gray-400 hover:bg-gray-700"
            }`}
            aria-pressed={playMode === "sequence"}
            aria-label="顺序播放"
            title="顺序播放"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h12M4 12h10M4 18h8" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 6l-2 2m0 0l-2-2m2 2V4" />
            </svg>
          </button>
          <button
            type="button"
            onClick={() => onPlayModeChange("shuffle")}
            className={`p-2 rounded-lg transition ${
              playMode === "shuffle"
                ? "bg-blue-600 text-white"
                : "text-gray-400 hover:bg-gray-700"
            }`}
            aria-pressed={playMode === "shuffle"}
            aria-label="乱序播放"
            title="乱序播放"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h4l4 4 4-4h4M4 18h4l4-4 4 4h4" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 6l-2 2m0 0l-2-2m2 2V4" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 18l-2-2m0 0l-2 2m2-2v4" />
            </svg>
          </button>

          <div className="relative">
            <button
              onClick={() => setShowVolume(!showVolume)}
              className="p-2 rounded-lg hover:bg-gray-700 transition"
            >
              <svg className="w-5 h-5 text-gray-400" fill="currentColor" viewBox="0 0 24 24">
                {volume === 0 ? (
                  <path d="M16.5 12c0-1.77-1.02-3.29-2.5-4.03v2.21l2.45 2.45c.03-.2.05-.41.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51C20.63 14.91 21 13.5 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06c1.38-.31 2.63-.95 3.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4L9.91 6.09 12 8.18V4z" />
                ) : volume < 0.5 ? (
                  <path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02z" />
                ) : (
                  <path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z" />
                )}
              </svg>
            </button>
            {showVolume && (
              <div className="fixed inset-0 z-40" onClick={() => setShowVolume(false)} />
            )}
            {showVolume && (
              <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 p-3 bg-gray-700 rounded-lg z-50 shadow-lg">
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.1}
                  value={volume}
                  onChange={handleVolumeChange}
                  className="h-24 w-2 bg-gray-600 rounded-lg appearance-none cursor-pointer"
                  style={{ writingMode: "vertical-lr", direction: "rtl" }}
                />
              </div>
            )}
          </div>

          <select
            value={speed}
            onChange={(e) => handleSpeedChange(parseFloat(e.target.value))}
            className="px-2 py-1 rounded text-sm bg-gray-700 text-gray-300 hover:bg-gray-600 cursor-pointer focus:outline-none"
          >
            {SPEEDS.map((s) => (
              <option key={s} value={s}>
                {s}x
              </option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );
}
