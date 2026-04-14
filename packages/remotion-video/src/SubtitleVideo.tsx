import { useState, useEffect, useCallback } from "react";
import {
  AbsoluteFill,
  Sequence,
  staticFile,
  useDelayRender,
  useCurrentFrame,
  useVideoConfig,
  Audio,
} from "remotion";
import type { Caption } from "@remotion/captions";
import { loadFont } from "@remotion/google-fonts/NotoSansSC";

const { fontFamily } = loadFont();

const SingleCaption: React.FC<{ caption: Caption }> = ({ caption }) => {
  return (
    <AbsoluteFill
      style={{
        justifyContent: "center",
        alignItems: "center",
        padding: "40px 50px",
      }}
    >
      <div
        style={{
          fontSize: 72,
          fontWeight: 700,
          color: "#FFFFFF",
          textAlign: "center",
          lineHeight: 1.5,
          fontFamily,
        }}
      >
        {caption.text}
      </div>
    </AbsoluteFill>
  );
};

export const SubtitleVideo: React.FC = () => {
  const [captions, setCaptions] = useState<Caption[] | null>(null);
  const { delayRender, continueRender, cancelRender } = useDelayRender();
  const [handle] = useState(() => delayRender());
  const { fps } = useVideoConfig();

  const fetchCaptions = useCallback(async () => {
    try {
      const response = await fetch(staticFile("captions.json"));
      const data: Caption[] = await response.json();
      const firstStart = data[0].startMs;
      const normalized = data.map((c) => ({
        ...c,
        startMs: c.startMs - firstStart,
        endMs: c.endMs - firstStart,
        timestampMs: c.timestampMs !== null ? c.timestampMs - firstStart : null,
      }));
      setCaptions(normalized);
      continueRender(handle);
    } catch (e) {
      cancelRender(e);
    }
  }, [continueRender, cancelRender, handle]);

  useEffect(() => {
    fetchCaptions();
  }, [fetchCaptions]);

  if (!captions) return null;

  return (
    <AbsoluteFill style={{ backgroundColor: "#000000" }}>
      <Audio src={staticFile("audio.mp3")} />
      {captions.map((caption, index) => {
        const startFrame = Math.round((caption.startMs / 1000) * fps);
        const durationMs = caption.endMs - caption.startMs;
        const durationInFrames = Math.max(Math.round((durationMs / 1000) * fps), 2);

        return (
          <Sequence key={index} from={startFrame} durationInFrames={durationInFrames}>
            <SingleCaption caption={caption} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
